#!/usr/bin/env python
"""Lightweight browser UI for paste-link downloads."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from jav_downloader.web.jobs import JobManager
from jav_downloader.web.paths import default_download_dir, validate_dest_folder
from jav_downloader.web.reveal import reveal_in_file_manager
from jav_downloader.web.thumbnail import fetch_thumbnail
from jav_downloader.web import cleanup, service

STATIC_DIR = Path(__file__).resolve().parent / 'static'
MANAGER = JobManager()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get('Content-Length') or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode('utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'invalid JSON: {exc}') from exc
    return data if isinstance(data, dict) else {}


class WebHandler(BaseHTTPRequestHandler):
    server_version = 'JAV-Web/1.0'

    def log_message(self, fmt: str, *args) -> None:
        print(f"[jav-web] {self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/thumbnail':
            raw_url = unquote(parse_qs(parsed.query).get('url', [''])[0])
            try:
                body, content_type = fetch_thumbnail(raw_url)
            except ValueError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': str(exc),
                })
                return
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.end_headers()
            self.wfile.write(body)
            return

        if path == '/api/health':
            _json_response(self, HTTPStatus.OK, {
                'ok': True,
                'download_dir': default_download_dir(),
            })
            return

        if path == '/api/jobs':
            jobs = [job.to_dict() for job in MANAGER.list_jobs()]
            _json_response(self, HTTPStatus.OK, {'ok': True, 'jobs': jobs})
            return

        if path.startswith('/api/jobs/'):
            job_id = path.rsplit('/', 1)[-1]
            job = MANAGER.get(job_id)
            if job is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {
                    'ok': False,
                    'error': 'Job not found',
                })
                return
            _json_response(self, HTTPStatus.OK, {'ok': True, 'job': job.to_dict()})
            return

        if path in ('/', '/index.html'):
            self._serve_static('index.html')
            return

        rel = path.lstrip('/')
        if rel and not rel.startswith('api/'):
            self._serve_static(rel)
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = _read_json(self)
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {
                'ok': False,
                'error': str(exc),
            })
            return

        dest = payload.get('dest_folder')
        output_title = payload.get('output_title')

        if path == '/api/validate-folder':
            raw_path = payload.get('path') or payload.get('dest_folder') or ''
            try:
                folder = validate_dest_folder(str(raw_path))
            except ValueError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': str(exc),
                })
                return
            _json_response(self, HTTPStatus.OK, {
                'ok': True,
                'path': folder,
            })
            return

        if path == '/api/reveal':
            raw_path = str(payload.get('path') or '').strip()
            if not raw_path:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': 'Path is required',
                })
                return
            try:
                reveal_in_file_manager(raw_path)
            except ValueError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': str(exc),
                })
                return
            _json_response(self, HTTPStatus.OK, {'ok': True})
            return

        if path == '/api/resolve':
            result = service.resolve_url(
                payload.get('url', ''),
                dest_folder=dest,
                cut_start=payload.get('cut_start'),
                cut_end=payload.get('cut_end'),
                cuts=payload.get('cuts'),
                output_title=output_title,
                **service._audio_options_from_mapping(payload),
                **service._encode_options_from_mapping(payload),
            )
            status = HTTPStatus.OK if result.get('ok') else HTTPStatus.UNPROCESSABLE_ENTITY
            _json_response(self, status, result)
            return

        if path == '/api/jobs/cleanup':
            job_id = str(payload.get('job_id') or '').strip()
            if not job_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': 'Job id is required',
                })
                return
            result = cleanup.cleanup_job(MANAGER, job_id)
            status = HTTPStatus.OK if result.get('ok') else HTTPStatus.BAD_REQUEST
            _json_response(self, status, result)
            return

        if path.startswith('/api/jobs/'):
            job_id = path[len('/api/jobs/'):]
            action = None
            for suffix in ('/cancel', '/pause', '/resume'):
                if job_id.endswith(suffix):
                    job_id = job_id[:-len(suffix)]
                    action = suffix[1:]
                    break
            if action:
                if not job_id:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {
                        'ok': False,
                        'error': 'Job id is required',
                    })
                    return
                if action == 'cancel':
                    ok = service.cancel_download(MANAGER, job_id)
                elif action == 'pause':
                    ok = service.pause_download(MANAGER, job_id)
                else:
                    ok = service.resume_download(MANAGER, job_id)
                if not ok:
                    _json_response(self, HTTPStatus.NOT_FOUND, {
                        'ok': False,
                        'error': f'Job not found or cannot {action}',
                    })
                    return
                job = MANAGER.get(job_id)
                _json_response(self, HTTPStatus.OK, {
                    'ok': True,
                    'job': job.to_dict() if job else None,
                })
                return

        if path == '/api/download':
            url = (payload.get('url') or '').strip()
            if not url:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': 'URL is required',
                })
                return
            try:
                validate_dest_folder(dest)
            except ValueError as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    'ok': False,
                    'error': str(exc),
                })
                return
            job = service.start_download(
                MANAGER,
                url,
                dest_folder=dest,
                cut_start=payload.get('cut_start'),
                cut_end=payload.get('cut_end'),
                cuts=payload.get('cuts'),
                output_title=output_title,
                **service._audio_options_from_mapping(payload),
                **service._encode_options_from_mapping(payload),
            )
            _json_response(self, HTTPStatus.ACCEPTED, {
                'ok': True,
                'job': job.to_dict(),
            })
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})

    def _serve_static(self, rel_path: str) -> None:
        rel = Path(rel_path)
        if rel.is_absolute() or '..' in rel.parts:
            _json_response(self, HTTPStatus.FORBIDDEN, {'ok': False, 'error': 'Forbidden'})
            return
        file_path = (STATIC_DIR / rel).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())):
            _json_response(self, HTTPStatus.FORBIDDEN, {'ok': False, 'error': 'Forbidden'})
            return
        if not file_path.is_file():
            _json_response(self, HTTPStatus.NOT_FOUND, {'ok': False, 'error': 'Not found'})
            return

        mime, _ = mimetypes.guess_type(str(file_path))
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='JAV Downloader web UI')
    parser.add_argument(
        '--host',
        default=os.environ.get('JAV_WEB_HOST', '127.0.0.1'),
        help='Bind address (default: 127.0.0.1, use 0.0.0.0 on Termux/LAN)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('JAV_WEB_PORT', '8765')),
        help='HTTP port (default: 8765)',
    )
    args = parser.parse_args(argv)

    download_dir = default_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    # Always advertise localhost; 0.0.0.0 is a bind address, not a URL
    # browsers can open (and it breaks Android WebView loading).
    print(f'JAV Downloader web UI at http://localhost:{args.port}/', flush=True)
    print(f'Listening on: {args.host}:{args.port}', flush=True)
    print(f'Downloads save to: {download_dir}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping web UI.', flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
