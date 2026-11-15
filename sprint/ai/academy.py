"""The Racing Academy: a graded course from car control to elite racecraft.

Eight modules, four levels each (beginner, intermediate, advanced, master):

  1 Vehicle control and racing lines        5 Traffic awareness and race management
  2 Braking, cornering, the grip limit      6 Defensive driving and overtaking
  3 Understeer, oversteer and recovery      7 Passing judgement, patience, opportunity
  4 Controlled sliding, adverse surfaces    8 Competitive racecraft, full races

Every challenge has measurable objectives and several variants: SEEN ones
(also used as training lessons) and UNSEEN ones (different tracks, settings
and seeds, never trained on), so improvement is judged on scenarios the
driver has not practised.

A driver goes through the Academy as a CANDIDATE: a copy of its brain,
trained in `academy/<driver>/` (git-ignored) with its own personality's
scoring (aggression and caution), lessons drawn from the seen variants in a
curriculum that moves from module 1 to module 8, plus normal racing.  The
original brain is never changed; `promote` makes a candidate the driver's
brain only when asked (the old one is kept).

    python -m ai.academy run "Dangerous Dave" [--generations 30] [--population 40]
    python -m ai.academy run all                 # every house rival
    python -m ai.academy report                  # write academy_report/
    python -m ai.academy promote "Dangerous Dave"
    python -m ai.academy list                    # the challenges

Everything runs on the existing physics (sim/) and brains (ai/brain.py): the
lessons are scenario kinds of evolve.test_race, the tests run real Worlds.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from sim import cartraits, traffic, tuning, wreck
from sim.driver import create_driver
from sim.race import FINISHED, Race
from sim.track import GRASS, Track
from sim.world import World

from . import evolve, jsonio, lessons, migrate, stable
from .brain import GRIP_PLAN, NeuralDriver, align, arch_for_vector, with_notes, fit_genomes

ACADEMY_DIR = evolve.PROJECT / "academy"
REPORT_DIR = evolve.PROJECT / "academy_report"
TRACKS = ["oval", "speedway", "esses", "technical", "grandprix"]
MODULES = {1: "Vehicle control and racing lines", 2: "Braking, cornering and the grip limit",
           3: "Understeer, oversteer and recovery", 4: "Controlled sliding and adverse surfaces",
           5: "Traffic awareness and race management", 6: "Defensive driving and overtaking",
           7: "Passing judgement, patience and opportunity", 8: "Competitive racecraft and full races"}
LEVELS = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "master"}
LESSON_SHARE = 0.7            # share of training races that are Academy lessons (the rest: normal racing)
GENERATIONS = 30
POPULATION = 40


# ------------------------------------------------------------------ challenges

def _v(track, seconds, rivals=(), slot=None, start=None, grip=None):
    rivals = list(rivals)
    return {"track": track, "seconds": seconds, "rivals": rivals,
            "slot": len(rivals) if slot is None else slot, "start": start, "grip": grip}


def _queue(n, pace, styles=("line",)):
    return [f"traffic:{pace + 0.02 * (k % 3) - 0.02:.2f}:{styles[k % len(styles)]}" for k in range(n)]


def _c(module, level, title, objectives, seen, unseen, kind="race"):
    return {"id": f"m{module}l{level}", "module": module, "level": level, "title": title,
            "kind": kind, "objectives": objectives, "seen": seen, "unseen": unseen}


def _lap(track, laps):
    return round(stable.SCRIPTED_LAPS[track] * laps + 6, 1)


def _start(corner, **kw):
    return dict({"corner": corner, "before": 22.0, "speed": 0.75}, **kw)


CHALLENGES = [
    # 1 -- vehicle control and racing lines (alone)
    _c(1, 1, "Clean laps", [("laps", ">=", 1.8), ("offtrack", "<=", 0.05), ("damage", "<=", 0.05)],
       [_v("oval", _lap("oval", 2.5)), _v("speedway", _lap("speedway", 2.5))],
       [_v("esses", _lap("esses", 2.5)), _v("oval", _lap("oval", 3.5))], "solo"),
    _c(1, 2, "Holding the line", [("pace", "<=", 1.05), ("line_error", "<=", 0.45), ("offtrack", "<=", 0.03)],
       [_v("speedway", _lap("speedway", 3)), _v("oval", _lap("oval", 3))],
       [_v("esses", _lap("esses", 3)), _v("technical", _lap("technical", 3))], "solo"),
    _c(1, 3, "Precision lines", [("pace", "<=", 1.02), ("line_error", "<=", 0.40), ("offtrack", "<=", 0.02)],
       [_v("esses", _lap("esses", 3)), _v("speedway", _lap("speedway", 3))],
       [_v("grandprix", _lap("grandprix", 3)), _v("oval", _lap("oval", 4))], "solo"),
    _c(1, 4, "Master of the line", [("pace", "<=", 1.00), ("line_error", "<=", 0.35), ("offtrack", "<=", 0.01),
                                    ("damage", "<=", 0.02)],
       [_v("grandprix", _lap("grandprix", 3)), _v("technical", _lap("technical", 3))],
       [_v("esses", _lap("esses", 3)), _v("speedway", _lap("speedway", 4))], "solo"),
    # 2 -- braking, cornering, driving on the grip limit (alone)
    _c(2, 1, "Brake before the bend", [("pace", "<=", 1.06), ("slide", "<=", 0.15), ("damage", "<=", 0.05)],
       [_v("speedway", _lap("speedway", 3)), _v("oval", _lap("oval", 3))],
       [_v("esses", _lap("esses", 3)), _v("technical", _lap("technical", 3))], "solo"),
    _c(2, 2, "Using the grip", [("pace", "<=", 0.97), ("limit_use", ">=", 0.14), ("damage", "<=", 0.05)],
       [_v("technical", _lap("technical", 3)), _v("speedway", _lap("speedway", 3))],
       [_v("grandprix", _lap("grandprix", 3)), _v("esses", _lap("esses", 3))], "solo"),
    _c(2, 3, "On the limit", [("pace", "<=", 0.95), ("limit_use", ">=", 0.17), ("damage", "<=", 0.05)],
       [_v("grandprix", _lap("grandprix", 3)), _v("esses", _lap("esses", 3))],
       [_v("technical", _lap("technical", 3)), _v("oval", _lap("oval", 4))], "solo"),
    _c(2, 4, "Fast and tidy", [("pace", "<=", 0.93), ("slide", "<=", 0.06), ("damage", "<=", 0.02)],
       [_v("speedway", _lap("speedway", 4)), _v("technical", _lap("technical", 3))],
       [_v("grandprix", _lap("grandprix", 3)), _v("esses", _lap("esses", 3))], "solo"),
    # 3 -- understeer, oversteer and recovery (alone, starting in trouble)
    _c(3, 1, "Catch a twitch", [("recovered", "<=", 3.0), ("walls", "<=", 0), ("damage", "<=", 0.03)],
       [_v("speedway", 10, start=_start(1, heading=0.15, slide=3.0)), _v("oval", 10, start=_start(0, heading=-0.15, slide=-3.0))],
       [_v("esses", 10, start=_start(2, heading=0.15, slide=-3.0)), _v("technical", 10, start=_start(1, heading=-0.12, slide=3.0))],
       "solo"),
    _c(3, 2, "Wide-eyed moment", [("recovered", "<=", 3.0), ("walls", "<=", 0), ("damage", "<=", 0.05)],
       [_v("speedway", 10, start=_start(2, heading=0.3, slide=6.0)), _v("esses", 10, start=_start(1, heading=-0.3, slide=-5.0))],
       [_v("grandprix", 10, start=_start(3, heading=0.28, slide=5.0)), _v("oval", 10, start=_start(2, heading=-0.32, slide=-6.0))],
       "solo"),
    _c(3, 3, "Spin rescue", [("recovered", "<=", 2.5), ("walls", "<=", 0), ("damage", "<=", 0.05)],
       [_v("technical", 12, start=_start(2, heading=0.45, slide=6.0, yaw=1.0)),
        _v("speedway", 12, start=_start(0, heading=-0.45, slide=-6.0, yaw=-1.0))],
       [_v("esses", 12, start=_start(4, heading=0.42, slide=6.5, yaw=1.1)),
        _v("grandprix", 12, start=_start(1, heading=-0.45, slide=-6.0, yaw=-0.9))], "solo"),
    _c(3, 4, "Hero recovery", [("recovered", "<=", 2.0), ("walls", "<=", 0), ("damage", "<=", 0.03)],
       [_v("grandprix", 12, start=_start(4, heading=0.6, slide=8.0, yaw=1.5, speed=0.85)),
        _v("technical", 12, start=_start(3, heading=-0.6, slide=-8.0, yaw=-1.5, speed=0.85))],
       [_v("esses", 12, start=_start(6, heading=0.58, slide=8.5, yaw=1.4, speed=0.85)),
        _v("speedway", 12, start=_start(3, heading=-0.62, slide=-8.0, yaw=-1.6, speed=0.85))], "solo"),
    # 4 -- controlled sliding and adverse surfaces (alone)
    _c(4, 1, "Back from the grass", [("recovered", "<=", 3.0), ("damage", "<=", 0.05)],
       [_v("speedway", 10, start=_start(1, lateral="grass")), _v("oval", 10, start=_start(1, lateral="-grass"))],
       [_v("esses", 10, start=_start(3, lateral="grass")), _v("technical", 10, start=_start(2, lateral="-grass"))], "solo"),
    _c(4, 2, "Greasy track", [("laps", ">=", 1.8), ("pace", "<=", 1.08), ("damage", "<=", 0.05)],
       [_v("speedway", _lap("speedway", 3), grip=0.9), _v("oval", _lap("oval", 3), grip=0.88)],
       [_v("esses", _lap("esses", 3), grip=0.9), _v("technical", _lap("technical", 3), grip=0.88)], "solo"),
    _c(4, 3, "Slippery and tight", [("laps", ">=", 1.8), ("offtrack", "<=", 0.05), ("damage", "<=", 0.05)],
       [_v("esses", _lap("esses", 3), grip=0.8), _v("technical", _lap("technical", 3), grip=0.8)],
       [_v("grandprix", _lap("grandprix", 3), grip=0.8), _v("speedway", _lap("speedway", 3), grip=0.78)], "solo"),
    _c(4, 4, "Ice dancer", [("laps", ">=", 1.6), ("pace", "<=", 1.15), ("damage", "<=", 0.1), ("recovered", "<=", 4.0)],
       [_v("grandprix", _lap("grandprix", 3), grip=0.75, start=_start(2, heading=0.3, slide=5.0)),
        _v("esses", _lap("esses", 3), grip=0.72, start=_start(3, heading=-0.3, slide=-5.0))],
       [_v("technical", _lap("technical", 3), grip=0.74, start=_start(4, heading=0.3, slide=5.0)),
        _v("speedway", _lap("speedway", 3), grip=0.72, start=_start(2, heading=-0.32, slide=-5.0))], "solo"),
    # 5 -- traffic awareness and race management
    _c(5, 1, "Catch the slow cars", [("reached", ">=", 2), ("contacts", "<=", 2), ("damage", "<=", 0.08)],
       [_v("oval", _lap("oval", 2.5), _queue(2, 0.64)), _v("speedway", _lap("speedway", 2.5), _queue(2, 0.64))],
       [_v("esses", _lap("esses", 2.5), _queue(2, 0.65)), _v("technical", _lap("technical", 2.5), _queue(2, 0.63))]),
    _c(5, 2, "Wreck ahead", [("fault", "<=", 1), ("damage", "<=", 0.1), ("laps", ">=", 1.5)],
       [_v("speedway", _lap("speedway", 2.5), ["scripted", "wreck:4.0:1:0.4", "scripted"], slot=3),
        _v("oval", _lap("oval", 2.5), ["wreck:3.0:-1:0.5", "scripted"], slot=2)],
       [_v("esses", _lap("esses", 2.5), ["scripted", "wreck:5.0:-1:0.3", "scripted"], slot=3),
        _v("grandprix", _lap("grandprix", 2.5), ["wreck:6.0:1:0.6", "scripted", "scripted"], slot=3)]),
    _c(5, 3, "Busy track", [("contacts", "<=", 4), ("place", "<=", 3), ("damage", "<=", 0.15)],
       [_v("speedway", _lap("speedway", 3), _queue(4, 0.74, ("line", "defend"))),
        _v("oval", _lap("oval", 3), _queue(4, 0.74, ("line", "wander")))],
       [_v("esses", _lap("esses", 3), _queue(4, 0.75, ("line", "defend", "wander"))),
        _v("technical", _lap("technical", 3), _queue(4, 0.73, ("line", "wander")))]),
    _c(5, 4, "Full field", [("contacts", "<=", 6), ("place", "<=", 5), ("damage", "<=", 0.2)],
       [_v("technical", _lap("technical", 3), _queue(7, 0.78, ("line", "defend", "line", "wander"))),
        _v("speedway", _lap("speedway", 3), _queue(7, 0.8, ("line", "defend", "line", "wander")))],
       [_v("grandprix", _lap("grandprix", 3), _queue(7, 0.78, ("line", "defend", "wander"))),
        _v("esses", _lap("esses", 3), _queue(7, 0.8, ("line", "wander", "defend")))]),
    # 6 -- defensive driving and overtaking
    _c(6, 1, "First pass", [("clean_passes", ">=", 1), ("contacts", "<=", 2)],
       [_v("oval", _lap("oval", 2.5), _queue(1, 0.8)), _v("speedway", _lap("speedway", 2.5), _queue(1, 0.8))],
       [_v("esses", _lap("esses", 2.5), _queue(1, 0.8)), _v("grandprix", _lap("grandprix", 2.5), _queue(1, 0.8))]),
    _c(6, 2, "Hold the lead", [("place", "<=", 1), ("fault", "<=", 0.5)],
       [_v("speedway", _lap("speedway", 3), ["scripted", "scripted"], slot=0),
        _v("oval", _lap("oval", 3), ["scripted", "scripted"], slot=0)],
       [_v("esses", _lap("esses", 3), ["scripted", "scripted"], slot=0),
        _v("technical", _lap("technical", 3), ["scripted", "scripted"], slot=0)]),
    _c(6, 3, "Pass a defender", [("clean_passes", ">=", 1), ("contacts", "<=", 1)],
       [_v("speedway", _lap("speedway", 3), ["traffic:0.84:defend"]), _v("oval", _lap("oval", 3), ["traffic:0.84:defend"])],
       [_v("technical", _lap("technical", 3), ["traffic:0.83:defend"]), _v("esses", _lap("esses", 3), ["traffic:0.84:defend"])]),
    _c(6, 4, "Keep a faster car behind", [("place", "<=", 1), ("fault", "<=", 0.5)],
       [_v("speedway", _lap("speedway", 3), ["house:zappy-zoe:1.04"], slot=0),
        _v("oval", _lap("oval", 3), ["house:dangerous-dave:1.04"], slot=0)],
       [_v("esses", _lap("esses", 3), ["house:zoe-bold:1.04"], slot=0),
        _v("grandprix", _lap("grandprix", 3), ["house:careful-keith:1.05"], slot=0)]),
    # 7 -- passing judgement, patience and opportunity
    _c(7, 1, "Wait for the gap", [("clean_passes", ">=", 1), ("clean_ratio", ">=", 0.5), ("contacts", "<=", 1)],
       [_v("technical", _lap("technical", 3), ["traffic:0.84:wander"]), _v("speedway", _lap("speedway", 3), ["traffic:0.85:wander"])],
       [_v("grandprix", _lap("grandprix", 3), ["traffic:0.84:wander"]), _v("esses", _lap("esses", 3), ["traffic:0.85:wander"])]),
    _c(7, 2, "Three defenders", [("clean_passes", ">=", 1), ("contacts", "<=", 2)],
       [_v("grandprix", _lap("grandprix", 3), _queue(3, 0.8, ("defend",))), _v("speedway", _lap("speedway", 3), _queue(3, 0.8, ("defend",)))],
       [_v("technical", _lap("technical", 3), _queue(3, 0.8, ("defend",))), _v("oval", _lap("oval", 3), _queue(3, 0.82, ("defend",)))]),
    _c(7, 3, "Narrow track, busy field", [("clean_passes", ">=", 2), ("contacts", "<=", 4)],
       [_v("esses", _lap("esses", 3), _queue(5, 0.8, ("line", "defend", "wander"))),
        _v("technical", _lap("technical", 3), _queue(5, 0.79, ("line", "wander", "defend")))],
       [_v("grandprix", _lap("grandprix", 3), _queue(5, 0.8, ("line", "defend", "wander"))),
        _v("speedway", _lap("speedway", 3), _queue(5, 0.82, ("defend", "line", "wander")))]),
    _c(7, 4, "Through the pack", [("clean_passes", ">=", 3), ("contacts", "<=", 5), ("clean_ratio", ">=", 0.4)],
       [_v("speedway", _lap("speedway", 3), _queue(7, 0.78, ("line", "defend", "line", "wander"))),
        _v("esses", _lap("esses", 3), _queue(7, 0.78, ("line", "defend", "line", "wander")))],
       [_v("grandprix", _lap("grandprix", 3), _queue(7, 0.78, ("line", "defend", "wander"))),
        _v("oval", _lap("oval", 3), _queue(7, 0.8, ("line", "wander", "defend")))]),
    # 8 -- competitive racecraft and full races
    _c(8, 1, "Beat the scripted field", [("place", "<=", 3), ("damage", "<=", 0.2)],
       [_v("oval", _lap("oval", 5), ["scripted"] * 5, slot=5), _v("speedway", _lap("speedway", 5), ["scripted"] * 5, slot=5)],
       [_v("esses", _lap("esses", 5), ["scripted"] * 5, slot=5), _v("technical", _lap("technical", 5), ["scripted"] * 5, slot=5)]),
    _c(8, 2, "Mixed field", [("place", "<=", 4), ("damage", "<=", 0.25)],
       [_v("speedway", _lap("speedway", 5), ["house:careful-keith", "scripted", "house:zoe-bold", "scripted", "scripted"], slot=5),
        _v("oval", _lap("oval", 5), ["house:dangerous-dave", "scripted", "house:careful-keith", "scripted", "scripted"], slot=5)],
       [_v("grandprix", _lap("grandprix", 5), ["house:zoe-bold", "scripted", "house:dangerous-dave", "scripted", "scripted"], slot=5),
        _v("esses", _lap("esses", 5), ["house:careful-keith", "scripted", "house:zappy-zoe", "scripted", "scripted"], slot=5)]),
    _c(8, 3, "House rivals from the back", [("place", "<=", 3), ("fault", "<=", 3)],
       [_v("esses", _lap("esses", 5), ["house:zappy-zoe", "house:dangerous-dave", "house:careful-keith", "house:zoe-bold", "scripted"], slot=5),
        _v("speedway", _lap("speedway", 5), ["house:zoe-bold", "house:careful-keith", "house:zappy-zoe", "house:dangerous-dave", "scripted"], slot=5)],
       [_v("technical", _lap("technical", 5), ["house:dangerous-dave", "house:zappy-zoe", "house:zoe-bold", "house:careful-keith", "scripted"], slot=5),
        _v("oval", _lap("oval", 5), ["house:careful-keith", "house:zoe-bold", "house:dangerous-dave", "house:zappy-zoe", "scripted"], slot=5)]),
    _c(8, 4, "Championship pressure", [("place", "<=", 2), ("damage", "<=", 0.25)],
       [_v("grandprix", _lap("grandprix", 5), ["house:zappy-zoe", "house:clinical-clara", "house:dangerous-dave", "house:zoe-bold", "house:careful-keith"], slot=5),
        _v("technical", _lap("technical", 5), ["house:clinical-clara", "house:zoe-bold", "house:zappy-zoe", "house:careful-keith", "house:dangerous-dave"], slot=5)],
       [_v("esses", _lap("esses", 5), ["house:dangerous-dave", "house:zappy-zoe", "house:clinical-clara", "house:careful-keith", "house:zoe-bold"], slot=5),
        _v("speedway", _lap("speedway", 5), ["house:zoe-bold", "house:dangerous-dave", "house:careful-keith", "house:clinical-clara", "house:zappy-zoe"], slot=5)]),
]
BY_ID = {c["id"]: c for c in CHALLENGES}


def challenges_for(driver_id: str) -> list[dict]:
    """The challenges with the driver itself taken out of its rivals (a house
    rival never races itself: its seat goes to a scripted car)."""
    out = []
    for c in CHALLENGES:
        def fix(v):
            return dict(v, rivals=["scripted" if r.startswith(f"house:{driver_id}") else r for r in v["rivals"]])
        out.append(dict(c, seen=[fix(v) for v in c["seen"]], unseen=[fix(v) for v in c["unseen"]]))
    return out


# --------------------------------------------------------------------- drivers

def driver_spec(name: str, root: Path | None = None) -> dict:
    """A driver by name: a house rival (by name or id) or a racer in the stable
    or workshop.  {"id", "name", "kind", "weights", "arch", "traits",
    "aggression", "caution", "source"}."""
    for card in stable.house_rivals():
        if name.lower() in (card["name"].lower(), card["id"]):
            d = stable.house_driver(card["id"])
            return {"id": card["id"], "name": card["name"], "kind": "house", "weights": np.asarray(d.weights),
                    "arch": d.arch, "traits": card.get("traits") or cartraits.default(),
                    "aggression": card.get("aggression", 0.5), "caution": card.get("caution", 0.5),
                    "source": f"house:{card['id']}"}
    for base in [root] if root else [stable.STABLE_DIR, stable.WORKSHOP_DIR]:
        for d in stable.list_racers(base, include_dead=True) if base else []:
            racer = stable.load(d)
            if name.lower() in (racer["name"].lower(), d.name) and stable.brain_file(d):
                w = stable.brain(d)
                w, arch = align(w, arch_for_vector(w, stable.graduate()["arch"]))
                return {"id": d.name, "name": racer["name"], "kind": "racer", "weights": w, "arch": arch,
                        "traits": racer.get("traits") or cartraits.default(), "aggression": racer["aggression"],
                        "caution": racer["caution"], "source": f"racer:{d}"}
    raise ValueError(f"no driver called {name!r}")


def _rival_driver(spec: str, slot: int):
    """A Driver (and its car params) for a rival spec string."""
    if spec.startswith("traffic:"):
        return traffic.TrafficDriver(slot=slot, **traffic.parse(spec)), None
    if spec.startswith("wreck:"):
        return wreck.WreckDriver(slot=slot, **wreck.parse(spec)), None
    if spec.startswith("house:"):
        parts = spec.split(":")
        d = stable.house_driver(parts[1])
        params = d.car_params
        if len(parts) > 2:                               # a faster car: top speed and power up
            boost = float(parts[2])
            params = replace(params, top_speed=params.top_speed * boost, accel=params.accel * boost)
        return d, params
    return create_driver(spec, slot=slot), None


# ----------------------------------------------------------------- the tests

def run_variant(weights, arch, traits, variant: dict) -> dict:
    """Drive one challenge variant with the driver's brain; return its metrics."""
    track = Track.load(variant["track"])
    rivals = variant["rivals"]
    slot = variant["slot"]
    others = [s for s in range(len(rivals) + 1) if s != slot]
    grip = variant.get("grip")
    me = NeuralDriver(weights, arch, "Student")
    my_params = lessons.grip_scaled(cartraits.params_for(traits), grip)
    drivers, params = [me], [my_params]
    for k, spec in enumerate(rivals):
        d, p = _rival_driver(spec, others[k])
        drivers.append(d)
        params.append(lessons.grip_scaled(p, grip) if grip else p)
    world = World(track, slots=[slot] + others, laps=10 ** 9, rolling=True, params=params)
    for i, d in enumerate(drivers):
        d.reset(world, i)
    lessons.place(world, 0, variant.get("start"))
    stats = evolve.RaceStats(world)
    off, curv = track.ideal()
    plan = my_params.grip * GRIP_PLAN
    car = world.cars[0]
    ticks = int(variant["seconds"] * tuning.TICK_RATE)
    world.end_tick = ticks
    length, half = track.length, track.length / 2.0
    last_s, covered = car.s, 0.0
    n = grass = slides = line_n = limit_n = corner_n = 0
    line_sum = 0.0
    walls = 0
    steady, recovered = 0.0, None
    started = variant.get("start") is not None
    for tick in range(ticks):
        controls = [d.act(world, i) for i, d in enumerate(drivers)]
        events = world.step(controls)
        stats.on_tick(events)
        walls += sum(1 for e in events if e[0] == "wall" and e[1] == 0)
        d = car.s - last_s
        if d > half:
            d -= length
        elif d < -half:
            d += length
        covered += d
        last_s = car.s
        if tick % 4:
            continue
        n += 1
        grass += car.surface == GRASS
        slides += bool(car.sliding)
        idx = car.idx
        hw = max(1e-6, track._hw[idx])
        if car.surface != GRASS:
            line_sum += min(2.0, abs(car.lateral - off[idx]) / hw)
            line_n += 1
        if curv[idx] > 0.012:
            corner_n += 1
            use = car.forward_speed ** 2 * curv[idx] / max(1e-6, plan)
            limit_n += 0.75 <= use <= 1.15
        calm = (not car.sliding and car.surface != GRASS
                and abs(track.heading_error(car.heading, car.s)) < 0.3 and car.speed > 3.0)
        steady = steady + 4 * tuning.DT if calm else 0.0
        if recovered is None and steady >= 0.5:
            recovered = round(world.time - 0.5, 2)
    laps_timed = car.lap_times[1:] if started else car.lap_times   # (after a special start the first is partial)
    best = min(laps_timed) if laps_timed else None
    passes = stats.overtakes
    return {
        "laps": round(covered / length, 3),
        "pace": round(best / stable.SCRIPTED_LAPS[track.key], 4) if best else None,
        "offtrack": round(grass / max(1, n), 4),
        "slide": round(slides / max(1, n), 4),
        "line_error": round(line_sum / max(1, line_n), 4),
        "limit_use": round(limit_n / max(1, corner_n), 4),
        "recovered": recovered if started else 0.0,
        "walls": walls, "damage": round(car.damage, 4),
        "fault": stats.fault, "suffered": stats.suffered, "contacts": stats.fault + stats.suffered,
        "passes": passes, "clean_passes": stats.clean_passes, "passed": stats.passed,
        "clean_ratio": round(stats.clean_passes / passes, 3) if passes else 0.0,
        "reached": len(stats.reached), "place": stats.place(), "field": len(rivals) + 1,
    }


