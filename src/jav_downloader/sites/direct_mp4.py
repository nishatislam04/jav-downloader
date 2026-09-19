#!/usr/bin/env python
# coding: utf-8
"""Resumable progressive-MP4 downloads and ffmpeg time-range cuts."""

from __future__ import annotations

import concurrent.futures
import os
import re
import select
import subprocess
import tempfile
import threading
import time

from jav_downloader.core import config
from jav_downloader.sites.base import (
    locate_ffmpeg,
    speed_limiter,
    _get_session,
    _no_window_kwargs,
)

_DIRECT_RANGE_WORKERS = 4
_DIRECT_RANGE_RETRIES = 4
_DIRECT_RETRY_BASE_DELAY = 1.0


def content_range(value):
    match = re.fullmatch(
        r'bytes\s+(\d+)-(\d+)/(\d+)', str(value or '').strip(), re.I)
    if not match:
        return None
    start, end, total = (int(part) for part in match.groups())
    if start > end or end >= total:
        return None
    return start, end, total


def split_byte_ranges(total, workers=_DIRECT_RANGE_WORKERS):
    workers = min(max(1, int(workers)), total)
    chunk, remainder = divmod(total, workers)
    ranges = []
    start = 0
    for index in range(workers):
        size = chunk + (1 if index < remainder else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _has_time_cut(site):
    if getattr(site, '_cut_ranges', None):
        return True
    return (getattr(site, '_cut_start_sec', None) is not None or
            getattr(site, '_cut_end_sec', None) is not None)


def _stop_requested(site):
    return bool(site._cancel_job or getattr(site, '_pause_job', False))


def _probe_headers(referer, extra_headers=None):
    headers = {'Referer': referer}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def probe_source_length(url, referer, extra_headers=None, session=None):
    """Return total byte length for a direct URL when the host supports ranges."""
    session = session or _get_session()
    headers = _probe_headers(referer, extra_headers)
    for method in ('head', 'get'):
        probe = None
        try:
            request = getattr(session, method, session.get)
            probe = request(
                url,
                headers={**headers, 'Range': 'bytes=0-0'} if method == 'get' else headers,
                timeout=60,
                stream=True,
                allow_redirects=True,
                **config.proxy_request_kwargs(),
            )
            info = content_range(getattr(probe, 'headers', {}).get('content-range'))
            if info:
                total = info[2]
            elif getattr(probe, 'status_code', 0) == 200:
                try:
                    total = int(probe.headers.get('content-length') or 0)
                except (TypeError, ValueError):
                    total = 0
            else:
                total = 0
            return total if total > 0 else 0
        except Exception:
            pass
        finally:
            if probe is not None:
                try:
                    probe.close()
                except Exception:
                    pass
    return 0


def _sync_part_with_source(site, part, referer):
    """Drop stale .part files that no longer match the current direct URL."""
    if not os.path.exists(part):
        return
    part_size = os.path.getsize(part)
    if part_size <= 0:
        return
    extra = getattr(site, '_extra_headers', None) or {}
    probed = probe_source_length(
        site._direct_url, referer, extra_headers=extra)
    if probed > 0 and part_size >= probed:
        _safe_remove(part)


def _clip_duration_sec(site, start_sec, end_sec, clip_duration):
    if clip_duration is not None:
        return max(0.0, float(clip_duration))
    if end_sec is not None:
        return max(0.0, float(end_sec) - float(start_sec or 0))
    video_duration = getattr(site, '_duration_sec', None)
    try:
        video_duration = float(video_duration)
    except (TypeError, ValueError):
        video_duration = 0.0
    if video_duration > 0:
        return max(0.0, video_duration - float(start_sec or 0))
    return 0.0


def _parse_ffmpeg_out_time_sec(line):
    text = str(line or '').strip()
    if not text.startswith('out_time'):
        return None
    _, _, value = text.partition('=')
    value = value.strip()
    if not value or value == 'N/A':
        return None
    if text.startswith('out_time_us='):
        return int(value) / 1_000_000.0
    if text.startswith('out_time_ms='):
        return int(value) / 1000.0
    if text.startswith('out_time='):
        hours, minutes, seconds = value.split(':')
        return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)
    return None


def _decode_pipe_line(line):
    try:
        return line.decode('utf-8', errors='replace')
    except AttributeError:
        return str(line)


def _poll_pipe_lines(stream):
    """Read any progress lines currently waiting on a pipe (never blocks)."""
    if stream is None:
        return []
    fd = stream.fileno()
    lines = []
    while True:
        ready, _, _ = select.select([fd], [], [], 0)
        if not ready:
            break
        chunk = stream.readline()
        if not chunk:
            break
        lines.append(_decode_pipe_line(chunk))
    return lines


