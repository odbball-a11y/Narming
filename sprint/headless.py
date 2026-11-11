"""Run a race with no window, as fast as the machine allows.

    python headless.py                       # scripted driver, Speedway, 3 laps
    python headless.py --track speedway --cars 4 --laps 3
    python headless.py --bench 200000        # just measure steps per second

Prints lap times and simulation steps per second.
"""
from __future__ import annotations

import argparse
import time

import sim.scripted  # noqa: F401  (registers the "scripted" driver)
from sim import tuning
from sim.driver import create_driver
from sim.track import Track
from sim.world import World


def run_race(track_name: str, cars: int, laps: int, driver_key: str = "scripted",
             seed: int = 0, max_seconds: float = 300.0, verbose: bool = True):
    """Returns (world, steps, wall_seconds)."""
    world = World(Track.load(track_name), num_cars=cars, seed=seed, laps=laps)
    drivers = [create_driver(driver_key, slot=slot) for slot in world.slots]
    for i, driver in enumerate(drivers):
        driver.reset(world, i)
    max_ticks = int(max_seconds * tuning.TICK_RATE)
    start = time.perf_counter()
    while world.tick < max_ticks and not all(car.finished for car in world.cars):
        controls = [driver.act(world, i) for i, driver in enumerate(drivers)]
        for event in world.step(controls):
            if verbose and event[0] == "lap":
                print(f"  t={world.time:7.2f}s  car {event[1] + 1}  lap {world.cars[event[1]].laps}"
                      f"  {event[2]:.3f}s")
    return world, world.tick, time.perf_counter() - start


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--cars", type=int, default=1)
    ap.add_argument("--laps", type=int, default=3)
    ap.add_argument("--driver", default="scripted")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bench", type=int, default=0, metavar="STEPS",
                    help="ignore laps; run this many steps and report speed")
    args = ap.parse_args()

    laps = 10 ** 9 if args.bench else args.laps
    limit = args.bench / tuning.TICK_RATE if args.bench else 300.0
    print(f"{args.track}: {args.cars} car(s), driver={args.driver}, "
          f"{'benchmark' if args.bench else str(args.laps) + ' laps'}")
    world, steps, wall = run_race(args.track, args.cars, laps, args.driver, args.seed,
                                  max_seconds=limit, verbose=not args.bench)
    ok = True
    if not args.bench:
        for i in world.standings():
            car = world.cars[i]
            times = ", ".join(f"{t:.3f}" for t in car.lap_times)
            status = f"finished in {car.finish_time:.3f}s" if car.finished else "DID NOT FINISH"
            ok = ok and car.finished
            best = f"{car.best_lap:.3f}" if car.best_lap is not None else "-"
            print(f"car {i + 1}: {status}; laps [{times}]; best {best}")
    sim_seconds = steps * tuning.DT
    print(f"{steps} steps ({sim_seconds:.1f} s of racing) in {wall:.3f} s wall = "
          f"{steps / wall:,.0f} steps/s = {sim_seconds / wall:,.0f}x real time")
    print(f"state hash {world.state_hash()[:16]}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
