import os

import pytest

from ai import evolve, trackschool


@pytest.fixture
def school(tmp_path, monkeypatch):
    monkeypatch.setattr(trackschool, "DIR", tmp_path / "trackschool")
    monkeypatch.setattr(trackschool, "POPULATION", 6)
    monkeypatch.setattr(trackschool, "ELITES", 2)
    option = next(o for o in trackschool.options(None) if o["key"].startswith("house:"))
    return trackschool.start(option, "oval")


def test_a_practice_copy_trains_for_speed_on_one_track_only(school):
    trackschool.train(school, generations=2)
    run = trackschool.run_path(school)
    assert evolve.list_generations(run) == [1, 2]
    history = evolve.load_history(run)
    assert all(h["mode"] == "solo" for h in history)              # never racing school
    assert list(history[-1]["exam"]) == ["oval"]
    assert trackschool.meta(school)["track"] == "oval"


def test_training_stops_when_nobody_is_watching(school):
    trackschool.touch(school)
    alive = school / "alive"
    os.utime(alive, (0, 0))                                         # last touched long ago
    with pytest.raises(trackschool.Stopped):
        trackschool.train(school, generations=5)
    assert evolve.list_generations(trackschool.run_path(school)) == [1]


def test_a_session_carries_on_and_can_become_the_house_car(tmp_path, monkeypatch):
    import json
    import shutil
    from ai import stable
    rivals = tmp_path / "rivals"
    shutil.copytree(stable.RIVALS_DIR, rivals)
    monkeypatch.setattr(stable, "RIVALS_DIR", rivals)
    monkeypatch.setattr(stable, "STABLE_DIR", tmp_path / "stable")
    monkeypatch.setattr(trackschool, "DIR", tmp_path / "trackschool")
    monkeypatch.setattr(trackschool, "POPULATION", 6)
    monkeypatch.setattr(trackschool, "ELITES", 2)
    dave = next(o for o in trackschool.options(None) if o["key"] == "house:dangerous-dave")
    school = trackschool.start(dave, "oval")
    trackschool.train(school, generations=2)
    assert trackschool.existing(dave, "oval") == 2
    assert trackschool.start(dave, "oval") == school                # carries on, nothing lost
    trackschool.train(school, generations=1)
    assert evolve.list_generations(trackschool.run_path(school)) == [1, 2, 3]
    best = trackschool.best_generation(school)
    before = (rivals / "dangerous-dave.npz").read_bytes()
    done = trackschool.save_to_house(school, gen=best["gen"] if best else 3)
    assert (rivals / "dangerous-dave.npz").read_bytes() != before
    assert list((rivals / "old").glob("dangerous-dave-*.npz"))       # the old Dave is kept
    card = json.loads((rivals / "dangerous-dave.json").read_text())
    assert card["name"] == "Dangerous Dave" and card["track_school"][-1]["track"] == "oval"
    assert [c["id"] for c in stable.house_rivals()].count("dangerous-dave") == 1   # still one Dave
    driver = stable.house_driver("dangerous-dave")
    assert driver.label == "Dangerous Dave" and done["gen"] in (1, 2, 3)
    assert trackschool.start(dave, "oval", fresh=True) == school
    assert trackschool.existing(dave, "oval") is None                # a fresh start wipes the old session
