"""Lap telemetry: what every car did around a lap.

A `LapRecorder` follows a World and, for every car, keeps samples of where it
was, how fast it went and what its driver did, 30 times a second.  When a car
completes a flying lap (lap 2 onwards: lap 1 includes the start), the samples
are resampled to every SPACING units of track distance and the lap is kept
in `recorder.laps` as (car index, lap dict):

    {"time": lap time, "spacing": SPACING, "t": [...], "x": [...], "y": [...],
     "heading": [...], "lateral": [...], "speed": [...], "throttle": [...],
     "brake": [...], "steering": [...], "slip": [...]}

Every list has one value per SPACING units from the start line, so two laps
can be compared point by point.  Pure data: no files, no clocks (sim rules).
"""
from __future__ import annotations

import math

SAMPLE_TICKS = 4            # one sample every 4 ticks (30 a second)
SPACING = 2.0               # lap data every 2 track units
FIELDS = ("t", "x", "y", "heading", "lateral", "speed", "throttle", "brake", "steering", "slip")


class LapRecorder:
    def __init__(self, world):
        self.world = world
        self.buffers = [[] for _ in world.cars]
        self.started = [False] * len(world.cars)
        self.laps: list[tuple[int, dict]] = []

    def record(self, controls, events) -> None:
        """Call after every World.step with the controls applied and its events."""
        world = self.world
        for ev in events:
            if ev[0] == "lap":
                i = ev[1]
                car = world.cars[i]
                if car.laps >= 2:                          # a flying lap
                    lap = self._lap(i, ev[2])
                    if lap:
                        self.laps.append((i, lap))
                self.buffers[i] = []
        if world.tick % SAMPLE_TICKS:
            return
        for i, car in enumerate(world.cars):
            if car.retired:
                continue
            if car.crossed_start and not self.started[i]:  # the lap clock starts here
                self.started[i] = True
                self.buffers[i] = []
            if not self.started[i]:
                continue
            c = controls[i] if i < len(controls) else None
            self.buffers[i].append((world.time - car.lap_start_time, car.s, car.x, car.y, car.heading,
                                    car.lateral, car.speed, c.throttle if c else 0.0, c.brake if c else 0.0,
                                    c.steering if c else 0.0, car.slip))

    def _lap(self, i: int, lap_time: float) -> dict | None:
        samples = self.buffers[i]
        if len(samples) < 20:
            return None
        length = self.world.track.length
        kept, last_s = [], -1.0
        for row in samples:
            s = row[1]
            if s > length * 0.9 and not kept:              # still just before the line
                continue
            if s >= last_s:
                kept.append(row)
                last_s = s
        if len(kept) < 20:
            return None
        grid = [k * SPACING for k in range(int(length / SPACING))]
        out = {"time": float(lap_time), "spacing": SPACING}
        columns = list(zip(*kept))
        ss = columns[1]
        for name, col in zip(("t", None, "x", "y", "heading", "lateral", "speed", "throttle", "brake",
                              "steering", "slip"), columns):
            if name is None:
                continue
            if name == "heading":                          # unwrap so it interpolates smoothly
                col = list(col)
                for k in range(1, len(col)):
                    while col[k] - col[k - 1] > math.pi:
                        col[k] -= 2 * math.pi
                    while col[k] - col[k - 1] < -math.pi:
                        col[k] += 2 * math.pi
            out[name] = [round(_interp(g, ss, col), 4) for g in grid]
        return out


def _interp(x: float, xs, ys) -> float:
    """Linear interpolation of ys at x (xs increasing); clamps at the ends."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    f = (x - xs[lo]) / span if span > 0 else 0.0
    return ys[lo] + (ys[hi] - ys[lo]) * f


def pose_at(lap: dict, t: float) -> tuple[float, float, float] | None:
    """(x, y, heading) of the car `t` seconds into the recorded lap (for a ghost)."""
    times = lap["t"]
    if not times or t < 0 or t > lap["time"]:
        return None
    return (_interp(t, times, lap["x"]), _interp(t, times, lap["y"]), _interp(t, times, lap["heading"]))
