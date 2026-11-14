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
