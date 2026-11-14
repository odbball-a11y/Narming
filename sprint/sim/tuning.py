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

    # Tyre scrub: a car that keeps sliding sideways loses forward speed in
    # proportion (deceleration = scrub x the sideways speed grip could not
    # remove).  0 = a slide is free (the original model, "classic" physics).  A clean line never
    # slides, so it never pays this.
    scrub: float = 8.0

    # Friction circle: braking and throttle use up the tyres' grip budget, so
    # cornering grip = grip x sqrt(1 - (brake_circle x brake)^2 - (throttle_circle x throttle)^2).
    # Both 0 = the original linear throttle/brake grip losses above (classic).
    # 0.8 / 0.6: braking while turning costs a lot of grip (0.6 x at full brake);
    # full throttle costs about what the linear loss did.
    brake_circle: float = 0.8
    throttle_circle: float = 0.6

    # --- two-grip model: understeer, oversteer and yaw inertia (0 = off) ---

    # Front tyres' lateral grip as a fraction of `grip`.  When steering asks
    # for more sideways acceleration than this the car turns less than
    # commanded and runs wide (understeer), and braking eats this grip (turn-in
    # understeer).  The rear end is the `grip` above: throttle eats it (power
    # oversteer) and braking unloads it (lift-off oversteer, see brake_transfer).
    # 0 = steering always gets what it asks, as in the original model.
    front_limit: float = 1.1   # was 1.2 (user: the rear stepped out too easily through the Esses)

    # Seconds the car takes to rotate to what steering asks (yaw inertia).
    # While the rear is sliding the lag grows (a spin keeps spinning).
    # 0 = rotation is instant.
    yaw_lag: float = 0.08

    # Car balance, -1 (stable: understeers first) .. +1 (loose: oversteers
    # first).  Moves grip between the front and the rear by 15% each way.
    balance: float = 0.0

    # Share of the rear grip lost under full braking (weight moves forward).
    brake_transfer: float = 0.25

    # --- weight transfer (needs the two-grip model; 0 = off) ---

    # Share of the axle load moved from one end to the other per "g" of
    # forward acceleration (g here = the car's own cornering grip, `grip`).
    # Braking loads the front (sharper turn-in, light rear: lift-off and
    # trail-braking oversteer); accelerating loads the rear (power
    # understeer, better traction).  About centre-of-gravity height / wheelbase.
    weight_transfer: float = 0.2

    # Grip lost to sideways load transfer at the cornering limit (the outside
    # tyres take the load but give less grip per unit of load).
    lateral_transfer: float = 0.1

    # Tyres give a little less grip per unit of load as load rises.
    load_sensitivity: float = 0.9

    # Seconds the suspension takes to move the load (the transfer lags the
    # acceleration that causes it).
    suspension_lag: float = 0.08

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

    # The car's traits as the driver sees them (see sim/cartraits.py):
    # top speed, acceleration, handling, braking, each -1..1 (1 to 5 stars),
    # and weight -1 light, 0 medium, 1 heavy.  Physics does not read these;
    # the values above already include the traits' effects.
    traits: tuple = (0.0, 0.0, 0.0, 0.0, 0.0)


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
# Car traits (AI racers' cars; see sim/cartraits.py)
# --------------------------------------------------------------------------

# Stars per car to spread over top speed, acceleration, handling and braking
# (each 1-5).  Every car has the same budget: different, never simply better.
TRAIT_BUDGET = 12

# Effect of one star either side of 3, as a fraction.
# Higher: specialists differ more and suit their tracks more strongly.
TRAIT_STEP = 0.04

# Weight costs no stars; it is a trade-off.  Heavy cars win shoves but
# accelerate and brake a little worse; light cars the reverse.
LIGHT_MASS = 0.8
HEAVY_MASS = 1.3
WEIGHT_PERFORMANCE = 0.04     # light: +4% accel and brakes; heavy: -4%


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
# Damage (permanent for the race; affects speed only, never steering)
# --------------------------------------------------------------------------

# Impacts gentler than this (closing speed, units/s) do no damage.
# Higher: only real crashes hurt.  Lower: every little tap counts.
DAMAGE_MIN_IMPACT = 3.0

# Damage added per unit of impact speed above the minimum.  Damage runs from
# 0 (new) to 1 (wrecked).  With 0.012 a flat-out head-on barrier hit (about
# 30 units/s) costs roughly a third of the car.
WALL_DAMAGE = 0.012

