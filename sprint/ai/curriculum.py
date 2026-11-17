"""The Racing Academy's progressive curriculum (an improvement on the fixed
eight-module course in ai/academy.py, using the same physics, tests,
training and candidate brains).

Five skills, each a ladder of stages from slow, forgiving and predictable to
fast, busy and hostile: vehicle control, braking and grip, recovery, adverse
conditions, and racecraft (ten stages, from following a car without contact
to full races).  Every scenario is generated afresh from a seeded random
draw (track, corner, rival pace and style, starting trouble), so a driver
cannot memorise them.

Mastery-based training (`course`): the candidate trains in short blocks on
the stage each skill is at, plus a share of review lessons from stages it
has already mastered.  After each block it is tested on new random scenarios
of each current stage:
- it moves on only when it passes `TARGET` of them at full difficulty;
- after repeated failures the stage is made easier (`ease` 0 = full
  difficulty .. 1 = easiest: slower, fewer or calmer rivals, gentler
  trouble, more grip) and repeated; ease is then stepped back up and the
  stage must be passed at full difficulty to count;
- one mastered stage per skill is re-tested every block; a forgotten stage
  goes back into the review lessons with extra weight until it is passed
  again;
- a skill that fails `STALL` checks in a row on one stage stops there.
Racecraft lessons are scored for judgement, not just speed (evolve.craft_score):
clean passes, catching cars, place, minus contact, tailgating and weaving,
plus each stage's own terms (time spent following, places lost).

Everything is recorded (attempts, pass rates, ease, forgetting) in
academy/<id>-curriculum/curriculum.json.  The benchmark is the all-car
tournament (league.py) with the original and the candidate both entered;
the report is academy_report/<id>-curriculum.md.

    python -m ai.curriculum run "Careful Keith" [--generations 80] [--workers 4] [--rounds 8]
"""
from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import academy, evolve, stable

# Adaptive version (agreed specification): placement from the before-test,
# rivals matched to the learner's own measured lap pace, pace targets against
# the scripted driver in the same car, adaptive skill weights with a cap,
# stalled stages move on (never mastered) with remedial lessons, and a
# fixed-grid + head-to-head benchmark.

TARGET = 0.67          # share of a stage's check scenarios passed to master it
CHECK_RUNS = 6         # fresh random scenarios per check
REVIEW_RUNS = 3        # scenarios when re-testing a mastered stage
FORGOT = 0.34          # a mastered stage re-tested below this is forgotten
EASE_AFTER = 2         # failed checks in a row before the stage is made easier
EASE_STEP = 0.34
STALL_AT_EASIEST = 4   # failed checks in a row at the easiest setting -> stalled
STALL_ATTEMPTS = 12    # or this many checks on one stage in all -> stalled
REMEDIAL_SHARE = 0.25  # one remedial lesson (stalled stages) for every three normal ones
WEIGHT_CAP = 0.4       # no skill gets more than this share of the normal lessons
RACECRAFT_EMPHASIS = 1.5
FOLLOW_PACE = 0.95     # following: the car ahead at 95% of the learner's pace (5% slower)
PASS_PACE = 0.85       # overtaking: cars ahead at 85% of the learner's pace (15% slower)
BLOCK = 4              # generations between checks
REVIEW_SHARE = 0.3     # share of lessons revisiting mastered stages
PROFILE_RUNS = 6       # scenarios per stage in the before/after profile
SKILLS = {"control": "Vehicle control and racing lines", "grip": "Braking, cornering and the grip limit",
          "recovery": "Understeer, oversteer and recovery", "adverse": "Adverse conditions",
          "racecraft": "Racecraft"}
EASY_TRACKS, MID_TRACKS, TIGHT_TRACKS = ["oval", "speedway"], ["speedway", "esses", "oval"], ["technical", "grandprix", "esses"]
ALL_TRACKS = academy.TRACKS
HOUSE = ["zappy-zoe", "dangerous-dave", "careful-keith", "zoe-bold", "clinical-clara"]


def _lap(track, laps):
    return academy._lap(track, laps)


def _pick(rng, items):
    return items[int(rng.integers(0, len(items)))]


def _trouble(rng, heading, slide, yaw=0.0, speed=0.75):
    sign = 1 if rng.random() < 0.5 else -1
    return {"corner": int(rng.integers(0, 4)), "before": float(rng.uniform(18, 28)), "speed": speed,
            "heading": sign * heading * rng.uniform(0.9, 1.1), "slide": sign * slide * rng.uniform(0.9, 1.1),
            "yaw": sign * yaw}


def _queue(rng, n, pace, styles):
    return [f"traffic:{pace + rng.uniform(-0.02, 0.02):.3f}:{_pick(rng, styles)}" for _ in range(n)]


# --------------------------------------------------------- pace calibration
# A traffic car's "pace" is a share of its top speed; what matters is its lap
# time.  traffic_laps() measures it once per track over a grid of paces (the
# same every time: no randomness), so a rival can be set to a lap time.

PACE_GRID = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0]
_LAPS_CACHE: dict = {}


def _best_lap(track: str, driver, laps: int = 3) -> float | None:
    import sim.scripted  # noqa: F401
    from sim.race import Race
    race = Race(track, [(0, driver)], laps=laps, seed=1, rolling=True).run(max_seconds=60 * laps)
    times = race.world.cars[0].lap_times[1:] or race.world.cars[0].lap_times
    return min(times) if times else None


def traffic_laps(track: str) -> list[float]:
    """Lap time of a traffic car (racing line, standard car) at each PACE_GRID value."""
    if track not in _LAPS_CACHE:
        from sim.traffic import TrafficDriver
        f = academy.ACADEMY_DIR / "traffic_laps.json"
        saved = json.loads(f.read_text()) if f.exists() else {}
        if track not in saved:
            saved[track] = [round(_best_lap(track, TrafficDriver(0, pace=p, style="line")), 3) for p in PACE_GRID]
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(saved, indent=1))
        _LAPS_CACHE[track] = saved[track]
    return _LAPS_CACHE[track]


def rival_pace(track: str, target_lap: float) -> float:
    """The traffic pace whose lap time is `target_lap` (clamped to the grid)."""
    laps = traffic_laps(track)                      # slower pace -> longer lap
    xs, ys = np.array(laps[::-1]), np.array(PACE_GRID[::-1])
    return float(np.clip(np.interp(target_lap, xs, ys), PACE_GRID[0], PACE_GRID[-1]))


