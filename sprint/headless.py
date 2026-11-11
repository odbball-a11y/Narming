"""Run a race with no window, as fast as the machine allows.

    python headless.py                                # scripted, Speedway, 3 laps
    python headless.py --track technical --cars 4
    python headless.py --record replays/test.replay.gz
    python headless.py --replay replays/test.replay.gz   # play back and verify
    python headless.py --bench 200000                 # just measure steps per second

Prints lap times and simulation steps per second.  Exit code 1 if a car fails
to finish or a replay does not reproduce.
"""
from __future__ import annotations

import argparse
import time

import sim.scripted  # noqa: F401  (registers the "scripted" driver)
from sim import tuning
from sim.driver import create_driver
from sim.race import Race
from sim.replay import Recording
from sim.track import Track
from sim.world import World


def _print_lap(race, event):
    if event[0] == "lap":
        car = race.world.cars[event[1]]
        print(f"  t={race.world.time:7.2f}s  car {race.slots[event[1]] + 1}  lap {car.laps}  {event[2]:.3f}s")


def bench(track: str, cars: int, steps: int) -> None:
    world = World(Track.load(track), num_cars=cars, laps=10 ** 9)
    drivers = [create_driver("scripted", slot=slot) for slot in world.slots]
    start = time.perf_counter()
    for _ in range(steps):
        world.step([d.act(world, i) for i, d in enumerate(drivers)])
    report_speed(steps, time.perf_counter() - start)


def report_speed(steps: int, wall: float) -> None:
    sim_seconds = steps * tuning.DT
    print(f"{steps} steps ({sim_seconds:.1f} s of racing) in {wall:.3f} s wall = "
          f"{steps / wall:,.0f} steps/s = {sim_seconds / wall:,.0f}x real time")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--cars", type=int, default=1, choices=[1, 2, 3, 4])
    ap.add_argument("--laps", type=int, default=3)
    ap.add_argument("--driver", default="scripted")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rolling", action="store_true", help="single-file rolling start")
    ap.add_argument("--record", metavar="FILE", help="save the race's controls to FILE")
    ap.add_argument("--replay", metavar="FILE", help="play back FILE and check it reproduces")
    ap.add_argument("--bench", type=int, default=0, metavar="STEPS",
                    help="ignore laps; run this many steps and report speed")
    args = ap.parse_args()

    if args.bench:
        print(f"{args.track}: {args.cars} car(s), benchmark")
        bench(args.track, args.cars, args.bench)
        return 0

    recording = None
    if args.replay:
        recording = Recording.load(args.replay)
        for problem in recording.compatibility_problems():
            print(f"warning: {problem}; playback may differ")
        race = recording.make_race()
        print(f"replay of {recording.track}: {len(recording.slots)} car(s), {recording.laps} laps")
    else:
        race = Race(args.track, [(slot, args.driver) for slot in range(args.cars)],
                    laps=args.laps, seed=args.seed, rolling=args.rolling)
        print(f"{args.track}: {args.cars} car(s), driver={args.driver}, {args.laps} laps")

    start = time.perf_counter()
    race.run(max_seconds=600.0, on_event=_print_lap)
    wall = time.perf_counter() - start

    ok = True
    for row in race.results():
        times = ", ".join(f"{t:.3f}" for t in row["lap_times"])
        status = f"finished in {row['time']:.3f}s" if row["finished"] else "DID NOT FINISH"
        ok = ok and row["finished"]
        best = f"{row['best_lap']:.3f}" if row["best_lap"] is not None else "-"
        print(f"P{row['place']} car {row['slot'] + 1} ({row['driver']}): {status}; laps [{times}]; best {best}")
    report_speed(race.world.tick, wall)
    print(f"state hash {race.world.state_hash()[:16]}")

    if recording is not None:
        same = race.final_hash == recording.final_hash
        print("replay reproduced the recorded race exactly" if same
              else "REPLAY MISMATCH: final state differs from the recording")
        ok = ok and same
    if args.record:
        path = Recording.from_race(race).save(args.record)
        print(f"recorded {len(race.controls_log)} ticks to {path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
