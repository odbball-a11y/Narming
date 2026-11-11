"""Rule-based driver: aim at a point ahead on the racing line, slow for bends.

It is the single-player opponent and the test tool that proves laps can be
completed.  It only uses the public track queries, the same ones a learned
driver will get in Stage 2.
"""
from __future__ import annotations

import math

from . import tuning
from .driver import Controls, Driver, register_driver
from .track import wrap_angle


class ScriptedDriver(Driver):
    label = "Scripted"

    def __init__(self, slot: int = 0, skill: float | None = None):
        # skill scales the cornering grip it dares to use; 1.0 = tuning default.
        if skill is None:
            skill = 1.0 - tuning.SCRIPT_SLOT_HANDICAP * slot
        self.skill = skill
        self.stuck_ticks = 0
        self.reverse_ticks = 0

    def reset(self, world, car_index: int) -> None:
        self.stuck_ticks = 0
        self.reverse_ticks = 0

    def act(self, world, car_index: int) -> Controls:
        car = world.cars[car_index]
        track = world.track
        p = car.params
        speed = car.speed

        # --- steer toward a look-ahead point on the racing line ------------
        look = tuning.SCRIPT_LOOKAHEAD_BASE + tuning.SCRIPT_LOOKAHEAD_TIME * speed
        tx, ty = track.racing_line_point(car.s + look)

        # --- traffic: go round a car just ahead, lift if about to hit it ----
        lift = False
        if len(world.cars) > 1 and not world.ghost:
            L = track.length
            reach = tuning.SCRIPT_TRAFFIC_RANGE
            nearest = reach
            other = None
            for j, o in enumerate(world.cars):
                if j == car_index or o.retired:
                    continue
                gap = (o.s - car.s) % L
                if 0.0 < gap < nearest:
                    nearest, other = gap, o
            if other is not None:
                side = car.lateral - other.lateral
                if abs(side) < 3.0:
                    # Pass on the side we are already on (or the roomier one).
                    way = 1.0 if (side > 0.0 or (side == 0.0 and other.lateral < 0.0)) else -1.0
                    idx = track.index_at(car.s + look)
                    room = track._hw[idx] - 1.6
                    want = max(-room, min(room, other.lateral + way * tuning.SCRIPT_PASS_OFFSET))
                    weight = 1.0 - nearest / reach
                    shift = (want - track.racing_offset[idx]) * weight
                    tx += -track._ty[idx] * shift
                    ty += track._tx[idx] * shift
                    lift = nearest < 5.5 and abs(side) < 2.4 and speed > other.speed
        angle = wrap_angle(math.atan2(ty - car.y, tx - car.x) - car.heading)
        steering = max(-1.0, min(1.0, tuning.SCRIPT_STEER_GAIN * angle))

        # --- unstick: if we have stopped (nose on a barrier), back out ------
        if self.reverse_ticks > 0:
            self.reverse_ticks -= 1
            # Steering acts reversed when rolling backwards, so the same sign
            # swings the nose toward the target.
            return Controls(-steering if car.forward_speed < 0 else 0.0, 0.0, 1.0)
        if speed < 1.0:
            self.stuck_ticks += 1
            if self.stuck_ticks > tuning.SCRIPT_STUCK_TIME * tuning.TICK_RATE:
                self.stuck_ticks = 0
                self.reverse_ticks = int(tuning.SCRIPT_REVERSE_TIME * tuning.TICK_RATE)
        else:
            self.stuck_ticks = 0

        # --- pick a speed the bends ahead allow ----------------------------
        # A bend of curvature k can be taken at sqrt(grip / |k|).  For each
        # point ahead, the speed we may carry *now* is that corner speed plus
        # what we can still brake off in the distance to it.
        lat_acc = p.grip * tuning.SCRIPT_CORNER_GRIP * self.skill
        decel = p.brake_decel * tuning.SCRIPT_BRAKE_USE
        horizon = speed * speed / (2.0 * decel) + 12.0
        target = p.top_speed
        d = 0.0
        while d <= horizon:
            k = abs(track.curvature_ahead(car.s, d))
            if k > 1e-4:
                allowed = math.sqrt(lat_acc / k + 2.0 * decel * d)
                if allowed < target:
                    target = allowed
            d += 2.0

        if lift:
            return Controls(steering, 0.0, 0.25)
        if speed > target * 1.03:
            return Controls(steering, 0.0, min(1.0, (speed - target) / 4.0 + 0.3))
        if speed < target:
            return Controls(steering, 1.0, 0.0)
        return Controls(steering, 0.3, 0.0)


register_driver("scripted", "Scripted", ScriptedDriver)
