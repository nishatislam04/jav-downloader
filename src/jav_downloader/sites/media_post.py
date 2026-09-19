#!/usr/bin/env python
# coding: utf-8
"""Post-download ffmpeg encode (size reduction) and audio processing."""

from __future__ import annotations

import os
import platform
import re
import select
import subprocess
import tempfile

from jav_downloader.sites.base import locate_ffmpeg, _no_window_kwargs

FADE_SEC = 0.5

_VALID_CODECS = frozenset({'h264', 'hevc'})
_VALID_PRESETS = frozenset({
    'auto', 'ultrafast', 'superfast', 'veryfast', 'faster',
    'fast', 'medium', 'slow',
})
_VALID_OUTPUT_MODES = frozenset({'replace', 'keep_both', 'suffix'})
_VALID_MAX_HEIGHTS = frozenset({0, 480, 720, 1080})


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _is_termux_like() -> bool:
    if os.environ.get('TERMUX_VERSION'):
        return True
    return platform.system().lower() == 'linux' and os.path.isdir('/data/data/com.termux')


def normalize_encode_codec(value) -> str:
    codec = str(value or 'h264').strip().lower()
    return codec if codec in _VALID_CODECS else 'h264'


def normalize_encode_crf(value) -> int:
    try:
        crf = int(value)
    except (TypeError, ValueError):
        crf = 23
    return max(18, min(28, crf))


def normalize_encode_max_height(value) -> int:
    try:
        height = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return height if height in _VALID_MAX_HEIGHTS else 0


def normalize_encode_output_mode(value) -> str:
    mode = str(value or 'replace').strip().lower()
    return mode if mode in _VALID_OUTPUT_MODES else 'replace'


def normalize_encode_preset(value) -> str:
    preset = str(value or 'auto').strip().lower()
    return preset if preset in _VALID_PRESETS else 'auto'


def normalize_encode_threads(value) -> int:
    try:
        threads = int(value if value is not None else 0)
    except (TypeError, ValueError):
        return 0
    if threads < 0:
        return 0
    cpu = os.cpu_count() or 1
    return min(threads, cpu) if threads > 0 else 0


def apply_encode_options(
        site,
        encode=None,
        encode_codec=None,
        encode_crf=None,
        encode_max_height=None,
        encode_output_mode=None,
        encode_preset=None,
        encode_threads=None) -> None:
    site._encode_enabled = bool(encode)
    site._encode_codec = normalize_encode_codec(encode_codec)
    site._encode_crf = normalize_encode_crf(encode_crf)
    site._encode_max_height = normalize_encode_max_height(encode_max_height)
    site._encode_output_mode = normalize_encode_output_mode(encode_output_mode)
    site._encode_preset = normalize_encode_preset(encode_preset)
    site._encode_threads = normalize_encode_threads(encode_threads)
    site._encoded_output_path = None


def site_wants_encode(site) -> bool:
    return bool(getattr(site, '_encode_enabled', False))


def site_wants_fade(site) -> bool:
    return bool(getattr(site, '_audio_fade', False))


def site_wants_loudnorm(site) -> bool:
    return bool(getattr(site, '_audio_loudnorm', False))


def needs_audio_processing(site) -> bool:
    return site_wants_fade(site) or site_wants_loudnorm(site)


def needs_media_post(site) -> bool:
    return site_wants_encode(site) or needs_audio_processing(site)


def encode_tag(site) -> str:
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = normalize_encode_crf(getattr(site, '_encode_crf', None))
    height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    label = 'h265' if codec == 'hevc' else 'h264'
    if height > 0:
        return f'{label}-crf{crf}-{height}p'
    return f'{label}-crf{crf}'


def resolved_encode_preset(site) -> str:
    preset = normalize_encode_preset(getattr(site, '_encode_preset', None))
    if preset != 'auto':
        return preset
    return 'veryfast' if _is_termux_like() else 'medium'


def resolved_encode_threads(site) -> int:
    threads = normalize_encode_threads(getattr(site, '_encode_threads', None))
    if threads > 0:
        return threads
    return os.cpu_count() or 1


