"""The application: window, main loop and screen switching."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pygame

from sim.track import Track


def _own_group() -> dict:
    """Start a job in its own process group, so stopping it also stops the
    worker processes it starts (they would otherwise be left running)."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _stop_group(proc) -> None:
    """Stop a job and every process it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

from . import input as game_input
from .audio import Audio
from .render import Camera, RaceRenderer, UI, render_track
from .screens import MainMenu, RaceScreen, SetupScreen

WINDOW_SIZE = (1280, 720)


class App:
    def __init__(self, screen: pygame.Surface, audio: Audio | None = None, workshop: bool = False):
        self.screen = screen
        self.workshop = workshop          # making house rivals instead of playing
        self.trainer = None               # {"proc": Popen, "dir": racer folder, "log": file}
        self.race_counter = 0
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
            "drivers": ["human1", "scripted", "scripted", "scripted", None, None],
        }
        self.ai_run = None          # training run shown in the AI lab (None = latest)
        self.current = MainMenu(self)

    # ----------------------------------------------------------- services

    def show(self, screen_obj) -> None:
        self.current = screen_obj

    def quit(self) -> None:
        self.running = False
        self.stop_training()

    # -------------------------------------------------------------- stable

    @property
    def stable_root(self) -> Path:
        from ai import stable
        return stable.WORKSHOP_DIR if self.workshop else stable.STABLE_DIR

    def training_dir(self) -> str | None:
        """Folder of the racer being trained, or None.  Notices when the
        training process has finished."""
        if self.trainer is None:
            return None
        if self.trainer["proc"].poll() is not None:
            self.trainer["log"].close()
            self.trainer = None
            return None
        return self.trainer["dir"]

    def start_training(self, racer_dir) -> None:
        """Train a racer in a separate process, so the game stays smooth."""
        self._start_job("train", racer_dir)

    def start_breeding(self, foal_dir) -> None:
        """Breed a foal's litter and pick the best, in a separate process."""
        self._start_job("breed", foal_dir)

    def start_trackschool(self, school_dir) -> None:
        """Train a track-school copy in a separate process."""
        self._start_job(None, school_dir, module="ai.trackschool")

    def _start_job(self, command: str | None, racer_dir, module: str = "ai.stable") -> None:
        from ai import evolve
        if self.training_dir():
            raise RuntimeError("already training")
        workers = max(1, min(3, (os.cpu_count() or 2) - 1))
        log = open(Path(racer_dir) / "train.log", "a", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-m", module] + ([command] if command else []) + [str(racer_dir),
                                 "--workers", str(workers)],
                                cwd=evolve.PROJECT, stdout=log, stderr=subprocess.STDOUT,
                                **_own_group())
        self.trainer = {"proc": proc, "dir": str(racer_dir), "log": log}

    def stop_training(self) -> None:
        """Stop training; it can be resumed later from where it stopped."""
        if self.trainer is None:
            return
        proc = self.trainer["proc"]
        if proc.poll() is None:
            _stop_group(proc)
        self.trainer["log"].close()
        self.trainer = None

    def record_race(self, race, defer_retire: bool = False) -> list[str]:
        """Add a finished race to the careers of any stable racers in it.
        Returns news (retirements, deaths) to show the player."""
        from ai import stable
        return stable.record_race(race, defer_retire)

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
    ap.add_argument("--workshop", action="store_true",
                    help="make house rivals (the opponents that ship with the game)")
    args = ap.parse_args(argv)

    from ai import migrate
    migrate.ensure()           # saved brains -> current input layout
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    # Initialise the pieces separately so a missing sound card cannot stop us.
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("AI Sprint Racing")
    flags = pygame.RESIZABLE | (pygame.FULLSCREEN if args.fullscreen else 0)
    screen = pygame.display.set_mode((0, 0) if args.fullscreen else WINDOW_SIZE, flags)
    app = App(screen, Audio(enabled=not args.no_sound), workshop=args.workshop)
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
    app.stop_training()
    pygame.quit()
    return 0