def meets(metrics: dict, objectives) -> list[bool]:
    out = []
    for metric, op, value in objectives:
        got = metrics.get(metric)
        out.append(got is not None and (got <= value if op == "<=" else got >= value))
    return out


def evaluate(weights, arch, traits, driver_id: str, split: str = "both") -> dict:
    """Every challenge, on its seen and/or unseen variants.
    {challenge id: {"seen": [{"metrics", "passed"}...], "unseen": [...]}}."""
    out = {}
    for c in challenges_for(driver_id):
        row = {}
        for part in (["seen", "unseen"] if split == "both" else [split]):
            row[part] = []
            for v in c[part]:
                m = run_variant(weights, arch, traits, v)
                row[part].append({"metrics": m, "passed": all(meets(m, c["objectives"]))})
        out[c["id"]] = row
    return out


def pass_rate(results: dict, part: str, module: int | None = None) -> float:
    tried = [r["passed"] for cid, row in results.items() if part in row
             and (module is None or BY_ID[cid]["module"] == module) for r in row[part]]
    return sum(tried) / len(tried) if tried else 0.0


def completed(results: dict, cid: str, part: str = "unseen") -> bool:
    """A challenge is completed when at least half its variants pass."""
    runs = results.get(cid, {}).get(part, [])
    return bool(runs) and sum(r["passed"] for r in runs) * 2 >= len(runs)


