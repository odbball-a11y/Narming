import json

import numpy as np
import pytest

from ai import snapshot


def make_stable(root):
    run = root / "zoe" / "v1"
    run.mkdir(parents=True)
    (root / "zoe" / "racer.json").write_text(json.dumps({"name": "Zoe", "file": "dynasty/stable/zoe/v1/gen_0002.npz"}))
    (root / "ratings.json").write_text("{}")
    (run / "history.json").write_text("[]")
    for g in (1, 2):
        np.savez_compressed(run / f"gen_{g:04d}.npz", pop=np.arange(80 * 5, dtype=np.float32).reshape(80, 5),
                            fitness=np.arange(80, dtype=np.float32))
    (root / "zoe" / "train.log").write_text("noise")


def test_save_then_load_round_trips_and_keeps_the_old_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "PROJECT", tmp_path)
    root = tmp_path / "dynasty" / "stable"
    make_stable(root)
    out = snapshot.save("demo", root, out_dir=tmp_path / "saves")
    target = tmp_path / "stable"
    target.mkdir()
    (target / "mine.txt").write_text("my own game")
    snapshot.load("demo", target, save_dir=tmp_path / "saves")
    assert (tmp_path / "stable.before-demo" / "mine.txt").exists()            # nothing is lost
    assert (target / "ratings.json").exists() and not (target / "zoe" / "train.log").exists()
    with np.load(target / "zoe" / "v1" / "gen_0001.npz") as old, np.load(target / "zoe" / "v1" / "gen_0002.npz") as last:
        assert len(old["pop"]) == snapshot.STUB_ROWS and len(last["pop"]) == 80      # last generation stays whole
    assert "stable/zoe/v1/gen_0002.npz" in (target / "zoe" / "racer.json").read_text()   # stored paths follow
    assert snapshot.names(tmp_path / "saves") == ["demo"] and out.exists()


def test_loading_a_missing_save_says_so(tmp_path):
    with pytest.raises(FileNotFoundError):
        snapshot.load("nope", tmp_path / "stable", save_dir=tmp_path)