def scripted_lap(track: str, traits) -> float:
    """The scripted driver's flying lap in the learner's own car (same traits)."""
    from sim import cartraits
    from sim.scripted import ScriptedDriver
    d = ScriptedDriver(0)
    d.car_params = cartraits.params_for(traits or cartraits.default())
    return _best_lap(track, d)


def _ctx_lap(ctx, track):
    """The learner's measured lap on `track` (or the scripted lap if unknown)."""
    if ctx and ctx.get("laps", {}).get(track):
        return ctx["laps"][track]
    return stable.SCRIPTED_LAPS[track]


def _relative(rng, ctx, track, share, jitter=0.01):
    """A traffic pace for a car lapping at `share` of the learner's pace."""
    target = _ctx_lap(ctx, track) / max(0.3, share + rng.uniform(-jitter, jitter))
    return rival_pace(track, target)


# Each stage: (id, title, kind, objectives(ease) -> list, make(rng, ease) -> variant, extra scoring terms).
# kind: "solo" lessons are scored as Academy solo lessons, "craft" with craft_score.
def _stage(sid, title, kind, objectives, make, extra=None):
    return {"id": sid, "title": title, "kind": kind, "objectives": objectives, "make": make, "extra": extra or {}}


def _solo(tracks, laps=3, grip=None, trouble=None):
    def make(rng, e, ctx=None):
        t = _pick(rng, tracks)
        g = None if grip is None else min(1.0, grip + 0.08 * e) * rng.uniform(0.98, 1.02)
        start = trouble(rng, e) if trouble else None
        return academy._v(t, _lap(t, laps) if not trouble or grip else 10 + 2 * laps, start=start, grip=g)
    return make


def _behind(tracks, n, share, styles, laps=2.0, slower=0.08):
    """`n` cars ahead lapping at `share` of the learner's own pace; easier:
    fewer, calmer and (for overtaking) slower cars."""
    def make(rng, e, ctx=None):
        t = _pick(rng, tracks)
        k = max(1, n - int(round(e * (n - 1) / 2)))
        rivals = [f"traffic:{_relative(rng, ctx, t, share - slower * e):.3f}:{_pick(rng, styles if e < 0.5 else ('line',))}"
                  for _ in range(k)]
        return academy._v(t, _lap(t, laps), rivals)
    return make


def _follow(tracks, laps=2.5):
    """Safe following: one car on the racing line at 95% of the learner's pace,
    starting just ahead.  Easier never means slower (that only invites a pass)."""
    def make(rng, e, ctx=None):
        t = _pick(rng, tracks)
        return academy._v(t, _lap(t, laps), [f"traffic:{_relative(rng, ctx, t, FOLLOW_PACE):.3f}:line"])
    return make


def _defend(rng, e, ctx=None):
    t = _pick(rng, MID_TRACKS + TIGHT_TRACKS)
    return academy._v(t, _lap(t, 2.0), [f"house:{_pick(rng, HOUSE)}:{1.10 - 0.08 * e:.3f}"], slot=0)


def _full_race(rng, e, ctx=None):
    t = _pick(rng, ALL_TRACKS)
    field = list(rng.permutation(HOUSE))
    keep = 5 - int(round(3 * e))                     # easier: some house rivals replaced by scripted cars
    rivals = [f"house:{h}" for h in field[:keep]] + ["scripted"] * (5 - keep)
    return academy._v(t, _lap(t, 3), rivals, slot=5)


def _judgement(rng, e, ctx=None):
    """A defending car nearly as quick as the learner: attack, wait or give up."""
    t = _pick(rng, TIGHT_TRACKS + ["speedway"])
    return academy._v(t, _lap(t, 2.5), [f"traffic:{_relative(rng, ctx, t, FOLLOW_PACE - 0.08 * e):.3f}:defend"])


