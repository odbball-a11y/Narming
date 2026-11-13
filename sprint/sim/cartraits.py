"""Car traits: what makes one AI racer's car different from another's.

A car has 1-5 stars in each of four traits, all cars sharing the same
budget (`tuning.TRAIT_BUDGET`), and a weight class:

    {"top_speed": 3, "accel": 3, "handling": 3, "braking": 3, "weight": "medium"}

Each star either side of 3 changes the car by `tuning.TRAIT_STEP`.  Weight
costs no stars: heavy cars shove harder in contact but accelerate and brake a
little worse; light cars the reverse.

Pure functions only (sim/ rule: no pygame, no clocks, no unseeded randomness;
callers pass their own random generator).
"""
from __future__ import annotations

from dataclasses import replace

from . import tuning
from .tuning import CarParams

STARS = ("top_speed", "accel", "handling", "braking")
WEIGHTS = ("light", "medium", "heavy")
LABELS = {"top_speed": "TOP SPEED", "accel": "ACCELERATION", "handling": "HANDLING", "braking": "BRAKING"}
MIN_STARS, MAX_STARS = 1, 5
# Balance costs no stars: -2 (very stable, understeers first) .. +2 (very loose,
# oversteers first).  A car without the key is neutral.  It only matters with the
# two-grip physics (`CarParams.front_limit`); it is bred, never chosen.
BALANCES = (-2, -1, 0, 1, 2)
BALANCE_NAMES = {-2: "very stable", -1: "stable", 0: "neutral", 1: "loose", 2: "very loose"}


def balance_of(traits: dict | None) -> int:
    return int((traits or {}).get("balance", 0))


def default() -> dict:
    """The standard car: 3 stars everywhere, medium weight (today's car)."""
    return {"top_speed": 3, "accel": 3, "handling": 3, "braking": 3, "weight": "medium"}


def stars_used(traits: dict) -> int:
    return sum(int(traits[k]) for k in STARS)


def is_valid(traits: dict) -> bool:
    return (all(MIN_STARS <= int(traits[k]) <= MAX_STARS for k in STARS)
            and stars_used(traits) == tuning.TRAIT_BUDGET and traits.get("weight") in WEIGHTS)


def params_for(traits: dict | None, base: CarParams | None = None) -> CarParams:
    """Physics parameters for a car with these traits."""
    base = base or CarParams()
    if traits is None:
        return base
    step = tuning.TRAIT_STEP

    def scale(key):
        return 1.0 + step * (int(traits[key]) - 3)

    weight = traits.get("weight", "medium")
    w_perf = {"light": 1.0 + tuning.WEIGHT_PERFORMANCE, "medium": 1.0,
              "heavy": 1.0 - tuning.WEIGHT_PERFORMANCE}[weight]
    mass = {"light": tuning.LIGHT_MASS, "medium": 1.0, "heavy": tuning.HEAVY_MASS}[weight]
    hand = scale("handling")
    steer = 1.0 + 0.5 * step * (int(traits["handling"]) - 3)
    return replace(
        base,
        top_speed=base.top_speed * scale("top_speed"),
        accel=base.accel * scale("accel") * w_perf,
        grip=base.grip * hand,
        steer_rate_low=base.steer_rate_low * steer,
        steer_rate_high=base.steer_rate_high * steer,
        brake_decel=base.brake_decel * scale("braking") * w_perf,
        mass=mass,
        balance=balance_of(traits) / 2.0,
        traits=tuple([(int(traits[k]) - 3) / 2.0 for k in STARS]
                     + [{"light": -1.0, "medium": 0.0, "heavy": 1.0}[weight]]),
    )


def rebalance(traits: dict, rng) -> dict:
    """Bring the stars back to the budget, a star at a time, picking traits
    at random (`rng` is a numpy Generator or random.Random)."""
    out = dict(traits)

    def pick(keys):
        return keys[int(rng.integers(0, len(keys)))] if hasattr(rng, "integers") else rng.choice(keys)

    while stars_used(out) > tuning.TRAIT_BUDGET:
        out[pick([k for k in STARS if out[k] > MIN_STARS])] -= 1
    while stars_used(out) < tuning.TRAIT_BUDGET:
        out[pick([k for k in STARS if out[k] < MAX_STARS])] += 1
    return out


def random_traits(rng) -> dict:
    """A random valid car (used to train drivers that can drive anything)."""
    stars = {k: int(rng.integers(MIN_STARS, MAX_STARS + 1)) for k in STARS}
    stars["weight"] = WEIGHTS[int(rng.integers(0, 3))]
    stars["balance"] = BALANCES[int(rng.integers(0, len(BALANCES)))]
    return rebalance(stars, rng)


def inherit(sire: dict, dam: dict, rng) -> tuple[dict, dict]:
    """A foal's car: each trait from one parent or the other, sometimes a
    star up or down, then rebalanced to the budget; weight from one parent.
    Returns (traits, which parent each came from)."""
    child, source = {}, {}
    for key in STARS + ("weight",):
        from_sire = rng.random() < 0.5
        child[key] = (sire if from_sire else dam).get(key, default()[key])
        source[key] = "sire" if from_sire else "dam"
    for key in STARS:
        if rng.random() < 0.25:
            child[key] = min(MAX_STARS, max(MIN_STARS, int(child[key]) + (1 if rng.random() < 0.5 else -1)))
    from_sire = rng.random() < 0.5                       # balance: from one parent, sometimes a step either way
    child["balance"] = balance_of(sire if from_sire else dam)
    source["balance"] = "sire" if from_sire else "dam"
    if rng.random() < 0.25:
        child["balance"] = max(BALANCES[0], min(BALANCES[-1], child["balance"] + (1 if rng.random() < 0.5 else -1)))
    return rebalance(child, rng), source


def describe(traits: dict) -> str:
    short = {"top_speed": "speed", "accel": "accel", "handling": "handling", "braking": "brakes"}
    text = "  ".join(f"{short[k]} {traits[k]}" for k in STARS) + f"  {traits['weight']}"
    if balance_of(traits):
        text += f"  {BALANCE_NAMES[balance_of(traits)]}"
    return text