# ------------------------------------------------------------- training lessons

def lesson_scenario(config: dict, gen: int, start: int, rng) -> dict:
    """A training race drawn from the seen variants, following the curriculum:
    early generations favour the early modules and easy levels, later ones the
    later modules and harder levels (every module stays in the mix)."""
    total = max(1, int(config.get("academy_generations", GENERATIONS)))
    stage = min(1.0, max(0.0, (gen - start) / total))
    ids = config.get("academy_challenges") or [c["id"] for c in CHALLENGES]
    pool = [BY_ID[i] for i in ids]
    weights = []
    for c in pool:
        centre = (c["module"] - 1) / 7.0
        level_cap = 1 + 3 * stage + 0.5
        weights.append((math.exp(-((stage - centre) / 0.3) ** 2) + 0.15) * (1.0 if c["level"] <= level_cap else 0.2))
    weights = np.array(weights) / sum(weights)
    c = pool[int(rng.choice(len(pool), p=weights))]
    v = c["seen"][int(rng.integers(0, len(c["seen"])))]
    me = config.get("academy_driver")
    partners = config.get("academy_partners") or []
    rivals, rival_cars = [], []
    for spec in v["rivals"]:
        if spec.startswith("house:"):
            parts = spec.split(":")
            if parts[1] == me or parts[1] not in partners:
                rivals.append("scripted")
                rival_cars.append(None)
                continue
            rivals.append(f"p:{partners.index(parts[1])}")
            card = next((h for h in stable.house_rivals() if h["id"] == parts[1]), {})
            traits = dict(card.get("traits") or cartraits.default())
            if len(parts) > 2:                           # a faster car
                traits["top_speed"] = min(5, traits["top_speed"] + 1)
                traits["accel"] = min(5, traits["accel"] + 1)
            rival_cars.append(traits)
        else:
            rivals.append(spec)
            rival_cars.append(None)
    kind = c["kind"] if c["kind"] == "solo" else ("traffic" if any(r.startswith("traffic:") for r in rivals) else "race")
    return {"track": v["track"], "slot": v["slot"], "rivals": rivals, "rival_cars": rival_cars,
            "car": config.get("car") if isinstance(config.get("car"), dict) else None,
            "seconds": min(v["seconds"], 70.0), "lesson": kind, "challenge": c["id"],
            "start": v.get("start"), "grip": v.get("grip")}