def _read_ffmpeg_progress(proc, out_time_sec=0.0):
    """Update encoded duration from any pending ffmpeg -progress output."""
    latest = out_time_sec
    for line in _poll_pipe_lines(getattr(proc, 'stdout', None)):
        parsed = _parse_ffmpeg_out_time_sec(line)
        if parsed is not None:
            latest = parsed
    return latest


def _drain_stderr(proc, tail=''):
    for line in _poll_pipe_lines(getattr(proc, 'stderr', None)):
        tail = (tail + line)[-800:]
    return tail


def _emit_cut_progress(
        site, downloaded, speed, out_time_sec, clip_len, estimated_total):
    if not site._progress_callback:
        return
    total = _cut_progress_total(
        estimated_total, downloaded, out_time_sec, clip_len)
    if (downloaded <= 0 and out_time_sec > 0 and clip_len > 0 and
            total <= 0):
        total = estimated_total or 1000
        downloaded = int(total * min(1.0, out_time_sec / clip_len))
    elif (downloaded > 0 and total <= 0 and out_time_sec > 0 and
          clip_len > 0):
        total = max(downloaded, int(downloaded * clip_len / out_time_sec))
    site._progress_callback(downloaded, total, speed, 'bytes')


def _cut_progress_total(estimated_total, downloaded, out_time_sec, clip_len):
    if estimated_total > 0:
        return estimated_total
    if downloaded > 0 and out_time_sec and out_time_sec > 0 and clip_len > 0:
        return max(downloaded, int(downloaded * clip_len / out_time_sec))
    return 0


def estimate_cut_total_bytes(site, start_sec, end_sec, clip_duration, referer):
    """Estimate output size for a time-range cut from source length and duration."""
    extra = getattr(site, '_extra_headers', None) or {}
    full_size = probe_source_length(
        site._direct_url, referer, extra_headers=extra)
    video_duration = getattr(site, '_duration_sec', None)
    try:
        video_duration = float(video_duration)
    except (TypeError, ValueError):
        video_duration = 0.0
    if full_size <= 0 or video_duration <= 0:
        return 0
    if clip_duration is not None:
        clip_len = max(0.0, float(clip_duration))
    elif end_sec is not None:
        clip_len = max(0.0, float(end_sec) - float(start_sec or 0))
    else:
        clip_len = max(0.0, video_duration - float(start_sec or 0))
    if clip_len <= 0:
        return 0
    return max(1, int(full_size * clip_len / video_duration))


def run_direct_download(site):
    """Download site._direct_url to the final MP4 path with resume or time cut."""
    if site._cancel_job:
        return False
    site._cancel_job = False
    site._pause_job = False
    site._create_dest_folder()
    if site.is_target_video_exist():
        print('檔案已存在!!', flush=True)
        return True

    out = site._get_video_savename()
    part = out + '.part'
    ref = getattr(site, '_direct_referer', None) or site.direct_default_referer
    label = getattr(site, 'direct_site_name', 'Direct')

    if _has_time_cut(site):
        from jav_downloader.sites.multi_cut import (
            run_hls_multi_cut,
            run_stream_multi_cut,
            site_is_multi_cut,
        )
        _safe_remove(part)
        if site_is_multi_cut(site):
            if getattr(site, '_m3u8url', None) and not getattr(site, '_direct_url', None):
                return run_hls_multi_cut(site)
            return run_stream_multi_cut(site)
        return _download_ffmpeg_cut(site, part, out, ref, label)

    _sync_part_with_source(site, part, ref)

    start = time.time()
    try:
        try:
            ranged = _download_parallel_ranges(site, part, ref, start)
        except Exception:
            if _stop_requested(site):
                return False
            print(
                f'\n[{label}] Parallel ranges failed; '
                'retrying with one resumable connection.',
                flush=True)
            ranged = None
        if ranged is None:
            done, total = _download_serial(site, part, ref, start)
        else:
            done, total = ranged
    except Exception:
        if _stop_requested(site):
            return False
        raise

    if _stop_requested(site):
        return False
    if total > 0 and done < int(total * 0.98):
        raise Exception('下載不完整（連線中斷？請重試，會從 .part 續傳）')
    try:
        os.replace(part, out)
    except OSError:
        _safe_remove(part)
        raise
    from jav_downloader.sites.media_post import post_process_media
    post_process_media(site, out, getattr(site, '_duration_sec', None))
    print(f'\n下載完成: {os.path.basename(out)}', flush=True)
    return True


