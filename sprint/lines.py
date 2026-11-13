"""How well does a driver take corners?  Solo laps on every track, measuring
lap time and how much of the lap is spent sliding.

    python lines.py house/graduate.npz [more.npz ...] [--car random|standard]

Each argument is a saved population (the best driver, row 0, is used).  A
slide is sideways speed above SLIDE_SPEED (units/s); `slide%` is the share of
the lap spent above it, `slip` the mean sideways speed.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from ai import brain, migrate
from ai.evolve import load_pop_file
from sim import tuning
from sim.track import Track
from sim.world import World

SLIDE_SPEED = 3.0


def measure(weights, arch, track_name: str, seconds: float = 60.0, car=None) -> dict:
    from sim.cartraits import params_for
    track = Track.load(track_name)
    params = [params_for(car)] if car else None
    world = World(track, 1, laps=3, params=params, ghost=True) if params else World(track, 1, laps=3, ghost=True)
    driver = brain.NeuralDriver(weights, arch)
    driver.reset(world, 0)
    slide = ticks = 0
    slip = 0.0
    while world.tick * tuning.DT < seconds and not world.cars[0].finished:
        world.step([driver.act(world, 0)])
        c = world.cars[0]
        import math
        lateral = abs(-c.vx * math.sin(c.heading) + c.vy * math.cos(c.heading))
        slide += lateral > SLIDE_SPEED
        slip += lateral
        ticks += 1
    laps = [t for t in world.cars[0].lap_times] if hasattr(world.cars[0], "lap_times") else []
    best = world.cars[0].best_lap
    return {"best": best, "slide": slide / max(1, ticks), "slip": slip / max(1, ticks),
            "damage": world.cars[0].damage}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--tracks", nargs="*", default=None)
    args = ap.parse_args()
    migrate.ensure()
    tracks = args.tracks or Track.available()
    for f in args.files:
        pop = load_pop_file(f)
        arch = dict(brain.DEFAULT_ARCH)
        print(f"\n{f}")
        total = []
        for t in tracks:
            r = measure(pop[0], arch, t)
            total.append(r)
            print(f"  {t:10s} lap {r['best'] if r['best'] else float('nan'):6.2f}  slide {r['slide'] * 100:5.1f}%  "
                  f"slip {r['slip']:4.2f}  damage {r['damage'] * 100:3.0f}%")
        print(f"  {'mean':10s} slide {np.mean([r['slide'] for r in total]) * 100:5.1f}%  "
              f"slip {np.mean([r['slip'] for r in total]):4.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
