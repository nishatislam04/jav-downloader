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
import time

from jav_downloader.sites.base import locate_ffmpeg, _no_window_kwargs

FADE_SEC = 0.5

_VALID_CODECS = frozenset({'h264', 'hevc'})
_VALID_PRESETS = frozenset({
    'auto', 'ultrafast', 'superfast', 'veryfast', 'faster',
    'fast', 'medium', 'slow',
})
_VALID_OUTPUT_MODES = frozenset({'replace', 'keep_both', 'suffix'})
_VALID_ENCODE_ENGINES = frozenset({'auto', 'direct', 'hardware', 'software'})
_VALID_HW_BITRATE_MODES = frozenset({'auto', 'vbr', 'cbr'})
_VALID_MAX_HEIGHTS = frozenset({0, 480, 720, 1080})
_VALID_AUDIO_BITRATES = frozenset({96, 128, 192})
_DEFAULT_AUDIO_BITRATE = 128


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


def normalize_encode_crf(value, *, ceiling: int = 28) -> int:
    try:
        crf = int(value)
    except (TypeError, ValueError):
        crf = 23
    cap = max(18, min(32, int(ceiling)))
    return max(18, min(cap, crf))


def normalize_encode_max_height(value) -> int:
    try:
        height = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return height if height in _VALID_MAX_HEIGHTS else 0


def normalize_encode_output_mode(value) -> str:
    mode = str(value or 'replace').strip().lower()
    return mode if mode in _VALID_OUTPUT_MODES else 'replace'


def normalize_encode_engine(value) -> str:
    engine = str(value or 'auto').strip().lower()
    return engine if engine in _VALID_ENCODE_ENGINES else 'auto'


def normalize_hardware_bitrate_kbps(value) -> int:
    try:
        kbps = int(value if value is not None else 0)
    except (TypeError, ValueError):
        return 0
    if kbps <= 0:
        return 0
    return max(200, min(50000, kbps))


def normalize_hardware_gop(value) -> int:
    try:
        gop = int(value if value is not None else 0)
    except (TypeError, ValueError):
        return 0
    if gop <= 0:
        return 0
    return max(1, min(600, gop))


def normalize_hardware_bitrate_mode(value) -> str:
    mode = str(value or 'auto').strip().lower()
    return mode if mode in _VALID_HW_BITRATE_MODES else 'auto'


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


def normalize_audio_bitrate(value) -> int:
    try:
        kbps = int(value or _DEFAULT_AUDIO_BITRATE)
    except (TypeError, ValueError):
        kbps = _DEFAULT_AUDIO_BITRATE
    return kbps if kbps in _VALID_AUDIO_BITRATES else _DEFAULT_AUDIO_BITRATE


def normalize_audio_volume(value) -> float:
    try:
        volume = float(value if value is not None else 1.0)
    except (TypeError, ValueError):
        volume = 1.0
    return max(1.0, min(3.0, round(volume, 1)))


def apply_audio_options(
        site,
        audio_fade=None,
        audio_loudnorm=None,
        audio_mute=None,
        audio_bitrate=None,
        audio_volume=None) -> None:
    if audio_fade is not None:
        site._audio_fade = bool(audio_fade)
    if audio_loudnorm is not None:
        site._audio_loudnorm = bool(audio_loudnorm)
    site._audio_mute = bool(audio_mute)
    site._audio_bitrate = normalize_audio_bitrate(audio_bitrate)
    site._audio_volume = normalize_audio_volume(audio_volume)


