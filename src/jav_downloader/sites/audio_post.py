#!/usr/bin/env python
# coding: utf-8
"""Backward-compatible re-exports; see media_post.py."""

from jav_downloader.sites.media_post import (  # noqa: F401
    FADE_SEC,
    append_ffmpeg_output_args,
    build_af_filter,
    needs_audio_processing,
    post_process_audio,
    site_wants_fade,
    site_wants_loudnorm,
)
