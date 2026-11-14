"""A car that crashes out: it races like the scripted driver, then at
`stop_after` seconds pulls towards one side of the track and stops dead,
partly on the tarmac, and stays there.  Used in AI training races so drivers
learn to go round a wreck instead of following it (a stopped car gives no
tow).  Deterministic: no randomness of its own."""
from __future__ import annotations

from .driver import Controls
from .scripted import ScriptedDriver


class WreckDriver(ScriptedDriver):
    label = "Wreck"

    def __init__(self, slot: int = 0, stop_after: float = 5.0, side: float = 1.0, place: float = 0.6):
        super().__init__(slot)
        self.stop_after = stop_after
        self.side = 1.0 if side >= 0 else -1.0
        self.place = place            # where it ends up: fraction of the half-width from the centre

    def act(self, world, car_index: int) -> Controls:
        if world.time < self.stop_after:
            return super().act(world, car_index)
        car = world.cars[car_index]
        track = world.track
        target = self.side * self.place * track.half_width_at(car.s)
        error = track.heading_error(car.heading, car.s)
        steer = max(-1.0, min(1.0, 0.25 * (target - car.lateral) - 1.2 * error))
        if car.speed < 1.5:                   # stopped: no brake either (holding the brake reverses)
            return Controls(0.0, 0.0, 0.0)
        settled = abs(target - car.lateral) < 1.0 or world.time > self.stop_after + 1.2
        return Controls(steer, 0.0 if settled else 0.15, 1.0 if settled else 0.3)


def parse(key: str) -> dict:
    """"wreck:<stop_after>:<side>:<place>" -> keyword arguments."""
    _, stop, side, place = key.split(":")
    return {"stop_after": float(stop), "side": float(side), "place": float(place)}