CURRICULUM = {
    "control": [
        _stage("control-1", "Smooth laps on a wide track", "solo",
               lambda e: [("laps", ">=", 1.8), ("offtrack", "<=", 0.05 + 0.03 * e), ("damage", "<=", 0.05)],
               _solo(EASY_TRACKS, 2.5)),
        _stage("control-2", "Hold the racing line", "solo",
               lambda e: [("pace", "<=", 1.06 + 0.04 * e), ("line_error", "<=", 0.5 + 0.08 * e), ("offtrack", "<=", 0.03)],
               _solo(MID_TRACKS)),
        _stage("control-3", "Tight tracks", "solo",
               lambda e: [("pace", "<=", 1.03 + 0.04 * e), ("offtrack", "<=", 0.02 + 0.02 * e), ("damage", "<=", 0.03)],
               _solo(TIGHT_TRACKS)),
        _stage("control-4", "Precision everywhere", "solo",
               lambda e: [("pace", "<=", 1.0 + 0.03 * e), ("line_error", "<=", 0.38 + 0.07 * e),
                          ("offtrack", "<=", 0.01 + 0.01 * e), ("damage", "<=", 0.02)],
               _solo(ALL_TRACKS)),
    ],
    "grip": [
        _stage("grip-1", "Brake before the bend", "solo",
               lambda e: [("pace", "<=", 1.08), ("slide", "<=", 0.15 + 0.05 * e), ("damage", "<=", 0.05)],
               _solo(EASY_TRACKS)),
        _stage("grip-2", "Use the grip", "solo",
               lambda e: [("pace", "<=", 0.98 + 0.03 * e), ("limit_use", ">=", 0.12 - 0.03 * e), ("damage", "<=", 0.05)],
               _solo(MID_TRACKS)),
        _stage("grip-3", "On the limit", "solo",
               lambda e: [("pace", "<=", 0.95 + 0.03 * e), ("limit_use", ">=", 0.16 - 0.03 * e), ("damage", "<=", 0.05)],
               _solo(TIGHT_TRACKS)),
        _stage("grip-4", "Fast and tidy", "solo",
               lambda e: [("pace", "<=", 0.93 + 0.03 * e), ("slide", "<=", 0.06 + 0.03 * e), ("damage", "<=", 0.02)],
               _solo(ALL_TRACKS)),
    ],
    "recovery": [
        _stage("recovery-1", "Catch a twitch", "solo",
               lambda e: [("recovered", "<=", 3.0 + e), ("walls", "<=", 0), ("damage", "<=", 0.03)],
               _solo(EASY_TRACKS, trouble=lambda r, e: _trouble(r, 0.12 * (1 - 0.4 * e), 3.0 * (1 - 0.4 * e)))),
        _stage("recovery-2", "A big moment", "solo",
               lambda e: [("recovered", "<=", 3.0 + e), ("walls", "<=", 0), ("damage", "<=", 0.05)],
               _solo(MID_TRACKS, trouble=lambda r, e: _trouble(r, 0.28 * (1 - 0.4 * e), 5.5 * (1 - 0.4 * e)))),
        _stage("recovery-3", "Spin rescue", "solo",
               lambda e: [("recovered", "<=", 2.8 + e), ("walls", "<=", 0), ("damage", "<=", 0.05)],
               _solo(TIGHT_TRACKS, trouble=lambda r, e: _trouble(r, 0.44 * (1 - 0.4 * e), 6.0 * (1 - 0.4 * e),
                                                                  1.0 * (1 - 0.4 * e)))),
        _stage("recovery-4", "Hero recovery", "solo",
               lambda e: [("recovered", "<=", 2.2 + e), ("walls", "<=", 0), ("damage", "<=", 0.03)],
               _solo(ALL_TRACKS, trouble=lambda r, e: _trouble(r, 0.6 * (1 - 0.4 * e), 8.0 * (1 - 0.4 * e),
                                                                1.5 * (1 - 0.4 * e), 0.85))),
    ],
    "adverse": [
        _stage("adverse-1", "Back from the grass", "solo",
               lambda e: [("recovered", "<=", 3.0 + e), ("damage", "<=", 0.05)],
               _solo(MID_TRACKS, trouble=lambda r, e: {"corner": int(r.integers(0, 4)), "before": float(r.uniform(18, 28)),
                                                        "speed": 0.75 - 0.2 * e, "lateral": _pick(r, ["grass", "-grass"])})),
        _stage("adverse-2", "Greasy track", "solo",
               lambda e: [("laps", ">=", 1.8), ("pace", "<=", 1.08 + 0.03 * e), ("damage", "<=", 0.05)],
               _solo(MID_TRACKS, grip=0.9)),
        _stage("adverse-3", "Slippery and tight", "solo",
               lambda e: [("laps", ">=", 1.8), ("offtrack", "<=", 0.05 + 0.03 * e), ("damage", "<=", 0.05)],
               _solo(TIGHT_TRACKS, grip=0.8)),
        _stage("adverse-4", "Ice dancer", "solo",
               lambda e: [("laps", ">=", 1.6), ("pace", "<=", 1.15 + 0.05 * e), ("damage", "<=", 0.1),
                          ("recovered", "<=", 4.0 + e)],
               _solo(ALL_TRACKS, grip=0.74, trouble=lambda r, e: _trouble(r, 0.3 * (1 - 0.4 * e), 5.0 * (1 - 0.4 * e)))),
    ],
    "racecraft": [
        _stage("racecraft-1", "Catch and follow a car without damage", "craft",
               lambda e: [("reached", ">=", 1), ("damage", "<=", 0.02), ("tailgate", "<=", 0.08 + 0.05 * e)],
               _behind(EASY_TRACKS, 1, PASS_PACE, ("line",), 2.5), {"close": 0.3}),
        _stage("racecraft-2", "Safe following distance through corners", "craft",
               lambda e: [("corner_tail", "<=", 0.03 + 0.03 * e), ("contacts", "<=", 0),
                          ("close", ">=", 0.6 - 0.15 * e), ("max_gap_s", "<=", 2.0 + 1.0 * e)],
               _follow(TIGHT_TRACKS + ["speedway"]), {"close": 0.5, "corner_tail": -1.5, "clean_passes": -0.6}),
        _stage("racecraft-3", "Spot the chance to pass a slower car", "craft",
               lambda e: [("clean_passes", ">=", 1), ("fault", "<=", 0)],
               _behind(EASY_TRACKS, 1, PASS_PACE, ("line",), 2.5)),
        _stage("racecraft-4", "Simple overtakes on predictable cars", "craft",
               lambda e: [("clean_passes", ">=", 2 - int(e > 0.5)), ("fault", "<=", 0.5)],
               _behind(MID_TRACKS, 2, PASS_PACE, ("line",), 2.5)),
        _stage("racecraft-5", "Overtake with little room", "craft",
               lambda e: [("clean_passes", ">=", 1), ("fault", "<=", 0), ("damage", "<=", 0.05)],
               _behind(TIGHT_TRACKS, 2, PASS_PACE, ("wander", "line"), 2.0)),
        _stage("racecraft-6", "Pass defensive drivers", "craft",
               lambda e: [("clean_passes", ">=", 1), ("contacts", "<=", 1), ("fault", "<=", 0)],
               _behind(MID_TRACKS + TIGHT_TRACKS, 2, PASS_PACE, ("defend",), 2.5)),
        _stage("racecraft-7", "Attack, wait or abandon", "craft",
               lambda e: [("fault", "<=", 0), ("damage", "<=", 0.03), ("judged", ">=", 1)],
               _judgement, {"close": 0.2}),
        _stage("racecraft-8", "Through traffic", "craft",
               lambda e: [("clean_passes", ">=", 3 - int(round(2 * e))), ("fault", "<=", 1), ("damage", "<=", 0.1)],
               _behind(ALL_TRACKS, 5, PASS_PACE, ("line", "defend", "wander"), 3.0)),
        _stage("racecraft-9", "Defend fairly: no weaving, no blocking", "craft",
               lambda e: [("weaves", "<=", 1), ("fault", "<=", 0), ("passed", "<=", 0)],
               _defend, {"passed": -0.6, "weaves": -0.3}),
        _stage("racecraft-10", "Complete racecraft: full races", "craft",
               lambda e: [("place", "<=", 3), ("damage", "<=", 0.2), ("fault", "<=", 1)],
               _full_race),
    ],
}
BY_ID = {st["id"]: dict(st, skill=k, n=i + 1) for k, stages in CURRICULUM.items() for i, st in enumerate(stages)}


