"""The pygame front end, driven with synthetic key presses on the dummy
video driver: menus, a whole race, pause, results, replay, and no-audio."""
import os
import subprocess
import sys
from pathlib import Path

import pygame
import pytest

from ai import evolve
from game import screens
from game.app import App
from game.audio import Audio
from game.screens import ControlsScreen, LabScreen, MainMenu, RaceScreen, ReplayScreen, SetupScreen
from sim import tuning
from sim.race import COUNTDOWN, FINISHED, RACING

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app(tmp_path, monkeypatch):
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((640, 360))
    monkeypatch.setattr(screens, "REPLAY_DIR", tmp_path / "replays")
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path / "training")
    return App(screen, Audio())


def press(app, *keys):
    for key in keys:
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
        app.draw()


def run_seconds(app, seconds, frame=1 / 60):
    for _ in range(int(seconds / frame)):
        app.update(frame)
    app.draw()


def test_main_menu_navigation(app):
    assert isinstance(app.current, MainMenu)
    press(app, pygame.K_DOWN, pygame.K_RETURN)
    from game.stable_screens import StableScreen
    assert isinstance(app.current, StableScreen)
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
    assert isinstance(app.current, LabScreen)
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
    from game.trackschool_screen import TrackSchoolScreen
    assert isinstance(app.current, TrackSchoolScreen) and app.current.mode == "pick"
    app.draw()
    press(app, pygame.K_RIGHT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_ESCAPE)       # choose, but do not start
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
    from game.telemetry_screen import TelemetryScreen
    assert isinstance(app.current, TelemetryScreen)
    press(app, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN, pygame.K_ESCAPE)
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)
    assert isinstance(app.current, ControlsScreen)
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_UP, pygame.K_UP, pygame.K_RETURN)          # wraps to REPLAYS
    assert isinstance(app.current, ReplayScreen) and app.current.files == []
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_UP, pygame.K_RETURN)             # wraps to QUIT
    assert not app.running


def test_setup_assigns_any_driver_to_any_slot(app):
    press(app, pygame.K_RETURN)
    setup_screen = app.current
    assert isinstance(setup_screen, SetupScreen)
    press(app, pygame.K_RIGHT)                           # track
    assert app.setup["track"] == "technical"
    press(app, pygame.K_DOWN, pygame.K_LEFT)             # laps 3 -> 2
    assert app.setup["laps"] == 2
    choices = [k for k, _ in setup_screen.driver_choices()]
    assert choices[0] is None and "scripted" in choices and "human3" in choices
    press(app, pygame.K_DOWN)                            # start type
    assert app.setup["rolling"] is True
    press(app, pygame.K_RIGHT)
    assert app.setup["rolling"] is False
    press(app, pygame.K_RIGHT)
    press(app, pygame.K_DOWN)                            # car 1
    for _ in range(len(choices)):                        # cycle all the way round
        press(app, pygame.K_RIGHT)
    assert app.setup["drivers"][0] == "human1"
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN)   # car 4
    while app.setup["drivers"][3] is not None:
        press(app, pygame.K_RIGHT)
    assert [slot for slot, _ in setup_screen.entries()] == [0, 1, 2]


def test_cannot_start_with_no_cars(app):
    app.setup["drivers"] = [None, None, None, None]
    app.show(SetupScreen(app))
    press(app, pygame.K_UP, pygame.K_RETURN)
    assert isinstance(app.current, SetupScreen)


def test_full_race_pause_results_and_replay(app):
    app.setup.update(track="speedway", laps=1, drivers=[None, "scripted", None, "scripted"])
    app.show(SetupScreen(app))
    press(app, pygame.K_UP, pygame.K_RETURN)             # START RACE
    view = app.current
    assert isinstance(view, RaceScreen) and view.race.slots == [1, 3]
    assert view.race.phase == COUNTDOWN and view.race.rolling

    run_seconds(app, 3.2)
    assert view.race.phase == RACING
    assert 0.1 < view.race.world.time < 0.4              # fixed steps tracked real time

    press(app, pygame.K_p)                               # pause freezes the sim
    tick = view.race.world.tick
    run_seconds(app, 1.0)
    assert view.paused and view.race.world.tick == tick
    press(app, pygame.K_F1)                              # debug overlay draws while paused
    press(app, pygame.K_RETURN)                          # RESUME
    assert not view.paused

    run_seconds(app, 30.0, frame=1 / 30)
    assert view.over and view.race.phase == FINISHED
    assert all(row["finished"] for row in view.race.results())
    result_hash = view.race.final_hash

    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)      # SAVE REPLAY
    saved = list(screens.REPLAY_DIR.glob("*.replay.gz"))
    assert len(saved) == 1 and "speedway" in saved[0].name

    press(app, pygame.K_UP, pygame.K_RETURN)             # WATCH REPLAY
    replay = app.current
    assert replay is not view and replay.is_replay
    run_seconds(app, 40.0, frame=1 / 30)
    assert replay.over and replay.race.final_hash == result_hash

    press(app, pygame.K_DOWN, pygame.K_RETURN)           # BACK TO MENU
    assert isinstance(app.current, MainMenu)
    press(app, pygame.K_UP, pygame.K_UP, pygame.K_RETURN)          # REPLAYS lists the file
    assert len(app.current.files) == 1
    press(app, pygame.K_RETURN)
    assert isinstance(app.current, RaceScreen) and app.current.is_replay


