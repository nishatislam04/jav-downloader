import pytest

from jav_downloader.web import reveal as reveal_mod


def test_reveal_in_file_manager_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        reveal_mod.reveal_in_file_manager(str(tmp_path / 'missing.mp4'))


def test_reveal_in_file_manager_uses_xdg_open(monkeypatch, tmp_path):
    target = tmp_path / 'clip.mp4'
    target.write_bytes(b'x')
    launched: list[list[str]] = []

    def fake_which(name):
        return '/usr/bin/xdg-open' if name == 'xdg-open' else None

    def fake_popen(args, **kwargs):
        launched.append(list(args))

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(reveal_mod.shutil, 'which', fake_which)
    monkeypatch.setattr(reveal_mod.subprocess, 'Popen', fake_popen)

    reveal_mod.reveal_in_file_manager(str(target))
    assert launched == [['/usr/bin/xdg-open', str(tmp_path)]]
