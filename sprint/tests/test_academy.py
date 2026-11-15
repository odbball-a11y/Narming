import json
import math
import shutil

import numpy as np
import pytest

from ai import academy, evolve, lessons, stable
from ai.brain import DEFAULT_ARCH, n_weights
from sim.track import Track
from sim.world import World


def test_eight_modules_of_four_levels_with_seen_and_unseen_variants():
    assert len(academy.CHALLENGES) == 32
    assert {(c["module"], c["level"]) for c in academy.CHALLENGES} == {(m, l) for m in range(1, 9) for l in range(1, 5)}
    for c in academy.CHALLENGES:
        assert len(c["seen"]) >= 2 and len(c["unseen"]) >= 2 and c["objectives"]
        assert not any(v in c["seen"] for v in c["unseen"])          # unseen really are different
        for v in c["seen"] + c["unseen"]:
            assert v["track"] in academy.TRACKS and v["seconds"] > 0
            assert 0 <= v["slot"] <= len(v["rivals"])


def test_a_driver_never_races_itself():
    for c in academy.challenges_for("zappy-zoe"):
        for v in c["seen"] + c["unseen"]:
            assert not any(r.startswith("house:zappy-zoe") for r in v["rivals"])


def test_a_lesson_start_puts_the_car_in_trouble_and_grip_can_be_lowered():
    world = World(Track.load("speedway"), 1)
    lessons.place(world, 0, {"corner": 1, "heading": 0.4, "slide": 5.0, "yaw": 1.0, "speed": 0.7})
    car = world.cars[0]
    assert abs(world.track.heading_error(car.heading, car.s) - 0.4) < 0.05
    assert car.speed > 10 and car.yaw_rate == 1.0
    lessons.place(world, 0, {"corner": 1, "lateral": "grass"})
    assert world.cars[0].surface == 1
    p = lessons.grip_scaled(None, 0.8)
    assert math.isclose(p.grip, 0.8 * type(p)().grip)


def test_objectives_and_pass_rates():
    m = {"pace": 0.95, "contacts": 3}
    assert academy.meets(m, [("pace", "<=", 1.0), ("contacts", "<=", 2)]) == [True, False]
    assert academy.meets({"pace": None}, [("pace", "<=", 1.0)]) == [False]
    res = {"m1l1": {"seen": [{"passed": True}, {"passed": False}], "unseen": [{"passed": True}, {"passed": True}]}}
    assert academy.pass_rate(res, "seen") == 0.5 and academy.pass_rate(res, "unseen", 1) == 1.0
    assert academy.completed(res, "m1l1")


def test_every_kind_of_challenge_runs_on_the_real_physics():
    w = np.random.default_rng(0).normal(0, 0.3, n_weights(DEFAULT_ARCH))
    for cid in ("m1l1", "m3l2", "m4l3", "m5l2", "m6l4", "m7l1", "m8l2"):
        v = dict(academy.BY_ID[cid]["unseen"][0], seconds=4.0)
        m = academy.run_variant(w, DEFAULT_ARCH, None, v)
        assert m["field"] == len(v["rivals"]) + 1 and 0 <= m["offtrack"] <= 1


def test_lessons_become_training_races():
    config = {"seed": 2, "tracks": ["oval"], "races_per_track": 12, "partners": [{"kind": "file"}] * 4,
              "car": None, "academy": True, "academy_driver": "careful-keith",
              "academy_partners": ["zappy-zoe", "dangerous-dave", "zoe-bold", "clinical-clara"],
              "academy_generations": 10}
    scenarios = evolve.make_scenarios(config, 5, 1, list(range(1, 5)))
    lessons_ = [s for s in scenarios if s.get("lesson")]
    assert lessons_ and all(s["challenge"] in academy.BY_ID for s in lessons_)
    for s in lessons_:
        assert all(not str(r).startswith("house:") for r in s["rivals"])     # house rivals become partners
    solo = next(s for s in lessons_ if s["lesson"] == "solo")
    w = np.random.default_rng(1).normal(0, 0.3, (2, n_weights(DEFAULT_ARCH)))
    out = evolve.test_race(w, DEFAULT_ARCH, dict(solo, seconds=3.0))
    assert len(out["offtrack"]) == 2 and len(evolve.lesson_score(out)) == 2