def build_af_filter(site, duration_sec: float | None) -> str | None:
    parts = []
    duration = float(duration_sec or 0)
    if site_wants_fade(site) and duration > 0:
        fade = min(FADE_SEC, duration / 2)
        parts.append(f'afade=t=in:st=0:d={fade:g}')
        if duration > fade * 2:
            parts.append(f'afade=t=out:st={duration - fade:g}:d={fade:g}')
    if site_wants_loudnorm(site):
        parts.append('loudnorm')
    return ','.join(parts) if parts else None


def append_ffmpeg_output_args(cmd, site, duration_sec: float | None = None) -> None:
    af = build_af_filter(site, duration_sec)
    if af:
        cmd.extend(['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', af])
    else:
        cmd.extend(['-c', 'copy'])
    cmd.extend(['-movflags', '+faststart'])


def _encode_destination_path(src_path: str, site) -> tuple[str, str]:
    """Return (output_path, mode)."""
    mode = normalize_encode_output_mode(getattr(site, '_encode_output_mode', None))
    tag = encode_tag(site)
    base, ext = os.path.splitext(src_path)
    if mode == 'keep_both':
        return f'{base} [{tag}]{ext or ".mp4"}', mode
    if mode == 'suffix':
        return f'{base} [{tag}]{ext or ".mp4"}', mode
    return src_path, mode


def _read_ffmpeg_progress(proc, out_time_sec: float) -> float:
    if proc.stdout is None:
        return out_time_sec
    while True:
        ready, _, _ = select.select([proc.stdout], [], [], 0)
        if not ready:
            break
        line = proc.stdout.readline()
        if not line:
            break
        text = line.decode('utf-8', errors='ignore').strip()
        if text.startswith('out_time_ms='):
            try:
                out_time_sec = int(text.split('=', 1)[1]) / 1_000_000.0
            except (TypeError, ValueError):
                pass
        elif text.startswith('out_time='):
            raw = text.split('=', 1)[1].strip()
            match = re.match(r'(\d+):(\d+):(\d+(?:\.\d+)?)', raw)
            if match:
                hours, minutes, seconds = match.groups()
                out_time_sec = (
                    int(hours) * 3600 + int(minutes) * 60 + float(seconds))
    return out_time_sec


def _emit_encode_progress(site, out_path, out_time_sec, duration_sec, input_size):
    cb = getattr(site, '_progress_callback', None)
    if not cb:
        return
    downloaded = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    total = input_size if input_size > 0 else downloaded
    if duration_sec and duration_sec > 0 and out_time_sec > 0 and input_size > 0:
        total = max(total, int(input_size * min(1.0, out_time_sec / duration_sec)))
        downloaded = max(downloaded, int(total * min(1.0, out_time_sec / duration_sec)))
    cb(max(downloaded, 0), max(total, 1), 0.0, 'bytes')


def _build_encode_cmd(ffmpeg, site, src_path, dst_path, duration_sec):
    threads = resolved_encode_threads(site)
    preset = resolved_encode_preset(site)
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = normalize_encode_crf(getattr(site, '_encode_crf', None))
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    af = build_af_filter(site, duration_sec)

    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-threads', str(threads),
        '-i', src_path,
    ]
    if max_height > 0:
        cmd.extend(['-vf', f'scale=-2:{max_height}'])
    if codec == 'hevc':
        cmd.extend(['-c:v', 'libx265', '-crf', str(crf), '-preset', preset])
    else:
        cmd.extend(['-c:v', 'libx264', '-crf', str(crf), '-preset', preset])
    if af:
        cmd.extend(['-c:a', 'aac', '-b:a', '128k', '-af', af])
    else:
        cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
    cmd.extend(['-movflags', '+faststart', dst_path])
    return cmd


