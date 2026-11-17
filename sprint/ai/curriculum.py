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

TARGET = 0.67          # share of a stage's check scenarios passed to master it
CHECK_RUNS = 6         # fresh random scenarios per check
REVIEW_RUNS = 3        # scenarios when re-testing a mastered stage
FORGOT = 0.34          # a mastered stage re-tested below this is forgotten
EASE_AFTER = 2         # failed checks in a row before the stage is made easier
EASE_STEP = 0.34
STALL = 10             # failed checks on one stage before the skill stops there
BLOCK = 4              # generations between checks
REVIEW_SHARE = 0.3     # share of lessons revisiting mastered stages
PROFILE_RUNS = 6       # scenarios per stage in the before/after profile
SKILL_WEIGHT = {"control": 1.0, "grip": 1.0, "recovery": 1.0, "adverse": 1.0, "racecraft": 2.0}
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


# Each stage: (id, title, kind, objectives(ease) -> list, make(rng, ease) -> variant, extra scoring terms).
# kind: "solo" lessons are scored as Academy solo lessons, "craft" with craft_score.
def _stage(sid, title, kind, objectives, make, extra=None):
    return {"id": sid, "title": title, "kind": kind, "objectives": objectives, "make": make, "extra": extra or {}}


def _solo(tracks, laps=3, grip=None, trouble=None):
    def make(rng, e):
        t = _pick(rng, tracks)
        g = None if grip is None else min(1.0, grip + 0.08 * e) * rng.uniform(0.98, 1.02)
        start = trouble(rng, e) if trouble else None
        return academy._v(t, _lap(t, laps) if not trouble or grip else 10 + 2 * laps, start=start, grip=g)
    return make


def _behind(tracks, n, pace, styles, laps=2.0, slower=0.08):
    def make(rng, e):
        t = _pick(rng, tracks)
        k = max(1, n - int(round(e * (n - 1) / 2)))
        return academy._v(t, _lap(t, laps), _queue(rng, k, pace - slower * e, styles if e < 0.5 else ("line",)))
    return make


def _defend(rng, e):
    t = _pick(rng, MID_TRACKS + TIGHT_TRACKS)
    return academy._v(t, _lap(t, 2.0), [f"house:{_pick(rng, HOUSE)}:{1.10 - 0.08 * e:.3f}"], slot=0)


def _full_race(rng, e):
    t = _pick(rng, ALL_TRACKS)
    field = list(rng.permutation(HOUSE))
    keep = 5 - int(round(3 * e))                     # easier: some house rivals replaced by scripted cars
    rivals = [f"house:{h}" for h in field[:keep]] + ["scripted"] * (5 - keep)
    return academy._v(t, _lap(t, 3), rivals, slot=5)


def _judgement(rng, e):
    t = _pick(rng, TIGHT_TRACKS + ["speedway"])
    return academy._v(t, _lap(t, 2.5), [f"traffic:{0.90 - 0.08 * e:.3f}:defend"])


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
               _behind(EASY_TRACKS, 1, 0.68, ("line",), 2.5), {"close": 0.3}),
        _stage("racecraft-2", "Safe following distance through corners", "craft",
               lambda e: [("close", ">=", 0.15 - 0.05 * e), ("tailgate", "<=", 0.03 + 0.03 * e), ("fault", "<=", 0)],
               _behind(TIGHT_TRACKS, 1, 0.80, ("line",), 2.5), {"close": 0.4}),
        _stage("racecraft-3", "Spot the chance to pass a slower car", "craft",
               lambda e: [("clean_passes", ">=", 1), ("fault", "<=", 0)],
               _behind(EASY_TRACKS, 1, 0.70, ("line",), 2.5)),
        _stage("racecraft-4", "Simple overtakes on predictable cars", "craft",
               lambda e: [("clean_passes", ">=", 2 - int(e > 0.5)), ("fault", "<=", 0.5)],
               _behind(MID_TRACKS, 2, 0.74, ("line",), 2.5)),
        _stage("racecraft-5", "Overtake with little room", "craft",
               lambda e: [("clean_passes", ">=", 1), ("fault", "<=", 0), ("damage", "<=", 0.05)],
               _behind(TIGHT_TRACKS, 2, 0.78, ("wander", "line"), 2.0)),
        _stage("racecraft-6", "Pass defensive drivers", "craft",
               lambda e: [("clean_passes", ">=", 1), ("contacts", "<=", 1), ("fault", "<=", 0)],
               _behind(MID_TRACKS + TIGHT_TRACKS, 2, 0.80, ("defend",), 2.5)),
        _stage("racecraft-7", "Attack, wait or abandon", "craft",
               lambda e: [("fault", "<=", 0), ("damage", "<=", 0.03), ("judged", ">=", 1)],
               _judgement, {"close": 0.2}),
        _stage("racecraft-8", "Through traffic", "craft",
               lambda e: [("clean_passes", ">=", 3 - int(round(2 * e))), ("fault", "<=", 1), ("damage", "<=", 0.1)],
               _behind(ALL_TRACKS, 5, 0.76, ("line", "defend", "wander"), 3.0)),
        _stage("racecraft-9", "Defend fairly: no weaving, no blocking", "craft",
               lambda e: [("weaves", "<=", 1), ("fault", "<=", 0), ("passed", "<=", 0)],
               _defend, {"passed": -0.6, "weaves": -0.3}),
        _stage("racecraft-10", "Complete racecraft: full races", "craft",
               lambda e: [("place", "<=", 3), ("damage", "<=", 0.2), ("fault", "<=", 1)],
               _full_race),
    ],
}
BY_ID = {st["id"]: dict(st, skill=k, n=i + 1) for k, stages in CURRICULUM.items() for i, st in enumerate(stages)}