# ------------------------------------------------------------------- pipeline

def folder(driver_id: str) -> Path:
    return ACADEMY_DIR / driver_id


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    jsonio.write_json(path, data)


def _load(path: Path):
    return jsonio.read_json(path) if path.exists() else None


def prepare(spec: dict) -> Path:
    """The driver's academy folder with a copy of its original brain (kept as
    it was when the driver enrolled)."""
    d = folder(spec["id"])
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "original.npz").exists():
        np.savez_compressed(d / "original.npz", pop=np.asarray(spec["weights"], dtype=np.float32)[None, :])
        _save(d / "driver.json", {k: spec[k] for k in ("id", "name", "kind", "arch", "traits", "aggression",
                                                       "caution", "source")}
              | {"enrolled": time.strftime("%Y-%m-%d %H:%M")})
    return d


def original(driver_id: str) -> tuple[np.ndarray, dict, dict]:
    d = folder(driver_id)
    info = _load(d / "driver.json")
    with np.load(d / "original.npz") as data:
        w = data["pop"][0].astype(np.float64)
    return w, info["arch"], info


def train(driver_id: str, generations: int = GENERATIONS, population: int = POPULATION, workers: int = 4,
          log=print) -> Path:
    """Train the candidate (resumable): a copy of the original, its own
    personality's scoring, Academy lessons plus normal racing."""
    w, arch, info = original(driver_id)
    d = folder(driver_id)
    run_arch = with_notes(arch)
    start_file = d / "start.npz"
    if not start_file.exists():
        np.savez_compressed(start_file, pop=fit_genomes(w[None, :], run_arch).astype(np.float32))
    partners_ids = [c["id"] for c in stable.house_rivals() if c["id"] != driver_id]
    partners = [{"name": c["name"], "kind": "file", "file": evolve.project_path(c["file"]),
                 "traits": c.get("traits")} for c in stable.house_rivals() if c["id"] != driver_id]
    partners += [{"name": "Scripted car", "kind": "scripted"}, {"name": "Itself", "kind": "self"}]
    return evolve.train(run="run", root=d, generations=generations, population=population, elites=4, seed=11,
                        tracks=list(TRACKS), arch=run_arch, races_per_track=2, race_bonuses=False,
                        start_file=str(start_file), race_seconds=dict(stable.graduate()["race_seconds"]),
                        race_weights=stable.sliders_to_weights(info["aggression"], info["caution"]),
                        partners=partners, car=info["traits"], solo_share=0.35, notes=True, workers=workers,
                        record_laps=False, log=lambda m: log(m),
                        academy={"driver": driver_id, "partners": partners_ids, "generations": generations},
                        on_generation=lambda e: log(f"  gen {e['gen']}: fitness {e['best']:.2f}"))


