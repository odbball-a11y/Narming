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

    def __init__(self, slot: int = 0, skill: float = 1.0):
        # skill scales the cornering speed it dares; 1.0 = tuning default.
        self.skill = skill

    def act(self, world, car_index: int) -> Controls:
        car = world.cars[car_index]
        track = world.track
        p = car.params
        speed = car.speed

        # --- steer toward a look-ahead point on the racing line ------------
        look = tuning.SCRIPT_LOOKAHEAD_BASE + tuning.SCRIPT_LOOKAHEAD_TIME * speed
        tx, ty = track.racing_line_point(car.s + look)
        angle = wrap_angle(math.atan2(ty - car.y, tx - car.x) - car.heading)
        steering = max(-1.0, min(1.0, tuning.SCRIPT_STEER_GAIN * angle))

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

        if speed > target * 1.03:
            return Controls(steering, 0.0, min(1.0, (speed - target) / 4.0 + 0.3))
        if speed < target:
            return Controls(steering, 1.0, 0.0)
        return Controls(steering, 0.3, 0.0)


register_driver("scripted", "Scripted", ScriptedDriver)