def apply_encode_options(
        site,
        encode=None,
        encode_codec=None,
        encode_crf=None,
        encode_max_height=None,
        encode_output_mode=None,
        encode_preset=None,
        encode_threads=None,
        encode_engine=None,
        encode_hardware_bitrate_kbps=None,
        encode_hardware_gop=None,
        encode_hardware_bitrate_mode=None,
        encode_small_file=None) -> None:
    site._encode_enabled = bool(encode)
    site._encode_codec = normalize_encode_codec(encode_codec)
    site._encode_crf = normalize_encode_crf(encode_crf)
    site._encode_max_height = normalize_encode_max_height(encode_max_height)
    site._encode_output_mode = normalize_encode_output_mode(encode_output_mode)
    site._encode_preset = normalize_encode_preset(encode_preset)
    site._encode_threads = normalize_encode_threads(encode_threads)
    site._encode_engine = normalize_encode_engine(encode_engine)
    site._encode_hardware_bitrate_kbps = normalize_hardware_bitrate_kbps(
        encode_hardware_bitrate_kbps)
    site._encode_hardware_gop = normalize_hardware_gop(encode_hardware_gop)
    site._encode_hardware_bitrate_mode = normalize_hardware_bitrate_mode(
        encode_hardware_bitrate_mode)
    if encode_small_file is not None:
        site._encode_small_file = bool(encode_small_file)
    site._encoded_output_path = None


def site_wants_small_file(site) -> bool:
    return bool(getattr(site, '_encode_small_file', False))


def effective_encode_crf(site) -> int:
    ceiling = 32 if site_wants_small_file(site) else 28
    crf = normalize_encode_crf(getattr(site, '_encode_crf', None), ceiling=ceiling)
    if site_wants_small_file(site):
        return max(crf, 30)
    return crf


def wants_software_bitrate_cap(site) -> bool:
    """VBR cap for software encode when user picked hardware/auto or smallest-file."""
    if site_wants_small_file(site):
        return True
    engine = normalize_encode_engine(getattr(site, '_encode_engine', None))
    return engine in ('hardware', 'auto')


def site_wants_encode(site) -> bool:
    return bool(getattr(site, '_encode_enabled', False))


def site_wants_fade(site) -> bool:
    return bool(getattr(site, '_audio_fade', False))


def site_wants_loudnorm(site) -> bool:
    return bool(getattr(site, '_audio_loudnorm', False))


def site_wants_mute(site) -> bool:
    return bool(getattr(site, '_audio_mute', False))


def site_wants_volume_boost(site) -> bool:
    if site_wants_mute(site):
        return False
    return normalize_audio_volume(getattr(site, '_audio_volume', 1.0)) > 1.0


def resolved_audio_bitrate(site) -> int:
    return normalize_audio_bitrate(getattr(site, '_audio_bitrate', None))


def _audio_bitrate_only_rewrite(site) -> bool:
    return resolved_audio_bitrate(site) != _DEFAULT_AUDIO_BITRATE


def needs_audio_processing(site) -> bool:
    if site_wants_mute(site):
        return True
    if site_wants_fade(site) or site_wants_loudnorm(site):
        return True
    if site_wants_volume_boost(site):
        return True
    return _audio_bitrate_only_rewrite(site)


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
    if site_wants_small_file(site):
        return 'slow'
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
    if site_wants_mute(site):
        return None
    parts = []
    volume = normalize_audio_volume(getattr(site, '_audio_volume', 1.0))
    if volume > 1.0:
        parts.append(f'volume={volume:g}')
    duration = float(duration_sec or 0)
    if site_wants_fade(site) and duration > 0:
        fade = min(FADE_SEC, duration / 2)
        parts.append(f'afade=t=in:st=0:d={fade:g}')
        if duration > fade * 2:
            parts.append(f'afade=t=out:st={duration - fade:g}:d={fade:g}')
    if site_wants_loudnorm(site):
        parts.append('loudnorm')
    return ','.join(parts) if parts else None


def _append_audio_mapping(cmd, site, duration_sec: float | None, *, video_copy: bool) -> None:
    if site_wants_mute(site):
        if video_copy:
            cmd.extend(['-c:v', 'copy', '-an'])
        else:
            cmd.append('-an')
        return
    af = build_af_filter(site, duration_sec)
    rewrite = bool(af) or _audio_bitrate_only_rewrite(site)
    if not rewrite:
        if video_copy:
            cmd.extend(['-c', 'copy'])
        return
    bitrate = resolved_audio_bitrate(site)
    if video_copy:
        cmd.extend(['-c:v', 'copy'])
    cmd.extend(['-c:a', 'aac', '-b:a', f'{bitrate}k'])
    if af:
        cmd.extend(['-af', af])


