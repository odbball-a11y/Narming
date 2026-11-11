"""The one interface every car is controlled through.

A Driver is asked for Controls once per simulation tick.  Human keyboard
drivers (in game/), the scripted driver and, in Stage 2, learned policies all
implement it; the physics never knows where the controls came from.
"""
from __future__ import annotations

from typing import Callable, NamedTuple


class Controls(NamedTuple):
    steering: float = 0.0   # -1 (full left) .. +1 (full right)
    throttle: float = 0.0   # 0 .. 1
    brake: float = 0.0      # 0 .. 1 (also reverses when nearly stopped)

    def clamped(self) -> "Controls":
        return Controls(
            max(-1.0, min(1.0, float(self.steering))),
            max(0.0, min(1.0, float(self.throttle))),
            max(0.0, min(1.0, float(self.brake))),
        )


NO_INPUT = Controls()


class Driver:
    """Base class.  Subclasses override `act` (and `reset` if they keep state)."""

    #: shown in menus and results
    label = "Driver"

    def reset(self, world, car_index: int) -> None:
        """Called when the car is placed on the grid."""

    def act(self, world, car_index: int) -> Controls:
        """Return the controls for this tick.

        `world` is the sim World *before* the tick is applied; treat it as
        read-only.  `world.cars[car_index]` is the car being driven and
        `world.track` has the geometry queries.
        """
        return NO_INPUT


# ---------------------------------------------------------------- registry

_REGISTRY: dict[str, tuple[str, Callable[..., Driver]]] = {}


def register_driver(key: str, label: str, factory: Callable[..., Driver]) -> None:
    """Make a driver type selectable for any car slot.

    `factory(slot=<int>)` must return a new Driver for that car slot.
    Registering an existing key replaces it.
    """
    _REGISTRY[key] = (label, factory)


def unregister_drivers(prefix: str) -> None:
    """Remove every driver type whose key starts with `prefix`."""
    for key in [k for k in _REGISTRY if k.startswith(prefix)]:
        del _REGISTRY[key]


def create_driver(key: str, slot: int = 0) -> Driver:
    if key not in _REGISTRY:
        raise KeyError(f"unknown driver type {key!r}; known: {sorted(_REGISTRY)}")
    return _REGISTRY[key][1](slot=slot)


def driver_types() -> list[tuple[str, str]]:
    """[(key, label), ...] in registration order."""
    return [(key, label) for key, (label, _) in _REGISTRY.items()]
