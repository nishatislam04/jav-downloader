from pathlib import Path

import pytest

from jav_downloader.web import reveal as reveal_mod


def test_reveal_in_file_manager_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        reveal_mod.reveal_in_file_manager(str(tmp_path / "missing.mp4"))


def test_reveal_in_file_manager_uses_xdg_open(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []

    def fake_which(name, path=None):
        return "/usr/bin/xdg-open" if name == "xdg-open" else None

    def fake_run(cmd, **kwargs):
        launched.append(list(cmd))

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: False)
    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched == [["/usr/bin/xdg-open", str(tmp_path)]]


def test_reveal_in_file_manager_uses_termux_open_on_android(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []
    binary = "/data/data/com.termux/files/usr/bin/termux-open"

    def fake_which(name, path=None):
        return binary if name == "termux-open" else None

    def fake_run(cmd, **kwargs):
        launched.append(list(cmd))

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(
        reveal_mod,
        "_termux_open_binary",
        lambda: binary,
    )

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched[0] == [binary, str(target.resolve())]


def test_reveal_in_file_manager_android_without_termux_open(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", lambda name, path=None: None)
    monkeypatch.setattr(reveal_mod.os.path, "isfile", lambda _p: False)

    with pytest.raises(ValueError, match="termux-open"):
        reveal_mod.reveal_in_file_manager(str(target))


def test_reveal_ignores_termux_open_outside_termux(monkeypatch, tmp_path):
    """Desktop linux must skip the termux branch."""
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: False)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")

    def fake_which(name, path=None):
        return "/usr/bin/xdg-open" if name == "xdg-open" else None

    def fake_run(cmd, **kwargs):
        launched.append(list(cmd))

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched == [["/usr/bin/xdg-open", str(tmp_path)]]


def test_reveal_termux_open_retries_with_chooser(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []
    binary = "/usr/bin/termux-open"

    def fake_which(name, path=None):
        return binary if name == "termux-open" else None

    def fake_run(cmd, **kwargs):
        launched.append(list(cmd))

        class _Result:
            returncode = 1 if len(launched) < 3 else 0
            stdout = ""
            stderr = "failed"

        return _Result()

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(reveal_mod, "_termux_open_binary", lambda: binary)

    reveal_mod.reveal_in_file_manager(str(target))
    assert any("--chooser" in cmd for cmd in launched)


def test_reveal_am_fallback_for_shared_storage(monkeypatch, tmp_path):
    from pathlib import Path

    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    shared = Path("/storage/emulated/0/Download/clip.mp4")
    am_calls: list[tuple[Path, str]] = []

    def fake_run(cmd, **kwargs):
        class _Result:
            returncode = 127
            stdout = ""
            stderr = "not found"

        return _Result()

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod, "_termux_open_binary", lambda: "/usr/bin/termux-open")
    monkeypatch.setattr(reveal_mod.os.path, "isfile", lambda _p: True)
    monkeypatch.setattr(reveal_mod, "_android_open_paths", lambda _target: [shared])
    monkeypatch.setattr(reveal_mod.Path, "is_file", lambda self: True)
    monkeypatch.setattr(
        reveal_mod,
        "_am_view",
        lambda path, mime: am_calls.append((path, mime)),
    )
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)

    reveal_mod.reveal_in_file_manager(str(target))
    assert am_calls
    assert am_calls[0][1] == "video/mp4"


def test_is_termux_like_detects_prefix(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    assert reveal_mod.is_termux_like() is True


def test_reveal_mode_on_termux(monkeypatch):
    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    assert reveal_mod.reveal_mode() == "open_file"


def test_android_open_paths_maps_shared_download_to_termux_home(monkeypatch):
    monkeypatch.setenv("HOME", "/data/data/com.termux/files/home")
    target = Path("/storage/emulated/0/Download/clip.mp4")
    paths = reveal_mod._android_open_paths(target)
    assert paths[0] == target.resolve()
    assert Path("/data/data/com.termux/files/home/storage/downloads/clip.mp4") in paths


def test_reveal_mode_on_desktop(monkeypatch):
    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: False)
    assert reveal_mod.reveal_mode() == "show_in_folder"
