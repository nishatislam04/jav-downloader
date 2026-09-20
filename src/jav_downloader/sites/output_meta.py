#!/usr/bin/env python
# coding: utf-8
"""Resolve-time HLS tier metadata and output size estimation."""

from __future__ import annotations

from urllib.parse import urljoin

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


def _media_playlist_duration_sec(m3u8obj) -> float:
    segments = list(getattr(m3u8obj, 'segments', None) or [])
    if not segments:
        return 0.0
    total = 0.0
    for segment in segments:
        try:
            total += float(getattr(segment, 'duration', 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _min_plausible_bandwidth_bps(height: int | None) -> int:
    if height and height >= 1080:
        return 1_500_000
    if height and height >= 720:
        return 800_000
    if height and height >= 480:
        return 400_000
    if height and height >= 360:
        return 300_000
    return 200_000


def _bandwidth_trustworthy(bandwidth: int, height: int | None) -> bool:
    try:
        bandwidth = int(bandwidth or 0)
    except (TypeError, ValueError):
        return False
    return bandwidth >= _min_plausible_bandwidth_bps(height)


def _size_estimate_plausible(size_bytes: int, duration_sec: float | None, height: int | None) -> bool:
    try:
        size_bytes = int(size_bytes or 0)
        duration_sec = float(duration_sec or 0)
    except (TypeError, ValueError):
        return False
    if size_bytes <= 0 or duration_sec <= 0:
        return False
    implied_bps = size_bytes * 8 / duration_sec
    return implied_bps >= _min_plausible_bandwidth_bps(height) * 0.5


def _segment_base_from_playlist_url(playlist_url: str) -> str:
    return playlist_url.rsplit('/', 1)[0] + '/'


def _resolve_hls_media_playlist(site, m3u8obj=None):
    """Return (media m3u8 object, segment base URL) for the current selection."""
    load_m3u8 = getattr(site, '_load_m3u8', None)
    m3u8url = getattr(site, '_m3u8url', None)
    if m3u8obj is None:
        if not m3u8url or not callable(load_m3u8):
            return None, None
        try:
            m3u8obj = load_m3u8(m3u8url)
        except Exception:
            return None, None

    playlists = list(getattr(m3u8obj, 'playlists', None) or [])
    if playlists:
        selected = pick_hls_playlist(playlists, site)
        if selected is None:
            return None, None
        get_playlist = getattr(site, '_getm3u8PlayList', None)
        if callable(get_playlist):
            try:
                media_obj, segment_base = get_playlist(selected.uri)
                return media_obj, segment_base
            except Exception:
                return None, None
        playlist_url = urljoin(str(m3u8url), str(getattr(selected, 'uri', '') or ''))
        try:
            media_obj = load_m3u8(playlist_url)
        except Exception:
            return None, None
        return media_obj, _segment_base_from_playlist_url(playlist_url)

    playlist_url = getattr(site, '_media_playlist_url', None) or m3u8url
    return m3u8obj, _segment_base_from_playlist_url(str(playlist_url or ''))


def _segment_absolute_url(segment, segment_base: str, playlist_url: str) -> str | None:
    uri = getattr(segment, 'absolute_uri', None) or getattr(segment, 'uri', None)
    if not uri:
        return None
    uri = str(uri)
    if uri.startswith(('http://', 'https://')):
        return uri
    base = segment_base or _segment_base_from_playlist_url(playlist_url)
    return urljoin(base, uri.lstrip('/'))


def _segment_probe_context(site) -> tuple[str, dict]:
    extra = dict(getattr(site, '_extra_headers', None) or {})
    referer = (
        getattr(site, '_segment_referer', None)
        or extra.get('Referer')
        or getattr(site, '_url', '')
        or getattr(site, '_direct_referer', '')
        or ''
    )
    return str(referer), extra


def _estimate_hls_size_from_segments(site) -> int | None:
    media_obj = getattr(site, '_hls_media_m3u8obj', None)
    segment_base = getattr(site, '_hls_segment_base', None)
    if media_obj is None:
        media_obj, segment_base = _resolve_hls_media_playlist(site)
    if media_obj is None:
        return None

    segments = list(getattr(media_obj, 'segments', None) or [])
    if not segments:
        return None

    media_duration = _media_playlist_duration_sec(media_obj)
    if media_duration <= 0:
        return None

    playlist_url = (
        getattr(site, '_media_playlist_url', None)
        or getattr(site, '_m3u8url', '')
        or ''
    )
    referer, extra = _segment_probe_context(site)
    from jav_downloader.sites.direct_mp4 import probe_source_length

    sample_indices = sorted({
        0,
        len(segments) // 2,
        len(segments) - 1,
    })
    sampled_sizes = []
    for index in sample_indices:
        url = _segment_absolute_url(segments[index], segment_base, playlist_url)
        if not url:
            continue
        segment_size = probe_source_length(url, referer, extra_headers=extra)
        if segment_size > 0:
            sampled_sizes.append(segment_size)

    if not sampled_sizes:
        return None

    avg_segment_size = sum(sampled_sizes) / len(sampled_sizes)
    full_size = max(1, int(avg_segment_size * len(segments)))

    clip_duration = effective_output_duration_sec(site)
    full_duration = getattr(site, '_duration_sec', None)
    try:
        full_duration = float(full_duration)
    except (TypeError, ValueError):
        full_duration = 0.0
    if full_duration <= 0:
        full_duration = media_duration

    return _scale_size(full_size, full_duration, clip_duration)


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

    media_obj, segment_base = _resolve_hls_media_playlist(site, m3u8obj)
    if media_obj is not None:
        site._hls_media_m3u8obj = media_obj
        site._hls_segment_base = segment_base
        media_duration = _media_playlist_duration_sec(media_obj)
        if media_duration > 0:
            site._hls_media_duration_sec = media_duration
            if not getattr(site, '_duration_sec', None):
                site._duration_sec = media_duration

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

    pref = get_resolution_pref()
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
    pref = get_resolution_pref()
    return select_variant(playlists, pref)


def estimate_output_size(site) -> tuple[int | None, bool]:
    """Return (byte size, exact?) for the current site selection and cut ranges."""
    if getattr(site, 'skip_output_size_estimate', False):
        return None, False

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
        height = getattr(site, '_selected_variant_height', None)
        try:
            height = int(height) if height is not None else None
        except (TypeError, ValueError):
            height = None

        media_duration = getattr(site, '_hls_media_duration_sec', None)
        try:
            media_duration = float(media_duration)
        except (TypeError, ValueError):
            media_duration = 0.0

        duration = clip_duration or full_duration or (
            media_duration if media_duration > 0 else None
        )

        segment_size = _estimate_hls_size_from_segments(site)
        if segment_size and _size_estimate_plausible(segment_size, duration, height):
            return segment_size, False

        bandwidth = int(getattr(site, '_selected_variant_bandwidth', 0) or 0)
        if (
            bandwidth > 0
            and duration
            and duration > 0
            and _bandwidth_trustworthy(bandwidth, height)
        ):
            size = max(1, int(bandwidth * duration / 8))
            if _size_estimate_plausible(size, duration, height):
                return size, False

    return None, False


def apply_download_options(site) -> None:
    """Apply default download resolution behaviour (no per-request UI overrides)."""
    site._resolution_pref = None
    site._hls_tier_id = None
