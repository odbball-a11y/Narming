"""Race management: grid, 3-2-1 countdown, racing, finish, results.

A Race owns a World and one Driver per car.  `step()` advances exactly one
tick, whatever the phase, so the game loop and the headless runner use it the
same way.  It also logs the controls applied on every racing tick, which is
all a replay needs (see sim/replay.py).
"""
from __future__ import annotations

from typing import Sequence

from . import tuning
from .driver import Controls, Driver, create_driver
from .telemetry import LapRecorder
from .track import Track
from .world import World

COUNTDOWN = "countdown"
RACING = "racing"
FINISHED = "finished"

# After the flag a car brakes at this strength (its driver still steers)
# until it is slower than PARK_SPEED.  It is then parked: no longer simulated
# and no longer solid, so cars still racing cannot hit it.  The brake must be
# released at that point, because holding it on a stopped car means reverse.
AFTER_FLAG_BRAKE = 0.6
PARK_SPEED = 1.0


class Race:
    def __init__(self, track, entries: Sequence[tuple], laps: int | None = None, seed: int = 0,
                 rolling: bool = False):
        """`entries` is a list of (slot, driver) for the cars taking part,
        where driver is a registry key such as "scripted" or a Driver object.
        Slot (0-3) picks the grid position, colour and parameter set.  With
        `rolling` the cars start in single file at speed, slot 0 leading."""
        self.rolling = rolling
        self.track = track if isinstance(track, Track) else Track.load(track)
        self.slots = [int(slot) for slot, _ in entries]
        self.driver_keys = [d if isinstance(d, str) else type(d).__name__ for _, d in entries]
        self.drivers: list[Driver] = [
            create_driver(d, slot=slot) if isinstance(d, str) else d for slot, d in entries
        ]
        # A driver can bring its own car (an AI racer with car traits).
        params = [getattr(d, "car_params", None) for d in self.drivers]
        self.world = World(self.track, slots=self.slots, seed=seed, laps=laps, rolling=rolling,
                           params=params)
        self.restart()

    def restart(self) -> None:
        self.world.reset()
        self.phase = COUNTDOWN
        self.countdown_tick = 0
        self.first_finish_tick = None
        self.end_tick = None
        self.controls_log: list[tuple] = []
        self.final_hash = None
        self.telemetry = LapRecorder(self.world)       # every car's flying laps, for records and ghosts
        for i, driver in enumerate(self.drivers):
            driver.reset(self.world, i)

    # ------------------------------------------------------------ queries

    @property
    def seed(self) -> int:
        return self.world.seed

    @property
    def laps(self) -> int:
        return self.world.laps

    @property
    def countdown_number(self) -> int:
        """3, 2, 1 while the lights count down, 0 once racing."""
        if self.phase != COUNTDOWN:
            return 0
        step = int(tuning.COUNTDOWN_STEP * tuning.TICK_RATE)
        return 3 - min(self.countdown_tick // step, 2)

    @property
    def seconds_since_go(self) -> float:
        return self.world.time

    def results(self) -> list[dict]:
        """Finishing order with times; unfinished cars are ranked by distance."""
        rows = []
        for place, i in enumerate(self.world.standings(), start=1):
            car = self.world.cars[i]
            rows.append({
                "place": place,
                "car": i,
                "slot": self.slots[i],
                "driver": self.drivers[i].label,
                "finished": car.finished,
                "laps": car.laps,
                "time": car.finish_time,
                "best_lap": car.best_lap,
                "lap_times": list(car.lap_times),
            })
        return rows

    # --------------------------------------------------------------- step

    def step(self) -> list[tuple]:
        """Advance one tick.  Returns World events plus:
          ("count", n)   a countdown light (n = 3, 2, 1)
          ("go",)        the race has started
          ("race_over",) results are final
        """
        if self.phase == COUNTDOWN:
            return self._step_countdown()
        if self.phase == FINISHED:
            return []
        world = self.world
        controls = []
        for i, driver in enumerate(self.drivers):
            car = world.cars[i]
            if car.retired:
                controls.append(Controls())
            elif car.finished:
                steering = Controls(*driver.act(world, i)).clamped().steering
                controls.append(Controls(steering, 0.0, AFTER_FLAG_BRAKE))
            else:
                controls.append(Controls(*driver.act(world, i)).clamped())
        self.controls_log.append(tuple(v for c in controls for v in c))
        events = world.step(controls)
        self.telemetry.record(controls, events)
        for car in world.cars:
            if car.finished and not car.retired and car.speed < PARK_SPEED:
                car.vx = car.vy = 0.0
                car.refresh_speed()
                car.prev_x, car.prev_y, car.prev_heading = car.x, car.y, car.heading
                car.retired = True

        if self.first_finish_tick is None and any(e[0] == "finish" for e in events):
            self.first_finish_tick = world.tick
        if self.end_tick is None:
            everyone = all(car.finished for car in world.cars)
            out_of_time = (self.first_finish_tick is not None and
                           world.tick - self.first_finish_tick >= tuning.FINISH_GRACE * tuning.TICK_RATE)
            if everyone or out_of_time:
                self.end_tick = world.tick + int(tuning.COOLDOWN * tuning.TICK_RATE)
        if self.end_tick is not None and world.tick >= self.end_tick:
            self.phase = FINISHED
            self.final_hash = world.state_hash()
            events.append(("race_over",))
        return events

    def _step_countdown(self) -> list[tuple]:
        step = int(tuning.COUNTDOWN_STEP * tuning.TICK_RATE)
        events = []
        if self.countdown_tick % step == 0 and self.countdown_tick < 3 * step:
            events.append(("count", 3 - self.countdown_tick // step))
        self.countdown_tick += 1
        if self.countdown_tick >= 3 * step:
            self.phase = RACING
            events.append(("go",))
        return events

    def run(self, max_seconds: float = 600.0, on_event=None) -> "Race":
        """Run to the end with no rendering (headless use)."""
        limit = int(max_seconds * tuning.TICK_RATE)
        while self.phase != FINISHED and self.world.tick < limit:
            events = self.step()
            if on_event:
                for event in events:
                    on_event(self, event)
        return self