def checkpoints(driver_id: str, count: int = 3) -> list[int]:
    gens = evolve.list_generations(folder(driver_id) / "run")
    if not gens:
        return []
    picks = sorted({gens[max(0, round(len(gens) * f) - 1)] for f in np.linspace(1.0 / count, 1.0, count)})
    return picks


def candidate_weights(driver_id: str, gen: int) -> tuple[np.ndarray, dict]:
    run = folder(driver_id) / "run"
    w = evolve.load_generation(run, gen)["pop"][0].astype(np.float64)
    arch = evolve.load_config(run)["arch"]
    return w, arch


def select(driver_id: str, log=print) -> dict:
    """Test the training checkpoints on the SEEN variants and keep the best
    (most passes; later wins a tie).  The unseen variants are not looked at."""
    _, _, info = original(driver_id)
    best = None
    tried = {}
    for gen in checkpoints(driver_id):
        w, arch = candidate_weights(driver_id, gen)
        res = evaluate(w, arch, info["traits"], driver_id, split="seen")
        score = pass_rate(res, "seen")
        tried[gen] = round(score, 4)
        log(f"  checkpoint gen {gen}: seen pass rate {score:.0%}")
        if best is None or score >= best[1]:
            best = (gen, score)
    choice = {"gen": best[0], "seen_pass_rate": best[1], "tried": tried}
    _save(folder(driver_id) / "selected.json", choice)
    w, _ = candidate_weights(driver_id, best[0])
    np.savez_compressed(folder(driver_id) / "candidate.npz", pop=w[None, :].astype(np.float32))
    return choice


