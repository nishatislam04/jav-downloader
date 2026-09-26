#!/usr/bin/env python
# coding: utf-8
"""Decide whether post-download processing can remux/copy or must re-encode."""

from __future__ import annotations

from dataclasses import dataclass

from jav_downloader.sites.media_post import (
    needs_audio_processing,
    normalize_encode_codec,
    normalize_encode_engine,
    normalize_encode_max_height,
    site_wants_encode,
)
from jav_downloader.sites.media_probe import MediaInfo

MODE_SKIP = 'skip'
MODE_DIRECT_REMUX = 'direct_remux'
MODE_SOFTWARE_ENCODE = 'software_encode'


@dataclass(frozen=True)
class EncodingDecision:
    mode: str
    video_copy: bool
    scale_needed: bool
    reasons: tuple[str, ...]

    @property
    def needs_video_encode(self) -> bool:
        return self.mode == MODE_SOFTWARE_ENCODE and not self.video_copy


def _target_codec_label(codec: str) -> str:
    return 'hevc' if codec == 'hevc' else 'h264'


def _source_meets_codec(source_norm: str | None, target: str) -> bool:
    if not source_norm:
        return False
    return source_norm == _target_codec_label(target)


def _source_meets_height(video, max_height: int) -> bool:
    if max_height <= 0:
        return True
    if video is None:
        return False
    return int(video.height) <= max_height


def decide_encoding(site, media_info: MediaInfo | None) -> EncodingDecision:
    """Return how post_process_media should handle the downloaded file."""
    wants_encode = site_wants_encode(site)
    wants_audio = needs_audio_processing(site)

    if not wants_encode and not wants_audio:
        return EncodingDecision(
            mode=MODE_SKIP,
            video_copy=True,
            scale_needed=False,
            reasons=('no post-processing requested',),
        )

    if not wants_encode:
        return EncodingDecision(
            mode=MODE_DIRECT_REMUX,
            video_copy=True,
            scale_needed=False,
            reasons=('audio processing only',),
        )

    if normalize_encode_engine(getattr(site, '_encode_engine', None)) == 'direct':
        if wants_audio:
            return EncodingDecision(
                mode=MODE_DIRECT_REMUX,
                video_copy=True,
                scale_needed=False,
                reasons=('encoding engine set to direct/remux',),
            )
        return EncodingDecision(
            mode=MODE_SKIP,
            video_copy=True,
            scale_needed=False,
            reasons=('encoding engine set to direct/remux; video stream copy only',),
        )

    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))

    if media_info is None or media_info.video is None:
        return EncodingDecision(
            mode=MODE_SOFTWARE_ENCODE,
            video_copy=False,
            scale_needed=max_height > 0,
            reasons=('source inspection unavailable; re-encode for safety',),
        )

    video = media_info.video
    source_codec = video.normalized_codec()
    codec_ok = _source_meets_codec(source_codec, target_codec)
    height_ok = _source_meets_height(video, max_height)
    scale_needed = max_height > 0 and video.height > max_height

    reasons: list[str] = []
    if not codec_ok:
        src_label = source_codec or video.codec_name or 'unknown'
        tgt_label = _target_codec_label(target_codec)
        reasons.append(f'codec mismatch ({src_label} → {tgt_label})')
    if scale_needed:
        reasons.append(f'resolution above max height ({video.height}p > {max_height}p)')

    if codec_ok and height_ok:
        if wants_audio:
            return EncodingDecision(
                mode=MODE_DIRECT_REMUX,
                video_copy=True,
                scale_needed=False,
                reasons=('source compatible; video copy with audio processing',),
            )
        return EncodingDecision(
            mode=MODE_SKIP,
            video_copy=True,
            scale_needed=False,
            reasons=(
                'source already matches requested codec and resolution; skipping re-encode',
            ),
        )

    return EncodingDecision(
        mode=MODE_SOFTWARE_ENCODE,
        video_copy=False,
        scale_needed=scale_needed,
        reasons=tuple(reasons) if reasons else ('re-encode required',),
    )


def _planned_encoder_label(
        decision: EncodingDecision,
        site,
        target_codec: str,
        codec_label: str) -> str:
    from jav_downloader.sites.encoding_capabilities import resolve_hardware_encoder
    from jav_downloader.sites.encoding_strategies import (
        STRATEGY_HARDWARE,
        strategy_for_decision,
    )

    strategy = strategy_for_decision(decision, site)
    if strategy == STRATEGY_HARDWARE:
        _, spec, _ = resolve_hardware_encoder(target_codec, validate=False)
        name = spec.encoder_name if spec else 'mediacodec'
        return f'{name} (hardware MediaCodec)'
    lib = 'libx265' if target_codec == 'hevc' else 'libx264'
    return f'{lib} ({codec_label} software)'


def format_encoding_decision_log(
        decision: EncodingDecision,
        media_info: MediaInfo | None,
        site) -> str:
    """Human-readable single-line encoding decision for job logs."""
    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    height_label = f'{max_height}p' if max_height > 0 else 'original'

    if media_info and media_info.video:
        video = media_info.video
        src_codec = video.normalized_codec() or video.codec_name
        source_part = f'source={src_codec.upper()} {video.width}x{video.height}'
    else:
        source_part = 'source=unknown'

    mode = decision.mode
    if mode == MODE_SKIP:
        action = 'direct-remux (no-op)'
        encoder = 'none'
    elif mode == MODE_DIRECT_REMUX:
        action = 'direct-remux'
        encoder = 'copy'
    else:
        action = 're-encode'
        codec_label = 'H.265' if target_codec == 'hevc' else 'H.264'
        encoder = _planned_encoder_label(decision, site, target_codec, codec_label)

    reason = '; '.join(decision.reasons) if decision.reasons else ''
    return (
        f'Encoding decision: {source_part} target=max_height={height_label} '
        f'mode={action} encoder={encoder}'
        + (f' reason={reason}' if reason else '')
    )
