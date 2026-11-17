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


FOLLOW_S = 1.0      # within this many seconds behind the car ahead (at the follower's speed) counts as following it
TAIL = 4.5          # closer than this, in the same lane, is tailgating
LANE = 2.6          # lateral distance that counts as the same lane
DEFEND = 10.0       # a car this close behind means the driver is defending
SWERVE = 0.22       # lateral move per sample (30 a second) that counts as a deliberate move
CORNER = 0.012      # centreline curvature above which the car is in a corner


class CraftMeter:
    """Racecraft measures for car `me`, sampled every decision tick (pure
    function of the World): share of the time following a car ahead, share
    of the time tailgating it, and weaves (changes of direction while a car
    is close behind: moving to block, then back, then across again)."""

    def __init__(self, world, me: int = 0):
        self.world, self.me = world, me
        self.n = self.close = self.tail = self.defend = self.weaves = 0
        self.corner_n = self.corner_tail = 0
        self.caught = False
        self.max_gap = 0.0
        self.last_lat = None
        self.last_dir = 0

    def sample(self) -> None:
        w = self.world
        car = w.cars[self.me]
        length = w.track.length
        ahead = behind = None
        for j, other in enumerate(w.cars):
            if j == self.me or getattr(other, "retired", False):
                continue
            d = (other.s - car.s) % length
            if d < length / 2:
                if ahead is None or d < ahead[0]:
                    ahead = (d, other)
            elif behind is None or length - d < behind:
                behind = length - d
        self.n += 1
        in_corner = abs(float(w.track.curvature[car.idx])) > CORNER
        tail = bool(ahead and ahead[0] < TAIL and abs(ahead[1].lateral - car.lateral) < LANE)
        if in_corner:
            self.corner_n += 1
            self.corner_tail += tail
        if ahead and ahead[0] / max(car.speed, 5.0) <= FOLLOW_S:
            self.close += 1
            self.caught = True
            if tail:
                self.tail += 1
        if ahead and self.caught:                      # once with the car ahead: how far does it drop back?
            self.max_gap = max(self.max_gap, ahead[0] / max(car.speed, 5.0))
        lat = car.lateral
        if behind is not None and behind < DEFEND:
            self.defend += 1
            if self.last_lat is not None:
                move = lat - self.last_lat
                d = 1 if move > SWERVE else -1 if move < -SWERVE else 0
                if d and self.last_dir and d != self.last_dir:
                    self.weaves += 1
                if d:
                    self.last_dir = d
        else:
            self.last_dir = 0
        self.last_lat = lat

    def result(self) -> dict:
        n = max(1, self.n)
        return {"close": round(self.close / n, 4), "tailgate": round(self.tail / n, 4),
                "corner_tail": round(self.corner_tail / max(1, self.corner_n), 4),
                "max_gap_s": round(self.max_gap, 2) if self.caught else 99.0,
                "defend_time": round(self.defend / n, 4), "weaves": self.weaves}
