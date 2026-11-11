"""The simulation world: a track, some cars, and one deterministic `step`.

No pygame, no wall-clock time, no unseeded randomness.  Time is the tick
counter; `World.time` is ticks * DT.  The same seed and the same sequence of
controls always produce the same state (see `state_hash`).
"""
from __future__ import annotations

import hashlib
import math
import random
import struct
from typing import Sequence

from . import tuning
from .car import Car
from .driver import Controls
from .track import GRASS, Track


class World:
    def __init__(self, track: Track, num_cars: int = 1, seed: int = 0,
                 slots: Sequence[int] | None = None, laps: int | None = None):
        """`slots` says which grid slot / parameter set each car uses
        (default 0..num_cars-1).  `laps` is the race distance."""
        self.track = track
        self.seed = seed
        self.slots = list(slots) if slots is not None else list(range(num_cars))
        self.laps = track.default_laps if laps is None else laps
        self.cars = [Car(tuning.car_params(slot)) for slot in self.slots]
        self.rng = random.Random(seed)
        self.tick = 0
        self.reset()

    # ------------------------------------------------------------- set-up

    def reset(self, seed: int | None = None) -> None:
        """Put every car back on the grid and restart the clock."""
        if seed is not None:
            self.seed = seed
        self.rng = random.Random(self.seed)
        self.tick = 0
        for car, slot in zip(self.cars, self.slots):
            car.params = tuning.car_params(slot)
            x, y, heading = self.track.grid[slot % len(self.track.grid)]
            self.place_car(car, x, y, heading)

    def place_car(self, car: Car, x: float, y: float, heading: float) -> None:
        car.place(x, y, heading)
        car.lap_start_time = self.time
        self._relocate(car, hint=None)

    def _relocate(self, car: Car, hint) -> None:
        track = self.track
        car.idx = track.nearest_index(car.x, car.y, hint)
        car.s, car.lateral = track.frenet(car.x, car.y, car.idx)
        car.surface = track.surface_at(car.idx, car.lateral)

    @property
    def time(self) -> float:
        return self.tick * tuning.DT

    # --------------------------------------------------------------- step

    def step(self, controls: Sequence[Controls]) -> list[tuple]:
        """Advance one tick.  `controls[i]` drives `cars[i]`.

        Returns the events of this tick, for sound and UI:
          ("wall", car_index, impact_speed)
          ("car", index_a, index_b, impact_speed)
          ("lap", car_index, lap_time)
          ("finish", car_index, race_time)
        """
        events: list[tuple] = []
        track = self.track
        for i, car in enumerate(self.cars):
            c = controls[i]
            steering = c[0]
            throttle = c[1]
            brake = c[2]
            steering = -1.0 if steering < -1.0 else 1.0 if steering > 1.0 else steering
            throttle = 0.0 if throttle < 0.0 else 1.0 if throttle > 1.0 else throttle
            brake = 0.0 if brake < 0.0 else 1.0 if brake > 1.0 else brake
            car.step(steering, throttle, brake, car.surface == GRASS)
            self._relocate(car, car.idx)
            self._collide_wall(i, car, events)

        self._collide_cars(events)

        self.tick += 1
        for i, car in enumerate(self.cars):
            self._update_checkpoints(i, car, events)
        return events

    # --------------------------------------------------------- collisions

    def _collide_wall(self, i: int, car: Car, events: list) -> None:
        track = self.track
        idx = car.idx
        room = track._lim[idx] - car.params.radius
        lat = car.lateral
        if -room <= lat <= room:
            return
        # Wall normal pointing back toward the road.
        side = 1.0 if lat > 0.0 else -1.0
        nx = track._ty[idx] * side
        ny = -track._tx[idx] * side
        over = abs(lat) - room
        car.x += nx * over
        car.y += ny * over
        vn = car.vx * nx + car.vy * ny
        if vn < 0.0:  # moving into the wall
            tx, ty = -ny, nx
            vt = car.vx * tx + car.vy * ty
            bounce = -vn * tuning.WALL_RESTITUTION
            scrub = tuning.WALL_FRICTION * (bounce - vn)
            if vt > scrub:
                vt -= scrub
            elif vt < -scrub:
                vt += scrub
            else:
                vt = 0.0
            car.vx = nx * bounce + tx * vt
            car.vy = ny * bounce + ty * vt
            car.refresh_speed()
            if -vn >= tuning.MIN_IMPACT_SPEED:
                events.append(("wall", i, -vn))
        self._relocate(car, idx)

    def _collide_cars(self, events: list) -> None:
        cars = self.cars
        count = len(cars)
        for a in range(count):
            ca = cars[a]
            for b in range(a + 1, count):
                cb = cars[b]
                dx = cb.x - ca.x
                dy = cb.y - ca.y
                reach = ca.params.radius + cb.params.radius
                d2 = dx * dx + dy * dy
                if d2 >= reach * reach:
                    continue
                dist = math.sqrt(d2)
                if dist > 1e-9:
                    nx, ny = dx / dist, dy / dist
                else:  # exactly on top of each other: push apart along x
                    nx, ny = 1.0, 0.0
                ma, mb = ca.params.mass, cb.params.mass
                total = ma + mb
                # Separate, lighter car moves more.
                over = reach - dist
                ca.x -= nx * over * (mb / total)
                ca.y -= ny * over * (mb / total)
                cb.x += nx * over * (ma / total)
                cb.y += ny * over * (ma / total)
                # Impulse along the line between centres.
                closing = (ca.vx - cb.vx) * nx + (ca.vy - cb.vy) * ny
                if closing > 0.0:
                    j = (1.0 + tuning.CAR_RESTITUTION) * closing / total
                    ca.vx -= j * mb * nx
                    ca.vy -= j * mb * ny
                    cb.vx += j * ma * nx
                    cb.vy += j * ma * ny
                    ca.refresh_speed()
                    cb.refresh_speed()
                    if closing >= tuning.MIN_IMPACT_SPEED:
                        events.append(("car", a, b, closing))
                self._relocate(ca, ca.idx)
                self._relocate(cb, cb.idx)

    # -------------------------------------------------------- lap counting

    def _update_checkpoints(self, i: int, car: Car, events: list) -> None:
        """Laps count only when the gates are crossed forwards and in order.

        Gate 0 is the start/finish line.  Cars start just behind it, so the
        first crossing only starts lap 1; each later crossing of gate 0, with
        every other gate passed in between, completes a lap.  Lap 1 is timed
        from the green light.
        """
        if car.finished:
            return
        ax, ay, bx, by, tx, ty = self.track.checkpoints[car.next_checkpoint]
        mx = car.x - car.prev_x
        my = car.y - car.prev_y
        if mx * tx + my * ty <= 0.0:
            return  # not moving forwards through the gate
        gx = bx - ax
        gy = by - ay
        denom = mx * gy - my * gx
        if denom == 0.0:
            return
        # prev + t * move == a + u * gate
        t = ((ax - car.prev_x) * gy - (ay - car.prev_y) * gx) / denom
        u = ((ax - car.prev_x) * my - (ay - car.prev_y) * mx) / denom
        if not (0.0 <= t < 1.0 and 0.0 <= u <= 1.0):
            return
        gate = car.next_checkpoint
        car.next_checkpoint = (gate + 1) % len(self.track.checkpoints)
        car.checkpoints_passed += 1
        if gate != 0:
            return
        if not car.crossed_start:
            car.crossed_start = True
            return
        # Sub-tick crossing time, so lap times are finer than 1/120 s.
        now = (self.tick - 1 + t) * tuning.DT
        lap_time = now - car.lap_start_time
        car.lap_start_time = now
        car.laps += 1
        car.last_lap = lap_time
        car.lap_times.append(lap_time)
        if car.best_lap is None or lap_time < car.best_lap:
            car.best_lap = lap_time
        events.append(("lap", i, lap_time))
        if car.laps >= self.laps:
            car.finished = True
            car.finish_time = now
            events.append(("finish", i, now))

    # ------------------------------------------------------------- queries

    def race_progress(self, car: Car) -> float:
        """Distance-like number that orders cars on track (bigger = ahead)."""
        gates = len(self.track.checkpoints)
        gate_len = self.track.length / gates
        last_gate = (car.next_checkpoint - 1) % gates
        into = (car.s - last_gate * gate_len) % self.track.length
        if into > self.track.length / 2:   # still behind the gate just crossed
            into -= self.track.length
        return car.checkpoints_passed * gate_len + min(into, gate_len)

    def standings(self) -> list[int]:
        """Car indices in race order.  Finishers first, by finish time."""
        def key(i):
            car = self.cars[i]
            if car.finished:
                return (0, car.finish_time, i)
            return (1, -self.race_progress(car), i)
        return sorted(range(len(self.cars)), key=key)

    def state(self) -> tuple:
        return (self.tick,) + tuple(car.state() for car in self.cars)

    def state_hash(self) -> str:
        """Bit-exact fingerprint of the whole state, for determinism checks."""
        h = hashlib.sha256()

        def feed(value):
            if isinstance(value, tuple):
                for v in value:
                    feed(v)
            elif isinstance(value, float):
                h.update(struct.pack("<d", value))
            else:
                h.update(repr(value).encode())

        feed(self.state())
        return h.hexdigest()