def _download_ffmpeg_cut(site, part, out, referer, label):
    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('時間裁剪需要 ffmpeg，但系統找不到 ffmpeg')

    start_sec = float(getattr(site, '_cut_start_sec', None) or 0)
    end_sec = getattr(site, '_cut_end_sec', None)
    duration = None
    if end_sec is not None:
        duration = max(0.0, float(end_sec) - start_sec)
        if duration <= 0:
            raise Exception('裁剪結束時間必須大於開始時間')

    clip_len = _clip_duration_sec(site, start_sec, end_sec, duration)

    header_blob = f'Referer: {referer}\r\n'
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-headers', header_blob,
        '-ss', str(start_sec),
        '-i', site._direct_url,
    ]
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    dest_dir = os.path.dirname(out) or os.getcwd()
    os.makedirs(dest_dir, exist_ok=True)
    fd, safe_part = tempfile.mkstemp(
        suffix='.mp4', prefix='jav-cut-', dir=dest_dir)
    os.close(fd)
    from jav_downloader.sites.audio_post import append_ffmpeg_output_args
    append_ffmpeg_output_args(cmd, site, clip_len)
    cmd.append(safe_part)

    estimated_total = estimate_cut_total_bytes(
        site, start_sec, end_sec, duration, referer)

    if not site.silence:
        end_label = f'{end_sec}s' if end_sec is not None else 'end'
        print(
            f'[{label}] ffmpeg 裁剪 {start_sec}s → {end_label} '
            f'({urlsplit_safe(site._direct_url)})',
            flush=True)

    started = time.time()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    site._ffmpeg_proc = proc
    stderr_tail = ''
    out_time_sec = 0.0
    if estimated_total > 0:
        _emit_cut_progress(site, 0, 0.0, 0.0, clip_len, estimated_total)
    try:
        while True:
            if _stop_requested(site):
                proc.kill()
                proc.wait(timeout=5)
                _safe_remove(safe_part)
                return False
            out_time_sec = _read_ffmpeg_progress(proc, out_time_sec)
            stderr_tail = _drain_stderr(proc, stderr_tail)
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                downloaded = (
                    os.path.getsize(safe_part)
                    if os.path.exists(safe_part) else 0)
                elapsed = time.time() - started
                speed = downloaded / elapsed if elapsed > 0 else 0
                _emit_cut_progress(
                    site, downloaded, speed, out_time_sec, clip_len,
                    estimated_total)
    finally:
        site._ffmpeg_proc = None
        out_time_sec = _read_ffmpeg_progress(proc, out_time_sec)
        stderr_tail = _drain_stderr(proc, stderr_tail)

    if (proc.returncode != 0 or not os.path.exists(safe_part) or
            os.path.getsize(safe_part) <= 0):
        _safe_remove(safe_part)
        detail = stderr_tail.strip() or f'ffmpeg exit {proc.returncode}'
        raise Exception(f'ffmpeg 裁剪失敗: {detail}')

    _safe_remove(part)
    os.replace(safe_part, out)
    if site._progress_callback:
        size = os.path.getsize(out)
        elapsed = time.time() - started
        speed = size / elapsed if elapsed > 0 else 0
        site._progress_callback(size, size, speed, 'bytes')
    print(f'\n下載完成: {os.path.basename(out)}', flush=True)
    return True


def urlsplit_safe(url):
    try:
        from urllib.parse import urlsplit
        return urlsplit(str(url or '')).netloc or str(url)
    except Exception:
        return str(url)