def derived(metrics: dict, track: str | None = None, ctx: dict | None = None) -> dict:
    """Measures built from others: `judged` = 1 when the driver either made a
    clean pass or sat patiently behind (following, no contact it caused);
    `pace` re-based on the scripted driver in the learner's own car."""
    m = dict(metrics)
    ref = (ctx or {}).get("scripted", {}).get(track) if track else None
    if ref and m.get("pace") is not None:
        m["pace"] = round(m["pace"] * stable.SCRIPTED_LAPS[track] / ref, 4)
    m["judged"] = int(m.get("fault", 0) <= 0 and (m.get("clean_passes", 0) >= 1 or m.get("close", 0) >= 0.3))
    return m


def variant(stage_id: str, rng, ease: float = 0.0, ctx: dict | None = None) -> dict:
    return BY_ID[stage_id]["make"](rng, ease, ctx)


def objectives(stage_id: str, ease: float = 0.0) -> list:
    return BY_ID[stage_id]["objectives"](ease)


# ----------------------------------------------------------------- training

def done_stages(state: dict) -> set:
    """Stages the driver has shown it can do: passed on entry or mastered."""
    return set(state.get("entry", [])) | set(state["mastered"])


def skill_weights(state: dict) -> dict:
    """Share of the normal (non-review) lessons for each skill still in
    training: weaker skills (fewer stages done, lower last check) get more,
    racecraft is emphasised, and no skill gets more than WEIGHT_CAP."""
    active = [sk for sk, s in state["skills"].items() if s["stage"]]
    if not active:
        return {}
    raw = {}
    for sk in active:
        ladder = [x["id"] for x in CURRICULUM[sk]]
        done = sum(1 for i in ladder if i in done_stages(state)) / len(ladder)
        last = (state["stages"][state["skills"][sk]["stage"]]["passes"] or [0.0])[-1]
        weakness = 1.0 - 0.5 * (done + last)
        raw[sk] = (0.5 + weakness) * (RACECRAFT_EMPHASIS if sk == "racecraft" else 1.0)
    total = sum(raw.values())
    w = {k: v / total for k, v in raw.items()}
    cap = max(WEIGHT_CAP, 1.0 / len(w))
    for _ in range(len(w)):                          # cap, handing the excess to the others in proportion
        over = {k: v for k, v in w.items() if v > cap + 1e-9}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        rest = {k: v for k, v in w.items() if k not in over}
        for k in over:
            w[k] = cap
        rest_total = sum(rest.values()) or 1.0
        for k, v in rest.items():
            w[k] = v + excess * v / rest_total
    return {k: round(v, 3) for k, v in w.items()}


def lesson(config: dict, rng) -> dict:
    """A training race for the current curriculum (`config["academy_curriculum"]`
    names the state file).  With stalled stages, REMEDIAL_SHARE of lessons are
    remedial work on them; of the rest, REVIEW_SHARE revisit stages already
    shown (forgotten ones weighted up) and the others are the stage each
    skill is at, by the adaptive skill weights."""
    state = json.loads(evolve.resolve_path(config["academy_curriculum"]).read_text())
    ctx = state.get("ctx")
    stalled = state.get("stalled", [])
    current = [(sk, s["stage"], s["ease"]) for sk, s in state["skills"].items() if s["stage"]]
    review = sorted(done_stages(state))
    roll = rng.random()
    if stalled and (roll < REMEDIAL_SHARE or not (current or review)):
        sid, ease = stalled[int(rng.integers(0, len(stalled)))], 0.0
    elif review and (not current or rng.random() < REVIEW_SHARE):
        w = np.array([3.0 if i in state.get("forgotten", []) else 1.0 for i in review])
        sid, ease = review[int(rng.choice(len(review), p=w / w.sum()))], 0.0
    else:
        weights = state.get("weights") or skill_weights(state)
        w = np.array([weights.get(sk, 0.0) for sk, _, _ in current]) + 1e-9
        _, sid, ease = current[int(rng.choice(len(current), p=w / w.sum()))]
    st = BY_ID[sid]
    v = st["make"](rng, ease, ctx)
    rivals, rival_cars = academy.training_rivals(config, v["rivals"])
    return {"track": v["track"], "slot": v["slot"], "rivals": rivals, "rival_cars": rival_cars,
            "car": config.get("car") if isinstance(config.get("car"), dict) else None,
            "seconds": min(v["seconds"], 70.0), "lesson": st["kind"], "challenge": sid, "extra": st["extra"],
            "start": v.get("start"), "grip": v.get("grip")}


# ------------------------------------------------------------------ testing

KEEP = ("pace", "offtrack", "damage", "contacts", "fault", "clean_passes", "close", "tailgate", "corner_tail",
        "max_gap_s", "weaves", "place", "recovered", "limit_use", "passed")


def _run(job):
    weights, arch, traits, sid, ease, seed, ctx = job
    v = variant(sid, np.random.default_rng(seed), ease, ctx)
    m = derived(academy.run_variant(weights, arch, traits, v, rep=seed % 3), v["track"], ctx)
    ok = all(academy.meets(m, objectives(sid, ease)))
    return sid, ok, {k: m.get(k) for k in KEEP}


def check(weights, arch, traits, stages: list[tuple[str, float, int]], seed: int, pool=None, ctx=None) -> dict:
    """Pass rates on fresh random scenarios: stages = [(stage id, ease, runs)].
    {stage id: {"pass": share, "runs": [bool], "metrics": [..]}}."""
    jobs = [(weights, arch, traits, sid, ease, seed * 1000 + k * 37 + list(BY_ID).index(sid) * 7919, ctx)
            for sid, ease, runs in stages for k in range(runs)]
    out = {}
    for sid, ok, m in (pool.map(_run, jobs) if pool else map(_run, jobs)):
        r = out.setdefault(sid, {"runs": [], "metrics": []})
        r["runs"].append(ok)
        r["metrics"].append(m)
    for r in out.values():
        r["pass"] = round(sum(r["runs"]) / len(r["runs"]), 3)
    return out


PROFILE_SEED = 900001        # the before/after profile uses the same scenarios for both brains


def profile(weights, arch, traits, pool=None, runs: int = PROFILE_RUNS, ctx=None) -> dict:
    """Every stage at full difficulty on the same fixed random scenarios."""
    return check(weights, arch, traits, [(sid, 0.0, runs) for sid in BY_ID], PROFILE_SEED, pool, ctx)