RACE_PANEL_TRACKS = TRACKS
RACE_PANEL_PER_TRACK = 2


def race_panel(driver_id: str) -> dict:
    """Six-car, five-lap races: the original and the candidate side by side
    with the other house rivals (scripted cars fill any gaps), rotating grid."""
    w0, arch0, info = original(driver_id)
    sel = _load(folder(driver_id) / "selected.json")
    w1, arch1 = candidate_weights(driver_id, sel["gen"])
    car = cartraits.params_for(info["traits"])
    others = [c["id"] for c in stable.house_rivals() if c["id"] != driver_id][:4]

    def field():
        a = NeuralDriver(w0, arch0, "Original")
        b = NeuralDriver(w1, arch1, "Candidate")
        a.car_params = b.car_params = car
        out = {"Original": a, "Candidate": b}
        for rid in others:
            out[rid] = stable.house_driver(rid)
        k = 0
        while len(out) < 6:
            out[f"scripted{k}"] = "scripted"
            k += 1
        return out
    names = list(field())
    tally = {n: {"races": 0, "wins": 0, "place": 0.0, "damage": 0.0, "finished": 0} for n in names}
    k = 0
    for track in RACE_PANEL_TRACKS:
        for _ in range(RACE_PANEL_PER_TRACK):
            drivers = field()
            order = names[k % 6:] + names[:k % 6]
            race = Race(track, [(slot, drivers[n]) for slot, n in enumerate(order)], laps=5, seed=k,
                        rolling=True).run(max_seconds=500)
            for row in race.results():
                n = order[row["car"]]
                t = tally[n]
                t["races"] += 1
                t["wins"] += row["place"] == 1
                t["place"] += row["place"]
                t["finished"] += bool(row["finished"])
                t["damage"] += race.world.cars[row["car"]].damage
            k += 1
    for t in tally.values():
        t["place"] = round(t["place"] / max(1, t["races"]), 2)
        t["damage"] = round(t["damage"] / max(1, t["races"]), 3)
    return tally


def run(name: str, generations: int = GENERATIONS, population: int = POPULATION, workers: int = 4,
        log=print) -> dict:
    """The whole course for one driver, step by step; every step is saved, so
    running again carries on where it stopped."""
    migrate.ensure()
    spec = driver_spec(name)
    d = prepare(spec)
    log(f"== {spec['name']} ({spec['id']})")
    w0, arch0, info = original(spec["id"])
    if not (d / "before.json").exists():
        log("  testing the original on every challenge ...")
        _save(d / "before.json", evaluate(w0, arch0, info["traits"], spec["id"]))
    done = len(evolve.list_generations(d / "run"))
    if done < generations:
        log(f"  training the candidate: generations {done + 1}-{generations}")
        train(spec["id"], generations - done, population, workers, log)
    if not (d / "selected.json").exists():
        select(spec["id"], log)
    if not (d / "after.json").exists():
        sel = _load(d / "selected.json")
        w1, arch1 = candidate_weights(spec["id"], sel["gen"])
        log(f"  testing the candidate (gen {sel['gen']}) on every challenge ...")
        _save(d / "after.json", evaluate(w1, arch1, info["traits"], spec["id"]))
    if not (d / "races.json").exists():
        log("  race panel: original v candidate v the house rivals ...")
        _save(d / "races.json", race_panel(spec["id"]))
    write_report(spec["id"])
    log(f"  report: {REPORT_DIR / (spec['id'] + '.md')}")
    return {"before": pass_rate(_load(d / "before.json"), "unseen"),
            "after": pass_rate(_load(d / "after.json"), "unseen")}