# Same for car-to-car hits; both cars take it.
CAR_DAMAGE = 0.008

# What a fully wrecked car loses.  0.30 means top speed falls to 70%.
# Higher: crashes decide races.  Lower: damage is cosmetic.
DAMAGE_TOP_SPEED_LOSS = 0.30
DAMAGE_ACCEL_LOSS = 0.35


# --------------------------------------------------------------------------
# Drafting (slipstream)
# --------------------------------------------------------------------------

# How far behind another car the tow reaches (units; a car is about 4 long).
# Longer: easier to pick up a tow.
DRAFT_LENGTH = 24.0

# Half-width of the tow right behind the lead car, and how much wider it gets
# per unit of distance behind.  Wider: less precision needed to stay in it.
DRAFT_HALF_WIDTH = 1.7
DRAFT_SPREAD = 0.10

# The lead car must be going at least this fast to punch a hole in the air.
DRAFT_MIN_SPEED = 12.0

# Extra top speed and acceleration at full tow (right on the leader's tail).
# Higher: slipstream passes are easy, packs form.  0 switches drafting off.
DRAFT_TOP_SPEED_GAIN = 0.15
DRAFT_ACCEL_GAIN = 0.40


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

# Traffic: when another car is this close ahead (units along the track) the
# scripted driver moves off its line to go round it, by up to
# SCRIPT_PASS_OFFSET units sideways, and lifts if it is about to hit it.
SCRIPT_TRAFFIC_RANGE = 14.0
SCRIPT_PASS_OFFSET = 3.0
SCRIPT_REVERSE_TIME = 0.9


# --------------------------------------------------------------------------
# Race rules
# --------------------------------------------------------------------------

# Seconds between the 3, 2, 1 lights; the race starts after three of them.
COUNTDOWN_STEP = 1.0

# Rolling start: the cars begin in single file on the run to the line, already
# moving at ROLLING_START_SPEED, ROLLING_START_GAP apart (centre to centre; a
# car is about 4 long).  The gap is well inside the tow, so every car behind
# the leader starts in a slipstream.
# Smaller gap: tighter pack, more contact at the first corner.
ROLLING_START_SPEED = 21.0
ROLLING_START_GAP = 9.0
# How far before the line the leading car starts.
ROLLING_START_LEAD = 4.0

# Once the winner finishes, the others get this many seconds to finish too.
FINISH_GRACE = 30.0

# Seconds the cars keep rolling after the last finisher before the results.
COOLDOWN = 1.5


CLASSIC_PHYSICS = {"scrub": 0.0, "brake_circle": 0.0, "throttle_circle": 0.0,   # the physics before tyre scrub
                   "front_limit": 0.0, "yaw_lag": 0.0, "weight_transfer": 0.0, "lateral_transfer": 0.0}
# Options left out of the physics fingerprint while at these values, so recordings still match.
_NEWER_PHYSICS = dict(CLASSIC_PHYSICS, balance=0.0, brake_transfer=0.25, load_sensitivity=0.9,
                      suspension_lag=0.08)


def _fingerprint_params():
    """repr(CAR_PARAMS) leaving out physics options that are switched off, so
    recordings made before they existed still match."""
    text = repr(CAR_PARAMS)
    for key, default in _NEWER_PHYSICS.items():
        text = text.replace(f", {key}={default!r}", "")

    class _Plain:                      # repr() of the text itself, without quotes
        def __repr__(self):
            return text
    return _Plain()


def physics_fingerprint() -> str:
    """Identifies the values a recorded replay depends on.  A replay made
    with a different fingerprint may not play back identically."""
    import hashlib
    parts = (TICK_RATE, _fingerprint_params(), GRASS_GRIP, GRASS_DRAG, WALL_RESTITUTION,
             WALL_FRICTION, CAR_RESTITUTION, DAMAGE_MIN_IMPACT, WALL_DAMAGE, CAR_DAMAGE,
             DAMAGE_TOP_SPEED_LOSS, DAMAGE_ACCEL_LOSS, DRAFT_LENGTH, DRAFT_HALF_WIDTH,
             DRAFT_SPREAD, DRAFT_MIN_SPEED, DRAFT_TOP_SPEED_GAIN, DRAFT_ACCEL_GAIN,
             ROLLING_START_SPEED, ROLLING_START_GAP, ROLLING_START_LEAD,
             TRAIT_BUDGET, TRAIT_STEP, LIGHT_MASS, HEAVY_MASS, WEIGHT_PERFORMANCE)
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]
