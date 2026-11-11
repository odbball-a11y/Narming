"""Breed AI drivers, generation by generation, in two phases.

    python train.py                          # 50 more generations of run "default"
    python train.py --generations 200
    python train.py --run big --hidden 32 32 --memory 8     # a separate run, bigger brain
    python train.py --run plain --no-race-bonuses           # results-only scoring
    python train.py --run long --race-laps 3                # longer training races
    python train.py --workers 4                             # use 4 CPU cores

Training camps start from an existing run's drivers and give them a racing
personality:

    python train.py --run dave --from speedway --style aggressive --name "Dangerous Dave"
    python train.py --run keith --from speedway --style cautious --name "Careful Keith"

Phase 1, driving school: the whole generation drives the track as ghosts.
Phase 2, racing school: real races with collisions, damage and drafting, from
every grid position, against scripted cars and the AI's own champions.

Progress is saved after every generation in training/<run>/, so you can stop
with Ctrl+C and continue later with the same command.  Network and scoring
settings are fixed when a run is created.  Leave this running and open the
game (python -m game, then AI LAB) in another terminal to watch.
"""
from __future__ import annotations

import argparse
import os
import time

from ai import evolve
from ai.brain import DEFAULT_ARCH, describe
from sim.track import Track


def fmt(value, spec="6.2f") -> str:
    return format(value, spec) if value is not None else "  -   "


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="default", help="name of the training run")
    ap.add_argument("--generations", type=int, default=50, help="how many more to breed")
    ap.add_argument("--population", type=int, default=80, help="drivers per generation (new runs)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tracks", nargs="+", default=None, choices=Track.available())
    ap.add_argument("--hidden", type=int, nargs="+", default=None,
                    help="hidden layer sizes (new runs), e.g. --hidden 32 32")
    ap.add_argument("--memory", type=int, default=None,
                    help="memory values the network carries between decisions (new runs; 0 = none)")
    ap.add_argument("--races", type=int, default=None,
                    help="racing-school races per driver per track (new runs; default 2, or the --from run's)")
    ap.add_argument("--from", dest="start_from", metavar="RUN[:GEN]",
                    help="training camp: start a new run from another run's drivers (its latest "
                         "generation unless GEN is given), straight into racing school")
    ap.add_argument("--style", choices=["balanced", "aggressive", "cautious"], default=None,
                    help="racing personality for a new run (how its races are scored)")
    ap.add_argument("--name", help="racer name shown in the game for a new run")
    ap.add_argument("--race-laps", type=float, default=None,
                    help="length of racing-school races in laps (new runs; default about 2). Longer races "
                         "make crashes cost more but each generation takes longer")
    ap.add_argument("--no-race-bonuses", action="store_true",
                    help="score racing school on results only, no early bonuses for overtaking and "
                         "drafting (new runs)")
    ap.add_argument("--racing-from", type=int, default=None, metavar="GEN",
                    help="start racing school at this generation (new runs; default: automatically "
                         "once the champion laps cleanly)")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="CPU cores to use")
    args = ap.parse_args()

    run_dir = evolve.RUNS_DIR / args.run
    print(f"run '{args.run}' in {run_dir}")
    clock = [time.perf_counter()]

    def report(entry):
        now = time.perf_counter()
        cells = []
        for name, e in entry["exam"].items():
            place = f"P{e['race_place']}" if e["race_finished"] else "DNF"
            cells.append(f"{name[:5]} lap {fmt(e['solo_best_lap'])} race {place:>3} "
                         f"pass {e['race_overtakes']} hit {e['race_fault']:g} dmg {e['race_damage'] * 100:2.0f}%")
        school = "racing " if entry["mode"] == "race" else "driving"
        print(f"gen {entry['gen']:3d} {school} best {entry['best']:5.2f} avg {entry['mean']:5.2f} | "
              + " | ".join(cells) + f"  ({now - clock[0]:.0f}s)", flush=True)
        clock[0] = now

    arch = None
    if args.hidden is not None or args.memory is not None:
        arch = {"hidden": args.hidden or DEFAULT_ARCH["hidden"],
                "memory": DEFAULT_ARCH["memory"] if args.memory is None else args.memory}
    try:
        evolve.train(run=args.run, generations=args.generations, population=args.population,
                     seed=args.seed, tracks=args.tracks, phase2_from=args.racing_from, arch=arch,
                     races_per_track=args.races, race_bonuses=False if args.no_race_bonuses else None,
                     race_laps=args.race_laps, start_from=args.start_from, style=args.style,
                     name=args.name,
                     workers=args.workers, on_generation=report,
                     log=lambda m: print(m, flush=True))
        config = evolve.load_config(run_dir)
        if config.get("name"):
            print(f"racer {config['name']} ({config.get('style')}), from {config.get('parent')}")
        print(f"network {describe(config['arch'])}; race bonuses "
              f"{'on' if config['race_bonuses'] else 'off'}; racing school from generation "
              f"{config.get('phase2_start') or '(not yet)'}")
    except KeyboardInterrupt:
        print("\nstopped; run the same command to continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