def promote(name: str) -> str:
    """Make the candidate the driver's brain (the old one is kept)."""
    spec = driver_spec(name)
    d = folder(spec["id"])
    sel = _load(d / "selected.json")
    if not sel:
        raise ValueError(f"{spec['name']} has not finished the Academy")
    w, arch = candidate_weights(spec["id"], sel["gen"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if spec["kind"] == "house":
        rivals = stable.RIVALS_DIR
        old = rivals / "old"
        old.mkdir(exist_ok=True)
        for ext in (".npz", ".json"):
            shutil.copy(rivals / f"{spec['id']}{ext}", old / f"{spec['id']}-{stamp}{ext}")
        np.savez_compressed(rivals / f"{spec['id']}.npz", pop=w[None, :].astype(np.float32))
        card = json.loads((rivals / f"{spec['id']}.json").read_text(encoding="utf-8"))
        card["arch"] = arch
        card["academy"] = {"gen": sel["gen"], "date": stamp,
                           "unseen_pass_rate": round(pass_rate(_load(d / "after.json") or {}, "unseen"), 3)}
        (rivals / f"{spec['id']}.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
        return f"{spec['name']} now races with the Academy candidate (old brain in house/rivals/old/)"
    racer_dir = Path(spec["source"][6:])
    racer = stable.load(racer_dir)
    version = {"run": f"v{len(racer['versions']) + 1}", "generations": 0, "aggression": racer["aggression"],
               "caution": racer["caution"], "partners": [], "track": racer["versions"][-1].get("track", "speedway"),
               "focus": None, "academy": {"gen": sel["gen"]}}
    dest = racer_dir / version["run"]
    dest.mkdir(parents=True, exist_ok=True)
    run_dir = d / "run"
    shutil.copy(run_dir / "config.json", dest / "config.json")
    shutil.copy(evolve.gen_path(run_dir, sel["gen"]), evolve.gen_path(dest, sel["gen"]))
    hist = [h for h in evolve.load_history(run_dir) if h["gen"] <= sel["gen"]]
    (dest / "history.json").write_text(json.dumps(hist), encoding="utf-8")
    racer["versions"].append(version)
    stable.save(racer_dir, racer)
    return f"{spec['name']} now races with the Academy candidate (earlier versions kept)"


# --------------------------------------------------------------------- report

KEY_METRICS = [("pace", "lap pace v scripted", "lower", 1, 2), ("line_error", "distance from the ideal line", "lower", 1, 1),
               ("limit_use", "corner time at the grip limit", "higher", 2, 2), ("slide", "time sliding", "lower", 2, 4),
               ("recovered", "seconds to recover", "lower", 3, 4), ("contacts", "contacts", "lower", 5, 7),
               ("clean_passes", "clean passes", "higher", 6, 7), ("place", "finishing place", "lower", 8, 8)]


def _metric_avg(results: dict, metric: str, modules: tuple[int, int], part: str = "unseen"):
    vals = [r["metrics"].get(metric) for cid, row in results.items()
            if modules[0] <= BY_ID[cid]["module"] <= modules[1] for r in row.get(part, [])]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _grade(rate: float) -> str:
    for cut, g in ((0.85, "A (elite)"), (0.7, "B (strong)"), (0.55, "C (competent)"), (0.4, "D (developing)")):
        if rate >= cut:
            return g
    return "E (novice)"


def report_text(driver_id: str) -> str:
    d = folder(driver_id)
    info = _load(d / "driver.json")
    before, after = _load(d / "before.json"), _load(d / "after.json")
    sel, races = _load(d / "selected.json"), _load(d / "races.json")
    hist = evolve.load_history(d / "run") if (d / "run").exists() else []
    lines = [f"# Academy report: {info['name']}", "",
             f"Aggression {info['aggression']}, caution {info['caution']}; car "
             f"{cartraits.describe(info['traits'])}.  Enrolled {info.get('enrolled', '?')}.", ""]
    if not before:
        return "\n".join(lines + ["Not tested yet."])
    if not after:
        lines += ["Training not finished: only the original has been tested.", ""]
        after = {}
    b_seen, b_un = pass_rate(before, "seen"), pass_rate(before, "unseen")
    a_seen, a_un = pass_rate(after, "seen"), pass_rate(after, "unseen")
    n_done_b = sum(completed(before, c["id"]) for c in CHALLENGES)
    n_done_a = sum(completed(after, c["id"]) for c in CHALLENGES) if after else 0
    lines += ["## Summary", "",
              f"- Training: {len(hist)} generations; candidate = generation {sel['gen'] if sel else '-'} "
              f"(chosen on the seen scenarios only).",
              f"- Pass rate on UNSEEN scenarios: **{b_un:.0%} -> {a_un:.0%}** "
              f"(seen: {b_seen:.0%} -> {a_seen:.0%}).",
              f"- Challenges completed (unseen, at least half the variants passed): {n_done_b} -> {n_done_a} of {len(CHALLENGES)}.",
              f"- Overall assessment: **{_grade(a_un if after else b_un)}** (before: {_grade(b_un)}).", ""]
    lines += ["## By module (unseen pass rate)", "", "| Module | Before | After | Change |", "|---|---|---|---|"]
    module_after = {}
    for m, title in MODULES.items():
        pb, pa = pass_rate(before, "unseen", m), pass_rate(after, "unseen", m)
        module_after[m] = pa if after else pb
        lines.append(f"| {m}. {title} | {pb:.0%} | {pa:.0%} | {pa - pb:+.0%} |")
    lines += ["", "## Challenges", "",
              "Unseen variants passed (of 2), before -> after. Seen variants in brackets.", "",
              "| Challenge | Level | Objectives | Before | After |", "|---|---|---|---|---|"]
    for c in CHALLENGES:
        def cell(res):
            if not res or c["id"] not in res:
                return "-"
            un = sum(r["passed"] for r in res[c["id"]].get("unseen", []))
            se = sum(r["passed"] for r in res[c["id"]].get("seen", []))
            return f"{un}/2 ({se}/2)"
        obj = ", ".join(f"{m} {op} {v}" for m, op, v in c["objectives"])
        lines.append(f"| {c['id'].upper()} {c['title']} | {LEVELS[c['level']]} | {obj} | {cell(before)} | {cell(after)} |")
    lines += ["", "## Skill measures (unseen scenarios, averages)", "", "| Measure | Modules | Before | After |",
              "|---|---|---|---|"]
    improved, worse = [], []
    for metric, label, better, m0, m1 in KEY_METRICS:
        vb, va = _metric_avg(before, metric, (m0, m1)), _metric_avg(after, metric, (m0, m1)) if after else None
        fmt = (lambda v: "-" if v is None else f"{v:.3f}")
        lines.append(f"| {label} | {m0}-{m1} | {fmt(vb)} | {fmt(va)} |")
        if vb is not None and va is not None and abs(va - vb) > 1e-9:
            good = va < vb if better == "lower" else va > vb
            (improved if good else worse).append(label)
    lines += ["", "## Race performance (six-car five-lap races, original and candidate in the same field)", ""]
    if races:
        lines += ["| Driver | Races | Wins | Avg place | Damage |", "|---|---|---|---|---|"]
        for n, t in sorted(races.items(), key=lambda kv: kv[1]["place"]):
            label = {"Original": f"**{info['name']} (original)**", "Candidate": f"**{info['name']} (Academy candidate)**"}
            lines.append(f"| {label.get(n, n)} | {t['races']} | {t['wins']} | {t['place']:.2f} | {t['damage']:.0%} |")
    else:
        lines.append("Not raced yet.")
    ranked = sorted(module_after.items(), key=lambda kv: -kv[1])
    strengths = [f"{MODULES[m]} ({r:.0%})" for m, r in ranked[:2] if r > 0]
    weaknesses = [f"{MODULES[m]} ({r:.0%})" for m, r in ranked[-2:]]
    failed = [f"{c['id'].upper()} {c['title']}" for c in CHALLENGES if not completed(after or before, c["id"])]
    lines += ["", "## Assessment", "",
              f"- Strengths: {', '.join(strengths) or 'none yet'}.",
              f"- Weaknesses: {', '.join(weaknesses)}.",
              f"- Improved: {', '.join(improved) or 'nothing measurable'}.",
              f"- Got worse: {', '.join(worse) or 'nothing'}.",
              f"- Still to develop ({len(failed)} challenges not completed on unseen scenarios): "
              + (", ".join(failed[:10]) + (" ..." if len(failed) > 10 else "") if failed else "none") + "."]
    if races and "Candidate" in races:
        o, c = races["Original"], races["Candidate"]
        verdict = ("races better" if c["place"] < o["place"] - 0.1 else
                   "races worse" if c["place"] > o["place"] + 0.1 else "races about the same")
        lines.append(f"- In races the candidate {verdict} than the original (avg place {c['place']:.2f} v "
                     f"{o['place']:.2f}, wins {c['wins']} v {o['wins']}).")
    lines += ["", "The original brain is unchanged; `python -m ai.academy promote "
              f"\"{info['name']}\"` would make the candidate race in its place.", ""]
    return "\n".join(lines)


def write_report(driver_id: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"{driver_id}.md"
    path.write_text(report_text(driver_id), encoding="utf-8")
    write_summary()
    return path


def write_summary() -> Path:
    rows = []
    for d in sorted(ACADEMY_DIR.glob("*/driver.json")) if ACADEMY_DIR.exists() else []:
        did = d.parent.name
        info = _load(d)
        before, after = _load(d.parent / "before.json"), _load(d.parent / "after.json")
        races = _load(d.parent / "races.json")
        if not before:
            continue
        b, a = pass_rate(before, "unseen"), pass_rate(after, "unseen") if after else None
        o = races["Original"]["place"] if races else None
        c = races["Candidate"]["place"] if races else None
        rows.append((info["name"], did, b, a, o, c))
    lines = ["# Racing Academy report", "",
             "Every driver took 32 challenges in 8 modules (beginner to master), each with seen variants "
             "(also used as training lessons) and unseen ones (never trained on). Candidates were trained "
             "from copies of the drivers' brains with their own personalities; originals are unchanged.",
             "", "| Driver | Unseen pass rate before | After | Grade | Race avg place original -> candidate |",
             "|---|---|---|---|---|"]
    for name, did, b, a, o, c in rows:
        after_txt = "-" if a is None else f"{a:.0%}"
        race = "-" if o is None else f"{o:.2f} -> {c:.2f}"
        lines.append(f"| [{name}]({did}.md) | {b:.0%} | {after_txt} | {_grade(a if a is not None else b)} | {race} |")
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------------ CLI

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("driver", help='a driver name, or "all" for every house rival')
    r.add_argument("--generations", type=int, default=GENERATIONS)
    r.add_argument("--population", type=int, default=POPULATION)
    r.add_argument("--workers", type=int, default=4)
    p = sub.add_parser("promote")
    p.add_argument("driver")
    sub.add_parser("report")
    sub.add_parser("list")
    args = ap.parse_args()
    if args.cmd == "list":
        for c in CHALLENGES:
            print(f"{c['id']:5s} {MODULES[c['module']][:34]:34s} {LEVELS[c['level']]:12s} {c['title']}")
        return 0
    if args.cmd == "report":
        for d in sorted(ACADEMY_DIR.glob("*/driver.json")):
            write_report(d.parent.name)
        print(write_summary())
        return 0
    if args.cmd == "promote":
        print(promote(args.driver))
        return 0
    names = [c["name"] for c in stable.house_rivals()] if args.driver == "all" else [args.driver]
    for name in names:
        result = run(name, args.generations, args.population, args.workers,
                     log=lambda m: print(f"{time.strftime('%H:%M')} {m}", flush=True))
        print(f"{name}: unseen pass rate {result['before']:.0%} -> {result['after']:.0%}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
