"""Every tunable number in the game lives in this file.

Edit a value, then press F5 in the running game to reload this file without
restarting (the cars are put back on the grid).

Units: distance is in "track units" (a car is about 4 long, the whole screen
is 160 x 90), time is in seconds, angles are in radians.  So speed is units/s
and acceleration is units/s^2.

This module must stay free of pygame: `sim/` imports it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# --------------------------------------------------------------------------
# Simulation clock
# --------------------------------------------------------------------------

# Physics steps per second.  Everything in sim/ advances by exactly 1/TICK_RATE
# per step.  Do not change casually: recorded replays are only valid for the
# tick rate (and tuning values) they were recorded with.
TICK_RATE = 120
DT = 1.0 / TICK_RATE


# --------------------------------------------------------------------------
# Per-car parameters
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CarParams:
    # --- straight-line performance ---

    # Engine acceleration at low speed with full throttle.
    # Higher: punchier launches and corner exits, easier to light up a slide
    # on exit.  Lower: lazier car, top speed matters less on short straights.
    accel: float = 20.0

    # Speed at which the engine stops pushing.  Real terminal speed is a few
    # percent lower because rolling friction and drag still apply.
    # Higher: longer braking zones, corners arrive sooner, more sliding.
    top_speed: float = 32.0

    # Deceleration with the brake fully pressed.
    # Higher: brake later, car feels sharp.  Lower: must plan corners early.
    brake_decel: float = 42.0

    # Reverse gear (hold brake when almost stopped).  Only there to get you
    # off a barrier, so it is deliberately slow.
    reverse_accel: float = 12.0
    reverse_speed: float = 8.0

    # Constant deceleration whenever the car is moving (tyres, drivetrain).
    # Higher: car stops quickly when you lift.  Lower: coasts for ages.
    rolling_friction: float = 1.2

    # Air drag, multiplied by speed squared.
    # Higher: lowers real top speed, lifting at speed slows you more.
    drag: float = 0.002

    # --- cornering ---

    # Sideways grip: the most lateral speed the tyres can cancel per second
    # (i.e. the maximum cornering acceleration) on tarmac.
    # Higher: car is on rails, slides are rare and short.
    # Lower: car drifts wide everywhere, feels like ice.
    grip: float = 34.0

    # Fraction of grip lost at full throttle (0 = none).
    # Higher: power-slides on corner exit, lifting off tucks the car back in.
    # Lower: throttle has no effect on the slide.
    throttle_grip_loss: float = 0.18

    # Fraction of grip lost under full braking (0 = none).
    # Higher: braking while turning makes the tail step out.
    brake_grip_loss: float = 0.10

    # Maximum turn rate (rad/s) at low speed with full steering lock.
    # Higher: darts into hairpins, twitchy.  Lower: wide turning circle.
    steer_rate_low: float = 3.0

    # Maximum turn rate (rad/s) at top speed.  This is the speed-sensitive
    # part: the turn rate blends from steer_rate_low to this as speed rises.
    # Higher: nervous at speed and full lock will overwhelm grip (big slides).
    # Lower: stable on straights, needs braking to rotate.
    steer_rate_high: float = 1.5

    # Speed below which steering authority fades to zero (you cannot spin a
    # parked car).  Higher: sluggish at parking speeds.
    steer_full_speed: float = 6.0

    # Lateral speed above which the car counts as "sliding" (skid marks,
    # tyre squeal).  Does not affect physics.
    slide_threshold: float = 2.5

    # --- body ---

    # Collision circle radius.  The drawn car is CAR_LENGTH x CAR_WIDTH.
    radius: float = 1.7

    # Mass only matters in car-to-car hits: heavier cars shove lighter ones.
    mass: float = 1.0


# The four cars.  Each slot has its own parameter set; they start nearly equal
# so the racing is fair.  Change a slot here to give it a personality.
_BASE = CarParams()
CAR_PARAMS = [
    _BASE,                                             # slot 1: the baseline
    replace(_BASE, top_speed=33.0, grip=32.5),         # slot 2: faster, looser
    replace(_BASE, accel=22.0, top_speed=31.3),        # slot 3: quick off the line
    replace(_BASE, grip=36.0, top_speed=31.5),         # slot 4: grippy, slower
]

# Visual size of a car (drawing only).
CAR_LENGTH = 4.2
CAR_WIDTH = 2.3


def car_params(slot: int) -> CarParams:
    return CAR_PARAMS[slot % len(CAR_PARAMS)]


# --------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------

# Grip on the grass verge as a fraction of tarmac grip.
# Lower: the car slews around helplessly once it leaves the track.
GRASS_GRIP = 0.40

# Extra drag on grass, per second, proportional to speed (1.5 means the grass
# tries to remove 150% of your speed every second).
# Higher: running wide costs more time; top speed on grass = accel / this.
GRASS_DRAG = 1.5


# --------------------------------------------------------------------------
# Collisions
# --------------------------------------------------------------------------

# Bounce off the barrier: 0 = dead stop against the wall, 1 = perfect rebound.
# Higher: pinball.  Lower: walls feel like sandbags.
WALL_RESTITUTION = 0.35

# How much a wall hit scrubs the speed *along* the wall, per unit of impact.
# Higher: even glancing hits cost a lot.  0: you can wall-ride for free.
WALL_FRICTION = 0.45

# Bounce between cars (same 0..1 meaning as the wall).
CAR_RESTITUTION = 0.5

# Impacts slower than this make no sound and raise no event.
MIN_IMPACT_SPEED = 2.0


# --------------------------------------------------------------------------
# Human keyboard input (used by game/, kept here so all tuning is in one file)
# --------------------------------------------------------------------------

# A key is either down or up, so the keyboard driver ramps the steering value.
# How fast steering moves toward full lock while a key is held (per second;
# 6 means centre to full lock in 1/6 s).
# Higher: instant, twitchy.  Lower: smooth but laggy.
KEY_STEER_RATE = 5.0

# How fast steering returns to centre when the keys are released (per second).
KEY_STEER_RETURN_RATE = 8.0

# When you press the opposite direction the steering first has to cross
# centre; it does so at this (faster) rate so direction changes feel snappy.
KEY_STEER_COUNTER_RATE = 12.0

# Throttle and brake ramp (per second).  High values = effectively on/off.
KEY_PEDAL_RATE = 12.0


# --------------------------------------------------------------------------
# Scripted driver
# --------------------------------------------------------------------------

# Look-ahead distance = SCRIPT_LOOKAHEAD_BASE + SCRIPT_LOOKAHEAD_TIME * speed.
# Longer: smoother but cuts corners.  Shorter: accurate but can weave.
SCRIPT_LOOKAHEAD_BASE = 5.0
SCRIPT_LOOKAHEAD_TIME = 0.22

# Steering gain on the angle to the look-ahead point.
SCRIPT_STEER_GAIN = 2.2

# Fraction of the car's grip the scripted driver is willing to use in a
# corner.  1.0 = on the limit (will slide), 0.6 = Sunday driver.
SCRIPT_CORNER_GRIP = 0.72

# Fraction of the car's braking the scripted driver plans with.
SCRIPT_BRAKE_USE = 0.6

# Each scripted car is a little slower than the one in the slot before it, so
# a field of scripted cars spreads out instead of queueing nose to tail.
# This is the fraction of cornering grip given up per slot.
SCRIPT_SLOT_HANDICAP = 0.04

# If a scripted car has been almost stationary for this long (seconds) it
# assumes it is stuck on a barrier and reverses out for SCRIPT_REVERSE_TIME.
SCRIPT_STUCK_TIME = 1.0
SCRIPT_REVERSE_TIME = 0.9


# --------------------------------------------------------------------------
# Race rules
# --------------------------------------------------------------------------

# Seconds between the 3, 2, 1 lights; the race starts after three of them.
COUNTDOWN_STEP = 1.0

# Once the winner finishes, the others get this many seconds to finish too.
FINISH_GRACE = 30.0

# Seconds the cars keep rolling after the last finisher before the results.
COOLDOWN = 1.5


def physics_fingerprint() -> str:
    """Identifies the values a recorded replay depends on.  A replay made
    with a different fingerprint may not play back identically."""
    import hashlib
    parts = (TICK_RATE, CAR_PARAMS, GRASS_GRIP, GRASS_DRAG, WALL_RESTITUTION,
             WALL_FRICTION, CAR_RESTITUTION)
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]
