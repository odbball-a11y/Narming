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


class TimeUp(Exception):
    """--minutes ran out (raised after a generation is saved)."""


def all_owners() -> list[dict]:
    """Every racer (your stable, the workshop, the dynasty) and house rival that has a car."""
    from ai import stable
    from sim import cartraits
    out = []
    roots = [("stable", stable.STABLE_DIR), ("workshop", stable.WORKSHOP_DIR),
             ("dynasty", stable.STABLE_DIR.parent / "dynasty" / "stable")]
    for where, root in roots:
        for d in stable.list_racers(root, include_dead=True) if root.exists() else []:
            r = stable.load(d)
            traits = stable.traits_of(d)
            status = {"stud": " (at stud)", "dead": " (legend)"}.get(stable.status(d), "")
            out.append({"name": r["name"], "where": where + status, "traits": traits,
                        "car": cartraits.describe(traits), "aggression": r["aggression"],
                        "caution": r["caution"], "brain": stable.brain_file(d)})
    for rival in stable.house_rivals():
        traits = rival.get("traits") or cartraits.default()
        out.append({"name": rival["name"], "where": "house", "traits": traits, "car": cartraits.describe(traits),
                    "aggression": rival.get("aggression", 0.5), "caution": rival.get("caution", 0.5),
                    "brain": rival["file"]})
    return out


def find_owner(name: str) -> dict:
    """A racer or house rival by name (any case; your stable first)."""
    matches = [o for o in all_owners() if o["name"].lower() == name.strip().lower()]
    if not matches:
        raise SystemExit(f"no racer or house rival called {name!r}; try --list")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="default", help="name of the training run")
    ap.add_argument("--generations", type=int, default=None,
                    help="how many more to breed (default 50, or as many as fit in --minutes)")
    ap.add_argument("--minutes", type=float, default=None,
                    help="stop after this long (it finishes the generation it is on); "
                         "run the same command again to carry on")
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
                         "generation unless GEN is given), straight into racing school.  "
                         "--from graduate starts from the shipped graduate (house/graduate.npz) "
                         "with its tracks, network and race lengths")
    ap.add_argument("--driving-school", action="store_true",
                    help="with --from: start in driving school (solo laps) and move on to racing school "
                         "once the champion laps every track cleanly, instead of racing straight away")
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
    ap.add_argument("--car", default="standard", metavar="standard|random|NAME",
                    help="car to train in (new runs): the standard car, a different random car each "
                         "generation (drivers learn to drive any car), or the car of an existing racer "
                         "or house rival, by name (one car only: an easier problem, so it learns faster)")
    ap.add_argument("--racer", metavar="NAME",
                    help="start from an existing racer's (or house rival's) brain, in its own car and "
                         "with its personality, with no lifetime limit; the run's name and tracks are "
                         "yours to choose (e.g. --tracks speedway)")
    ap.add_argument("--list", action="store_true", help="list the racers and house rivals you can name")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="CPU cores to use")
    args = ap.parse_args()

    from ai import migrate
    migrate.ensure()
    if args.list:
        for owner in all_owners():
            print(f"{owner['name']:24s} {owner['where']:10s} {owner['car']}")
        return 0
    run_dir = evolve.RUNS_DIR / args.run
    print(f"run '{args.run}' in {run_dir}")
    clock = [time.perf_counter()]
    deadline = time.perf_counter() + args.minutes * 60.0 if args.minutes else None
    if args.generations is None:
        args.generations = 10 ** 6 if deadline else 50

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
        if deadline and now >= deadline:
            raise TimeUp(entry["gen"])

    arch = None
    if args.hidden is not None or args.memory is not None:
        arch = {"hidden": args.hidden or DEFAULT_ARCH["hidden"],
                "memory": DEFAULT_ARCH["memory"] if args.memory is None else args.memory,
                "inputs": DEFAULT_ARCH["inputs"]}
    start_file = race_seconds = race_weights = None
    car = None if args.car == "standard" else "random" if args.car == "random" else None
    if args.racer:
        owner = find_owner(args.racer)
        if owner["brain"] is None:
            print(f"{owner['name']} has no trained brain yet")
            return 1
        start_file = str(owner["brain"])
        args.start_from = "graduate"            # tracks, network and race lengths as the graduate's
        car = owner["traits"]
        if args.style is None:
            from ai import stable as _stable
            race_weights = _stable.sliders_to_weights(owner["aggression"], owner["caution"])
        args.name = args.name or owner["name"]
        print(f"from {owner['name']} ({owner['where']}): {owner['car']}")
    if args.car not in ("standard", "random"):
        owner = find_owner(args.car)
        car = owner["traits"]
        print(f"car: {owner['name']}'s ({owner['car']})")
    if args.start_from == "graduate":           # the shipped graduate is a file, not a run
        from ai import stable
        grad = stable.graduate()
        start_file = start_file or str(stable.GRADUATE.with_suffix(".npz"))
        args.start_from = None
        arch = arch or grad["arch"]
        args.tracks = args.tracks or list(grad["tracks"])
        args.races = args.races or grad["races_per_track"]
        if args.race_laps is None:
            race_seconds = dict(grad["race_seconds"])
    try:
        evolve.train(run=args.run, generations=args.generations, population=args.population,
                     seed=args.seed, tracks=args.tracks, phase2_from=args.racing_from, arch=arch,
                     races_per_track=args.races, race_bonuses=False if args.no_race_bonuses else None,
                     race_laps=args.race_laps, start_from=args.start_from, style=args.style,
                     name=args.name, car=car, race_weights=race_weights,
                     driving_school=args.driving_school, start_file=start_file, race_seconds=race_seconds,
                     workers=args.workers, on_generation=report,
                     log=lambda m: print(m, flush=True))
        config = evolve.load_config(run_dir)
        if config.get("name"):
            print(f"racer {config['name']} ({config.get('style')}), from {config.get('parent')}")
        print(f"network {describe(config['arch'])}; race bonuses "
              f"{'on' if config['race_bonuses'] else 'off'}; racing school from generation "
              f"{config.get('phase2_start') or '(not yet)'}")
    except TimeUp as stop:
        print(f"time is up after generation {stop.args[0]}; run the same command again to carry on")
    except KeyboardInterrupt:
        print("\nstopped; run the same command to continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