@pytest.fixture
def small_academy(tmp_path, monkeypatch):
    monkeypatch.setattr(academy, "ACADEMY_DIR", tmp_path / "academy")
    monkeypatch.setattr(academy, "REPORT_DIR", tmp_path / "report")
    few = [dict(c, seen=[dict(v, seconds=6.0) for v in c["seen"]], unseen=[dict(v, seconds=6.0) for v in c["unseen"]])
           for c in academy.CHALLENGES if c["id"] in ("m1l1", "m3l1", "m6l1")]
    monkeypatch.setattr(academy, "CHALLENGES", few)
    monkeypatch.setattr(academy, "RACE_PANEL_TRACKS", ["oval"])
    monkeypatch.setattr(academy, "RACE_PANEL_PER_TRACK", 1)
    return tmp_path


def test_the_whole_course_runs_keeps_the_original_and_writes_a_report(small_academy, monkeypatch):
    rivals = small_academy / "rivals"
    shutil.copytree(stable.RIVALS_DIR, rivals)
    monkeypatch.setattr(stable, "RIVALS_DIR", rivals)
    before = (rivals / "careful-keith.npz").read_bytes()
    result = academy.run("Careful Keith", generations=2, population=4, workers=1, log=lambda m: None)
    d = academy.folder("careful-keith")
    for name in ("original.npz", "before.json", "selected.json", "after.json", "races.json"):
        assert (d / name).exists(), name
    assert (rivals / "careful-keith.npz").read_bytes() == before          # the original is untouched
    assert 0.0 <= result["before"] <= 1.0 and 0.0 <= result["after"] <= 1.0
    races = json.loads((d / "races.json").read_text())
    assert {"Original", "Candidate"} <= set(races)
    text = (small_academy / "report" / "careful-keith.md").read_text()
    for part in ("## Summary", "## By module", "## Challenges", "## Skill measures", "## Race performance",
                 "## Assessment", "Overall assessment"):
        assert part in text
    assert "Careful Keith" in (small_academy / "report" / "README.md").read_text()
    # Promoting is a separate, deliberate step; the old brain is kept.
    academy.promote("Careful Keith")
    assert (rivals / "careful-keith.npz").read_bytes() != before
    assert list((rivals / "old").glob("careful-keith-*.npz"))
    assert json.loads((rivals / "careful-keith.json").read_text())["academy"]["gen"] in (1, 2)


def test_repeats_differ_and_margins_say_what_is_noise():
    spec = academy.driver_spec("Zappy Zoe")
    for cid in ("m3l2", "m6l3", "m1l2"):
        v = academy.BY_ID[cid]["unseen"][0]
        a = academy.run_variant(spec["weights"], spec["arch"], spec["traits"], dict(v, seconds=8.0), rep=0)
        b = academy.run_variant(spec["weights"], spec["arch"], spec["traits"], dict(v, seconds=8.0), rep=1)
        assert a != b, cid                                           # a repeat is a different run
    res = {"m1l1": {"unseen": [{"passed": 2 / 3, "runs": [True, True, False]},
                               {"passed": 1.0, "runs": [True, True, True]}]}}
    assert academy.pass_rate(res, "unseen") == 5 / 6 and academy.completed(res, "m1l1")
    assert 0 < academy.margin(res, "unseen") < 0.3
    worse = {"m1l1": {"unseen": [{"passed": 0.0, "runs": [False] * 3}] * 2}}
    assert "real" in academy.change_text(res, worse) and "noise" in academy.change_text(res, res)
