"""Human input: keyboard bindings and the keyboard Driver.

Keys are digital, so the smoothing that turns key presses into steering and
pedal values lives here, in the input layer.  The physics receives ordinary
Controls and cannot tell a human from a script.
"""
from __future__ import annotations

import json
from pathlib import Path

import pygame

from sim import tuning
from sim.driver import Controls, Driver, register_driver

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "controls.json"

DEFAULT_BINDINGS = [
    {"name": "Arrows", "left": "left", "right": "right", "throttle": "up", "brake": "down"},
    {"name": "WASD", "left": "a", "right": "d", "throttle": "w", "brake": "s"},
    {"name": "IJKL", "left": "j", "right": "l", "throttle": "i", "brake": "k"},
    {"name": "Numpad", "left": "[4]", "right": "[6]", "throttle": "[8]", "brake": "[5]"},
]
ACTIONS = ("left", "right", "throttle", "brake")


def load_bindings(path: Path = CONFIG_PATH) -> list[dict]:
    """Bindings for players 1-4.  Falls back to the defaults per player if the
    file is missing or an entry is broken, and says so on the console."""
    players = []
    if not pygame.get_init():
        pygame.init()   # key names cannot be resolved before SDL is up
    try:
        with open(path, "r", encoding="utf-8") as fh:
            players = json.load(fh).get("players", [])
    except (OSError, ValueError) as exc:
        print(f"controls: could not read {path} ({exc}); using defaults")
    result = []
    for i, default in enumerate(DEFAULT_BINDINGS):
        entry = dict(default)
        if i < len(players) and isinstance(players[i], dict):
            entry.update({k: v for k, v in players[i].items() if k in ACTIONS or k == "name"})
        try:
            entry["codes"] = {a: pygame.key.key_code(str(entry[a])) for a in ACTIONS}
        except ValueError as exc:
            print(f"controls: player {i + 1}: {exc}; using defaults")
            entry = dict(default)
            entry["codes"] = {a: pygame.key.key_code(default[a]) for a in ACTIONS}
        result.append(entry)
    return result


def _approach(value: float, target: float, step: float) -> float:
    if value < target:
        return min(value + step, target)
    return max(value - step, target)


class KeyboardDriver(Driver):
    """Reads one player's keys and ramps them into smooth Controls.

    `act` is called once per sim tick, so the ramps advance by tuning.DT.
    """

    def __init__(self, binding: dict, label: str = "Human"):
        self.binding = binding
        self.codes = binding["codes"]
        self.label = label
        self.steering = 0.0
        self.throttle = 0.0
        self.brake = 0.0

    def reset(self, world, car_index: int) -> None:
        self.steering = self.throttle = self.brake = 0.0

    def act(self, world, car_index: int) -> Controls:
        keys = pygame.key.get_pressed()
        codes = self.codes
        want = float(keys[codes["right"]]) - float(keys[codes["left"]])
        dt = tuning.DT
        if want == 0.0:
            rate = tuning.KEY_STEER_RETURN_RATE
        elif want * self.steering < 0.0:
            rate = tuning.KEY_STEER_COUNTER_RATE   # crossing centre: be quick
        else:
            rate = tuning.KEY_STEER_RATE
        self.steering = _approach(self.steering, want, rate * dt)
        pedal = tuning.KEY_PEDAL_RATE * dt
        self.throttle = _approach(self.throttle, float(keys[codes["throttle"]]), pedal)
        self.brake = _approach(self.brake, float(keys[codes["brake"]]), pedal)
        return Controls(self.steering, self.throttle, self.brake)


_bindings_cache: list[dict] | None = None


def bindings() -> list[dict]:
    global _bindings_cache
    if _bindings_cache is None:
        _bindings_cache = load_bindings()
    return _bindings_cache


def key_label(binding: dict) -> str:
    """Human-readable summary of one player's keys, for menus."""
    return "  ".join(f"{action} [{str(binding[action]).upper()}]"
                     for action in ("left", "right", "throttle", "brake"))


class GamepadDriver(Driver):
    """Left stick steers; right trigger or A accelerates; left trigger, B or X
    brakes.  Analogue, so no smoothing is needed beyond a small dead zone."""

    DEAD_ZONE = 0.12

    def __init__(self, joystick, label: str = "Gamepad"):
        self.joystick = joystick
        self.label = label

    def _axis(self, index: int, default: float = 0.0) -> float:
        js = self.joystick
        return js.get_axis(index) if index < js.get_numaxes() else default

    def _button(self, index: int) -> bool:
        js = self.joystick
        return bool(js.get_button(index)) if index < js.get_numbuttons() else False

    def act(self, world, car_index: int) -> Controls:
        x = self._axis(0)
        dz = self.DEAD_ZONE
        steering = 0.0 if abs(x) < dz else (abs(x) - dz) / (1.0 - dz) * (1.0 if x > 0 else -1.0)
        # Triggers rest at -1 and reach +1 when pulled.
        throttle = max((self._axis(5, -1.0) + 1.0) / 2.0, 1.0 if self._button(0) else 0.0)
        brake = max((self._axis(4, -1.0) + 1.0) / 2.0,
                    1.0 if (self._button(1) or self._button(2)) else 0.0)
        return Controls(steering, throttle, brake)


_registered = False


def register_human_drivers() -> None:
    """Add every human input to the driver registry: one entry per keyboard
    binding set ("human1".."human4") and one per connected gamepad ("pad1"..).
    Any of them can then be assigned to any car slot."""
    global _registered
    if _registered:
        return
    _registered = True
    for i, binding in enumerate(bindings()):
        label = f"Human: {binding['name']}"
        register_driver(f"human{i + 1}", label,
                        lambda slot=0, b=binding, lab=label: KeyboardDriver(b, label=lab))
    try:
        pygame.joystick.init()
        for i in range(min(pygame.joystick.get_count(), 4)):
            js = pygame.joystick.Joystick(i)
            label = f"Gamepad {i + 1}"
            register_driver(f"pad{i + 1}", label,
                            lambda slot=0, j=js, lab=label: GamepadDriver(j, label=lab))
    except pygame.error as exc:
        print(f"gamepads: unavailable ({exc})")
