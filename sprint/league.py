"""A league of every brain there is: your stable's racers (racing, retired
and dead), the house rivals and the guests, in divisions of six with
promotion and relegation.

    python league.py [--rounds 10] [--laps 5] [--workers 4] [--fresh]

A season: every division races each of the five tracks once (points
10-7-5-3-2-1).  At the end of the season the top two of each division go up
and the bottom two go down (the top division has no one above, the bottom
none below).  The first season's divisions are drawn by rating (at random
when there is none); a car joining later starts in the bottom division.
TrueSkill is updated after every race across all divisions, as the fair
overall measure (it allows for who a car beat); a rating counts as settled
once its uncertainty is at most SETTLED points, before that it is provisional.
Nothing in the stable is changed.  Resumable (`--rounds` = seasons to add);
results in league/league.json and league/TABLE.md.
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
MOVE = 2               # promoted and relegated per division each season
SETTLED = 40.0         # a rating's +- (displayed points) at or under which it counts as settled


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
    if kind == "file":                               # a brain saved as <path>.npz + <path>.json (e.g. an Academy candidate)
        import numpy as np
        from ai import evolve
        from ai.brain import NeuralDriver
        from sim import cartraits
        base = evolve.resolve_path(rid)
        card = json.loads(base.with_suffix(".json").read_text())
        with np.load(base.with_suffix(".npz")) as data:
            w = data["pop"][0].astype(np.float64)
        d = NeuralDriver(w, card["arch"], card["name"])
        d.car_params = cartraits.params_for(card.get("traits") or cartraits.default())
        d.livery = card.get("livery")
        return d
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


def settled(d: dict) -> bool:
    from ai import rating
    return rating.SCALE * d["sigma"] <= SETTLED


def divisions_of(state: dict, keys: list[str]) -> list[list[str]]:
    """The divisions for the coming season.  Kept from the last season (cars
    that left are dropped; new cars join the bottom division), or, the first
    time, drawn by rating (randomly when everyone is new)."""
    known = [k for div in state.get("divisions", []) for k in div if k in keys]
    new = [k for k in keys if k not in known]
    if not known:
        rng = random.Random(len(keys))
        new = rng.sample(new, len(new))
        new.sort(key=lambda k: -state["drivers"][k]["mu"])
    order = known + new
    divs = [order[i:i + SIZE] for i in range(0, len(order), SIZE)]
    if len(divs) > 1 and len(divs[-1]) < 3:              # no tiny last division
        divs[-2:] = [divs[-2] + divs[-1]]
    return divs


def promote_relegate(divs: list[list[str]], season_points: dict, wins: dict, places: dict) -> tuple[list, list]:
    """Standings within each division (points, then wins, then total places),
    then the top MOVE of each division swap with the bottom MOVE of the one
    above.  Returns (new divisions, standings per division)."""
    tables = [sorted(div, key=lambda k: (-season_points.get(k, 0), -wins.get(k, 0), places.get(k, 0), k))
              for div in divs]
    new = [list(t) for t in tables]
    for d in range(len(tables) - 1):
        n = min(MOVE, len(tables[d]) // 2, len(tables[d + 1]) // 2)
        down = tables[d][-n:]
        up = tables[d + 1][:n]
        new[d] = [k for k in new[d] if k not in down] + up
        new[d + 1] = down + [k for k in new[d + 1] if k not in up]
    return new, tables


def table(state: dict) -> str:
    from ai import rating
    L = [f"# League after {state['round']} seasons", ""]
    last = state.get("seasons", [])[-1] if state.get("seasons") else None
    if last:
        for d, rows in enumerate(last["tables"], 1):
            L += [f"## Division {d} (season {last['season']})", "",
                  "| Pos | Driver | Season points | Wins | Movement |", "|---|---|---|---|---|"]
            for pos, k in enumerate(rows, 1):
                move = "promoted" if k in last["promoted"] else "relegated" if k in last["relegated"] else ""
                L.append(f"| {pos} | {state['drivers'][k]['name']} | {last['points'].get(k, 0)} | "
                         f"{last['wins'].get(k, 0)} | {move} |")
            L.append("")
    L += ["## Ratings (all seasons)", "", "TrueSkill: allows for who each car raced. Provisional until the +- is at most "
          f"{SETTLED:.0f}.", "", "| # | Driver | Division | Rating | +- | Races | Wins | Podiums | Points per race | DNFs |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    rows = sorted(state["drivers"].items(), key=lambda kv: -(kv[1]["mu"] - 3 * kv[1]["sigma"]))
    div_of = {k: d + 1 for d, div in enumerate(state.get("divisions", [])) for k in div}
    for n, (k, d) in enumerate(rows, start=1):
        races = max(1, d["races"])
        shown = f"{rating.show(d['mu']):.0f}" + ("" if settled(d) else " (provisional)")
        L.append(f"| {n} | {d['name']} | {div_of.get(k, '-')} | {shown} | {rating.SCALE * d['sigma']:.0f} | {d['races']} | "
                 f"{d['wins']} | {d['podiums']} | {d.get('points', 0) / races:.2f} | {d['dnf']} |")
    return "\n".join(L) + "\n"


def run_league(entries: dict, rounds: int = 10, laps: int = 5, workers: int = 4, save: Path | None = None,
               fresh: bool = False, log=print) -> dict:
    """Race `entries` ({key: {"name", "status"}}) season by season up to
    `rounds` seasons in all, with promotion and relegation; resumable from `save`.
    Returns the state."""
    from ai import championship, rating
    save = Path(save or OUT / "league.json")
    save.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(save.read_text()) if save.exists() and not fresh else {"round": 0, "drivers": {}}
    state["laps"] = laps
    for key, d in entries.items():                         # new brains join; old results are kept
        state["drivers"].setdefault(key, {"mu": rating.ENV.mu, "sigma": rating.ENV.sigma, "races": 0, "wins": 0,
                                          "podiums": 0, "places": 0, "dnf": 0, "points": 0}).update(d)
    keys = [k for k in state["drivers"] if k in entries]
    if len(keys) < 2:
        raise ValueError("need at least two drivers")
    log(f"{len(keys)} drivers, seasons of {len(championship.TRACK_ORDER)} races, {laps} laps")
    pool = Pool(workers) if workers > 1 else None
    try:
        while state["round"] < rounds:
            season = state["round"] + 1
            rng = random.Random(season)
            divs = divisions_of(state, keys)
            points, wins, places = {}, {}, {}
            for t, track in enumerate(championship.TRACK_ORDER):
                jobs = [(track, rng.sample(div, len(div)), laps, season * 100 + t * 10 + n) for n, div in enumerate(divs)]
                for _, rows in (pool.map(run_race, jobs) if pool else map(run_race, jobs)):
                    rows.sort(key=lambda r: r[1])
                    last = max(r[1] for r in rows)
                    ranks = [r[1] if r[2] else last for r in rows]
                    groups = [(rating.ENV.create_rating(state["drivers"][r[0]]["mu"], state["drivers"][r[0]]["sigma"]),)
                              for r in rows]
                    for (k, place, fin, _), (new,) in zip(rows, rating.ENV.rate(groups, ranks=ranks)):
                        d = state["drivers"][k]
                        d["mu"], d["sigma"] = new.mu, new.sigma
                        got = championship.POINTS[min(place, len(championship.POINTS)) - 1] if fin else 0
                        d["races"] += 1
                        d["wins"] += fin and place == 1
                        d["podiums"] += fin and place <= 3
                        d["places"] += place
                        d["dnf"] += not fin
                        d["points"] = d.get("points", 0) + got
                        points[k] = points.get(k, 0) + got
                        wins[k] = wins.get(k, 0) + (fin and place == 1)
                        places[k] = places.get(k, 0) + place
            new_divs, tables = promote_relegate(divs, points, wins, places)
            before = {k: d for d, div in enumerate(tables) for k in div}
            after = {k: d for d, div in enumerate(new_divs) for k in div}
            moved_up = [k for k in after if after[k] < before[k]]
            moved_down = [k for k in after if after[k] > before[k]]
            state.setdefault("seasons", []).append({"season": season, "tables": tables, "points": points, "wins": wins,
                                                    "promoted": moved_up, "relegated": moved_down})
            state["divisions"] = new_divs
            state["round"] = season
            save.write_text(json.dumps(state, indent=1))
            top = tables[0][:3]
            log(f"season {season}: division 1 won by {state['drivers'][top[0]]['name']}; "
                f"up: {', '.join(state['drivers'][k]['name'] for k in moved_up) or '-'}; "
                f"down: {', '.join(state['drivers'][k]['name'] for k in moved_down) or '-'}")
    finally:
        if pool:
            pool.close()
            pool.join()
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rounds", type=int, default=10, help="seasons to add")
    ap.add_argument("--laps", type=int, default=5)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fresh", action="store_true", help="start the league again")
    args = ap.parse_args()
    from ai import migrate
    migrate.ensure()
    OUT.mkdir(exist_ok=True)
    save = OUT / "league.json"
    done = json.loads(save.read_text())["round"] if save.exists() and not args.fresh else 0
    try:
        state = run_league(drivers(), rounds=done + args.rounds, laps=args.laps, workers=args.workers, save=save,
                           fresh=args.fresh, log=lambda m: print(m, flush=True))
    except ValueError as e:
        print(e)
        return 1
    (OUT / "TABLE.md").write_text(table(state), encoding="utf-8")
    print(table(state))
    print(f"saved: {OUT / 'TABLE.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
