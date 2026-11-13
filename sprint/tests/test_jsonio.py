from pathlib import Path

import pytest

from ai import jsonio


def test_a_briefly_locked_file_is_read_and_replaced_after_a_retry(tmp_path, monkeypatch):
    target = tmp_path / "racer.json"
    jsonio.write_json(target, {"name": "Zoe"})
    real_read, real_replace = Path.read_text, Path.replace
    fails = {"read": 2, "replace": 2}

    def flaky_read(self, *a, **k):
        if fails["read"]:
            fails["read"] -= 1
            raise PermissionError("locked")           # what Windows says while the other process saves it
        return real_read(self, *a, **k)

    def flaky_replace(self, other):
        if fails["replace"]:
            fails["replace"] -= 1
            raise PermissionError("locked")
        return real_replace(self, other)

    monkeypatch.setattr(jsonio, "PAUSE", 0.0)
    monkeypatch.setattr(Path, "read_text", flaky_read)
    monkeypatch.setattr(Path, "replace", flaky_replace)
    assert jsonio.read_json(target) == {"name": "Zoe"}
    jsonio.write_json(target, {"name": "Ann"})
    assert jsonio.read_json(target) == {"name": "Ann"}


def test_a_file_that_stays_locked_still_fails(tmp_path, monkeypatch):
    target = tmp_path / "x.json"
    jsonio.write_json(target, {})
    monkeypatch.setattr(jsonio, "PAUSE", 0.0)
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("locked")))
    with pytest.raises(PermissionError):
        jsonio.read_json(target)
