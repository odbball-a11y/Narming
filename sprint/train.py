"""Breed AI drivers, generation by generation.

    python train.py                       # 50 more generations of run "default"
    python train.py --generations 200
    python train.py --run fresh --seed 3  # start a separate run
    python train.py --workers 4           # use 4 CPU cores

Progress is saved after every generation in training/<run>/, so you can stop
with Ctrl+C and continue later with the same command.  Leave this running and
open the game (python -m game, then AI LAB) in another terminal to watch each
generation drive and see the charts update.
"""
from __future__ import annotations

import argparse
import os
import time

from ai import evolve
from sim.track import Track


def fmt_lap(value) -> str:
    return f"{value:6.2f}" if value is not None else "   -  "


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="default", help="name of the training run")
    ap.add_argument("--generations", type=int, default=50, help="how many more to breed")
    ap.add_argument("--population", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tracks", nargs="+", default=None, choices=Track.available())
    ap.add_argument("--race-from", type=int, default=None, metavar="GEN",
                    help="generation at which tests switch from solo ghosts to real races "
                         "(default: automatically, once the champion laps cleanly)")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1),
                    help="CPU cores to use")
    args = ap.parse_args()

    print(f"run '{args.run}' in {evolve.RUNS_DIR / args.run}")
    print("gen  test   best   mean | " + " | ".join(
        f"{t[:9]:>9}: lap   race pos hits dmg" for t in (args.tracks or Track.available())))
    clock = [time.perf_counter()]

    def report(entry):
        now = time.perf_counter()
        cells = []
        for name, e in entry["exam"].items():
            place = f"P{e['race_place']}" if e["race_finished"] else "DNF"
            cells.append(f"{'':>9} {fmt_lap(e['solo_best_lap'])}  {place:>4} {e['race_hits']:4d} "
                         f"{e['race_damage'] * 100:3.0f}%")
        print(f"{entry['gen']:3d}  {entry['mode']:4s} {entry['best']:6.3f} {entry['mean']:6.3f} | "
              + " | ".join(cells) + f"   ({now - clock[0]:.1f}s)", flush=True)
        clock[0] = now

    try:
        evolve.train(run=args.run, generations=args.generations, population=args.population,
                     seed=args.seed, tracks=args.tracks, race_from=args.race_from,
                     workers=args.workers, on_generation=report)
    except KeyboardInterrupt:
        print("\nstopped; run the same command to continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