def test_restart_and_quit_from_pause(app):
    app.setup.update(laps=1, drivers=["scripted", None, None, None])
    app.show(SetupScreen(app))
    press(app, pygame.K_UP, pygame.K_RETURN)
    run_seconds(app, 5.0)
    assert app.current.race.world.tick > 0
    press(app, pygame.K_ESCAPE, pygame.K_DOWN, pygame.K_RETURN)    # RESTART
    assert app.current.race.phase == COUNTDOWN and app.current.race.world.tick == 0
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)      # QUIT TO MENU
    assert isinstance(app.current, MainMenu)


def test_long_frame_does_not_spiral(app):
    app.setup.update(drivers=["scripted", None, None, None])
    app.show(SetupScreen(app))
    press(app, pygame.K_UP, pygame.K_RETURN)
    view = app.current
    app.update(5.0)                                      # a 5 second hitch
    assert view.race.countdown_tick <= int(screens.MAX_FRAME_TIME * tuning.TICK_RATE) + 1


def test_window_resize_rebuilds_drawing(app):
    app.setup.update(drivers=["scripted", "scripted", None, None])
    app.show(SetupScreen(app))
    press(app, pygame.K_UP, pygame.K_RETURN)
    run_seconds(app, 4.0)
    app.screen = pygame.display.set_mode((960, 540))
    app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, size=(960, 540), w=960, h=540))
    app.draw()
    assert app.current.renderer.track_surface.get_size() == (960, 540)


def test_audio_synthesis_and_playback_on_dummy_device(app):
    audio = app.audio
    assert audio.ok
    for name in ("beep", "go", "blip", "select", "lap", "fanfare", "thump"):
        assert getattr(audio, name).get_length() > 0.03
        audio.play(name)
    assert len(audio.engine_loops) > 8
    audio.handle_events([("wall", 0, 12.0), ("car", 0, 1, 20.0), ("count", 3), ("go",), ("lap", 0, 9.0)])


def test_game_runs_with_no_audio_device():
    """The whole game, started as a user would, with a sound driver that
    cannot open: it must fall back to silence and still run a race."""
    code = (
        "import pygame\n"
        "import game.app as app\n"
        "ticks = [0]\n"
        "class Clock:\n"
        "    def tick(self, fps):\n"
        "        ticks[0] += 1\n"
        "        n = ticks[0]\n"
        "        if n in (2, 3, 4, 5, 6, 7, 8):\n"       # RACE, then up from TRACK to START, enter
        "            key = {2: pygame.K_RETURN, 3: pygame.K_UP, 4: pygame.K_RETURN}.get(n)\n"
        "            if key: pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))\n"
        "        if n == 400: pygame.event.post(pygame.event.Event(pygame.QUIT))\n"
        "        return 16\n"
        "pygame.time.Clock = Clock\n"
        "seen = []\n"
        "import game.screens as s\n"
        "orig = s.RaceScreen.tick\n"
        "def tick(self):\n"
        "    orig(self); seen.append(self.race.world.tick)\n"
        "s.RaceScreen.tick = tick\n"
        "code = app.main([])\n"
        "assert not pygame.mixer.get_init(), 'mixer unexpectedly opened'\n"
        "assert seen and max(seen) > 100, 'race did not run'\n"
        "print('ok', code)\n"
    )
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="no-such-audio-driver")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "audio: disabled" in out.stdout
    assert out.stdout.strip().endswith("ok 0")