def measure(weights, arch, traits) -> dict:
    """The learner's baseline for pace-relative rivals and fair pace targets:
    its own best flying lap on every track (driving alone) and the scripted
    driver's in the same car."""
    from ai.brain import NeuralDriver
    from sim import cartraits
    laps, scripted = {}, {}
    for t in ALL_TRACKS:
        d = NeuralDriver(weights, arch, "Learner")
        d.car_params = cartraits.params_for(traits or cartraits.default())
        scripted[t] = round(scripted_lap(t, traits), 3)
        mine = _best_lap(t, d)
        laps[t] = round(mine, 3) if mine else scripted[t]
    return {"laps": laps, "scripted": scripted}


# --------------------------------------------------------------- the course

def folder(driver_id: str, tag: str = "adaptive") -> Path:
    return academy.ACADEMY_DIR / f"{driver_id}-{tag}"


def fresh_state(spec: dict) -> dict:
    return {"driver": spec["id"], "name": spec["name"], "generations": 0, "block": 0, "entry": [], "mastered": [],
            "stalled": [], "forgotten": [],
            "skills": {sk: {"stage": stages[0]["id"], "ease": 0.0, "fails": 0, "fails_at_easiest": 0, "attempts": 0}
                       for sk, stages in CURRICULUM.items()},
            "stages": {sid: {"attempts": 0, "passes": [], "mastered_at": None, "stalled_at": None, "ease_used": 0.0,
                             "forgotten": 0, "retests": []} for sid in BY_ID},
            "log": []}


def place(state: dict, before: dict) -> None:
    """Placement: each skill starts at the first stage the car fails; the
    stages before it are Passed on entry."""
    for sk, stages in CURRICULUM.items():
        s = state["skills"][sk]
        s["stage"] = None
        for st in stages:
            if before[st["id"]]["pass"] >= TARGET:
                state["entry"].append(st["id"])
            else:
                s["stage"] = st["id"]
                break


def _move_on(state: dict, skill: str, sid: str) -> None:
    ladder = [x["id"] for x in CURRICULUM[skill]]
    k = ladder.index(sid)
    s = state["skills"][skill]
    s["stage"] = ladder[k + 1] if k + 1 < len(ladder) else None
    s["ease"], s["fails"], s["fails_at_easiest"] = 0.0, 0, 0


def _advance(state: dict, skill: str, sid: str, rate: float) -> str:
    """Apply one check result to a skill.  Returns what happened."""
    s, st = state["skills"][skill], state["stages"][sid]
    st["attempts"] += 1
    st["passes"].append(rate)
    s["attempts"] += 1
    if rate >= TARGET:
        s["fails"] = s["fails_at_easiest"] = 0
        if s["ease"] > 0:                                   # passed an easier version: step the difficulty back up
            s["ease"] = round(max(0.0, s["ease"] - EASE_STEP), 2)
            return "passed (easier); harder again"
        st["mastered_at"] = state["generations"]
        state["mastered"].append(sid)
        _move_on(state, skill, sid)
        return "mastered" + ("" if s["stage"] else "; skill complete")
    s["fails"] += 1
    if s["ease"] >= 1.0:
        s["fails_at_easiest"] += 1
    if s["fails_at_easiest"] >= STALL_AT_EASIEST or st["attempts"] >= STALL_ATTEMPTS:
        st["stalled_at"] = state["generations"]            # moving on is not passing: never mastered
        state["stalled"].append(sid)
        _move_on(state, skill, sid)
        return "stalled; moved on (not mastered)"
    if s["fails"] >= EASE_AFTER and s["ease"] < 1.0:
        s["ease"] = round(min(1.0, s["ease"] + EASE_STEP), 2)
        st["ease_used"] = max(st["ease_used"], s["ease"])
        s["fails"] = 0
        return "failed; made easier"
    return "failed; repeat"


def status_of(state: dict, sid: str) -> str:
    if sid in state.get("entry", []):
        return "Passed on entry"
    if sid in state["mastered"]:
        return "Mastered in training"
    if sid in state.get("stalled", []):
        return "Stalled - moved on, competency not demonstrated"
    if any(s["stage"] == sid for s in state["skills"].values()):
        return "In training"
    return "Not reached"


