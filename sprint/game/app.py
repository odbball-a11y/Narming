"""Milestone 1 prototype: one car on Speedway, straight into the action.

The fixed-timestep loop lives here: real time is accumulated, the sim is
stepped in exact 1/120 s ticks, and the renderer blends between the last two
sim states so motion is smooth at any frame rate.
"""
from __future__ import annotations

import argparse
import importlib
import os

import pygame

import sim.scripted  # noqa: F401  (registers "scripted")
from sim import tuning
from sim.driver import create_driver, driver_types
from sim.track import Track
from sim.world import World

from . import input as game_input  # noqa: F401  (registers "human")
from .render import RaceRenderer

WINDOW_SIZE = (1280, 720)
MAX_FRAME_TIME = 0.25   # after a long stall, do not try to catch up for ever
HINT = "R restart    F1 debug    F5 reload tuning    F11 fullscreen    Esc quit"


class RaceSession:
    """A world, its drivers and the fixed-step clock.  No drawing here."""

    def __init__(self, track_name: str, driver_keys: list[str], laps: int | None = None, seed: int = 0):
        self.track = Track.load(track_name)
        self.world = World(self.track, num_cars=len(driver_keys), seed=seed, laps=laps)
        self.drivers = [create_driver(key, slot=slot) for key, slot in zip(driver_keys, self.world.slots)]
        self.accumulator = 0.0
        self.on_tick = None      # optional callback(world, events) after each tick
        self.restart()

    def restart(self) -> None:
        self.world.reset()
        self.accumulator = 0.0
        for i, driver in enumerate(self.drivers):
            driver.reset(self.world, i)

    def tick(self) -> None:
        world = self.world
        controls = [driver.act(world, i) for i, driver in enumerate(self.drivers)]
        events = world.step(controls)
        if self.on_tick:
            self.on_tick(world, events)

    def advance(self, frame_seconds: float) -> float:
        """Run as many fixed ticks as `frame_seconds` covers.  Returns the
        interpolation factor (0..1) for drawing."""
        self.accumulator += min(frame_seconds, MAX_FRAME_TIME)
        while self.accumulator >= tuning.DT:
            self.tick()
            self.accumulator -= tuning.DT
        return self.accumulator / tuning.DT


class PrototypeApp:
    def __init__(self, screen: pygame.Surface, track: str = "speedway", driver: str = "human",
                 laps: int = 99):
        self.screen = screen
        self.session = RaceSession(track, [driver], laps=laps)
        self.renderer = RaceRenderer(self.session.track, screen.get_size())
        self.session.on_tick = lambda world, events: self.renderer.add_skid_marks(world)
        self.debug = False
        self.alpha = 1.0

    def restart(self) -> None:
        self.session.restart()
        self.renderer.clear_skids()

    def reload_tuning(self) -> None:
        importlib.reload(tuning)
        self.restart()
        print("tuning reloaded")

    def handle_event(self, event) -> bool:
        """Returns False when the app should quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.VIDEORESIZE:
            self.renderer.resize(self.screen.get_size())
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_r:
                self.restart()
            elif event.key == pygame.K_F1:
                self.debug = not self.debug
            elif event.key == pygame.K_F5:
                self.reload_tuning()
            elif event.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
                self.renderer.resize(self.screen.get_size())
        return True

    def update(self, frame_seconds: float) -> None:
        self.alpha = self.session.advance(frame_seconds)

    def draw(self) -> None:
        self.screen.fill((0, 0, 0))
        world = self.session.world
        self.renderer.draw_world(self.screen, world, self.alpha)
        self.renderer.draw_hud(self.screen, world, 0, HINT)
        if self.debug:
            self.renderer.draw_debug(self.screen, world, 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m game", description="AI Sprint Racing (Stage 1 prototype)")
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--driver", default="human", choices=[k for k, _ in driver_types()],
                    help="who drives the car (try 'scripted' to watch the computer)")
    ap.add_argument("--laps", type=int, default=99)
    args = ap.parse_args(argv)

    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()
    pygame.display.set_caption("AI Sprint Racing")
    screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
    app = PrototypeApp(screen, args.track, args.driver, args.laps)
    clock = pygame.time.Clock()
    running = True
    while running:
        frame = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            running = app.handle_event(event) and running
        app.update(frame)
        app.draw()
        pygame.display.flip()
    pygame.quit()
    return 0
