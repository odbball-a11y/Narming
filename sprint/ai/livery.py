"""Racer liveries: a colour, a trim and a number that make each AI racer
easy to recognise on track.

A livery is plain data, stored with the racer (no pygame here):

    {"colour": "red", "trim": "stripe", "trim_colour": "white", "number": 13}

The game assigns it when a racer is created, and a bred foal gets a family
look: its own body colour, its sire's colour as trim colour and its dam's
trim style.  Dangerous Dave is always red and Careful Keith always green.
"""
from __future__ import annotations

PALETTE = {
    "red": (236, 52, 60), "green": (60, 200, 100), "blue": (48, 140, 255), "yellow": (255, 214, 10),
    "orange": (255, 140, 30), "purple": (170, 90, 255), "pink": (255, 105, 190), "cyan": (40, 215, 225),
    "white": (240, 240, 245), "lime": (200, 235, 50),
}
DARK = (28, 28, 40)
# Red and green belong to the house rivals Dangerous Dave and Careful Keith.
RESERVED = ("red", "green")
ORDER = [c for c in PALETTE if c not in RESERVED]
TRIMS = ("stripe", "twin", "nose", "wing", "band")
LIGHT_BODIES = ("white", "yellow", "cyan", "lime", "orange", "pink")
# Colours of the four standard slots, for cars with no livery (human, scripted).
SLOT_COLOURS = ("red", "blue", "yellow", "green", "purple", "cyan")
FIRST_NUMBER = 10


def rgb(name: str) -> tuple:
    return PALETTE.get(name, DARK)


def trim_rgb(livery: dict) -> tuple:
    return PALETTE.get(livery.get("trim_colour", "white"), DARK if livery.get("trim_colour") == "dark" else
                       (250, 250, 250))


def _default_trim_colour(body: str) -> str:
    return "dark" if body in LIGHT_BODIES else "white"


def _free_number(taken: list[dict]) -> int:
    used = {t.get("number") for t in taken}
    n = FIRST_NUMBER
    while n in used or n in (5, 13):          # Keith's and Dave's numbers
        n += 1
    return n


def _free_colour(taken: list[dict]) -> str:
    """The first colour nobody has; if all are taken, the least used."""
    count = {c: 0 for c in ORDER}
    for t in taken:
        if t.get("colour") in count:
            count[t["colour"]] += 1
    return min(ORDER, key=lambda c: (count[c], ORDER.index(c)))


def assign(taken: list[dict]) -> dict:
    """A livery for a new racer, different from `taken` (the liveries of the
    racers and house rivals already about)."""
    colour = _free_colour(taken)
    return {"colour": colour, "trim": TRIMS[len(taken) % len(TRIMS)],
            "trim_colour": _default_trim_colour(colour), "number": _free_number(taken)}


def inherit(sire: dict, dam: dict, taken: list[dict]) -> dict:
    """A foal's family look: its own free body colour, its sire's colour as
    trim colour and its dam's trim style."""
    colour = _free_colour(taken)
    trim_colour = sire["colour"] if sire["colour"] != colour else _default_trim_colour(colour)
    return {"colour": colour, "trim": dam.get("trim", TRIMS[0]), "trim_colour": trim_colour,
            "number": _free_number(taken)}


def resolve(drivers: list, slots: list[int]) -> list[dict]:
    """The livery shown for each car of a race: a driver's own (`driver.livery`),
    or its slot's standard colour.  Cars with no livery never take a colour
    a liveried car has: they get the next free one instead."""
    out = []
    used = {getattr(d, "livery", None)["colour"] for d in drivers if getattr(d, "livery", None)}
    for i, driver in enumerate(drivers):
        own = getattr(driver, "livery", None)
        if own:
            out.append(dict(own))
            continue
        colour = SLOT_COLOURS[slots[i] % len(SLOT_COLOURS)]
        if colour in used:
            colour = next(c for c in list(PALETTE) if c not in used)
        used.add(colour)
        out.append({"colour": colour, "trim": "stripe", "trim_colour": "white", "number": slots[i] + 1})
    return out
