import pytest

from jav_downloader.web import reveal as reveal_mod


def test_reveal_in_file_manager_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        reveal_mod.reveal_in_file_manager(str(tmp_path / "missing.mp4"))


def test_reveal_in_file_manager_uses_xdg_open(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []

    def fake_which(name):
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

    def fake_which(name):
        return (
            "/data/data/com.termux/files/usr/bin/termux-open"
            if name == "termux-open"
            else None
        )

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

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched[0][:4] == [
        "/data/data/com.termux/files/usr/bin/termux-open",
        "--view",
        "--content-type",
        "video/mp4",
    ]
    assert launched[0][-1] == str(target.resolve())


def test_reveal_in_file_manager_android_without_termux_open(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", lambda name: None)

    with pytest.raises(ValueError, match="termux-open"):
        reveal_mod.reveal_in_file_manager(str(target))


def test_reveal_ignores_termux_open_outside_termux(monkeypatch, tmp_path):
    """Desktop linux must skip the termux branch."""
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: False)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")

    def fake_which(name):
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

    def fake_which(name):
        return "/usr/bin/termux-open" if name == "termux-open" else None

    def fake_run(cmd, **kwargs):
        launched.append(list(cmd))

        class _Result:
            returncode = 1 if "--chooser" not in cmd else 0
            stdout = ""
            stderr = "failed"

        return _Result()

    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "run", fake_run)

    reveal_mod.reveal_in_file_manager(str(target))
    assert any("--chooser" in cmd for cmd in launched)


def test_is_termux_like_detects_prefix(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    assert reveal_mod.is_termux_like() is True


def test_reveal_mode_on_termux(monkeypatch):
    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: True)
    assert reveal_mod.reveal_mode() == "open_file"


def test_reveal_mode_on_desktop(monkeypatch):
    monkeypatch.setattr(reveal_mod, "is_termux_like", lambda: False)
    assert reveal_mod.reveal_mode() == "show_in_folder"
