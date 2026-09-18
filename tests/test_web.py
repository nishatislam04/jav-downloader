import json
import os
import threading
from http.client import HTTPConnection

from uav_downloader.web.paths import default_download_dir
from uav_downloader.web.server import WebHandler, ThreadingHTTPServer


def test_default_download_dir_honors_env(tmp_path, monkeypatch):
    target = tmp_path / 'out'
    target.mkdir()
    monkeypatch.setenv('DOWNLOAD_DIR', str(target))
    assert default_download_dir() == str(target.resolve())


def test_health_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request('GET', '/api/health')
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        assert body['ok'] is True
        assert body['download_dir'] == str(tmp_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_resolve_rejects_empty_url(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        payload = json.dumps({'url': ''}).encode('utf-8')
        conn.request(
            'POST',
            '/api/resolve',
            body=payload,
            headers={'Content-Type': 'application/json'},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 422
        assert body['ok'] is False
    finally:
        server.shutdown()
        server.server_close()
