"""Map job log lines to user-facing progress phase labels."""

from __future__ import annotations

import re

_LOG_STAMP_RE = re.compile(r'^\[[^\]]+\]\s*')


def _strip_log_stamp(message: str) -> str:
    return _LOG_STAMP_RE.sub('', str(message or '')).strip()


def phase_from_log(message: str) -> tuple[str, str] | None:
    """Return (phase, detail) when message describes a known activity."""
    text = _strip_log_stamp(message)
    if not text:
        return None

    lower = text.lower()
    if lower.startswith('segments temp dir:'):
        return 'Segments folder ready', text.split(':', 1)[-1].strip()
    if lower.startswith('clip staging folder:'):
        return 'Clip staging ready', text.split(':', 1)[-1].strip()
    if lower.startswith('removing segment temp dir'):
        return 'Cleaning up', 'segment temp dir'
    if lower.startswith('removing merge staging folder'):
        return 'Cleaning up', 'merge staging'
    if lower.startswith('fetching thumbnail'):
        return 'Fetching thumbnail', ''
    if lower.startswith('reusing ') and 'already-downloaded segments' in lower:
        match = re.search(r'reusing\s+(\d+)', lower)
        count = match.group(1) if match else ''
        return 'Reusing segments', count
    match = re.match(r'retrying round\s+(\d+)\s+·\s+(\d+) segments left', lower)
    if match:
        return 'Retrying', f'Round {match.group(1)} · {match.group(2)} left'
    if lower.startswith('saving as '):
        return 'Saving', text.split('Saving as ', 1)[-1].strip()
    if lower.startswith('preparing download'):
        return 'Preparing', ''
    if lower.startswith('using stream mirror:'):
        mirror = text.split(':', 1)[-1].strip()
        return 'Stream mirror', mirror
    if lower.startswith('hls source:'):
        return 'Source ready', 'HLS'
    if lower.startswith('direct mp4 source'):
        return 'Source ready', 'Direct MP4'
    if lower.startswith('starting transfer'):
        return 'Transfer', ''
    if lower.startswith('loading hls playlist for clip'):
        match = re.search(r'clip\s+(\d+)', lower)
        clip = match.group(1) if match else ''
        return 'Loading playlist', f'Clip {clip}' if clip else ''
    if lower.startswith('loading hls playlist'):
        return 'Loading playlist', ''
    match = re.match(r'clip\s+(\d+):\s+found\s+(\d+)\s+segments', lower)
    if match:
        return 'Segments found', f'Clip {match.group(1)} · {match.group(2)}'
    if lower.startswith('found ') and 'segment' in lower:
        match = re.search(r'(\d+)\s+segments', lower)
        count = match.group(1) if match else ''
        return 'Segments found', count
    match = re.match(r'clip\s+(\d+):\s+downloading segments', lower)
    if match:
        return 'Downloading', f'Clip {match.group(1)} · segments'
    if lower.startswith('downloading segments'):
        return 'Downloading', 'segments'
    match = re.match(r'clip\s+(\d+):\s+merging segments', lower)
    if match:
        return 'Merging', f'Clip {match.group(1)}'
    if lower.startswith('merging segments'):
        return 'Merging', 'segments'
    if lower.startswith('encoding'):
        detail = text.split('…', 1)[-1].strip() if '…' in text else text[8:].strip()
        return 'Encoding', detail
    if lower.startswith('complete:'):
        return 'Complete', ''
    if 'resolving next mirror' in lower:
        return 'Stream mirror', 'Trying next'
    if lower.startswith('trying next stream mirror'):
        return 'Stream mirror', 'Trying next'
    return None