def _run_ffmpeg(cmd, site, out_path, duration_sec, input_size):
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    site._ffmpeg_proc = proc
    out_time_sec = 0.0
    stderr_tail = ''
    try:
        while True:
            if getattr(site, '_cancel_job', False) or getattr(site, '_pause_job', False):
                proc.kill()
                proc.wait(timeout=5)
                return False, stderr_tail
            out_time_sec = _read_ffmpeg_progress(proc, out_time_sec)
            if proc.stderr is not None:
                ready, _, _ = select.select([proc.stderr], [], [], 0)
                if ready:
                    chunk = proc.stderr.read(800)
                    if chunk:
                        stderr_tail = (stderr_tail + chunk.decode('utf-8', errors='ignore'))[-800:]
            _emit_encode_progress(site, out_path, out_time_sec, duration_sec, input_size)
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        site._ffmpeg_proc = None
        if proc.stderr is not None:
            chunk = proc.stderr.read()
            if chunk:
                stderr_tail = (stderr_tail + chunk.decode('utf-8', errors='ignore'))[-800:]

    if proc.returncode != 0:
        return False, stderr_tail
    return True, stderr_tail


def post_process_media(site, src_path: str, duration_sec: float | None = None) -> str | None:
    """Run optional encode and/or audio processing. Returns final output path."""
    if not src_path or not os.path.isfile(src_path):
        return src_path
    if not needs_media_post(site):
        return src_path

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('Media processing requires ffmpeg')

    emit = getattr(site, '_emit_job_log', None)
    input_size = os.path.getsize(src_path)

    if site_wants_encode(site):
        dst_path, mode = _encode_destination_path(src_path, site)
        dest_dir = os.path.dirname(dst_path) or os.getcwd()
        os.makedirs(dest_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            suffix='.mp4', prefix='jav-encode-', dir=dest_dir)
        os.close(fd)

        codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
        preset = resolved_encode_preset(site)
        height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
        threads = resolved_encode_threads(site)
        if emit:
            height_label = f'{height}p' if height > 0 else 'original'
            codec_label = 'H.265' if codec == 'hevc' else 'H.264'
            emit(
                f'Encoding… {codec_label} CRF {site._encode_crf} · '
                f'{height_label} · {preset} · {threads} thread(s)')

        cmd = _build_encode_cmd(ffmpeg, site, src_path, temp_path, duration_sec)
        ok, stderr_tail = _run_ffmpeg(
            cmd, site, temp_path, float(duration_sec or 0), input_size)
        if not ok or not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
            _safe_remove(temp_path)
            detail = stderr_tail.strip() or 'ffmpeg encode failed'
            raise Exception(f'Encode failed: {detail}')

        if mode == 'replace':
            os.replace(temp_path, src_path)
            final_path = src_path
        elif mode == 'keep_both':
            os.replace(temp_path, dst_path)
            final_path = dst_path
        else:  # suffix
            _safe_remove(src_path)
            os.replace(temp_path, dst_path)
            final_path = dst_path

        site._encoded_output_path = final_path
        cb = getattr(site, '_progress_callback', None)
        if cb:
            size = os.path.getsize(final_path)
            cb(size, size, 0.0, 'bytes')
        return final_path

    # Audio-only (video copy)
    post_process_audio(site, src_path, duration_sec)
    return src_path


def post_process_audio(site, src_path: str, duration_sec: float | None = None) -> None:
    """Rewrite src_path in place when fade/loudnorm is enabled (video copy)."""
    if not needs_audio_processing(site):
        return
    if not src_path or not os.path.isfile(src_path):
        return

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('Audio processing requires ffmpeg')

    af = build_af_filter(site, duration_sec)
    if not af:
        return

    dest_dir = os.path.dirname(src_path) or os.getcwd()
    fd, temp_path = tempfile.mkstemp(suffix='.mp4', prefix='jav-audio-', dir=dest_dir)
    os.close(fd)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', src_path,
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', af,
        '-movflags', '+faststart', temp_path,
    ]
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        **_no_window_kwargs(),
    )
    if proc.returncode != 0 or not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
        _safe_remove(temp_path)
        detail = (proc.stderr or proc.stdout or '').strip() or f'ffmpeg exit {proc.returncode}'
        raise Exception(f'Audio processing failed: {detail}')
    os.replace(temp_path, src_path)