def course(name: str, generations: int = 120, population: int = academy.POPULATION, workers: int = 4,
           log=print, block: int = BLOCK, tag: str = "adaptive") -> dict:
    """Train a candidate from the ORIGINAL brain through the adaptive
    curriculum (resumable)."""
    from . import migrate
    migrate.ensure()
    spec = academy.driver_spec(name)
    academy.prepare(spec)
    w0, arch0, info = academy.original(spec["id"])
    d = folder(spec["id"], tag)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "curriculum.json"
    state = json.loads(path.read_text()) if path.exists() else fresh_state(spec)
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        if "ctx" not in state:
            log(f"{spec['name']}: measuring its lap pace (and the scripted driver's in the same car) ...")
            state["ctx"] = measure(w0, arch0, info["traits"])
            for t in ALL_TRACKS:                          # build the traffic lap tables once, before workers need them
                traffic_laps(t)
            path.write_text(json.dumps(state, indent=1))
        ctx = state["ctx"]
        if "before" not in state:
            log("  placement: every stage at full difficulty ...")
            state["before"] = profile(w0, arch0, info["traits"], pool, ctx=ctx)
            place(state, state["before"])
            state["weights"] = skill_weights(state)
            path.write_text(json.dumps(state, indent=1))
            log("  starts: " + ", ".join(f"{sk} {s['stage'] or 'complete'}" for sk, s in state["skills"].items())
                + f"; weights {state['weights']}")
        while state["generations"] < generations:
            active = [(sk, s) for sk, s in state["skills"].items() if s["stage"]]
            if not active and not state["stalled"]:
                log("  every skill complete")
                break
            state["weights"] = skill_weights(state)
            path.write_text(json.dumps(state, indent=1))
            academy.train(spec["id"], block, population, workers, log=lambda m: None, where=d, lesson_share=0.85,
                          planned=generations, curriculum=evolve.project_path(path))
            gen = evolve.list_generations(d / "run")[-1]
            state["generations"], state["block"] = gen, state["block"] + 1
            w, arch = academy._gen_weights(d, gen)
            todo = [(s["stage"], s["ease"], CHECK_RUNS) for _, s in active]
            rng = np.random.default_rng([state["block"], 5])
            reviews = {}
            for sk in CURRICULUM:
                done = [i for i in sorted(done_stages(state)) if BY_ID[i]["skill"] == sk]
                if done:
                    reviews[sk] = done[int(rng.integers(0, len(done)))]
            retest = state["stalled"][state["block"] % len(state["stalled"])] if state["stalled"] else None
            todo += [(sid, 0.0, REVIEW_RUNS) for sid in reviews.values()]
            if retest and retest not in [t[0] for t in todo]:
                todo.append((retest, 0.0, REVIEW_RUNS))
            res = check(w, arch, info["traits"], todo, seed=state["block"], pool=pool, ctx=ctx)
            entry = {"block": state["block"], "gen": gen, "weights": state["weights"], "checks": {}, "reviews": {},
                     "retest": None}
            for sk, s in active:
                sid, ease = s["stage"], s["ease"]
                rate = res[sid]["pass"]
                entry["checks"][sid] = {"pass": rate, "ease": ease, "result": _advance(state, sk, sid, rate)}
            for sk, sid in reviews.items():
                rate = res[sid]["pass"]
                forgot = rate < FORGOT
                if forgot and sid not in state["forgotten"]:
                    state["forgotten"].append(sid)
                    state["stages"][sid]["forgotten"] += 1
                elif not forgot and sid in state["forgotten"]:
                    state["forgotten"].remove(sid)
                entry["reviews"][sid] = {"pass": rate, "forgotten": forgot}
            if retest:
                rate = res[retest]["pass"]
                state["stages"][retest]["retests"].append({"gen": gen, "pass": rate})
                entry["retest"] = {"stage": retest, "pass": rate}
            state["log"].append(entry)
            path.write_text(json.dumps(state, indent=1))
            log(f"  gen {gen}: " + "; ".join(f"{sid} {c['pass']:.0%} {c['result']}" for sid, c in entry["checks"].items())
                + ("; review " + ", ".join(f"{sid} {r['pass']:.0%}{' FORGOTTEN' if r['forgotten'] else ''}"
                                           for sid, r in entry["reviews"].items()) if entry["reviews"] else "")
                + (f"; retest {retest} {entry['retest']['pass']:.0%}" if retest else ""))
        if "after" not in state and evolve.list_generations(d / "run"):
            w, arch = academy._gen_weights(d, state["generations"])
            log("  testing the candidate on every stage ...")
            state["after"] = profile(w, arch, info["traits"], pool, ctx=ctx)
            path.write_text(json.dumps(state, indent=1))
    finally:
        if pool:
            pool.shutdown()
    return state


# -------------------------------------------------------------- benchmark

PANEL_OPPONENTS = ["house:zoe-bold", "house:zappy-zoe", "house:clinical-clara"]
PANEL_PER_TRACK = 6
PANEL_LAPS = 5


def _save_brain(where: Path, which: str, w, arch, info) -> str:
    where.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(where / f"{which}.npz", pop=np.asarray(w, dtype=np.float32)[None, :])
    (where / f"{which}.json").write_text(json.dumps({"name": f"{info['name']} ({which})", "arch": arch,
                                                    "traits": info["traits"]}))
    return f"file:{evolve.project_path(where / which)}"


def versions(driver_id: str, tag: str = "adaptive") -> dict:
    """The versions compared: {label: league key}.  The original, the previous
    (fixed-curriculum) candidate if there is one, and this candidate."""
    d = folder(driver_id, tag)
    w0, arch0, info = academy.original(driver_id)
    out = {"original": _save_brain(d / "bench", "original", w0, arch0, info)}
    old = academy.ACADEMY_DIR / f"{driver_id}-curriculum"           # the first, fixed curriculum
    if (old / "curriculum.json").exists():
        g = json.loads((old / "curriculum.json").read_text())["generations"]
        w, arch = academy._gen_weights(old, g)
        out["previous candidate"] = _save_brain(d / "bench", "previous candidate", w, arch, info)
    state = json.loads((d / "curriculum.json").read_text())
    w, arch = academy._gen_weights(d, state["generations"])
    out["new candidate"] = _save_brain(d / "bench", "new candidate", w, arch, info)
    return out


def _panel_race(job):
    """One fixed-grid race: [(key, place, finished, damage, contacts, walls, best lap)]."""
    import league
    import sim.scripted  # noqa: F401
    from sim.race import Race
    track, keys, laps, seed = job
    race = Race(track, [(slot, league.make(k)) for slot, k in enumerate(keys)], laps=laps, seed=seed, rolling=True)
    contacts = [0] * len(keys)
    walls = [0] * len(keys)
    limit = int(120 * laps * 120)
    while race.phase != "finished" and race.world.tick < limit:
        for e in race.step():
            if e[0] == "car":
                contacts[e[1]] += 1
                contacts[e[2]] += 1
            elif e[0] == "wall":
                walls[e[1]] += 1
    return track, [(keys[r["car"]], r["place"], bool(r["finished"]), round(race.world.cars[r["car"]].damage, 3),
                    contacts[r["car"]], walls[r["car"]], r.get("best_lap")) for r in race.results()]


def panel(keys: list[str], workers: int = 4, per_track: int = PANEL_PER_TRACK, laps: int = PANEL_LAPS,
          seed: int = 77) -> list[dict]:
    """Fixed-grid benchmark: every version in every race against the same
    opponents, the same tracks and seeds; grid order drawn per race (seeded)."""
    from multiprocessing import Pool
    field = list(keys) + PANEL_OPPONENTS
    rng = np.random.default_rng(seed)
    jobs = [(t, [field[k] for k in rng.permutation(len(field))], laps, seed * 1000 + n)
            for n, t in enumerate([t for t in ALL_TRACKS for _ in range(per_track)])]
    with Pool(workers) as pool:
        out = pool.map(_panel_race, jobs)
    return [{"track": t, "results": [dict(zip(("key", "place", "finished", "damage", "contacts", "walls", "best_lap"), r))
                                     for r in rows]} for t, rows in out]


