import json

import numpy as np
import pytest

from ai import academy, curriculum, evolve, stable

CTX = {"laps": dict(stable.SCRIPTED_LAPS), "scripted": dict(stable.SCRIPTED_LAPS)}


def test_every_skill_is_a_ladder_and_racecraft_has_ten_stages():
    assert list(curriculum.CURRICULUM) == ["control", "grip", "recovery", "adverse", "racecraft"]
    assert len(curriculum.CURRICULUM["racecraft"]) == 10
    for sid in curriculum.BY_ID:
        v = curriculum.variant(sid, np.random.default_rng(1), 0.0, CTX)
        assert v["track"] in academy.TRACKS and curriculum.objectives(sid)
        assert len(curriculum.objectives(sid, 1.0)) == len(curriculum.objectives(sid))
    draws = {json.dumps(curriculum.variant("racecraft-8", np.random.default_rng(k), 0.0, CTX), sort_keys=True)
             for k in range(6)}
    assert len(draws) > 1                                                   # randomised


def test_rivals_are_set_from_the_learners_own_pace_and_repeatable():
    rel = lambda ctx, sid, k=3: curriculum.variant(sid, np.random.default_rng(k), 0.0, ctx)
    lap = lambda v: float(np.interp(float(v["rivals"][0].split(":")[1]), curriculum.PACE_GRID,
                                    curriculum.traffic_laps(v["track"])))
    for laps in (dict(stable.SCRIPTED_LAPS), {t: x * 1.1 for t, x in stable.SCRIPTED_LAPS.items()}):
        ctx = {"laps": laps, "scripted": laps}
        follow, overtake = rel(ctx, "racecraft-2"), rel(ctx, "racecraft-3")
        assert laps[follow["track"]] / lap(follow) == pytest.approx(curriculum.FOLLOW_PACE, abs=0.03)
        assert laps[overtake["track"]] / lap(overtake) == pytest.approx(curriculum.PASS_PACE, abs=0.03)
        assert rel(ctx, "racecraft-4") == rel(ctx, "racecraft-4")             # same baseline + seed, same rivals
    # easing stage 2 never slows the car ahead: it only relaxes the marks
    ctx = {"laps": dict(stable.SCRIPTED_LAPS)}
    assert rel(ctx, "racecraft-2") == curriculum.variant("racecraft-2", np.random.default_rng(3), 1.0, ctx)
    assert {m for m, _, _ in curriculum.objectives("racecraft-2")} == {"corner_tail", "contacts", "close", "max_gap_s"}


def test_pace_targets_compare_with_the_scripted_driver_in_the_same_car():
    m = curriculum.derived({"pace": 1.0}, "oval", {"scripted": {"oval": stable.SCRIPTED_LAPS["oval"] * 1.1}})
    assert m["pace"] == pytest.approx(1 / 1.1, abs=1e-3)                    # a slower car is judged against its own scripted lap
    heavy = {"top_speed": 1, "accel": 1, "handling": 5, "braking": 5, "weight": "heavy"}
    assert curriculum.scripted_lap("oval", heavy) != curriculum.scripted_lap("oval", None)


def test_placement_starts_each_skill_at_its_first_failed_stage():
    state = curriculum.fresh_state({"id": "x", "name": "X"})
    before = {sid: {"pass": 1.0} for sid in curriculum.BY_ID}
    before["control-3"]["pass"] = 0.0
    before["racecraft-1"]["pass"] = 0.0
    before["control-4"]["pass"] = 0.0
    curriculum.place(state, before)
    assert state["skills"]["control"]["stage"] == "control-3"
    assert state["skills"]["racecraft"]["stage"] == "racecraft-1"
    assert state["skills"]["grip"]["stage"] is None                       # everything shown on entry
    assert "control-2" in state["entry"] and "control-4" not in state["entry"]
    assert not state["mastered"]                                          # passed on entry is not mastered
    assert curriculum.status_of(state, "control-1") == "Passed on entry"


def test_progress_easing_and_stalled_stages_move_on_but_are_never_mastered():
    state = curriculum.fresh_state({"id": "x", "name": "X"})
    adv = lambda rate: curriculum._advance(state, "racecraft", state["skills"]["racecraft"]["stage"], rate)
    assert adv(0.2) == "failed; repeat"
    assert adv(0.2) == "failed; made easier"
    assert adv(0.9).startswith("passed (easier)")
    assert state["skills"]["racecraft"]["stage"] == "racecraft-1"
    assert adv(0.9) == "mastered" and state["skills"]["racecraft"]["stage"] == "racecraft-2"
    results = [adv(0.0) for _ in range(20)]
    assert "stalled; moved on (not mastered)" in results
    assert "racecraft-2" in state["stalled"] and "racecraft-2" not in state["mastered"]
    assert state["skills"]["racecraft"]["stage"] not in ("racecraft-1", "racecraft-2")
    assert curriculum.status_of(state, "racecraft-2").startswith("Stalled")


