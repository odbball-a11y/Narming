"""Arcade car physics.

Not "rotate and move forward": the velocity vector is tracked separately from
the heading.  Each tick the velocity is split into a forward part and a
sideways part in the car's own frame.  Tyres cancel sideways speed, but only
at a limited rate (`grip`).  Turning at speed keeps converting forward speed
into sideways speed; when that happens faster than grip can remove it, the
car slides, and it recovers when you slow down, straighten up or lift.
"""
from __future__ import annotations

import math

from . import tuning
from .tuning import CarParams


class Car:
    __slots__ = (
        "params", "x", "y", "vx", "vy", "heading",
        "prev_x", "prev_y", "prev_heading",
        "idx", "s", "lateral", "surface",
        "speed", "forward_speed", "slip", "sliding",
        "steering", "throttle", "brake",
        "next_checkpoint", "crossed_start", "laps", "lap_start_time",
        "last_lap", "best_lap", "lap_times", "checkpoints_passed",
        "finished", "finish_time",
        "damage", "draft", "draft_source", "retired",
        "yaw_rate", "front_use", "rear_slip",
    )

    def __init__(self, params: CarParams):
        self.params = params
        self.place(0.0, 0.0, 0.0)

    def place(self, x: float, y: float, heading: float) -> None:
        """Put the car somewhere, stationary, with a clean race record."""
        self.x = self.prev_x = x
        self.y = self.prev_y = y
        self.heading = self.prev_heading = heading
        self.vx = self.vy = 0.0
        self.idx = 0
        self.s = self.lateral = 0.0
        self.surface = 0
        self.speed = self.forward_speed = self.slip = 0.0
        self.sliding = False
        self.steering = self.throttle = self.brake = 0.0
        self.next_checkpoint = 0
        self.crossed_start = False
        self.laps = 0
        self.lap_start_time = 0.0
        self.last_lap = None
        self.best_lap = None
        self.lap_times = []
        self.checkpoints_passed = 0
        self.finished = False
        self.finish_time = None
        self.damage = 0.0          # 0 = new, 1 = wrecked; permanent for the race
        self.draft = 0.0           # 0..1 strength of the tow this tick
        self.draft_source = -1     # index of the car giving the tow, or -1
        self.retired = False       # retired cars are not simulated (AI training)
        self.yaw_rate = 0.0        # rad/s, with yaw inertia on; otherwise what steering commands
        self.front_use = 0.0       # steering demand / front grip: above 1 the car understeers
        self.rear_slip = 0.0       # 0..1, how far the rear end is sliding

    def add_damage(self, amount: float) -> None:
        if amount > 0.0:
            self.damage = min(1.0, self.damage + amount)

    def refresh_speed(self) -> None:
        """Recompute the derived speeds after something changed vx, vy."""
        ch, sh = math.cos(self.heading), math.sin(self.heading)
        self.forward_speed = self.vx * ch + self.vy * sh
        self.slip = abs(-self.vx * sh + self.vy * ch)
        self.speed = math.hypot(self.vx, self.vy)

    def state(self) -> tuple:
        """Everything that defines the car's physical and race state."""
        return (self.x, self.y, self.vx, self.vy, self.heading, self.idx,
                self.next_checkpoint, self.crossed_start, self.laps,
                self.lap_start_time, tuple(self.lap_times),
                self.checkpoints_passed, self.finished, self.finish_time,
                self.damage, self.retired, self.yaw_rate)

    def step(self, steering: float, throttle: float, brake: float, on_grass: bool) -> None:
        """Advance one tick.  Inputs must already be clamped."""
        p = self.params
        dt = tuning.DT
        self.prev_x, self.prev_y, self.prev_heading = self.x, self.y, self.heading
        self.steering, self.throttle, self.brake = steering, throttle, brake

        # --- steering: speed-sensitive turn rate ---------------------------
        ch, sh = math.cos(self.heading), math.sin(self.heading)
        vf = self.vx * ch + self.vy * sh
        avf = abs(vf)
        authority = min(avf / p.steer_full_speed, 1.0)
        blend = min(avf / p.top_speed, 1.0)
        rate = p.steer_rate_low + (p.steer_rate_high - p.steer_rate_low) * blend
        direction = 1.0 if vf >= 0.0 else -1.0  # steering reverses in reverse
        omega = steering * rate * authority * direction
        two_grip = p.front_limit > 0.0
        if two_grip:
            # Front tyres: steering can only turn the car as far as they can hold.
            front = p.grip * p.front_limit * (1.0 + 0.15 * p.balance)
            front *= math.sqrt(max(0.0, 1.0 - (p.brake_circle * brake) ** 2))
            if on_grass:
                front *= tuning.GRASS_GRIP
            demand = avf * abs(omega)
            self.front_use = demand / front if front > 0.0 else 0.0
            if demand > front > 0.0:
                omega *= front / demand
        if p.yaw_lag > 0.0:
            tau = p.yaw_lag * (1.0 + 2.0 * self.rear_slip)       # a sliding rear end stops damping the rotation
            self.yaw_rate += (omega - self.yaw_rate) * min(1.0, dt / tau)
            omega = self.yaw_rate
        else:
            self.yaw_rate = omega
        self.heading += omega * dt

        # --- split velocity in the car's (new) frame -----------------------
        ch, sh = math.cos(self.heading), math.sin(self.heading)
        vf = self.vx * ch + self.vy * sh       # forward speed
        vl = -self.vx * sh + self.vy * ch      # sideways speed (+ = to the right)

        # --- engine, brake, reverse ----------------------------------------
        # Damage saps the engine; a tow from the car ahead helps it.
        damage, draft = self.damage, self.draft
        top = (p.top_speed * (1.0 - tuning.DAMAGE_TOP_SPEED_LOSS * damage)
               * (1.0 + tuning.DRAFT_TOP_SPEED_GAIN * draft))
        accel = (p.accel * (1.0 - tuning.DAMAGE_ACCEL_LOSS * damage)
                 * (1.0 + tuning.DRAFT_ACCEL_GAIN * draft))
        if throttle > 0.0:
            if vf < top:
                vf += throttle * accel * (1.0 - max(vf, 0.0) / top) ** 0.5 * dt
        if brake > 0.0:
            if vf > 0.3:
                vf = max(vf - brake * p.brake_decel * dt, 0.0)
            elif throttle == 0.0 and vf > -p.reverse_speed:
                vf -= brake * p.reverse_accel * dt   # brake doubles as reverse

        # --- rolling friction and drag (always oppose motion) --------------
        resist = (p.rolling_friction + p.drag * vf * vf) * dt
        if vf > resist:
            vf -= resist
        elif vf < -resist:
            vf += resist
        else:
            vf = 0.0

        # --- lateral grip: remove sideways speed at a limited rate ---------
        if two_grip:
            # Rear tyres: power eats their grip; braking unloads them.
            used = (p.throttle_circle * throttle) ** 2
            grip = p.grip * (1.0 - 0.15 * p.balance) * math.sqrt(max(0.0, 1.0 - used))
            grip *= 1.0 - p.brake_transfer * brake
        elif p.brake_circle or p.throttle_circle:
            used = (p.brake_circle * brake) ** 2 + (p.throttle_circle * throttle) ** 2
            grip = p.grip * math.sqrt(max(0.0, 1.0 - used))
        else:
            grip = p.grip * (1.0 - p.throttle_grip_loss * throttle) * (1.0 - p.brake_grip_loss * brake)
        if on_grass:
            grip *= tuning.GRASS_GRIP
        max_cancel = grip * dt
        if vl > max_cancel:
            vl -= max_cancel
        elif vl < -max_cancel:
            vl += max_cancel
        else:
            vl = 0.0

        if p.scrub and vf > 0.0:                      # what is still sliding drags the car back
            vf = max(0.0, vf - p.scrub * abs(vl) * dt)

        # --- back to world frame, surface drag, integrate ------------------
        vx = vf * ch - vl * sh
        vy = vf * sh + vl * ch
        if on_grass:
            keep = max(0.0, 1.0 - tuning.GRASS_DRAG * dt)
            vx *= keep
            vy *= keep
            vl *= keep
            vf *= keep
        self.vx, self.vy = vx, vy
        self.x += vx * dt
        self.y += vy * dt

        self.forward_speed = vf
        self.slip = abs(vl)
        self.rear_slip = min(1.0, abs(vl) / 6.0)
        self.speed = math.hypot(vx, vy)
        self.sliding = self.slip > p.slide_threshold
