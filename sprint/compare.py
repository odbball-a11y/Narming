"""Race trained drivers against each other and compare how they race.

    python compare.py dave keith                  # 8 races on Speedway
    python compare.py dave keith speedway --races 12 --laps 3
    python compare.py dave:40 keith:40            # a particular generation

Each name is a training run (its latest champion unless :GEN is given).
Up to four drivers race; empty places are filled with scripted cars. Races
use a rolling start and the starting order rotates, so nobody always leads.
Prints wins, average place, passes, collisions caused and suffered, damage
and best lap for each driver.
"""
from __future__ import annotations

import argparse

import numpy as np

from ai import evolve, roster
from ai.evolve import RaceStats
from sim import tuning
from sim.race import FINISHED, Race
from sim.track import Track


def resolve(spec: str):
    run, _, gen = spec.partition(":")
    gens = evolve.list_generations(evolve.RUNS_DIR / run)
    if not gens:
        raise SystemExit(f"no trained run called '{run}'")
    gen = int(gen) if gen else gens[-1]
    return run, gen, roster.display_name(run) or run


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("drivers", nargs="+", help="training runs to race (RUN or RUN:GEN), up to 4")
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--races", type=int, default=8)
    ap.add_argument("--laps", type=int, default=3)
    args = ap.parse_args()
    if len(args.drivers) > 4:
        raise SystemExit("at most four drivers")

    racers = [resolve(spec) for spec in args.drivers]
    names = [f"{name} g{gen}" for _, gen, name in racers]
    names += ["Scripted"] * (4 - len(racers))
    rows = {name: {"wins": 0, "place": [], "passes": [], "caused": [], "suffered": [], "walls": [],
                   "damage": [], "draft": [], "best": []} for name in names}
    print(f"{args.races} races of {args.laps} laps on {args.track}, rolling start, rotating order\n")
    for k in range(args.races):
        order = [(i + k) % 4 for i in range(4)]          # car i starts in place order[i]
        entries = []
        for i, name in enumerate(names):
            if i < len(racers):
                run, gen, _ = racers[i]
                entries.append((order[i], roster.champion(run, gen, name)))
            else:
                entries.append((order[i], "scripted"))
        race = Race(args.track, entries, laps=args.laps, rolling=True, seed=k)
        stats = [RaceStats(race.world, me=i) for i in range(4)]
        while race.phase != FINISHED and race.world.tick < 300 * tuning.TICK_RATE:
            events = race.step()
            if race.phase != "countdown":
                for i, s in enumerate(stats):
                    if not race.world.cars[i].finished:
                        s.on_tick(events)
        result = {r["car"]: r for r in race.results()}
        line = []
        for i, name in enumerate(names):
            r, s, car = result[i], stats[i], race.world.cars[i]
            row = rows[name]
            row["wins"] += r["place"] == 1
            row["place"].append(r["place"])
            row["passes"].append(s.overtakes)
            row["caused"].append(s.fault)
            row["suffered"].append(s.suffered)
            row["walls"].append(s.walls)
            row["damage"].append(car.damage)
            row["draft"].append(s.draft_share())
            if r["best_lap"]:
                row["best"].append(r["best_lap"])
            line.append(f"{name.split(' g')[0][:14]} P{r['place']}")
        print(f"race {k + 1:2d}: " + ", ".join(line), flush=True)

    print(f"\n{'driver':24s} {'wins':>4s} {'avg pl':>6s} {'passes':>6s} {'caused':>6s} {'hit by':>6s} "
          f"{'walls':>5s} {'damage':>6s} {'draft':>5s} {'best lap':>8s}")
    for name, row in rows.items():
        best = f"{min(row['best']):8.2f}" if row["best"] else "     -  "
        print(f"{name[:24]:24s} {row['wins']:4d} {np.mean(row['place']):6.2f} {np.mean(row['passes']):6.2f} "
              f"{np.mean(row['caused']):6.2f} {np.mean(row['suffered']):6.2f} {np.mean(row['walls']):5.1f} "
              f"{np.mean(row['damage']) * 100:5.0f}% {np.mean(row['draft']) * 100:4.0f}% {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
