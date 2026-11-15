"""Backmarkers for traffic drills: scripted cars held to a share of their
top speed, in one of three styles, so a learner has a queue of slower cars
to get past cleanly.

  line    keeps to the racing line
  defend  moves across to cover a car closing in behind, once per approach
  wander  drifts off line and back (a slow, deterministic weave)

Deterministic: no randomness of its own (the drill's settings come from the
scenario).  Key format "traffic:<pace>:<style>"."""
from __future__ import annotations

import math

from .driver import Controls
from .scripted import ScriptedDriver

STYLES = ("line", "defend", "wander")


class TrafficDriver(ScriptedDriver):
    label = "Traffic"

    def __init__(self, slot: int = 0, pace: float = 0.9, style: str = "line"):
        super().__init__(slot)
        self.pace = pace              # share of its top speed it will use
        self.style = style if style in STYLES else "line"
        self.cover = 0.0              # defend: the side it has moved to (0 = not defending)
        self.cover_until = -1.0

    def reset(self, world, car_index: int) -> None:
        super().reset(world, car_index)
        self.cover, self.cover_until = 0.0, -1.0

    def act(self, world, car_index: int) -> Controls:
        c = super().act(world, car_index)
        car = world.cars[car_index]
        throttle = c.throttle if car.speed < self.pace * car.params.top_speed else 0.0
        steer = c.steering
        offset = self._offset(world, car_index)
        if offset is not None:
            target = offset * world.track.half_width_at(car.s)
            steer = max(-1.0, min(1.0, steer + 0.08 * (target - car.lateral)))
        return Controls(steer, throttle, c.brake)

    def _offset(self, world, me: int):
        """Where across the track it wants to be (fraction of the half-width), or None."""
        car = world.cars[me]
        if self.style == "wander":
            return 0.45 * math.sin(world.time * 0.7 + me * 1.9)
        if self.style != "defend":
            return None
        if world.time < self.cover_until:
            return self.cover
        length = world.track.length
        half = length / 2.0
        for j, other in enumerate(world.cars):
            if j == me or other.retired:
                continue
            gap = (car.s - other.s + half) % length - half          # + = other is behind me
            if 0.0 < gap < 8.0 and other.speed > car.speed + 1.0:
                self.cover = 0.5 if other.lateral > car.lateral else -0.5   # cover the side it is on
                self.cover_until = world.time + 2.5
                return self.cover
        return None


def parse(key: str) -> dict:
    """"traffic:<pace>:<style>" -> keyword arguments."""
    _, pace, style = key.split(":")
    return {"pace": float(pace), "style": style}
