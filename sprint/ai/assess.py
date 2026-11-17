"""The Scouting Report: an objective assessment of a driver, independent of
any training score (phase 1 of weakness-led Upskilling; nothing is trained).

Every car sits the same battery of real-physics tests (`BATTERY`): solo laps
on every track, overtaking slower cars set from its own pace, defending
against a faster car, busy traffic, a full race against the house rivals,
recoveries and low grip, plus National, which no driver has trained on, as
an unseen check.  The battery runs twice with different seeds (A and B).

Measures are real quantities (seconds, contacts per race, share of slower
cars passed...), never invented points.  Each is placed against the whole
field (every assessed car) as a percentile.  A measure only names a strength
or a weakness when it is
- reliable: the A and B runs agree across the field (test-retest), and
- clearly away from the field median: by more than twice that measure's own
  A-B noise;
and validity (does the measure go with tournament results across the field?)
is checked when a field tournament has been run (`validate`).

    python -m ai.assess run NAME        # one car (re-scores the field)
    python -m ai.assess field           # every car
    python -m ai.assess validate        # field tournament + validity check
Files: scouting/<id>.json, scouting/field.json (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import academy, curriculum, evolve, stable

OUT = evolve.PROJECT / "scouting"
TRACKS = ["oval", "speedway", "esses", "technical", "grandprix"]
UNSEEN = "national"
SEEDS = {"A": 1, "B": 2}
HOUSE = curriculum.HOUSE


# -------------------------------------------------------------- the battery
# Each test: (id, area, builder(rng, ctx, track) -> variant, tracks)

def _solo(rng, ctx, t):
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 5 + 6, 1))


def _overtake(rng, ctx, t):
    styles = ["line", "defend"]
    rivals = [f"traffic:{curriculum._relative(rng, ctx, t, curriculum.PASS_PACE, 0.02):.3f}:{styles[k]}" for k in range(2)]
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 3 + 6, 1), rivals)


def _defend(rng, ctx, t):
    who = HOUSE[int(rng.integers(0, len(HOUSE)))]
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 3 + 6, 1), [f"house:{who}:1.06"], slot=0)


def _traffic(rng, ctx, t):
    styles = ("line", "defend", "wander")
    rivals = [f"traffic:{curriculum._relative(rng, ctx, t, 0.95, 0.03):.3f}:{styles[int(rng.integers(0, 3))]}"
              for _ in range(5)]
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 3 + 6, 1), rivals, slot=int(rng.integers(2, 6)))


def _race(rng, ctx, t):
    field = [f"house:{h}" if h != ctx.get("self") else "scripted" for h in rng.permutation(HOUSE)]   # never itself
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 4 + 6, 1), field, slot=int(rng.integers(0, 6)))


def _recover(rng, ctx, t):
    return academy._v(t, 12, start=curriculum._trouble(rng, 0.45, 6.5, 1.0))


def _grip(rng, ctx, t):
    return academy._v(t, round(stable.SCRIPTED_LAPS[t] * 3 + 6, 1), grip=0.8)


BATTERY = [("solo", "pace", _solo, TRACKS + [UNSEEN]), ("overtake", "overtaking", _overtake, TRACKS + [UNSEEN]),
           ("defend", "defending", _defend, TRACKS), ("traffic", "awareness", _traffic, TRACKS),
           ("race", "racing", _race, TRACKS), ("recover", "recovery", _recover, TRACKS),
           ("grip", "adverse", _grip, TRACKS)]


def _job(job):
    weights, arch, traits, test, track, seed, ctx = job
    builder = next(b for t, _, b, _ in BATTERY if t == test)
    v = builder(np.random.default_rng([seed, TRACKS.index(track) if track in TRACKS else 9, len(test)]), ctx, track)
    m = academy.run_variant(weights, arch, traits, v, rep=seed)
    m = curriculum.derived(m, track, ctx)
    m["minutes"] = v["seconds"] / 60.0
    return test, track, m


def battery(weights, arch, traits, ctx, seed: int, pool=None) -> list:
    jobs = [(weights, arch, traits, test, t, seed, ctx) for test, _, _, tracks in BATTERY for t in tracks]
    return list(pool.map(_job, jobs) if pool else map(_job, jobs))


# ------------------------------------------------------------- the measures
# (key, area, label, unit, better: "low" | "high", from runs)

def _avg(runs, test, key, tracks=TRACKS):
    vals = [m[key] for t, tr, m in runs if t == test and tr in tracks and m.get(key) is not None]
    return float(np.mean(vals)) if vals else None


def _ratio(runs, test, num, den, tracks=TRACKS):
    """Sum of `num` over sum of `den` across the test's runs (None when `den`
    never happened: a car that never tries is not measured, not praised)."""
    rows = [m for t, tr, m in runs if t == test and tr in tracks]
    total = sum(den(m) for m in rows)
    return float(sum(num(m) for m in rows) / total) if total > 0 else None


def _per_min(runs, test, key):
    rows = [(m[key], m["minutes"]) for t, tr, m in runs if t == test and tr in TRACKS and m.get(key) is not None]
    return float(sum(v for v, _ in rows) / max(1e-9, sum(mn for _, mn in rows))) if rows else None


MEASURES = [
    ("pace", "pace", "lap pace v the scripted car (same car)", "x", "low", lambda r: _avg(r, "solo", "pace")),
    ("lap_spread", "consistency", "lap-time spread", "%", "low", lambda r: _avg(r, "solo", "lap_cv")),
    ("offtrack", "consistency", "time off the tarmac", "%", "low", lambda r: _avg(r, "solo", "offtrack")),
    ("walls_per_min", "mistakes", "barrier hits per minute alone", "", "low", lambda r: _per_min(r, "solo", "walls")),
    ("solo_damage", "mistakes", "damage alone", "%", "low", lambda r: _avg(r, "solo", "damage")),
    ("pass_share", "overtaking", "share of slower cars passed cleanly", "%", "high",
     lambda r: (_avg(r, "overtake", "clean_passes") or 0.0) / 2.0),
    ("forced_passes", "overtaking", "share of passes made with contact", "%", "low",
     lambda r: _ratio(r, "overtake", lambda m: max(0, m["passes"] - m["clean_passes"]), lambda m: m["passes"])),
    ("overtake_caused", "overtaking", "contacts caused per slower car caught", "", "low",
     lambda r: _ratio(r, "overtake", lambda m: m["fault"], lambda m: m["reached"])),
    ("places_lost", "defending", "places lost to a faster car, per race", "", "low", lambda r: _avg(r, "defend", "passed")),
    ("weaves", "defending", "weaves while defending, per race", "", "low", lambda r: _avg(r, "defend", "weaves")),
    ("traffic_caused", "awareness", "contacts caused in traffic, per race", "", "low", lambda r: _avg(r, "traffic", "fault")),
    ("tailgate", "awareness", "time tailgating in traffic", "%", "low", lambda r: _avg(r, "traffic", "tailgate")),
    ("traffic_damage", "awareness", "damage in traffic", "%", "low", lambda r: _avg(r, "traffic", "damage")),
    ("race_place", "racing", "place in a six-car race with the house rivals", "", "low", lambda r: _avg(r, "race", "place")),
    ("race_damage", "racing", "damage in that race", "%", "low", lambda r: _avg(r, "race", "damage")),
    ("recover_time", "recovery", "seconds to recover from a big moment", "s", "low",
     lambda r: _avg(r, "recover", "recovered")),
    ("recover_walls", "recovery", "barrier hits after a big moment", "", "low", lambda r: _avg(r, "recover", "walls")),
    ("grip_pace", "adverse", "lap pace on a greasy track (same car)", "x", "low", lambda r: _avg(r, "grip", "pace")),
    ("grip_offtrack", "adverse", "time off the tarmac when greasy", "%", "low", lambda r: _avg(r, "grip", "offtrack")),
    ("unseen_pace", "unseen", "lap pace at National (never trained there)", "x", "low",
     lambda r: _avg(r, "solo", "pace", [UNSEEN])),
    ("unseen_pass", "unseen", "share of slower cars passed cleanly at National", "%", "high",
     lambda r: (_avg(r, "overtake", "clean_passes", [UNSEEN]) or 0.0) / 2.0),
]
BY_KEY = {m[0]: m for m in MEASURES}


def measures(runs) -> dict:
    out = {}
    for key, *_, fn in MEASURES:
        v = fn(runs)
        out[key] = None if v is None else round(v, 4)
    return out


# --------------------------------------------------------------- assessing

def path(driver_id: str) -> Path:
    return OUT / f"{driver_id}.json"


def assess(name: str, workers: int = 4, log=print) -> dict:
    """Run the battery twice (seeds A and B) and save the raw measures."""
    from . import migrate
    migrate.ensure()
    spec = academy.driver_spec(name)
    ctx = curriculum.measure(spec["weights"], spec["arch"], spec["traits"])
    ctx["self"] = spec["id"]
    for t in [UNSEEN]:                                  # the unseen track's laps too
        from ai.brain import NeuralDriver
        from sim import cartraits
        d = NeuralDriver(spec["weights"], spec["arch"], "Learner")
        d.car_params = cartraits.params_for(spec["traits"] or cartraits.default())
        ctx["scripted"][t] = round(curriculum.scripted_lap(t, spec["traits"]), 3)
        ctx["laps"][t] = round(curriculum._median_lap(t, d) or ctx["scripted"][t], 3)
        curriculum.traffic_laps(t)
    for t in TRACKS:
        curriculum.traffic_laps(t)
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        out = {"id": spec["id"], "name": spec["name"], "kind": spec["kind"], "ctx": ctx, "runs": {}, "measures": {}}
        for label, seed in SEEDS.items():
            log(f"  {spec['name']}: battery {label} ...")
            runs = battery(spec["weights"], spec["arch"], spec["traits"], ctx, seed, pool)
            out["runs"][label] = [[t, tr, m] for t, tr, m in runs]
            out["measures"][label] = measures(runs)
    finally:
        if pool:
            pool.shutdown()
    OUT.mkdir(exist_ok=True)
    path(spec["id"]).write_text(json.dumps(out, indent=1))
    return out


def everyone() -> list[str]:
    """Every car with a brain: house rivals, guests and the stable's racers."""
    names = [c["name"] for c in stable.house_rivals()] + [g["name"] for g in stable.guests()]
    root = stable.STABLE_DIR
    for d in stable.list_racers(root, include_dead=True) if root.exists() else []:
        if stable.brain_file(d) is not None and not stable.is_breeding(d) and not stable.is_house_stud(d):
            names.append(stable.load(d)["name"])
    return names


