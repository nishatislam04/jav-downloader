from jav_downloader.web.settings_store import SettingsStore


def test_defaults_when_empty(tmp_path):
    store = SettingsStore(appdata=tmp_path)
    settings = store.get_all()
    assert settings["hide_thumbnails"] is False
    assert settings["history_group_by_url"] is False
    assert settings["remember_encode"] is False
    assert settings["encode_settings"]["codec"] == "h264"


def test_persist_hide_thumbnails(tmp_path):
    store = SettingsStore(appdata=tmp_path)
    store.update({"hide_thumbnails": True})
    again = SettingsStore(appdata=tmp_path)
    assert again.get_all()["hide_thumbnails"] is True


def test_update_ignores_unknown_keys(tmp_path):
    store = SettingsStore(appdata=tmp_path)
    store.update({"hide_thumbnails": True, "other": 1})
    rows_path = store.path
    import sqlite3

    conn = sqlite3.connect(rows_path)
    try:
        keys = {row[0] for row in conn.execute("SELECT key FROM app_settings")}
    finally:
        conn.close()
    assert keys == {"hide_thumbnails"}


def test_coerce_bool_from_string(tmp_path):
    store = SettingsStore(appdata=tmp_path)
    store.update({"hide_thumbnails": "yes"})
    assert store.get_all()["hide_thumbnails"] is True
