#!/usr/bin/env python
# coding: utf-8
"""Resumable progressive-MP4 downloads and ffmpeg time-range cuts."""

from __future__ import annotations

import concurrent.futures
import os
import re
import subprocess
import tempfile
import threading
import time

from uav_downloader.core import config
from uav_downloader.sites.base import (
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
    return (getattr(site, '_cut_start_sec', None) is not None or
            getattr(site, '_cut_end_sec', None) is not None)


def probe_source_length(url, referer):
    """Return total byte length for a direct URL when the host supports ranges."""
    session = _get_session()
    probe = None
    try:
        probe = session.get(
            url,
            headers={'Referer': referer, 'Range': 'bytes=0-0'},
            timeout=60,
            stream=True,
            allow_redirects=True,
            **config.proxy_request_kwargs(),
        )
        info = content_range(getattr(probe, 'headers', {}).get('content-range'))
        if info:
            return info[2]
        if getattr(probe, 'status_code', 0) == 200:
            return int(probe.headers.get('content-length') or 0)
    except Exception:
        return 0
    finally:
        if probe is not None:
            try:
                probe.close()
            except Exception:
                pass
    return 0


def estimate_cut_total_bytes(site, start_sec, end_sec, clip_duration, referer):
    """Estimate output size for a time-range cut from source length and duration."""
    full_size = probe_source_length(site._direct_url, referer)
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
    site._create_dest_folder()
    if site.is_target_video_exist():
        print('檔案已存在!!', flush=True)
        return True

    out = site._get_video_savename()
    part = out + '.part'
    ref = getattr(site, '_direct_referer', None) or site.direct_default_referer
    label = getattr(site, 'direct_site_name', 'Direct')

    if _has_time_cut(site):
        _safe_remove(part)
        return _download_ffmpeg_cut(site, part, out, ref, label)

    start = time.time()
    try:
        try:
            ranged = _download_parallel_ranges(site, part, ref, start)
        except Exception:
            if site._cancel_job:
                raise
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
        raise

    if site._cancel_job:
        return False
    if total > 0 and done < int(total * 0.98):
        raise Exception('下載不完整（連線中斷？請重試，會從 .part 續傳）')
    try:
        os.replace(part, out)
    except OSError:
        _safe_remove(part)
        raise
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

    header_blob = f'Referer: {referer}\r\n'
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-headers', header_blob,
        '-ss', str(start_sec),
        '-i', site._direct_url,
    ]
    if duration is not None:
        cmd.extend(['-t', str(duration)])
    dest_dir = os.path.dirname(out) or os.getcwd()
    os.makedirs(dest_dir, exist_ok=True)
    fd, safe_part = tempfile.mkstemp(
        suffix='.mp4', prefix='uav-cut-', dir=dest_dir)
    os.close(fd)
    cmd.extend(['-c', 'copy', '-movflags', '+faststart', safe_part])

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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **_no_window_kwargs(),
    )
    site._ffmpeg_proc = proc
    stderr_tail = ''
    try:
        while True:
            if site._cancel_job:
                proc.kill()
                proc.wait(timeout=5)
                _safe_remove(safe_part)
                return False
            try:
                proc.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if site._progress_callback and os.path.exists(safe_part):
                    downloaded = os.path.getsize(safe_part)
                    elapsed = time.time() - started
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    total = estimated_total or downloaded
                    site._progress_callback(downloaded, total, speed)
    finally:
        site._ffmpeg_proc = None
        if proc.stderr is not None:
            try:
                stderr_tail = proc.stderr.read().decode('utf-8', errors='replace')[-800:]
            except Exception:
                stderr_tail = ''

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
        site._progress_callback(size, size, speed)
    print(f'\n下載完成: {os.path.basename(out)}', flush=True)
    return True


def urlsplit_safe(url):
    try:
        from urllib.parse import urlsplit
        return urlsplit(str(url or '')).netloc or str(url)
    except Exception:
        return str(url)


def _download_parallel_ranges(site, part, referer, start_time):
    session = _get_session()
    probe = None
    try:
        probe = session.get(
            site._direct_url,
            headers={'Referer': referer, 'Range': 'bytes=0-0'},
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
        return None
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
        while written < expected and not site._cancel_job and not stop_event.is_set():
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
                        if site._cancel_job or stop_event.is_set():
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

                if site._cancel_job or stop_event.is_set():
                    break
                if written < expected:
                    detail = '未收到資料' if received == 0 else '連線提前結束'
                    raise Exception(f'直接下載分段{detail}')
            except Exception:
                if site._cancel_job or stop_event.is_set():
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

        if not site._cancel_job and not stop_event.is_set() and written != expected:
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

    if site._cancel_job:
        return done, total
    if done != total:
        raise Exception('直接下載不完整（連線中斷？請重試）')
    return done, total


def _download_serial(site, part, referer, start_time):
    done = os.path.getsize(part) if os.path.exists(part) else 0
    total = 0
    retries = 0
    session = _get_session()
    while not site._cancel_job:
        request_headers = {'Referer': referer}
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
                    if site._cancel_job:
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

            if site._cancel_job:
                break
            if total > 0 and done >= total:
                return done, total
            if total == 0 and received > 0:
                return done, done
            raise Exception('直接下載連線提前結束')
        except Exception:
            if site._cancel_job:
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
