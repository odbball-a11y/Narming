"""Rate every brain there is: your stable's racers (racing, retired and dead),
the house rivals and the guests, in divisions of six.

    python league.py [--rounds 10] [--laps 5] [--workers 4]

Each round the drivers are split into divisions of six by rating (random the
first time), each division races every track once, TrueSkill is updated after
every race (non-finishers share last), and the divisions are redrawn, so the
best end up racing each other.  Nothing in the stable is changed: no careers,
ratings or records.  Resumable; results in league/league.json and league/TABLE.md.
"""
from __future__ import annotations

import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "league"
SIZE = 6


def drivers() -> dict:
    """{key: {"name", "status"}} for everything with a brain."""
    from ai import stable
    out = {}
    for c in stable.house_rivals():
        out[f"house:{c['id']}"] = {"name": c["name"], "status": "house rival"}
    for g in stable.guests():
        out[f"guest:{g['id']}"] = {"name": g["name"], "status": "guest"}
    root = stable.STABLE_DIR
    for d in stable.list_racers(root, include_dead=True) if root.exists() else []:
        if stable.brain_file(d) is None or stable.is_breeding(d) or stable.is_house_stud(d):
            continue
        state = stable.status(d)
        out[f"racer:{d.name}"] = {"name": stable.load(d)["name"],
                                  "status": {"racing": "racing", "stud": "retired", "dead": "dead"}.get(state, state)}
    return out


def make(key: str):
    from ai import stable
    kind, rid = key.split(":", 1)
    if kind == "house":
        return stable.house_driver(rid)
    if kind == "guest":
        return stable.guest_driver(rid)
    return stable.champion(stable.STABLE_DIR / rid)


def run_race(job):
    """One race; returns [(key, place, finished, best_lap)]."""
    track, keys, laps, seed = job
    import sim.scripted  # noqa: F401
    from sim.race import Race
    race = Race(track, [(slot, make(k)) for slot, k in enumerate(keys)], laps=laps, seed=seed,
                rolling=True).run(max_seconds=120 * laps)
    return track, [(keys[r["car"]], r["place"], bool(r["finished"]), r.get("best_lap")) for r in race.results()]


def table(state: dict) -> str:
    from ai import rating
    rows = sorted(state["drivers"].items(), key=lambda kv: -(kv[1]["mu"] - 3 * kv[1]["sigma"]))
    lines = [f"# League after {state['round']} rounds", "",
             "Ranked by the cautious rating (rating minus three times its uncertainty).", "",
             "| # | Driver | Status | Rating | +- | Races | Wins | Podiums | Avg place | DNFs |", "|---|---|---|---|---|---|---|---|---|---|"]
    for n, (_, d) in enumerate(rows, start=1):
        races = max(1, d["races"])
        lines.append(f"| {n} | {d['name']} | {d['status']} | {rating.show(d['mu']):.0f} | {rating.SCALE * d['sigma']:.0f} | "
                     f"{d['races']} | {d['wins']} | {d['podiums']} | {d['places'] / races:.2f} | {d['dnf']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--laps", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fresh", action="store_true", help="start the league again")
    args = ap.parse_args()
    from ai import championship, migrate, rating
    migrate.ensure()
    OUT.mkdir(exist_ok=True)
    save = OUT / "league.json"
    state = json.loads(save.read_text()) if save.exists() and not args.fresh else {"round": 0, "drivers": {}}
    for key, d in drivers().items():                       # new brains join; old results are kept
        state["drivers"].setdefault(key, {"mu": rating.ENV.mu, "sigma": rating.ENV.sigma, "races": 0, "wins": 0,
                                          "podiums": 0, "places": 0, "dnf": 0}).update(d)
    live = set(drivers())
    keys = [k for k in state["drivers"] if k in live]
    if len(keys) < 2:
        print("need at least two trained drivers")
        return 1
    print(f"{len(keys)} drivers, {args.rounds} rounds of {len(championship.TRACK_ORDER)} races, {args.laps} laps")
    with Pool(args.workers) as pool:
        for _ in range(args.rounds):
            rnd = state["round"] + 1
            rng = random.Random(rnd)
            order = sorted(keys, key=lambda k: -state["drivers"][k]["mu"]) if rnd > 1 else rng.sample(keys, len(keys))
            if rnd > 1 and rnd % 3 == 0:                   # every third round is a random draw, to mix the divisions
                order = rng.sample(keys, len(keys))
            divisions = [order[i:i + SIZE] for i in range(0, len(order), SIZE)]
            if len(divisions) > 1 and len(divisions[-1]) < 3:      # no tiny last division
                divisions[-2:] = [divisions[-2] + divisions[-1]]
            for t, track in enumerate(championship.TRACK_ORDER):
                jobs = [(track, rng.sample(div, len(div)), args.laps, rnd * 100 + t * 10 + n)
                        for n, div in enumerate(divisions)]
                for _, rows in pool.map(run_race, jobs):
                    rows.sort(key=lambda r: r[1])
                    last = max(r[1] for r in rows)
                    ranks = [r[1] if r[2] else last for r in rows]
                    groups = [(rating.ENV.create_rating(state["drivers"][r[0]]["mu"], state["drivers"][r[0]]["sigma"]),)
                              for r in rows]
                    for (k, place, fin, _), (new,) in zip(rows, rating.ENV.rate(groups, ranks=ranks)):
                        d = state["drivers"][k]
                        d["mu"], d["sigma"] = new.mu, new.sigma
                        d["races"] += 1
                        d["wins"] += fin and place == 1
                        d["podiums"] += fin and place <= 3
                        d["places"] += place
                        d["dnf"] += not fin
            state["round"] = rnd
            save.write_text(json.dumps(state, indent=1))
            (OUT / "TABLE.md").write_text(table(state), encoding="utf-8")
            top = sorted(keys, key=lambda k: -state["drivers"][k]["mu"])[:3]
            print(f"round {rnd}: " + ", ".join(f"{state['drivers'][k]['name']} {rating.show(state['drivers'][k]['mu']):.0f}"
                                               for k in top), flush=True)
    print(table(state))
    print(f"saved: {OUT / 'TABLE.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