# ----------------------------------------------------------- field scoring

def _corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _rank(v):
    return np.argsort(np.argsort(v)).astype(float)


RELIABLE = 0.5         # test-retest correlation (A v B across the field) a measure needs
MIN_FIELD = 5          # cars needed before reliability means anything
MIN_VALIDITY = 8       # cars needed before a validity check means anything


def field() -> dict:
    """Score every assessed car against the field: per measure the field's
    values, test-retest reliability, A-B noise, percentiles, strengths and
    weaknesses.  Saved as scouting/field.json."""
    cars = {}
    for f in sorted(OUT.glob("*.json")) if OUT.exists() else []:
        if f.name in ("field.json", "tournament.json", "validity.json"):
            continue
        car = json.loads(f.read_text())
        car["measures"] = {k: measures(v) for k, v in car["runs"].items()}   # rescored from the saved runs
        cars[f.stem] = car
    validity = json.loads((OUT / "validity.json").read_text()) if (OUT / "validity.json").exists() else {}
    stats = {}
    for key, area, label, unit, better, _ in MEASURES:
        a = {c: d["measures"]["A"].get(key) for c, d in cars.items()}
        b = {c: d["measures"]["B"].get(key) for c, d in cars.items()}
        both = [c for c in cars if a[c] is not None and b[c] is not None]
        r = _corr([a[c] for c in both], [b[c] for c in both]) if len(both) >= MIN_FIELD else None
        noise = float(np.mean([abs(a[c] - b[c]) for c in both]) / math.sqrt(2)) if both else 0.0
        value = {c: (a[c] + b[c]) / 2 for c in both}
        median = float(np.median(list(value.values()))) if value else None
        stats[key] = {"reliability": None if r is None else round(r, 2), "reliable": r is not None and r >= RELIABLE,
                      "noise": round(noise, 4), "median": median, "values": value, "validity": validity.get(key)}
    report = {}
    for c in cars:
        rows = []
        for key, area, label, unit, better, _ in MEASURES:
            st = stats[key]
            v = st["values"].get(c)
            if v is None:
                continue
            others = [x for k, x in st["values"].items() if k != c]
            beat = sum((v < x) if better == "low" else (v > x) for x in others) + 0.5 * sum(v == x for x in others)
            pct = beat / len(others) if others else 0.5
            # The car's own value is the mean of two runs: its noise is noise / sqrt(2).
            away = abs(v - st["median"]) > 2 * st["noise"] / math.sqrt(2) + 1e-9
            valid = st["validity"] is None or st["validity"].get("valid", True)
            tag = None
            if st["reliable"] and away and valid:
                good = (v < st["median"]) if better == "low" else (v > st["median"])
                tag = "strength" if good else "weakness"
            rows.append({"key": key, "area": area, "label": label, "unit": unit, "value": round(v, 4),
                         "percentile": round(pct, 2), "tag": tag, "reliable": st["reliable"],
                         "reliability": st["reliability"], "noise": st["noise"]})
        report[c] = {"name": cars[c]["name"], "rows": rows}
    out = {"cars": len(cars), "measures": {k: {x: y for x, y in v.items() if x != "values"} for k, v in stats.items()},
           "report": report}
    OUT.mkdir(exist_ok=True)
    (OUT / "field.json").write_text(json.dumps(out, indent=1))
    return out


