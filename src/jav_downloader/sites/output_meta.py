#!/usr/bin/env python
# coding: utf-8
"""Resolve-time HLS tier metadata and output size estimation."""

from __future__ import annotations

from jav_downloader.sites.base import (
    _variant_height_bw,
    get_resolution_pref,
    select_variant,
)


def _normalize_resolution_pref(value) -> str | None:
    from jav_downloader.sites.base import _VALID_RESOLUTION_PREFS

    pref = str(value or '').strip().lower()
    if pref in _VALID_RESOLUTION_PREFS:
        return pref
    return None


def _tier_label(height, bandwidth, index: int) -> str:
    if height:
        return f'{height}p'
    if bandwidth:
        return f'{bandwidth // 1000} kbps'
    return f'Variant {index + 1}'


def _tier_id(height, bandwidth, index: int) -> str:
    if height:
        return str(height)
    if bandwidth:
        return f'bw-{bandwidth}'
    return str(index)


def _tier_pref(height, bandwidth, index: int, total: int) -> str:
    if height:
        return str(height)
    if total <= 1:
        return 'highest'
    if index == 0:
        return 'lowest'
    if index == total - 1:
        return 'highest'
    return 'highest'


def effective_output_duration_sec(site) -> float | None:
    cut_ranges = getattr(site, '_cut_ranges', None) or []
    if cut_ranges:
        total = 0.0
        for start, end in cut_ranges:
            start = float(start or 0)
            if end is not None:
                total += max(0.0, float(end) - start)
            else:
                duration = getattr(site, '_duration_sec', None)
                try:
                    duration = float(duration)
                except (TypeError, ValueError):
                    duration = 0.0
                if duration > 0:
                    total += max(0.0, duration - start)
        return total if total > 0 else None
    duration = getattr(site, '_duration_sec', None)
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _scale_size(full_size: int, full_duration: float | None, clip_duration: float | None) -> int:
    if full_size <= 0:
        return 0
    if not full_duration or full_duration <= 0 or not clip_duration or clip_duration <= 0:
        return full_size
    if clip_duration >= full_duration:
        return full_size
    return max(1, int(full_size * clip_duration / full_duration))


def populate_hls_tiers(site) -> None:
    """Fill site._hls_tiers and site._active_hls_tier when a master playlist exists."""
    site._hls_tiers = []
    site._active_hls_tier = ''
    site._selected_variant_bandwidth = 0
    site._selected_variant_height = None

    m3u8url = getattr(site, '_m3u8url', None)
    load_m3u8 = getattr(site, '_load_m3u8', None)
    if not m3u8url or not callable(load_m3u8):
        return

    try:
        m3u8obj = load_m3u8(m3u8url)
    except Exception:
        return

    playlists = list(getattr(m3u8obj, 'playlists', None) or [])
    if len(playlists) <= 1:
        if playlists:
            height, bandwidth = _variant_height_bw(playlists[0])
            site._selected_variant_height = height
            site._selected_variant_bandwidth = bandwidth
        return

    tiers = []
    for index, playlist in enumerate(playlists):
        height, bandwidth = _variant_height_bw(playlist)
        tiers.append({
            'id': _tier_id(height, bandwidth, index),
            'label': _tier_label(height, bandwidth, index),
            'height': height,
            'bandwidth': bandwidth,
            'pref': _tier_pref(height, bandwidth, index, len(playlists)),
            'index': index,
        })

    tier_id = getattr(site, '_hls_tier_id', None)
    tier_map = {tier['id']: tier for tier in tiers}
    selected = None
    if tier_id and tier_id in tier_map:
        selected = playlists[tier_map[tier_id]['index']]
        active_id = tier_id
    else:
        pref = getattr(site, '_resolution_pref', None) or get_resolution_pref()
        selected = select_variant(playlists, pref)
        active_id = ''
        if selected is not None:
            for tier in tiers:
                if playlists[tier['index']] is selected:
                    active_id = tier['id']
                    break
        if not active_id and tiers:
            active_id = tiers[-1]['id']

    site._hls_tiers = tiers
    site._active_hls_tier = active_id
    if selected is not None:
        height, bandwidth = _variant_height_bw(selected)
        site._selected_variant_height = height
        site._selected_variant_bandwidth = bandwidth
        for tier in tiers:
            if tier['id'] == active_id:
                site._quality_label = tier['label']
                break


def pick_hls_playlist(playlists, site):
    """Return the playlist entry chosen for this site instance."""
    if not playlists:
        return None

    tiers = getattr(site, '_hls_tiers', None) or []
    tier_id = getattr(site, '_hls_tier_id', None)
    if tier_id and tiers:
        for tier in tiers:
            if tier.get('id') == tier_id:
                index = tier.get('index')
                if isinstance(index, int) and 0 <= index < len(playlists):
                    return playlists[index]

    pref = getattr(site, '_resolution_pref', None) or get_resolution_pref()
    return select_variant(playlists, pref)


def estimate_output_size(site) -> tuple[int | None, bool]:
    """Return (byte size, exact?) for the current site selection and cut ranges."""
    clip_duration = effective_output_duration_sec(site)
    full_duration = getattr(site, '_duration_sec', None)
    try:
        full_duration = float(full_duration)
    except (TypeError, ValueError):
        full_duration = 0.0

    direct_url = getattr(site, '_direct_url', None)
    if direct_url:
        from jav_downloader.sites.direct_mp4 import probe_source_length

        referer = getattr(site, '_direct_referer', None) or getattr(site, '_url', '')
        extra = getattr(site, '_extra_headers', None) or {}
        full_size = probe_source_length(direct_url, referer, extra_headers=extra)
        if full_size > 0:
            size = _scale_size(full_size, full_duration, clip_duration)
            return size, True
        return None, False

    if getattr(site, '_m3u8url', None):
        bandwidth = int(getattr(site, '_selected_variant_bandwidth', 0) or 0)
        duration = clip_duration or full_duration
        if bandwidth > 0 and duration and duration > 0:
            return max(1, int(bandwidth * duration / 8)), False

    return None, False


def apply_download_options(site, resolution_pref=None, hls_tier=None) -> None:
    site._resolution_pref = _normalize_resolution_pref(resolution_pref)
    tier = str(hls_tier).strip() if hls_tier else None
    site._hls_tier_id = tier or None
