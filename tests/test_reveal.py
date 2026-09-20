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

    def fake_popen(args, **kwargs):
        launched.append(list(args))

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "Popen", fake_popen)

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

    def fake_popen(args, **kwargs):
        launched.append(list(args))

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(reveal_mod, "sys", type(reveal_mod.sys) and reveal_mod.sys)
    monkeypatch.setattr(
        reveal_mod.os, "environ", {**reveal_mod.os.environ, "TERMUX_VERSION": "0.118"}
    )
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "Popen", fake_popen)

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched == [
        ["/data/data/com.termux/files/usr/bin/termux-open", str(target)],
    ]


def test_reveal_in_file_manager_android_without_termux_open(monkeypatch, tmp_path):
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")

    monkeypatch.setattr(
        reveal_mod.os, "environ", {**reveal_mod.os.environ, "TERMUX_VERSION": "0.118"}
    )
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")
    monkeypatch.setattr(reveal_mod.shutil, "which", lambda name: None)

    with pytest.raises(ValueError, match="termux-open"):
        reveal_mod.reveal_in_file_manager(str(target))


def test_reveal_ignores_termux_open_outside_termux(monkeypatch, tmp_path):
    """Desktop linux with TERMUX_VERSION unset must skip the termux branch."""
    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    launched: list[list[str]] = []

    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setattr(reveal_mod.sys, "platform", "linux")

    def fake_which(name):
        return "/usr/bin/xdg-open" if name == "xdg-open" else None

    def fake_popen(args, **kwargs):
        launched.append(list(args))

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(reveal_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, "Popen", fake_popen)

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched == [["/usr/bin/xdg-open", str(tmp_path)]]