def validate(rounds: int = 6, laps: int = 5, workers: int = 4, log=print) -> dict:
    """Validity: run a tournament of the assessed field (league.run_league) and
    correlate each measure with points per race across the cars (rank
    correlation).  A measure is valid when it goes with results in the
    expected direction (rho >= 0.3); with fewer than MIN_VALIDITY cars the
    check is marked inconclusive and nothing is ruled out."""
    import league
    cars = {f.stem: json.loads(f.read_text()) for f in OUT.glob("*.json")
            if f.name not in ("field.json", "tournament.json", "validity.json")}
    keys = {k: v for k, v in league.drivers().items() if k.split(":", 1)[1] in cars}
    t = league.run_league(keys, rounds=rounds, laps=laps, workers=workers, save=OUT / "tournament.json", log=log)
    ppr = {k.split(":", 1)[1]: d["points"] / max(1, d["races"]) for k, d in t["drivers"].items()}
    out = {}
    for key, area, label, unit, better, _ in MEASURES:
        both = [c for c in cars if c in ppr and cars[c]["measures"]["A"].get(key) is not None]
        vals = [(cars[c]["measures"]["A"][key] + cars[c]["measures"]["B"][key]) / 2 for c in both]
        rho = _corr(_rank(vals), _rank([ppr[c] for c in both])) if len(both) >= 3 else None
        if rho is not None and better == "low":
            rho = -rho                                   # lower is better: positive rho = goes with results
        enough = len(both) >= MIN_VALIDITY
        out[key] = {"rho": None if rho is None else round(rho, 2), "cars": len(both),
                    "valid": (rho is None or rho >= 0.3) if enough else True, "conclusive": enough}
    (OUT / "validity.json").write_text(json.dumps(out, indent=1))
    field()
    return out