def append_ffmpeg_output_args(cmd, site, duration_sec: float | None = None) -> None:
    _append_audio_mapping(cmd, site, duration_sec, video_copy=True)
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
    duration = float(duration_sec or 0)
    if duration > 0 and out_time_sec >= 0:
        now = time.monotonic()
        last = getattr(site, '_encode_progress_state', None)
        speed = 0.0
        if isinstance(last, dict):
            dt = now - float(last.get('t', now))
            dout = out_time_sec - float(last.get('out', out_time_sec))
            if dt > 0.05 and dout > 0:
                speed = (dout * 1000.0) / dt
        site._encode_progress_state = {'t': now, 'out': out_time_sec}
        done_ms = int(min(out_time_sec, duration) * 1000.0)
        total_ms = max(1, int(duration * 1000.0))
        cb(done_ms, total_ms, speed, 'time')
        return
    downloaded = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    total = input_size if input_size > 0 else downloaded
    cb(max(downloaded, 0), max(total, 1), 0.0, 'bytes')


def _build_encode_cmd(ffmpeg, site, src_path, dst_path, duration_sec, decision=None):
    """Backward-compatible wrapper; prefer build_encode_command directly."""
    from jav_downloader.sites.encoding_decision import (
        MODE_SOFTWARE_ENCODE,
        EncodingDecision,
    )
    from jav_downloader.sites.encoding_strategies import build_encode_command

    if decision is None:
        decision = EncodingDecision(
            mode=MODE_SOFTWARE_ENCODE,
            video_copy=False,
            scale_needed=False,
            reasons=('legacy encode path',),
        )
    cmd = build_encode_command(
        ffmpeg, site, src_path, dst_path, duration_sec, decision)
    if cmd is None:
        raise Exception('encode command requested for direct-remux decision')
    return cmd


def _finalize_encoded_mp4(ffmpeg: str, path: str) -> None:
    """Remux with faststart so players (e.g. MX Player) can seek reliably."""
    if not path or not os.path.isfile(path):
        return
    dest_dir = os.path.dirname(path) or os.getcwd()
    fd, tmp = tempfile.mkstemp(suffix='.mp4', prefix='jav-remux-', dir=dest_dir)
    os.close(fd)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', path,
        '-c', 'copy',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        tmp,
    ]
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        **_no_window_kwargs(),
    )
    if proc.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, path)
    else:
        _safe_remove(tmp)


def _run_ffmpeg(cmd, site, out_path, duration_sec, input_size):
    from jav_downloader.sites.encoding_performance import ffmpeg_work_session

    with ffmpeg_work_session(site):
        return _run_ffmpeg_inner(cmd, site, out_path, duration_sec, input_size)


def _run_ffmpeg_inner(cmd, site, out_path, duration_sec, input_size):
    site._encode_progress_state = None
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