def head_to_head(races: list[dict], a: str, b: str) -> dict:
    """In races with both: how often a finished ahead of b, the mean place
    difference (b - a: positive = a better) with its standard error, and a
    two-sided sign-test p value."""
    ahead = behind = 0
    diffs = []
    for race in races:
        res = {r["key"]: r for r in race["results"]}
        if a in res and b in res:
            pa, pb = res[a]["place"], res[b]["place"]
            ahead += pa < pb
            behind += pb < pa
            diffs.append(pb - pa)
    n = ahead + behind
    k = min(ahead, behind)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    mean = float(np.mean(diffs)) if diffs else 0.0
    se = float(np.std(diffs, ddof=1) / math.sqrt(len(diffs))) if len(diffs) > 1 else 0.0
    return {"races": len(diffs), "ahead": ahead, "behind": behind, "mean": round(mean, 2), "se": round(se, 2),
            "p": round(p, 4), "real": bool(n and p < 0.05 and abs(mean) > 2 * se)}


def summary_of(races: list[dict], key: str) -> dict:
    rows = [r for race in races for r in race["results"] if r["key"] == key]
    n = max(1, len(rows))
    by_track = {}
    for race in races:
        for r in race["results"]:
            if r["key"] == key:
                by_track.setdefault(race["track"], []).append(r["place"])
    return {"races": len(rows), "wins": sum(r["finished"] and r["place"] == 1 for r in rows),
            "podiums": sum(r["finished"] and r["place"] <= 3 for r in rows),
            "avg_place": round(sum(r["place"] for r in rows) / n, 2),
            "place_se": round(float(np.std([r["place"] for r in rows], ddof=1) / math.sqrt(n)) if len(rows) > 1 else 0, 2),
            "dnf": sum(not r["finished"] for r in rows), "damage": round(sum(r["damage"] for r in rows) / n, 3),
            "contacts": round(sum(r.get("contacts", 0) for r in rows) / n, 2),
            "walls": round(sum(r.get("walls", 0) for r in rows) / n, 2),
            "by_track": {t: round(float(np.mean(v)), 2) for t, v in by_track.items()}}


