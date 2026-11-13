"""Static test of physics options on the house graduate and the scripted driver:
how much slower and cleaner do old drivers get with tyre scrub / a friction circle?

    python lines_physics.py
"""
import sys, math
from dataclasses import replace
import numpy as np
from ai import brain, migrate
from ai.evolve import load_pop_file
from sim import tuning
from sim.track import Track
from sim.world import World
from sim.driver import create_driver
import sim.scripted
migrate.ensure()
pop = load_pop_file("house/graduate.npz")
arch = dict(brain.DEFAULT_ARCH)
VARIANTS = {"current (scrub + circle)": {},
            "+ understeer + yaw lag": dict(front_limit=1.0, yaw_lag=0.08),
            "+ weight transfer": dict(front_limit=1.0, yaw_lag=0.08, weight_transfer=0.25, lateral_transfer=0.1),
            "+ transfer 0.15": dict(front_limit=1.0, yaw_lag=0.08, weight_transfer=0.15, lateral_transfer=0.1)}
def run(kind, track, change):
    params = replace(tuning.car_params(0), **change)
    w = World(Track.load(track), 1, laps=3, params=[params], ghost=True)
    d = brain.NeuralDriver(pop[0], arch) if kind == "ai" else create_driver("scripted", 0)
    d.reset(w, 0)
    slide = ticks = 0
    while w.tick * tuning.DT < 60 and not w.cars[0].finished:
        w.step([d.act(w, 0)]); c = w.cars[0]
        l = abs(-c.vx * math.sin(c.heading) + c.vy * math.cos(c.heading)); slide += l > 3; ticks += 1
    return w.cars[0].best_lap, slide / max(1, ticks), w.cars[0].damage
tracks = Track.available()
print(f"{'physics':18s} {'AI lap vs old-physics scripted':>32s} {'AI slide%':>10s} {'AI damage%':>10s}   scripted lap vs old")
base_s = {t: run("scripted", t, dict(scrub=0.0, brake_circle=0.0, throttle_circle=0.0))[0] for t in tracks}
for name, change in VARIANTS.items():
    ai = {t: run("ai", t, change) for t in tracks}
    sc = {t: run("scripted", t, change) for t in tracks}
    ratio = np.mean([ai[t][0] / base_s[t] for t in tracks])
    sratio = np.mean([sc[t][0] / base_s[t] for t in tracks])
    print(f"{name:18s} {ratio:32.3f} {np.mean([ai[t][1] for t in tracks]) * 100:10.1f} {np.mean([ai[t][2] for t in tracks]) * 100:10.0f}   {sratio:.3f}", flush=True)
