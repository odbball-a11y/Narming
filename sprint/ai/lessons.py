"""Special starting states and conditions for Racing Academy lessons and
challenges, used both by training (evolve.test_race) and by the Academy's
tests (ai/academy.py).  Pure functions on a World; no randomness.

A start spec puts a car somewhere on the track already in trouble:

    {"corner": k,          # the k-th corner of the track (wraps)
     "before": 25.0,       # this many units before its apex
     "lateral": 0.0,       # across the track: fraction of the half-width (+ = right),
                           # or "grass" / "-grass" for just off the tarmac
     "heading": 0.0,       # radians off the track's direction (+ = pointing right)
     "speed": 0.8,         # forward speed as a share of the car's top speed
     "slide": 0.0,         # sideways speed (+ = to the right)
     "yaw": 0.0}           # rotation rate (rad/s, + = turning right)

`grip` scales a car's tyre grip (an adverse, greasy surface): 1.0 = normal.
"""
from __future__ import annotations

import math
from dataclasses import replace

from sim import tuning


def grip_scaled(params, scale: float | None):
    """The car's parameters on a surface with `scale` x the normal grip."""
    if params is None:
        params = tuning.CarParams()
    if not scale or scale == 1.0:
        return params
    return replace(params, grip=params.grip * scale)


def place(world, i: int, spec: dict | None) -> None:
    """Put car `i` in the state `spec` describes (see the module docstring)."""
    if not spec:
        return
    track = world.track
    corners = track.corners()["apex"]
    apex = corners[int(spec.get("corner", 0)) % len(corners)]
    idx = int(round(apex - spec.get("before", 25.0) / track.ds)) % track.n
    hw = track._hw[idx]
    lateral = spec.get("lateral", 0.0)
    if lateral in ("grass", "-grass"):
        offset = (hw + 1.6) * (1.0 if lateral == "grass" else -1.0)
    else:
        offset = float(lateral) * hw
    cx, cy = track.center[idx]
    nx, ny = track.normal[idx]
    heading = float(track.heading[idx]) + float(spec.get("heading", 0.0))
    car = world.cars[i]
    world.place_car(car, cx + nx * offset, cy + ny * offset, heading)
    forward = float(spec.get("speed", 0.8)) * car.params.top_speed
    slide = float(spec.get("slide", 0.0))
    c, s = math.cos(heading), math.sin(heading)
    rx, ry = -s, c                                   # the car's right (positive lateral)
    car.vx = c * forward + rx * slide
    car.vy = s * forward + ry * slide
    car.yaw_rate = float(spec.get("yaw", 0.0))
    car.refresh_speed()
    car.prev_x, car.prev_y, car.prev_heading = car.x, car.y, car.heading