def test_weights_favour_weak_skills_with_a_cap_and_remedial_lessons(tmp_path):
    state = curriculum.fresh_state({"id": "careful-keith", "name": "Careful Keith"})
    before = {sid: {"pass": 1.0 if not sid.startswith(("racecraft", "grip")) else 0.0} for sid in curriculum.BY_ID}
    before["control-4"]["pass"] = 0.0
    curriculum.place(state, before)
    w = curriculum.skill_weights(state)
    assert set(w) == {"control", "grip", "racecraft"} and max(w.values()) <= curriculum.WEIGHT_CAP + 1e-6
    assert w["racecraft"] >= w["grip"] > w["control"]                    # weak skills and racecraft get more
    state["stalled"] = ["recovery-4"]
    state["weights"] = w
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(dict(state, ctx=CTX)))
    config = {"academy_curriculum": str(path), "academy_driver": "careful-keith", "academy_partners": [], "car": None}
    got = [curriculum.lesson(config, np.random.default_rng(k))["challenge"] for k in range(400)]
    remedial = got.count("recovery-4") / len(got)
    assert 0.17 < remedial < 0.33                                         # about one in four
    from ai.brain import DEFAULT_ARCH, n_weights
    craft = next(x for x in (curriculum.lesson(config, np.random.default_rng(k)) for k in range(80)) if x["lesson"] == "craft")
    out = evolve.test_race(np.random.default_rng(1).normal(0, 0.3, (2, n_weights(DEFAULT_ARCH))), DEFAULT_ARCH,
                           dict(craft, seconds=3.0))
    assert {"close", "corner_tail", "weaves"} <= set(out) and len(evolve.craft_score(out, None, craft["extra"])) == 2


def test_head_to_head_counts_only_shared_races():
    races = [{"track": "oval", "results": [{"key": "a", "place": 1}, {"key": "b", "place": 3}]}] * 12
    races += [{"track": "oval", "results": [{"key": "a", "place": 2}, {"key": "c", "place": 1}]}]
    h = curriculum.head_to_head(races, "a", "b")
    assert h["races"] == 12 and h["ahead"] == 12 and h["mean"] == 2 and h["real"]
    assert curriculum.head_to_head(races, "b", "c")["races"] == 0


def test_the_adaptive_course_places_trains_benchmarks_and_reports(tmp_path, monkeypatch):
    from ai import migrate
    if migrate.ensure():
        pytest.skip("the house files were upgraded just now: run again")
    monkeypatch.setattr(academy, "ACADEMY_DIR", tmp_path / "academy")
    monkeypatch.setattr(academy, "REPORT_DIR", tmp_path / "report")
    for k in ("CHECK_RUNS", "REVIEW_RUNS", "PROFILE_RUNS"):
        monkeypatch.setattr(curriculum, k, 1)
    monkeypatch.setattr(curriculum, "ALL_TRACKS", ["oval", "speedway"])
    import league
    monkeypatch.setattr(league, "drivers", lambda: {"house:zappy-zoe": {"name": "Zappy Zoe", "status": "house rival"},
                                                    "house:careful-keith": {"name": "Careful Keith", "status": "x"}})
    before = (stable.RIVALS_DIR / "careful-keith.npz").read_bytes()
    state = curriculum.course("Careful Keith", generations=2, population=4, workers=1, log=lambda m: None, block=1)
    assert state["ctx"]["laps"] and state["before"] and state["after"] and len(state["log"]) == 2
    assert all(s["stage"] is None or s["stage"] not in state["entry"] for s in state["skills"].values())
    out = curriculum.benchmark("careful-keith", rounds=1, laps=1, workers=1, log=lambda m: None, per_track=1)
    assert len(out["panel"]) == 2 and {"original", "new candidate"} <= set(out["keys"])
    assert all(len(r["results"]) == len(out["keys"]) + 3 for r in out["panel"])
    text = curriculum.report("careful-keith").read_text()
    for part in ("## Placement", "## A. Has he become more competent?", "## B. Has he become a better racer?",
                 "Fixed-grid benchmark", "Head to head", "## Verdicts", "Not promoted"):
        assert part in text
    assert (stable.RIVALS_DIR / "careful-keith.npz").read_bytes() == before            # the original is untouched
