"""The application: window, main loop and screen switching."""
from __future__ import annotations

import argparse
import os

import pygame

from sim.track import Track

from . import input as game_input
from .audio import Audio
from .render import Camera, RaceRenderer, UI, render_track
from .screens import MainMenu, RaceScreen, SetupScreen

WINDOW_SIZE = (1280, 720)


class App:
    def __init__(self, screen: pygame.Surface, audio: Audio | None = None):
        self.screen = screen
        self.audio = audio or Audio(enabled=False)
        self.running = True
        self.ui = UI(screen.get_size())
        self._renderers: dict = {}
        game_input.register_human_drivers()
        import sim.scripted  # noqa: F401  (registers "scripted" after the humans)
        # What the setup screen remembers between races.
        self.setup = {
            "track": "speedway",
            "laps": 3,
            "seed": 0,
            "rolling": True,
            "drivers": ["human1", "scripted", "scripted", "scripted"],
        }
        self.ai_run = None          # training run shown in the AI lab (None = latest)
        self.current = MainMenu(self)

    # ----------------------------------------------------------- services

    def show(self, screen_obj) -> None:
        self.current = screen_obj

    def quit(self) -> None:
        self.running = False

    def renderer_for(self, track: Track) -> RaceRenderer:
        """Track paintings are cached: drawing one takes a moment."""
        key = (track.key, self.screen.get_size())
        if key not in self._renderers:
            if len(self._renderers) > 4:
                self._renderers.clear()
            self._renderers[key] = RaceRenderer(track, self.screen.get_size())
        return self._renderers[key]

    def track_thumbnail(self, track: Track, size: tuple[int, int]) -> pygame.Surface:
        return render_track(track, Camera(size))

    # ---------------------------------------------------------- main loop

    def resize(self) -> None:
        size = self.screen.get_size()
        self.ui = UI(size)
        self._renderers.clear()
        if isinstance(self.current, RaceScreen):
            self.current.renderer = self.renderer_for(self.current.race.track)
        self.current.on_resize()

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.quit()
        elif event.type == pygame.VIDEORESIZE:
            self.resize()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
            self.screen = pygame.display.get_surface()
            self.resize()
        else:
            self.current.handle_event(event)

    def update(self, seconds: float) -> None:
        self.current.update(seconds)

    def draw(self) -> None:
        self.current.draw(self.screen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m game", description="AI Sprint Racing")
    ap.add_argument("--no-sound", action="store_true", help="start with audio off")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--race", action="store_true",
                    help="skip the main menu and go straight to race setup")
    ap.add_argument("--track", choices=Track.available(), help="preselect a track")
    args = ap.parse_args(argv)

    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    # Initialise the pieces separately so a missing sound card cannot stop us.
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("AI Sprint Racing")
    flags = pygame.RESIZABLE | (pygame.FULLSCREEN if args.fullscreen else 0)
    screen = pygame.display.set_mode((0, 0) if args.fullscreen else WINDOW_SIZE, flags)
    app = App(screen, Audio(enabled=not args.no_sound))
    if args.track:
        app.setup["track"] = args.track
        app.setup["laps"] = Track.load(args.track).default_laps
    if args.race or args.track:
        app.show(SetupScreen(app))

    clock = pygame.time.Clock()
    while app.running:
        frame = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            app.handle_event(event)
        app.update(frame)
        app.draw()
        pygame.display.flip()
    pygame.quit()
    return 0
