"""Persistent UI preferences in the same app-data SQLite DB as history."""

from __future__ import annotations

import json
import os
import sqlite3
import threading

from jav_downloader.web.history_store import history_db_path

_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
"""

_DEFAULT_AUDIO = {
    "fade": False,
    "loudnorm": False,
    "mute": False,
    "bitrate": 128,
    "volume": 1,
}

_DEFAULT_ENCODE = {
    "enabled": False,
    "codec": "h264",
    "crf": 23,
    "maxHeight": 0,
    "outputMode": "replace",
    "preset": "auto",
    "threads": 0,
    "advancedEnabled": False,
    "engine": "auto",
    "hardwareBitrateMode": "auto",
    "hardwareBitrateKbps": 0,
    "hardwareGop": 0,
    "smallFile": False,
}

_DEFAULTS: dict[str, object] = {
    "hide_thumbnails": False,
    "history_group_by_url": False,
    "remember_save_path": False,
    "save_path": "",
    "remember_audio": False,
    "audio_settings": dict(_DEFAULT_AUDIO),
    "remember_encode": False,
    "encode_settings": dict(_DEFAULT_ENCODE),
}

_BOOL_KEYS = frozenset({
    "hide_thumbnails",
    "history_group_by_url",
    "remember_save_path",
    "remember_audio",
    "remember_encode",
})

_DICT_KEYS = frozenset({
    "audio_settings",
    "encode_settings",
})

_STR_KEYS = frozenset({"save_path"})

_KNOWN_KEYS = frozenset(_DEFAULTS)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off", ""):
            return False
    return bool(value)


def _coerce_dict(value: object, fallback: dict) -> dict:
    if isinstance(value, dict):
        return value
    return dict(fallback)


class SettingsStore:
    def __init__(self, appdata: str | os.PathLike | None = None) -> None:
        self._path = history_db_path(appdata)
        self._lock = threading.Lock()
        self._init_db()

    @property
    def path(self) -> str:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SETTINGS_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def _normalize_out(self, out: dict[str, object]) -> dict[str, object]:
        for key in _BOOL_KEYS:
            out[key] = _coerce_bool(out.get(key))
        out["save_path"] = str(out.get("save_path") or "")
        out["audio_settings"] = _coerce_dict(
            out.get("audio_settings"), _DEFAULT_AUDIO)
        out["encode_settings"] = _coerce_dict(
            out.get("encode_settings"), _DEFAULT_ENCODE)
        return out

    def get_all(self) -> dict[str, object]:
        out = dict(_DEFAULTS)
        out["audio_settings"] = dict(_DEFAULT_AUDIO)
        out["encode_settings"] = dict(_DEFAULT_ENCODE)
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            finally:
                conn.close()
        for key, raw in rows:
            if key not in _KNOWN_KEYS:
                continue
            try:
                out[key] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
        return self._normalize_out(out)

    def update(self, patch: dict[str, object]) -> dict[str, object]:
        if not patch:
            return self.get_all()
        with self._lock:
            conn = self._connect()
            try:
                for key, value in patch.items():
                    if key not in _KNOWN_KEYS:
                        continue
                    if key in _BOOL_KEYS:
                        value = _coerce_bool(value)
                    elif key in _STR_KEYS:
                        value = str(value or "").strip()
                    elif key in _DICT_KEYS:
                        if not isinstance(value, dict):
                            continue
                    conn.execute(
                        "INSERT INTO app_settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, json.dumps(value)),
                    )
                conn.commit()
            finally:
                conn.close()
        return self.get_all()