def _download_parallel_ranges(site, part, referer, start_time):
    extra = getattr(site, '_extra_headers', None) or {}
    session = _get_session()
    probe = None
    try:
        probe = session.get(
            site._direct_url,
            headers={**_probe_headers(referer, extra), 'Range': 'bytes=0-0'},
            timeout=60,
            stream=True,
            allow_redirects=True,
            **config.proxy_request_kwargs(),
        )
        info = content_range(getattr(probe, 'headers', {}).get('content-range'))
        if getattr(probe, 'status_code', 0) != 206 or not info or info[:2] != (0, 0):
            return None
        total = info[2]
    except Exception:
        return None
    finally:
        if probe is not None:
            try:
                probe.close()
            except Exception:
                pass
    existing = os.path.getsize(part) if os.path.exists(part) else 0
    if existing > 0 and existing != total:
        _safe_remove(part)
        existing = 0
    if existing == 0:
        with open(part, 'wb') as target:
            target.truncate(total)

    workers = min(
        _DIRECT_RANGE_WORKERS,
        getattr(site, '_max_workers', _DIRECT_RANGE_WORKERS))
    ranges = split_byte_ranges(total, workers)
    pending = []
    for bounds in ranges:
        range_start, range_end = bounds
        if range_start >= total:
            continue
        if existing and range_end < existing:
            continue
        pending.append(bounds)
    if len(pending) <= 1:
        return None

    progress_lock = threading.Lock()
    stop_event = threading.Event()
    done = min(existing, total)

    def _fetch_range(bounds):
        nonlocal done
        range_start, range_end = bounds
        expected = range_end - range_start + 1
        written = 0
        retries = 0
        while written < expected and not _stop_requested(site) and not stop_event.is_set():
            cursor = range_start + written
            response = None
            try:
                response = session.get(
                    site._direct_url,
                    headers={'Referer': referer, 'Range': f'bytes={cursor}-{range_end}'},
                    timeout=60,
                    stream=True,
                    allow_redirects=True,
                    **config.proxy_request_kwargs(),
                )
                response_range = content_range(
                    getattr(response, 'headers', {}).get('content-range'))
                if (getattr(response, 'status_code', 0) != 206 or
                        response_range != (cursor, range_end, total)):
                    raise Exception('直接下載來源未正確回應分段請求')

                received = 0
                with open(part, 'r+b', buffering=0) as target:
                    target.seek(cursor)
                    for chunk in response.iter_content(chunk_size=262144):
                        if _stop_requested(site) or stop_event.is_set():
                            break
                        if not chunk:
                            continue
                        if written + len(chunk) > expected:
                            raise Exception('直接下載分段長度超出預期')
                        speed_limiter.acquire(len(chunk))
                        if target.write(chunk) != len(chunk):
                            raise Exception('直接下載寫入失敗')
                        written += len(chunk)
                        received += len(chunk)
                        with progress_lock:
                            done += len(chunk)
                            current_done = done
                            elapsed = time.time() - start_time
                            speed = current_done / elapsed if elapsed > 0 else 0
                            if site._progress_callback:
                                site._progress_callback(current_done, total, speed)

                if _stop_requested(site) or stop_event.is_set():
                    break
                if written < expected:
                    detail = '未收到資料' if received == 0 else '連線提前結束'
                    raise Exception(f'直接下載分段{detail}')
            except Exception:
                if _stop_requested(site) or stop_event.is_set():
                    break
                retries += 1
                if retries > _DIRECT_RANGE_RETRIES:
                    raise
                stop_event.wait(_DIRECT_RETRY_BASE_DELAY * retries)
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        if not _stop_requested(site) and not stop_event.is_set() and written != expected:
            raise Exception('直接下載分段不完整（連線中斷？請重試）')
        return written

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(pending))
    site._t2_executor = executor
    futures = [executor.submit(_fetch_range, bounds) for bounds in pending]
    try:
        for future in concurrent.futures.as_completed(futures):
            future.result()
    except Exception:
        stop_event.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True)
        site._t2_executor = None

    if _stop_requested(site):
        return done, total
    if done != total:
        raise Exception('直接下載不完整（連線中斷？請重試）')
    return done, total


def _download_serial(site, part, referer, start_time):
    extra = getattr(site, '_extra_headers', None) or {}
    done = os.path.getsize(part) if os.path.exists(part) else 0
    total = 0
    retries = 0
    session = _get_session()
    while not _stop_requested(site):
        request_headers = _probe_headers(referer, extra)
        if done:
            request_headers['Range'] = f'bytes={done}-'
        resp = None
        try:
            resp = session.get(
                site._direct_url,
                headers=request_headers,
                timeout=60,
                stream=True,
                allow_redirects=True,
                **config.proxy_request_kwargs(),
            )
            status = getattr(resp, 'status_code', 0)
            response_range = content_range(
                getattr(resp, 'headers', {}).get('content-range'))
            if done and status == 416:
                _safe_remove(part)
                done = 0
                retries += 1
                continue
            if done:
                if status != 206 or not response_range or response_range[0] != done:
                    raise Exception(f'直接續傳失敗 (HTTP {status})')
                total = response_range[2]
            elif status == 206 and response_range:
                total = response_range[2]
            elif status == 200:
                try:
                    total = int(resp.headers.get('content-length') or 0)
                except (TypeError, ValueError):
                    total = 0
            else:
                raise Exception(f'直接下載失敗 (HTTP {status})')

            received = 0
            with open(part, 'ab' if done else 'wb') as target:
                for chunk in resp.iter_content(chunk_size=262144):
                    if _stop_requested(site):
                        break
                    if not chunk:
                        continue
                    speed_limiter.acquire(len(chunk))
                    target.write(chunk)
                    done += len(chunk)
                    received += len(chunk)
                    elapsed = time.time() - start_time
                    speed = done / elapsed if elapsed > 0 else 0
                    if site._progress_callback and total > 0:
                        site._progress_callback(done, total, speed)

            if _stop_requested(site):
                break
            if total > 0 and done >= total:
                return done, total
            if total == 0 and received > 0:
                return done, done
            raise Exception('直接下載連線提前結束')
        except Exception:
            if _stop_requested(site):
                break
            retries += 1
            if retries > _DIRECT_RANGE_RETRIES:
                raise
            time.sleep(_DIRECT_RETRY_BASE_DELAY * retries)
        finally:
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
    return done, total