def derived(metrics: dict) -> dict:
    """Measures built from others: `judged` = 1 when the driver either made a
    clean pass or sat patiently behind (following, no contact it caused)."""
    m = dict(metrics)
    m["judged"] = int(m.get("fault", 0) <= 0 and (m.get("clean_passes", 0) >= 1 or m.get("close", 0) >= 0.3))
    return m


def variant(stage_id: str, rng, ease: float = 0.0) -> dict:
    return BY_ID[stage_id]["make"](rng, ease)


def objectives(stage_id: str, ease: float = 0.0) -> list:
    return BY_ID[stage_id]["objectives"](ease)


# ----------------------------------------------------------------- training

def lesson(config: dict, rng) -> dict:
    """A training race for the current curriculum (`config["academy_curriculum"]`
    names the state file): mostly the stage each skill is at (at its ease),
    some review of mastered stages (forgotten ones weighted up)."""
    state = json.loads(evolve.resolve_path(config["academy_curriculum"]).read_text())
    current = [(sk, s["stage"], s["ease"]) for sk, s in state["skills"].items() if s["stage"]]
    review = [(BY_ID[i]["skill"], i, 0.0) for i in state["mastered"]]
    if review and (not current or rng.random() < REVIEW_SHARE):
        w = np.array([3.0 if i in state.get("forgotten", []) else 1.0 for _, i, _ in review])
        skill, sid, ease = review[int(rng.choice(len(review), p=w / w.sum()))]
    else:
        w = np.array([SKILL_WEIGHT[sk] for sk, _, _ in current])
        skill, sid, ease = current[int(rng.choice(len(current), p=w / w.sum()))]
    st = BY_ID[sid]
    v = st["make"](rng, ease)
    rivals, rival_cars = academy.training_rivals(config, v["rivals"])
    return {"track": v["track"], "slot": v["slot"], "rivals": rivals, "rival_cars": rival_cars,
            "car": config.get("car") if isinstance(config.get("car"), dict) else None,
            "seconds": min(v["seconds"], 70.0), "lesson": st["kind"], "challenge": sid, "extra": st["extra"],
            "start": v.get("start"), "grip": v.get("grip")}


# ------------------------------------------------------------------ testing

def _run(job):
    weights, arch, traits, sid, ease, seed = job
    v = variant(sid, np.random.default_rng(seed), ease)
    m = derived(academy.run_variant(weights, arch, traits, v, rep=seed % 3))
    ok = all(academy.meets(m, objectives(sid, ease)))
    return sid, ok, {k: m[k] for k in ("pace", "offtrack", "damage", "contacts", "fault", "clean_passes",
                                       "close", "tailgate", "weaves", "place", "recovered", "limit_use")}


