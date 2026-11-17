import json

import numpy as np
import pytest

from ai import academy, curriculum, evolve, stable


def test_every_skill_is_a_ladder_and_racecraft_has_ten_stages():
    assert list(curriculum.CURRICULUM) == ["control", "grip", "recovery", "adverse", "racecraft"]
    assert len(curriculum.CURRICULUM["racecraft"]) == 10
    for sid, st in curriculum.BY_ID.items():
        a = curriculum.variant(sid, np.random.default_rng(1))
        b = curriculum.variant(sid, np.random.default_rng(2))
        assert a["track"] in academy.TRACKS and curriculum.objectives(sid)
        easy = curriculum.objectives(sid, 1.0)
        assert len(easy) == len(curriculum.objectives(sid))
    # scenarios are drawn afresh: different seeds give different scenarios
    draws = {json.dumps(curriculum.variant("racecraft-8", np.random.default_rng(k)), sort_keys=True) for k in range(6)}
    assert len(draws) > 1


def test_easing_makes_a_stage_gentler():
    hard = curriculum.variant("racecraft-8", np.random.default_rng(3), 0.0)
    easy = curriculum.variant("racecraft-8", np.random.default_rng(3), 1.0)
    assert len(easy["rivals"]) < len(hard["rivals"])
    pace = lambda v: max(float(r.split(":")[1]) for r in v["rivals"])
    assert pace(easy) < pace(hard)
    rec = curriculum.variant("recovery-4", np.random.default_rng(3), 1.0)["start"]
    assert abs(rec["heading"]) < 0.6


def test_progress_only_on_passing_at_full_difficulty_with_easing_and_stalling():
    state = curriculum.fresh_state({"id": "x", "name": "X"})
    adv = lambda rate: curriculum._advance(state, "racecraft", state["skills"]["racecraft"]["stage"], rate)
    assert adv(0.2) == "failed; repeat"
    assert adv(0.2) == "failed; made easier" and state["skills"]["racecraft"]["ease"] > 0
    assert adv(0.9).startswith("passed (easier)")                 # easier pass: not mastered yet
    assert state["skills"]["racecraft"]["stage"] == "racecraft-1" and state["skills"]["racecraft"]["ease"] == 0
    assert adv(0.9) == "mastered" and state["skills"]["racecraft"]["stage"] == "racecraft-2"
    assert "racecraft-1" in state["mastered"]
    for _ in range(curriculum.STALL - 1):
        adv(0.0)
    assert adv(0.0) == "stalled" and state["skills"]["racecraft"]["stalled"]


def test_lessons_follow_the_state_and_review_mastered_stages(tmp_path):
    state = curriculum.fresh_state({"id": "careful-keith", "name": "Careful Keith"})
    state["mastered"] = ["control-1"]
    state["skills"]["control"]["stage"] = "control-2"
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(state))
    config = {"academy_curriculum": str(path), "academy_driver": "careful-keith",
              "academy_partners": ["zappy-zoe"], "car": None}
    rng = np.random.default_rng(0)
    got = [curriculum.lesson(config, rng)["challenge"] for _ in range(200)]
    current = {s["stage"] for s in state["skills"].values()}
    assert set(got) <= current | {"control-1"} and "control-1" in got        # review happens
    assert sum(g.startswith("racecraft") for g in got) > sum(g.startswith("grip") for g in got)  # racecraft weighted up
    from ai.brain import DEFAULT_ARCH, n_weights
    craft = next(x for x in (curriculum.lesson(config, np.random.default_rng(k)) for k in range(50))
                 if x["lesson"] == "craft")
    w = np.random.default_rng(1).normal(0, 0.3, (2, n_weights(DEFAULT_ARCH)))
    out = evolve.test_race(w, DEFAULT_ARCH, dict(craft, seconds=3.0))
    assert {"close", "tailgate", "weaves"} <= set(out) and len(evolve.craft_score(out, None, craft["extra"])) == 2


def test_the_whole_curriculum_course_trains_tests_benchmarks_and_reports(tmp_path, monkeypatch):
    from ai import migrate
    if migrate.ensure():
        pytest.skip("the house files were upgraded just now: run again")
    monkeypatch.setattr(academy, "ACADEMY_DIR", tmp_path / "academy")
    monkeypatch.setattr(academy, "REPORT_DIR", tmp_path / "report")
    monkeypatch.setattr(curriculum, "CHECK_RUNS", 1)
    monkeypatch.setattr(curriculum, "REVIEW_RUNS", 1)
    monkeypatch.setattr(curriculum, "PROFILE_RUNS", 1)
    monkeypatch.setattr(curriculum, "TARGET", 0.0)              # everything passes: the ladder moves
    import league
    monkeypatch.setattr(league, "drivers", lambda: {"house:zappy-zoe": {"name": "Zappy Zoe", "status": "house rival"},
                                                    "house:careful-keith": {"name": "Careful Keith", "status": "x"}})
    before = (stable.RIVALS_DIR / "careful-keith.npz").read_bytes()
    state = curriculum.course("Careful Keith", generations=2, population=4, workers=1, log=lambda m: None, block=1)
    assert state["generations"] == 2 and len(state["log"]) == 2
    assert all(s["stage"] != stages[0]["id"] for s, stages in
               zip(state["skills"].values(), curriculum.CURRICULUM.values()))      # everyone moved up
    assert state["before"] and state["after"] and state["log"][1]["reviews"]      # mastered stages re-tested
    out = curriculum.benchmark("careful-keith", rounds=1, laps=1, workers=1, log=lambda m: None)
    keys = set(out["drivers"])
    assert "house:careful-keith" not in keys and sum(k.startswith("file:") for k in keys) == 2
    text = curriculum.report("careful-keith").read_text()
    for part in ("## Progression", "## Every stage", "## Skills before and after", "## Tournament benchmark", "Verdict"):
        assert part in text
    assert (stable.RIVALS_DIR / "careful-keith.npz").read_bytes() == before            # the original is untouched
