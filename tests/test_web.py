import json
import threading
from http.client import HTTPConnection

import pytest

from jav_downloader.web.paths import default_download_dir, validate_dest_folder
from jav_downloader.web.server import WebHandler, ThreadingHTTPServer


def test_default_download_dir_honors_env(tmp_path, monkeypatch):
    target = tmp_path / 'out'
    target.mkdir()
    monkeypatch.setenv('DOWNLOAD_DIR', str(target))
    assert default_download_dir() == str(target.resolve())


def test_validate_dest_folder_requires_existing_writable_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    child = tmp_path / 'videos'
    child.mkdir()
    assert validate_dest_folder(str(child)) == str(child.resolve())


def test_validate_dest_folder_rejects_missing_path(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    with pytest.raises(ValueError):
        validate_dest_folder(str(tmp_path / 'missing'))


def test_encoding_capabilities_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request('GET', '/api/encoding/capabilities')
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        assert body['ok'] is True
        assert 'platform' in body
        assert 'hardware_codecs' in body
        assert 'h264' in body['hardware_codecs']
    finally:
        server.shutdown()
        server.server_close()


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


def test_validate_folder_endpoint(tmp_path, monkeypatch):
    target = tmp_path / 'jav'
    target.mkdir()
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        payload = json.dumps({'path': str(target)}).encode('utf-8')
        conn.request(
            'POST',
            '/api/validate-folder',
            body=payload,
            headers={'Content-Type': 'application/json'},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        assert body['ok'] is True
        assert body['path'] == str(target.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_reveal_endpoint(tmp_path, monkeypatch):
    target = tmp_path / 'clip.mp4'
    target.write_bytes(b'x')
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    called: list[str] = []
    monkeypatch.setattr(
        'jav_downloader.web.server.reveal_in_file_manager',
        lambda path: called.append(path),
    )
    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        payload = json.dumps({'path': str(target)}).encode('utf-8')
        conn.request(
            'POST',
            '/api/reveal',
            body=payload,
            headers={'Content-Type': 'application/json'},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        assert body['ok'] is True
        assert called == [str(target.resolve())]
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


def test_history_list_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_DIR', str(tmp_path))
    from jav_downloader.web import service
    from jav_downloader.web.history_store import HistoryStore
    from jav_downloader.web.jobs import Job, JobStatus

    service._history_store_instance = HistoryStore(appdata=tmp_path / 'appdata')
    store = service._history_store_instance
    store.upsert_job(
        Job(id='h1', url='https://example.test/h', status=JobStatus.COMPLETED),
    )

    server = ThreadingHTTPServer(('127.0.0.1', 0), WebHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(host, port, timeout=5)
        conn.request('GET', '/api/history?limit=10')
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        assert body['ok'] is True
        assert body['entries'][0]['id'] == 'h1'
    finally:
        server.shutdown()
        server.server_close()
        service._history_store_instance = None