def check(weights, arch, traits, stages: list[tuple[str, float, int]], seed: int, pool=None) -> dict:
    """Pass rates on fresh random scenarios: stages = [(stage id, ease, runs)].
    {stage id: {"pass": share, "runs": [bool], "metrics": [..]}}."""
    jobs = [(weights, arch, traits, sid, ease, seed * 1000 + k * 37 + list(BY_ID).index(sid) * 7919)
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


def profile(weights, arch, traits, pool=None, runs: int = PROFILE_RUNS) -> dict:
    """Every stage at full difficulty on the same fixed random scenarios."""
    return check(weights, arch, traits, [(sid, 0.0, runs) for sid in BY_ID], PROFILE_SEED, pool)


# --------------------------------------------------------------- the course

def folder(driver_id: str) -> Path:
    return academy.ACADEMY_DIR / f"{driver_id}-curriculum"


def fresh_state(spec: dict) -> dict:
    return {"driver": spec["id"], "name": spec["name"], "generations": 0, "block": 0, "mastered": [], "forgotten": [],
            "skills": {sk: {"stage": stages[0]["id"], "ease": 0.0, "fails": 0, "attempts": 0, "stalled": False}
                       for sk, stages in CURRICULUM.items()},
            "stages": {sid: {"attempts": 0, "passes": [], "mastered_at": None, "ease_used": 0.0, "forgotten": 0}
                       for sid in BY_ID},
            "log": []}


def _advance(state: dict, skill: str, sid: str, rate: float) -> str:
    """Apply one check result to a skill.  Returns what happened."""
    s, st = state["skills"][skill], state["stages"][sid]
    st["attempts"] += 1
    st["passes"].append(rate)
    s["attempts"] += 1
    if rate >= TARGET:
        s["fails"] = 0
        if s["ease"] > 0:                                   # passed an easier version: step the difficulty back up
            s["ease"] = round(max(0.0, s["ease"] - EASE_STEP), 2)
            return "passed (easier); harder again"
        st["mastered_at"] = state["generations"]
        state["mastered"].append(sid)
        ladder = [x["id"] for x in CURRICULUM[skill]]
        k = ladder.index(sid)
        s["stage"] = ladder[k + 1] if k + 1 < len(ladder) else None
        return "mastered" + ("" if s["stage"] else "; skill complete")
    s["fails"] += 1
    if st["attempts"] >= STALL:
        s["stalled"] = True
        return "stalled"
    if s["fails"] >= EASE_AFTER and s["ease"] < 1.0:
        s["ease"] = round(min(1.0, s["ease"] + EASE_STEP), 2)
        st["ease_used"] = max(st["ease_used"], s["ease"])
        s["fails"] = 0
        return "failed; made easier"
    return "failed; repeat"


def course(name: str, generations: int = 80, population: int = academy.POPULATION, workers: int = 4,
           log=print, block: int = BLOCK) -> dict:
    """Train a candidate through the curriculum (resumable)."""
    from . import migrate
    migrate.ensure()
    spec = academy.driver_spec(name)
    academy.prepare(spec)
    w0, arch0, info = academy.original(spec["id"])
    d = folder(spec["id"])
    d.mkdir(parents=True, exist_ok=True)
    path = d / "curriculum.json"
    state = json.loads(path.read_text()) if path.exists() else fresh_state(spec)
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        if "before" not in state:
            log(f"{spec['name']}: testing the original on every stage ...")
            state["before"] = profile(w0, arch0, info["traits"], pool)
            path.write_text(json.dumps(state, indent=1))
        while state["generations"] < generations:
            active = [(sk, s) for sk, s in state["skills"].items() if s["stage"] and not s["stalled"]]
            if not active:
                log("  every skill complete or stalled")
                break
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
                done = [i for i in state["mastered"] if BY_ID[i]["skill"] == sk]
                if done:
                    reviews[sk] = done[int(rng.integers(0, len(done)))]
            todo += [(sid, 0.0, REVIEW_RUNS) for sid in reviews.values()]
            res = check(w, arch, info["traits"], todo, seed=state["block"], pool=pool)
            entry = {"block": state["block"], "gen": gen, "checks": {}, "reviews": {}}
            for sk, s in active:
                sid, ease = s["stage"], s["ease"]
                rate = res[sid]["pass"]
                what = _advance(state, sk, sid, rate)
                entry["checks"][sid] = {"pass": rate, "ease": ease, "result": what}
            for sk, sid in reviews.items():
                rate = res[sid]["pass"]
                forgot = rate < FORGOT
                if forgot and sid not in state["forgotten"]:
                    state["forgotten"].append(sid)
                    state["stages"][sid]["forgotten"] += 1
                elif not forgot and sid in state["forgotten"]:
                    state["forgotten"].remove(sid)
                entry["reviews"][sid] = {"pass": rate, "forgotten": forgot}
            state["log"].append(entry)
            path.write_text(json.dumps(state, indent=1))
            log(f"  gen {gen}: " + "; ".join(f"{sid} {c['pass']:.0%} {c['result']}" for sid, c in entry["checks"].items())
                + ("; review " + ", ".join(f"{sid} {r['pass']:.0%}{' FORGOTTEN' if r['forgotten'] else ''}"
                                           for sid, r in entry["reviews"].items()) if entry["reviews"] else ""))
        if "after" not in state and evolve.list_generations(d / "run"):
            w, arch = academy._gen_weights(d, state["generations"])
            log("  testing the candidate on every stage ...")
            state["after"] = profile(w, arch, info["traits"], pool)
            path.write_text(json.dumps(state, indent=1))
    finally:
        if pool:
            pool.shutdown()
    return state


# -------------------------------------------------------------- benchmark

def bench_entries(driver_id: str) -> dict:
    """The tournament field: every brain league.py knows, with this driver's
    own entry replaced by its original and its candidate."""
    import league
    d = folder(driver_id)
    state = json.loads((d / "curriculum.json").read_text())
    w0, arch0, info = academy.original(driver_id)
    w1, arch1 = academy._gen_weights(d, state["generations"])
    for which, (w, arch) in (("original", (w0, arch0)), ("candidate", (w1, arch1))):
        (d / "bench").mkdir(exist_ok=True)
        np.savez_compressed(d / "bench" / f"{which}.npz", pop=np.asarray(w, dtype=np.float32)[None, :])
        (d / "bench" / f"{which}.json").write_text(json.dumps(
            {"name": f"{info['name']} ({which})", "arch": arch, "traits": info["traits"]}))
    entries = {k: v for k, v in league.drivers().items() if not k.endswith(f":{driver_id}")}
    for which in ("original", "candidate"):
        entries[f"file:{evolve.project_path(d / 'bench' / which)}"] = {"name": f"{info['name']} ({which})",
                                                                       "status": "academy " + which}
    return entries


def benchmark(driver_id: str, rounds: int = 8, laps: int = 5, workers: int = 4, log=print) -> dict:
    import league
    d = folder(driver_id)
    out = league.run_league(bench_entries(driver_id), rounds=rounds, laps=laps, workers=workers,
                            save=d / "tournament.json", log=log)
    return out


# ------------------------------------------------------------------- report

def _rate(profile_: dict, sids) -> float | None:
    runs = [r for sid in sids if sid in profile_ for r in profile_[sid]["runs"]]
    return sum(runs) / len(runs) if runs else None


def _se(p, n):
    return math.sqrt(max(p * (1 - p), 0.25 / n) / n) if n else 0.0


def report(driver_id: str) -> Path:
    d = folder(driver_id)
    state = json.loads((d / "curriculum.json").read_text())
    before, after = state.get("before", {}), state.get("after", {})
    t = json.loads((d / "tournament.json").read_text()) if (d / "tournament.json").exists() else None
    L = [f"# {state['name']}: progressive Academy curriculum", "",
         f"{state['generations']} generations of training in {state['block']} blocks of {BLOCK}; checks of "
         f"{CHECK_RUNS} fresh random scenarios per stage; a stage is mastered at {TARGET:.0%} at full difficulty. "
         "The original brain is untouched; the candidate trained separately.", "", "## Progression", "",
         "| Skill | Stage reached | Mastered | Status |", "|---|---|---|---|"]
    for sk, stages in CURRICULUM.items():
        s = state["skills"][sk]
        done = [x for x in stages if x["id"] in state["mastered"]]
        status = "complete" if not s["stage"] else ("stalled" if s["stalled"] else f"working on it (ease {s['ease']:.2f})")
        at = BY_ID[s["stage"]]["title"] if s["stage"] else "-"
        L.append(f"| {SKILLS[sk]} | {at} | {len(done)} of {len(stages)} | {status} |")
    L += ["", "## Every stage", "",
          "| Stage | Attempts | Hardest ease needed | Mastered at gen | Forgotten | Before | After | Change |",
          "|---|---|---|---|---|---|---|---|"]
    for sk, stages in CURRICULUM.items():
        for k, st in enumerate(stages, 1):
            r = state["stages"][st["id"]]
            b, a = _rate(before, [st["id"]]), _rate(after, [st["id"]])
            change = "-" if a is None or b is None else f"{a - b:+.0%}"
            L.append(f"| {SKILLS[sk].split(' ')[0]} {k}: {st['title']} | {r['attempts']} | {r['ease_used']:.2f} | "
                     f"{r['mastered_at'] if r['mastered_at'] is not None else '-'} | {r['forgotten']} | "
                     f"{'-' if b is None else f'{b:.0%}'} | {'-' if a is None else f'{a:.0%}'} | {change} |")
    L += ["", "## Skills before and after (the same fixed scenarios for both brains)", "",
          "| Skill | Before | After | Change |", "|---|---|---|---|"]
    rows = []
    for sk, stages in CURRICULUM.items():
        ids = [x["id"] for x in stages]
        b, a = _rate(before, ids), _rate(after, ids)
        if b is None or a is None:
            continue
        n = sum(len(before[i]["runs"]) for i in ids)
        se = math.sqrt(_se(b, n) ** 2 + _se(a, n) ** 2)
        real = "real" if abs(a - b) > 2 * se else "within noise"
        rows.append((sk, a))
        L.append(f"| {SKILLS[sk]} | {b:.0%} | {a:.0%} | {a - b:+.0%} ({real}) |")
    if rows:
        rows.sort(key=lambda r: -r[1])
        L += ["", f"Strengths: {', '.join(SKILLS[r[0]] for r in rows[:2])}.  "
                  f"Weaknesses: {', '.join(SKILLS[r[0]] for r in rows[-2:])}."]
        weak = [BY_ID[sid]["title"] for sid, r in after.items() if r["pass"] < 0.34]
        if weak:
            L += ["", "Stages still failed most of the time: " + "; ".join(weak) + "."]
    if t:
        L += ["", "## Tournament benchmark (all cars, divisions of six)", "",
              f"{t['round']} rounds; every division races all five tracks, {t.get('laps', 5)} laps; TrueSkill ratings; "
              "points 10-7-5-3-2-1 per race.", "",
              "| # | Driver | Rating | +- | Races | Wins | Podiums | Avg place | Points per race | DNFs |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        from . import rating
        ranked = sorted(t["drivers"].items(), key=lambda kv: -(kv[1]["mu"] - 3 * kv[1]["sigma"]))
        for k, (key, r) in enumerate(ranked, 1):
            n = max(1, r["races"])
            bold = "**" if key.startswith("file:") else ""
            L.append(f"| {k} | {bold}{r['name']}{bold} | {rating.show(r['mu']):.0f} | {rating.SCALE * r['sigma']:.0f} | "
                     f"{r['races']} | {r['wins']} | {r['podiums']} | {r['places'] / n:.2f} | {r.get('points', 0) / n:.2f} | {r['dnf']} |")
        o = next(r for k, r in t["drivers"].items() if k.startswith("file:") and k.endswith("original"))
        c = next(r for k, r in t["drivers"].items() if k.startswith("file:") and k.endswith("candidate"))
        diff = rating.SCALE * (c["mu"] - o["mu"])
        se = rating.SCALE * math.sqrt(c["sigma"] ** 2 + o["sigma"] ** 2)
        verdict = ("better" if diff > 2 * se else "worse" if diff < -2 * se else "no different, within the uncertainty")
        pc, po = c["places"] / max(1, c["races"]), o["places"] / max(1, o["races"])
        L += ["", f"**Verdict:** the candidate is rated {diff:+.0f} against the original (+- {2 * se:.0f} for a real "
                  f"difference): **{verdict}**. Average place {po:.2f} -> {pc:.2f}; points per race "
                  f"{o.get('points', 0) / max(1, o['races']):.2f} -> {c.get('points', 0) / max(1, c['races']):.2f}."]
    path = academy.REPORT_DIR / f"{driver_id}-curriculum.md"
    academy.REPORT_DIR.mkdir(exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="The Racing Academy's progressive curriculum")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="train through the curriculum, benchmark in the tournament, write the report")
    r.add_argument("driver")
    r.add_argument("--generations", type=int, default=80)
    r.add_argument("--population", type=int, default=academy.POPULATION)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--rounds", type=int, default=8)
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
    course(args.driver, args.generations, args.population, args.workers, log)
    if not (folder(spec["id"]) / "tournament.json").exists() or \
            json.loads((folder(spec["id"]) / "tournament.json").read_text())["round"] < args.rounds:
        log("  tournament benchmark ...")
        benchmark(spec["id"], rounds=args.rounds, workers=args.workers, log=log)
    print(report(spec["id"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