def _log_encoding_decision(site, decision, media_info) -> None:
    from jav_downloader.sites.encoding_decision import format_encoding_decision_log

    message = format_encoding_decision_log(decision, media_info, site)
    emit = getattr(site, '_emit_job_log', None)
    if emit:
        emit(message)
    phase_cb = getattr(site, '_progress_phase', None)
    if phase_cb and decision.mode != 'skip':
        phase_cb('Encoding', message.split('Encoding decision:', 1)[-1].strip())


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
        from jav_downloader.sites.encoding_decision import (
            MODE_DIRECT_REMUX,
            MODE_SKIP,
            decide_encoding,
        )
        from jav_downloader.sites.encoding_performance import cached_probe_media

        media_info = cached_probe_media(site, src_path)
        source_height = (
            media_info.video.height
            if media_info and media_info.video else None)
        decision = decide_encoding(site, media_info)
        _log_encoding_decision(site, decision, media_info)

        if decision.mode == MODE_SKIP:
            return finalize_processed_output(site, src_path, duration_sec)

        if decision.mode == MODE_DIRECT_REMUX:
            return finalize_processed_output(site, src_path, duration_sec)

        dst_path, mode = _encode_destination_path(src_path, site)
        dest_dir = os.path.dirname(dst_path) or os.getcwd()
        os.makedirs(dest_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            suffix='.mp4', prefix='jav-encode-', dir=dest_dir)
        os.close(fd)

        from jav_downloader.sites.encoding_strategies import (
            STRATEGY_HARDWARE,
            STRATEGY_SOFTWARE,
            build_encode_command,
            encode_strategy_label,
            strategy_for_decision,
        )

        strategy = strategy_for_decision(decision, site)
        encode_detail = encode_strategy_label(strategy, site)
        phase_cb = getattr(site, '_progress_phase', None)
        if phase_cb:
            phase_cb('Encoding', encode_detail)
        if emit:
            emit(f'Encoding… {encode_detail}')

        cmd = build_encode_command(
            ffmpeg, site, src_path, temp_path, duration_sec, decision,
            strategy=strategy, source_height=source_height)
        ok, stderr_tail = _run_ffmpeg(
            cmd, site, temp_path, float(duration_sec or 0), input_size)
        if (not ok or not os.path.isfile(temp_path) or
                os.path.getsize(temp_path) <= 0) and strategy == STRATEGY_HARDWARE:
            fallback_detail = stderr_tail.strip() or 'hardware encode failed'
            if emit:
                emit(
                    f'Hardware encoder failed ({fallback_detail}); '
                    f'falling back to software')
            strategy = STRATEGY_SOFTWARE
            encode_detail = encode_strategy_label(strategy, site)
            if phase_cb:
                phase_cb('Encoding', encode_detail)
            if emit:
                emit(f'Encoding… {encode_detail}')
            _safe_remove(temp_path)
            cmd = build_encode_command(
                ffmpeg, site, src_path, temp_path, duration_sec, decision,
                strategy=strategy, source_height=source_height)
            ok, stderr_tail = _run_ffmpeg(
                cmd, site, temp_path, float(duration_sec or 0), input_size)

        if not ok or not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
            _safe_remove(temp_path)
            detail = stderr_tail.strip() or 'ffmpeg encode failed'
            raise Exception(f'Encode failed: {detail}')

        _finalize_encoded_mp4(ffmpeg, temp_path)

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

    return finalize_processed_output(site, src_path, duration_sec)


def finalize_processed_output(
        site, src_path: str, duration_sec: float | None = None) -> str:
    """Apply audio processing; honor encode output_mode when set."""
    if not needs_audio_processing(site):
        return src_path
    mode = normalize_encode_output_mode(getattr(site, '_encode_output_mode', None))
    if mode == 'replace':
        post_process_audio(site, src_path, duration_sec)
        return src_path
    dst_path, mode = _encode_destination_path(src_path, site)
    post_process_audio(site, src_path, duration_sec, dst_path=dst_path)
    if mode == 'keep_both':
        site._encoded_output_path = dst_path
        return dst_path
    _safe_remove(src_path)
    site._encoded_output_path = dst_path
    return dst_path


def post_process_audio(
        site,
        src_path: str,
        duration_sec: float | None = None,
        *,
        dst_path: str | None = None) -> None:
    """Rewrite audio to dst_path or in-place (video copy)."""
    if not needs_audio_processing(site):
        return
    if not src_path or not os.path.isfile(src_path):
        return

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('Audio processing requires ffmpeg')

    dest_dir = os.path.dirname(src_path) or os.getcwd()
    fd, temp_path = tempfile.mkstemp(suffix='.mp4', prefix='jav-audio-', dir=dest_dir)
    os.close(fd)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', src_path,
    ]
    _append_audio_mapping(cmd, site, duration_sec, video_copy=True)
    cmd.extend(['-movflags', '+faststart', temp_path])
    from jav_downloader.sites.encoding_performance import ffmpeg_work_session

    with ffmpeg_work_session(site):
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
    os.replace(temp_path, dst_path or src_path)