def benchmark(driver_id: str, rounds: int = 8, laps: int = 5, workers: int = 4, log=print, tag: str = "adaptive",
              per_track: int = PANEL_PER_TRACK) -> dict:
    """Fixed-grid panel (the verdict) and the all-car tournament (context)."""
    import league
    d = folder(driver_id, tag)
    keys = versions(driver_id, tag)
    out = json.loads((d / "benchmark.json").read_text()) if (d / "benchmark.json").exists() else {}
    if "panel" not in out:
        log(f"  fixed-grid panel: {per_track * len(ALL_TRACKS)} races ...")
        out["panel"] = panel(list(keys.values()), workers, per_track, laps)
        out["keys"] = keys
        (d / "benchmark.json").write_text(json.dumps(out, indent=1))
    entries = {k: v for k, v in league.drivers().items() if not k.endswith(f":{driver_id}")}
    for label, key in keys.items():
        entries[key] = {"name": f"{academy.original(driver_id)[2]['name']} ({label})", "status": "academy " + label}
    log("  all-car tournament ...")
    out["tournament"] = league.run_league(entries, rounds=rounds, laps=laps, workers=workers,
                                          save=d / "tournament.json", log=log)
    (d / "benchmark.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------- report

def _rate(profile_: dict, sids) -> float | None:
    runs = [r for sid in sids if sid in profile_ for r in profile_[sid]["runs"]]
    return sum(runs) / len(runs) if runs else None


def _se(p, n):
    return math.sqrt(max(p * (1 - p), 0.25 / n) / n) if n else 0.0


def report(driver_id: str, tag: str = "adaptive") -> Path:
    from . import rating
    d = folder(driver_id, tag)
    state = json.loads((d / "curriculum.json").read_text())
    before, after = state.get("before", {}), state.get("after", {})
    bench = json.loads((d / "benchmark.json").read_text()) if (d / "benchmark.json").exists() else None
    ctx = state.get("ctx", {})
    L = [f"# {state['name']}: adaptive Academy curriculum", "",
         f"Started from the original brain. {state['generations']} generations in {state['block']} blocks of {BLOCK}; "
         f"each check uses {CHECK_RUNS} fresh random scenarios; a stage is mastered at {TARGET:.0%} at full difficulty. "
         f"Rivals are matched to the driver's own measured lap pace (following {FOLLOW_PACE:.0%}, overtaking "
         f"{PASS_PACE:.0%}); pace targets compare with the scripted driver in the same car. The original is untouched "
         "and the candidate is not promoted.", "",
         "## Placement", "", "Measured flying laps (alone) and the scripted driver in the same car:", "",
         "| Track | Driver | Scripted, same car |", "|---|---|---|"]
    for t in ALL_TRACKS:
        L.append(f"| {stable.TRACK_NAMES[t]} | {ctx.get('laps', {}).get(t, '-')} s | {ctx.get('scripted', {}).get(t, '-')} s |")
    first = state["log"][0]["weights"] if state["log"] else state.get("weights", {})
    L += ["", "| Skill | Passed on entry | Started at | First lesson weights |", "|---|---|---|---|"]
    for sk, stages in CURRICULUM.items():
        entry = [x["title"] for x in stages if x["id"] in state.get("entry", [])]
        start = next((x for x in stages if x["id"] not in state.get("entry", [])), None)
        L.append(f"| {SKILLS[sk]} | {len(entry)} of {len(stages)} | "
                 f"{f'{stages.index(start) + 1}. ' + start['title'] if start else 'all passed'} | {first.get(sk, 0):.0%} |")
    # A. competence
    L += ["", "## A. Has he become more competent?", "", "| Stage | Status | Checks | Hardest ease | Before | After |",
          "|---|---|---|---|---|---|"]
    counts = {}
    for sk, stages in CURRICULUM.items():
        for k, st in enumerate(stages, 1):
            r = state["stages"][st["id"]]
            status = status_of(state, st["id"])
            counts[status] = counts.get(status, 0) + 1
            if r["retests"] and any(x["pass"] >= TARGET for x in r["retests"]) and st["id"] in state["stalled"]:
                status += " (later passed on retest)"
            b, a = _rate(before, [st["id"]]), _rate(after, [st["id"]])
            L.append(f"| {SKILLS[sk].split(' ')[0]} {k}: {st['title']} | {status} | {r['attempts']} | {r['ease_used']:.2f} | "
                     f"{'-' if b is None else f'{b:.0%}'} | {'-' if a is None else f'{a:.0%}'} |")
    L += ["", "Stages: " + ", ".join(f"{v} {k.lower()}" for k, v in sorted(counts.items())) + ".", "",
          "| Skill | Before | After | Change |", "|---|---|---|---|"]
    rows = []
    for sk, stages in CURRICULUM.items():
        ids = [x["id"] for x in stages]
        b, a = _rate(before, ids), _rate(after, ids)
        if b is None or a is None:
            continue
        n = sum(len(before[i]["runs"]) for i in ids)
        se = math.sqrt(_se(b, n) ** 2 + _se(a, n) ** 2)
        rows.append((sk, a))
        L.append(f"| {SKILLS[sk]} | {b:.0%} | {a:.0%} | {a - b:+.0%} ({'real' if abs(a - b) > 2 * se else 'within noise'}) |")
    if rows:
        rows.sort(key=lambda r: -r[1])
        L += ["", f"Strongest: {', '.join(SKILLS[r[0]] for r in rows[:2])}.  Weakest: {', '.join(SKILLS[r[0]] for r in rows[-2:])}."]
    # B. racing
    if bench:
        keys = bench["keys"]
        label = {v: k for k, v in keys.items()}
        races = bench["panel"]
        L += ["", "## B. Has he become a better racer?", "",
              f"### Fixed-grid benchmark (the verdict): {len(races)} races, {PANEL_LAPS} laps, every version in every race "
              f"with {', '.join(k.split(':')[1] for k in PANEL_OPPONENTS)}; the same tracks, grids and seeds for all.", "",
              "| Version | Avg place | Wins | Podiums | DNFs | Damage | Car contacts / race | Wall hits / race |",
              "|---|---|---|---|---|---|---|---|"]
        for lab, key in keys.items():
            sm = summary_of(races, key)
            L.append(f"| {lab} | {sm['avg_place']:.2f} +- {sm['place_se']:.2f} | {sm['wins']} | {sm['podiums']} | {sm['dnf']} | "
                     f"{sm['damage']:.0%} | {sm['contacts']:.1f} | {sm['walls']:.1f} |")
        L += ["", "By track (average place):", "", "| Version | " + " | ".join(stable.TRACK_NAMES[t] for t in ALL_TRACKS) + " |",
              "|---|" + "---|" * len(ALL_TRACKS)]
        for lab, key in keys.items():
            bt = summary_of(races, key)["by_track"]
            L.append(f"| {lab} | " + " | ".join(f"{bt.get(t, 0):.2f}" for t in ALL_TRACKS) + " |")
        L += ["", "### Head to head (same races)", "", "| Pair | Races | Ahead - behind | Mean places better | Sign test p | Verdict |",
              "|---|---|---|---|---|---|"]
        pairs = [("new candidate", "original"), ("new candidate", "previous candidate"), ("previous candidate", "original")]
        verdicts = {}
        for a, b in pairs:
            if a in keys and b in keys:
                h = head_to_head(races, keys[a], keys[b])
                v = ("better" if h["mean"] > 0 else "worse") if h["real"] else "no real difference"
                verdicts[(a, b)] = (v, h)
                L.append(f"| {a} v {b} | {h['races']} | {h['ahead']} - {h['behind']} | {h['mean']:+.2f} +- {h['se']:.2f} | "
                         f"{h['p']:.3f} | {v} |")
        t = bench.get("tournament")
        if t:
            L += ["", f"### All-car tournament (context only: divisions differ), {t['round']} rounds", "",
                  "| # | Driver | Rating | +- | Races | Wins | Podiums | Avg place | DNFs |", "|---|---|---|---|---|---|---|---|---|"]
            ranked = sorted(t["drivers"].items(), key=lambda kv: -(kv[1]["mu"] - 3 * kv[1]["sigma"]))
            for k, (key, r) in enumerate(ranked, 1):
                n = max(1, r["races"])
                bold = "**" if key in label else ""
                L.append(f"| {k} | {bold}{r['name']}{bold} | {rating.show(r['mu']):.0f} | {rating.SCALE * r['sigma']:.0f} | "
                         f"{r['races']} | {r['wins']} | {r['podiums']} | {r['places'] / n:.2f} | {r['dnf']} |")
        v, h = verdicts.get(("new candidate", "original"), ("-", {}))
        L += ["", "## Verdicts", "",
              f"- **A. Competence:** {counts.get('Mastered in training', 0)} stages mastered in training, "
              f"{counts.get('Passed on entry', 0)} passed on entry, {counts.get('Stalled - moved on, competency not demonstrated', 0)} "
              f"stalled, {counts.get('Not reached', 0) + counts.get('In training', 0)} not finished.",
              f"- **B. Racing (fixed grid, against the original):** {v}"
              + (f" (finished ahead in {h['ahead']} of {h['ahead'] + h['behind']} races, {h['mean']:+.2f} places a race)" if h else "")
              + ".", "- Not promoted: promotion is a separate decision."]
    path = academy.REPORT_DIR / f"{driver_id}-{tag}.md"
    academy.REPORT_DIR.mkdir(exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="The Racing Academy's adaptive curriculum")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="place, train, benchmark and report (resumable)")
    r.add_argument("driver")
    r.add_argument("--generations", type=int, default=120)
    r.add_argument("--population", type=int, default=academy.POPULATION)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--rounds", type=int, default=8)
    r.add_argument("--tag", default="adaptive")
    sub.add_parser("stages", help="list the curriculum")
    args = ap.parse_args()
    if args.cmd == "stages":
        for sk, stages in CURRICULUM.items():
            print(SKILLS[sk])
            for k, st in enumerate(stages, 1):
                print(f"  {k}. {st['title']}")
        return 0
    log = lambda m: print(f"{time.strftime('%H:%M')} {m}", flush=True)
    spec = academy.driver_spec(args.driver)
    course(args.driver, args.generations, args.population, args.workers, log, tag=args.tag)
    benchmark(spec["id"], rounds=args.rounds, workers=args.workers, log=log, tag=args.tag)
    print(report(spec["id"], args.tag), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