def report_text(driver_id: str) -> str:
    f = json.loads((OUT / "field.json").read_text())
    r = f["report"][driver_id]
    L = [f"# Scouting report: {r['name']}", "",
         f"Assessed against {f['cars']} cars, two runs of the same battery with different seeds.  Percentile = share "
         "of the field this car does better than.  A strength or weakness needs a reliable measure and a value clearly "
         "away from the field median (more than twice its run-to-run noise).", "",
         "| Area | Measure | Value | Field percentile | Verdict |", "|---|---|---|---|---|"]
    for row in r["rows"]:
        v = row["value"]
        shown = f"{v:.0%}" if row["unit"] == "%" else (f"{v:.3f}" if row["unit"] == "x" else f"{v:.2f}{row['unit']}")
        verdict = row["tag"] or ("not reliable yet" if not row["reliable"] else "-")
        L.append(f"| {row['area']} | {row['label']} | {shown} | {row['percentile']:.0%} | {verdict} |")
    strengths = [x["label"] for x in r["rows"] if x["tag"] == "strength"]
    weaknesses = [x["label"] for x in r["rows"] if x["tag"] == "weakness"]
    L += ["", f"**Strengths:** {', '.join(strengths) or 'none clear'}.", f"**Weaknesses:** {', '.join(weaknesses) or 'none clear'}."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Scouting reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="assess one car, then re-score the field")
    r.add_argument("driver")
    r.add_argument("--workers", type=int, default=4)
    f = sub.add_parser("field", help="assess every car")
    f.add_argument("--workers", type=int, default=4)
    v = sub.add_parser("validate", help="field tournament and the validity check")
    v.add_argument("--rounds", type=int, default=6)
    v.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    log = lambda m: print(m, flush=True)
    if args.cmd == "run":
        out = assess(args.driver, args.workers, log)
        field()
        print(report_text(out["id"]))
    elif args.cmd == "field":
        for name in everyone():
            assess(name, args.workers, log)
        field()
        print(f"saved: {OUT / 'field.json'}")
    else:
        print(json.dumps(validate(args.rounds, workers=args.workers, log=log), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
