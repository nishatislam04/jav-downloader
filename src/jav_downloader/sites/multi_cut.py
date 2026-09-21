#!/usr/bin/env python
# coding: utf-8
"""Extract and concatenate multiple time ranges via ffmpeg."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time

from jav_downloader.sites.base import locate_ffmpeg, _no_window_kwargs


def normalize_cut_list(cuts=None, cut_start=None, cut_end=None):
    """Normalize API cut payload into a list of {start, end} dicts."""
    if cuts:
        out = []
        for item in cuts:
            if not isinstance(item, dict):
                continue
            start = str(item.get('start') or '').strip() or None
            end = str(item.get('end') or '').strip() or None
            if start or end:
                out.append({'start': start, 'end': end})
        if out:
            return out
    start = str(cut_start or '').strip() if cut_start else None
    end = str(cut_end or '').strip() if cut_end else None
    if start or end:
        return [{'start': start, 'end': end}]
    return []


def parse_cut_range_pair(start_raw, end_raw):
    from jav_downloader.sites.base import parse_time_seconds

    start_sec = parse_time_seconds(start_raw) if start_raw else None
    end_sec = parse_time_seconds(end_raw) if end_raw else None
    if start_raw and start_sec is None:
        raise ValueError('invalid start time')
    if end_raw and end_sec is None:
        raise ValueError('invalid end time')
    effective_start = float(start_sec or 0)
    if end_sec is not None and end_sec <= effective_start:
        raise ValueError('cut end must be after cut start')
    return start_sec, end_sec


def build_cut_ranges(cuts=None, cut_start=None, cut_end=None):
    items = normalize_cut_list(cuts, cut_start, cut_end)
    return [parse_cut_range_pair(item.get('start'), item.get('end')) for item in items]


def validate_cuts_against_duration(cut_ranges, duration_sec):
    from jav_downloader.sites.base import validate_cut_against_duration

    for start_sec, end_sec in cut_ranges:
        validate_cut_against_duration(start_sec, end_sec, duration_sec)


def site_has_cuts(site):
    return bool(getattr(site, '_cut_ranges', None))


def site_is_multi_cut(site):
    return len(getattr(site, '_cut_ranges', []) or []) > 1


def _stream_source(site):
    if getattr(site, '_direct_url', None):
        referer = getattr(site, '_direct_referer', None) or site.direct_default_referer
        return site._direct_url, referer, False
    if getattr(site, '_m3u8url', None):
        referer = getattr(site, '_extra_headers', {}).get('Referer') or site.get_url_full()
        return site._m3u8url, referer, True
    return None, None, False


def _header_blob(referer):
    return f'Referer: {referer}\r\n'


def _clip_file_valid(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def _multicut_workdir(site, dest_dir, prefix):
    saved = getattr(site, '_multicut_workdir', None)
    if saved and os.path.isdir(saved):
        return saved
    job_id = getattr(site, '_web_job_id', None) or getattr(site, '_dirName', 'clip')
    safe = re.sub(r'[^\w.-]+', '_', str(job_id))
    workdir = os.path.join(dest_dir, f'{prefix}{safe}')
    os.makedirs(workdir, exist_ok=True)
    site._multicut_workdir = workdir
    return workdir


def _discard_multicut_workdir(site):
    """Remove staging dir on success/cancel; keep it when paused."""
    return bool(getattr(site, '_cancel_job', False))


def _range_duration(start_sec, end_sec):
    start = float(start_sec or 0)
    if end_sec is None:
        return None
    return max(0.0, float(end_sec) - start)


def _extract_clip(
        site, ffmpeg, input_url, referer, start_sec, end_sec, output_path, label, index):
    from jav_downloader.sites.direct_mp4 import (
        _drain_stderr,
        _read_ffmpeg_progress,
        _stop_requested,
        urlsplit_safe,
    )

    start = float(start_sec or 0)
    duration = _range_duration(start_sec, end_sec)
    if duration is not None and duration <= 0:
        raise Exception('裁剪結束時間必須大於開始時間')

    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-headers', _header_blob(referer),
        '-ss', str(start),
        '-i', input_url,
    ]
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    cmd.extend(['-c', 'copy', '-movflags', '+faststart', output_path])

    if not site.silence:
        end_label = f'{end_sec}s' if end_sec is not None else 'end'
        print(
            f'[{label}] clip {index + 1}: ffmpeg {start}s → {end_label} '
            f'({urlsplit_safe(input_url)})',
            flush=True)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    site._ffmpeg_proc = proc
    stderr_tail = ''
    try:
        while True:
            if _stop_requested(site):
                proc.kill()
                proc.wait(timeout=5)
                return False, stderr_tail
            _read_ffmpeg_progress(proc)
            stderr_tail = _drain_stderr(proc, stderr_tail)
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        site._ffmpeg_proc = None
        stderr_tail = _drain_stderr(proc, stderr_tail)

    if proc.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        detail = stderr_tail.strip() or f'ffmpeg exit {proc.returncode}'
        raise Exception(f'ffmpeg 裁剪失敗 (clip {index + 1}): {detail}')
    return True, stderr_tail


def _concat_clips(site, ffmpeg, clip_paths, output_path, workdir, label):
    from jav_downloader.sites.direct_mp4 import _drain_stderr

    list_path = os.path.join(workdir, 'concat.txt')
    with open(list_path, 'w', encoding='utf-8') as handle:
        for path in clip_paths:
            safe = path.replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")

    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0', '-i', list_path,
        '-c', 'copy', '-movflags', '+faststart', output_path,
    ]
    if not site.silence:
        print(f'[{label}] merging {len(clip_paths)} clips', flush=True)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    site._ffmpeg_proc = proc
    stderr_tail = ''
    try:
        proc.wait()
        stderr_tail = _drain_stderr(proc, stderr_tail)
    finally:
        site._ffmpeg_proc = None

    if proc.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        detail = stderr_tail.strip() or f'ffmpeg exit {proc.returncode}'
        raise Exception(f'ffmpeg 合併失敗: {detail}')


def _total_clip_length(site, cut_ranges):
    from jav_downloader.sites.direct_mp4 import _clip_duration_sec

    total = 0.0
    for start_sec, end_sec in cut_ranges:
        duration = _range_duration(start_sec, end_sec)
        if duration is None:
            duration = _clip_duration_sec(site, start_sec, end_sec, None)
        total += max(0.0, float(duration or 0))
    return total


def _download_hls_clip(site, start_sec, end_sec, clip_path, index):
    """Download one cut range via filtered HLS segments."""
    from jav_downloader.sites.base import DownloadIncompleteError

    site._cut_start_sec = start_sec
    site._cut_end_sec = end_sec
    site._create_temp_folder()
    emit = getattr(site, '_emit_job_log', None)
    if emit:
        emit(f'Loading HLS playlist for clip {index + 1}…')
    site._create_m3u8()
    if emit:
        emit(f'Clip {index + 1}: found {len(site._tsList)} segments')
    if not site._stop_requested():
        if emit:
            emit(f'Clip {index + 1}: downloading segments…')
        site._prepareCrawl()
    if site._stop_requested():
        return False
    if site._pending_set:
        pending = len(site._pending_set)
        raise DownloadIncompleteError(pending)
    if emit:
        emit(f'Clip {index + 1}: merging segments…')
    merged = site._mergeMp4Chunks()
    if not merged:
        raise Exception(f'clip {index + 1} merge failed')
    merged_out = site._get_video_savename()
    if not os.path.isfile(merged_out):
        raise Exception(f'clip {index + 1} output missing')
    os.replace(merged_out, clip_path)
    site._deleteMp4Chunks()
    return True


def run_hls_multi_cut(site):
    """Multi-range HLS cuts via per-range segment download and ffmpeg concat."""
    from jav_downloader.sites.direct_mp4 import _safe_remove, _stop_requested

    cut_ranges = getattr(site, '_cut_ranges', None) or []
    if not cut_ranges:
        return False

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('時間裁剪需要 ffmpeg，但系統找不到 ffmpeg')

    out = site._get_video_savename()
    label = getattr(site, 'direct_site_name', None) or site.__class__.__name__
    dest_dir = os.path.dirname(out) or os.getcwd()
    os.makedirs(dest_dir, exist_ok=True)
    workdir = _multicut_workdir(site, dest_dir, 'jav-hlsmulticut-')
    emit = getattr(site, '_emit_job_log', None)
    if emit:
        emit(f'Clip staging folder: {workdir}')
    clip_paths = []
    discard_workdir = True
    try:
        for index, (start_sec, end_sec) in enumerate(cut_ranges):
            if _stop_requested(site):
                discard_workdir = _discard_multicut_workdir(site)
                return False
            clip_path = os.path.join(workdir, f'clip_{index:02d}.mp4')
            if _clip_file_valid(clip_path):
                if emit:
                    emit(f'Clip {index + 1}: reusing completed clip')
                clip_paths.append(clip_path)
                continue
            if not _download_hls_clip(site, start_sec, end_sec, clip_path, index):
                discard_workdir = _discard_multicut_workdir(site)
                return False
            clip_paths.append(clip_path)

        fd, safe_part = tempfile.mkstemp(suffix='.mp4', prefix='jav-hlsmulticut-', dir=dest_dir)
        os.close(fd)
        if len(clip_paths) == 1:
            os.replace(clip_paths[0], safe_part)
        else:
            _concat_clips(site, ffmpeg, clip_paths, safe_part, workdir, label)
        _safe_remove(out)
        os.replace(safe_part, out)
        from jav_downloader.sites.media_post import post_process_media
        post_process_media(
            site, out, _total_clip_length(site, cut_ranges) or getattr(site, '_duration_sec', None))
    finally:
        if discard_workdir:
            for path in clip_paths:
                _safe_remove(path)
            if emit:
                emit(f'Removing merge staging folder {workdir}')
            try:
                import shutil
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass
        elif emit:
            emit(f'Clip staging folder kept for resume: {workdir}')

    _emit_hls_multicut_progress(site, out)
    print(f'\n下載完成: {os.path.basename(out)}', flush=True)
    return True


def _emit_hls_multicut_progress(site, output_path):
    cb = getattr(site, '_progress_callback', None)
    if not cb or not os.path.isfile(output_path):
        return
    size = os.path.getsize(output_path)
    cb(size, size, 0.0, 'bytes')


def run_stream_multi_cut(site):
    """Download by extracting each cut range and concatenating into one MP4."""
    from jav_downloader.sites.direct_mp4 import (
        _emit_cut_progress,
        _safe_remove,
        _stop_requested,
        estimate_cut_total_bytes,
    )

    cut_ranges = getattr(site, '_cut_ranges', None) or []
    if not cut_ranges:
        return False

    # Remote ffmpeg HLS cannot fetch disguised segment URLs (google CDN, .woff2, etc.).
    if getattr(site, '_m3u8url', None) and not getattr(site, '_direct_url', None):
        return run_hls_multi_cut(site)

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('時間裁剪需要 ffmpeg，但系統找不到 ffmpeg')

    input_url, referer, _is_hls = _stream_source(site)
    if not input_url:
        raise Exception('無法裁剪：找不到可用的影片來源')

    out = site._get_video_savename()
    part = out + '.part'
    _safe_remove(part)
    site._create_dest_folder()

    label = getattr(site, 'direct_site_name', None) or site.__class__.__name__
    dest_dir = os.path.dirname(out) or os.getcwd()
    os.makedirs(dest_dir, exist_ok=True)
    workdir = _multicut_workdir(site, dest_dir, 'jav-multicut-')
    emit = getattr(site, '_emit_job_log', None)
    if emit:
        emit(f'Clip staging folder: {workdir}')
    clip_paths = []
    discard_workdir = True
    total_clip_len = _total_clip_length(site, cut_ranges)
    estimated_total = 0
    if getattr(site, '_direct_url', None):
        for start_sec, end_sec in cut_ranges:
            duration = _range_duration(start_sec, end_sec)
            estimated_total += estimate_cut_total_bytes(
                site, float(start_sec or 0), end_sec, duration, referer)

    started = time.time()
    downloaded = 0
    try:
        for index, (start_sec, end_sec) in enumerate(cut_ranges):
            if _stop_requested(site):
                discard_workdir = _discard_multicut_workdir(site)
                return False
            clip_path = os.path.join(workdir, f'clip_{index:02d}.mp4')
            if _clip_file_valid(clip_path):
                if emit:
                    emit(f'Clip {index + 1}: reusing completed clip')
                clip_paths.append(clip_path)
                continue
            ok, _stderr = _extract_clip(
                site, ffmpeg, input_url, referer, start_sec, end_sec, clip_path, label, index)
            if not ok:
                discard_workdir = _discard_multicut_workdir(site)
                return False
            clip_paths.append(clip_path)
            downloaded = sum(os.path.getsize(path) for path in clip_paths if os.path.exists(path))
            elapsed = time.time() - started
            speed = downloaded / elapsed if elapsed > 0 else 0
            _emit_cut_progress(
                site, downloaded, speed, min(total_clip_len, downloaded and total_clip_len or 0),
                total_clip_len, estimated_total)

        fd, safe_part = tempfile.mkstemp(suffix='.mp4', prefix='jav-multicut-', dir=dest_dir)
        os.close(fd)
        _concat_clips(site, ffmpeg, clip_paths, safe_part, workdir, label)
        _safe_remove(part)
        os.replace(safe_part, out)
        from jav_downloader.sites.media_post import post_process_media
        post_process_media(
            site, out, total_clip_len or getattr(site, '_duration_sec', None))
    finally:
        if discard_workdir:
            for path in clip_paths:
                _safe_remove(path)
            if emit:
                emit(f'Removing merge staging folder {workdir}')
            try:
                import shutil
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception:
                pass
        elif emit:
            emit(f'Clip staging folder kept for resume: {workdir}')

    _emit_hls_multicut_progress(site, out)
    print(f'\n下載完成: {os.path.basename(out)}', flush=True)
    return True
