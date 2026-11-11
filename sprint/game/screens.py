"""Menus and the race screen.

Every screen has handle_event(event), update(seconds) and draw(surface), and
asks the App to switch screens.  Menus are driven with the arrow keys, Enter
and Esc.
"""
from __future__ import annotations

import datetime
import importlib
from pathlib import Path

import pygame

from sim import race as race_module
from sim import tuning
from sim.driver import driver_types
from sim.race import Race
from sim.replay import Recording
from sim.track import Track

from . import input as game_input
from .render import (CAR_COLOURS, CAR_NAMES, C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK,
                     HUD_H, PLACES, WORLD_H, WORLD_W, format_time)

REPLAY_DIR = Path(__file__).resolve().parent.parent / "replays"
MAX_FRAME_TIME = 0.25    # after a long stall, do not try to catch up for ever
UP = (pygame.K_UP,)
DOWN = (pygame.K_DOWN,)
LEFT = (pygame.K_LEFT,)
RIGHT = (pygame.K_RIGHT,)
ACCEPT = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
BACK = (pygame.K_ESCAPE, pygame.K_BACKSPACE)


class Screen:
    def __init__(self, app):
        self.app = app

    def handle_event(self, event) -> None:
        pass

    def update(self, seconds: float) -> None:
        pass

    def draw(self, screen) -> None:
        pass

    def on_resize(self) -> None:
        pass


def draw_title(ui, screen, y: float = 10.0) -> None:
    for k, colour in enumerate((C_PINK, C_HUD_ACCENT, C_CYAN)):
        pygame.draw.rect(screen, colour, ui.rect(20, y + 12.5 + k * 1.3, 120, 0.8))
    ui.text(screen, "title", "AI SPRINT RACING", C_HUD_TEXT, WORLD_W / 2, y + 6, "center", shadow=True)


def draw_list(ui, screen, items, selected: int, x: float, y: float, step: float = 6.0,
              font: str = "big") -> None:
    for i, label in enumerate(items):
        colour = C_HUD_ACCENT if i == selected else C_HUD_TEXT
        if i == selected:
            ui.text(screen, font, ">", C_PINK, x - 4, y + i * step)
        ui.text(screen, font, label, colour, x, y + i * step, shadow=True)


# ------------------------------------------------------------------ menus

class MainMenu(Screen):
    ITEMS = ["RACE", "CONTROLS", "REPLAYS", "QUIT"]

    def __init__(self, app):
        super().__init__(app)
        self.selected = 0

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in UP:
            self.selected = (self.selected - 1) % len(self.ITEMS)
            self.app.audio.play("blip")
        elif event.key in DOWN:
            self.selected = (self.selected + 1) % len(self.ITEMS)
            self.app.audio.play("blip")
        elif event.key in ACCEPT:
            self.app.audio.play("select")
            choice = self.ITEMS[self.selected]
            if choice == "RACE":
                self.app.show(SetupScreen(self.app))
            elif choice == "CONTROLS":
                self.app.show(ControlsScreen(self.app))
            elif choice == "REPLAYS":
                self.app.show(ReplayScreen(self.app))
            else:
                self.app.quit()
        elif event.key in BACK:
            self.app.quit()

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        draw_title(ui, screen)
        draw_list(ui, screen, self.ITEMS, self.selected, 66, 38, 7.5)
        ui.text(screen, "small", "ARROWS move    ENTER select    ESC back    F11 fullscreen",
                C_HUD_DIM, WORLD_W / 2, 84, "center")


class SetupScreen(Screen):
    """Track, laps and who drives each of the four cars."""

    LAP_CHOICES = [1, 2, 3, 5, 8, 10]

    def __init__(self, app):
        super().__init__(app)
        self.tracks = Track.available()
        self.row = 0
        self.thumb_key = None
        self.thumb = None

    @property
    def setup(self) -> dict:
        return self.app.setup

    def driver_choices(self) -> list[tuple]:
        return [(None, "None")] + driver_types()

    def rows(self) -> list[str]:
        return ["track", "laps", 0, 1, 2, 3, "start"]

    def change(self, row, delta: int) -> None:
        setup = self.setup
        if row == "track":
            i = (self.tracks.index(setup["track"]) + delta) % len(self.tracks)
            setup["track"] = self.tracks[i]
            setup["laps"] = Track.load(setup["track"]).default_laps
        elif row == "laps":
            laps = setup["laps"]
            choices = self.LAP_CHOICES
            i = choices.index(laps) if laps in choices else 2
            setup["laps"] = choices[(i + delta) % len(choices)]
        elif isinstance(row, int):
            keys = [k for k, _ in self.driver_choices()]
            current = setup["drivers"][row]
            i = keys.index(current) if current in keys else 0
            setup["drivers"][row] = keys[(i + delta) % len(keys)]

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows()
        if event.key in UP:
            self.row = (self.row - 1) % len(rows)
            self.app.audio.play("blip")
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
            self.app.audio.play("blip")
        elif event.key in LEFT:
            self.change(rows[self.row], -1)
            self.app.audio.play("blip")
        elif event.key in RIGHT:
            self.change(rows[self.row], 1)
            self.app.audio.play("blip")
        elif event.key in ACCEPT:
            if rows[self.row] == "start":
                self.start()
            else:
                self.change(rows[self.row], 1)
                self.app.audio.play("blip")
        elif event.key in BACK:
            self.app.show(MainMenu(self.app))

    def entries(self) -> list[tuple]:
        return [(slot, key) for slot, key in enumerate(self.setup["drivers"]) if key]

    def start(self) -> None:
        entries = self.entries()
        if not entries:
            return
        self.app.audio.play("select")
        race = Race(self.setup["track"], entries, laps=self.setup["laps"], seed=self.setup["seed"])
        self.app.show(RaceScreen(self.app, race))

    def draw(self, screen) -> None:
        ui = self.app.ui
        setup = self.setup
        ui.backdrop(screen)
        ui.text(screen, "big", "RACE SETUP", C_HUD_ACCENT, 8, 5, shadow=True)
        labels = dict(self.driver_choices())
        bindings = {f"human{i + 1}": b for i, b in enumerate(game_input.bindings())}
        track = Track.load(setup["track"])
        y = 15.0
        for i, row in enumerate(self.rows()):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 5, y)
            if row == "track":
                ui.text(screen, "mid", "TRACK", C_HUD_DIM, 8, y)
                ui.text(screen, "mid", f"<  {track.name.upper()}  >", colour, 34, y)
                y += 7
            elif row == "laps":
                ui.text(screen, "mid", "LAPS", C_HUD_DIM, 8, y)
                ui.text(screen, "mid", f"<  {setup['laps']}  >", colour, 34, y)
                y += 9
            elif row == "start":
                y += 2
                ok = bool(self.entries())
                ui.text(screen, "big", "START RACE" if ok else "PICK AT LEAST ONE DRIVER",
                        colour if ok else C_HUD_DIM, 8, y, shadow=True)
            else:
                key = setup["drivers"][row]
                pygame.draw.rect(screen, CAR_COLOURS[row], ui.rect(8, y + 0.3, 3.2, 3.2))
                ui.text(screen, "mid", f"CAR {row + 1}", CAR_COLOURS[row], 13, y)
                ui.text(screen, "mid", f"<  {labels.get(key, '?').upper()}  >",
                        colour if key else C_HUD_DIM, 34, y)
                if key in bindings:
                    ui.text(screen, "small", game_input.key_label(bindings[key]), C_HUD_DIM, 13, y + 4.2)
                elif key and key.startswith("pad"):
                    ui.text(screen, "small", "stick steers, right trigger / A go, left trigger / B brake",
                            C_HUD_DIM, 13, y + 4.2)
                y += 8.6
        # Track preview
        size = (int(ui.unit * 64), int(ui.unit * 36))
        key = (setup["track"], size)
        if key != self.thumb_key:
            self.thumb = self.app.track_thumbnail(track, size)
            self.thumb_key = key
        frame = ui.panel(screen, 90, 14, 66, 38)
        screen.blit(self.thumb, self.thumb.get_rect(center=frame.center))
        report = track.report()
        ui.text(screen, "small", f"length {report['length']:.0f}    tightest corner radius "
                f"{report['min_radius']:.0f}", C_HUD_DIM, 123, 54, "midtop")
        duplicates = [k for k in setup["drivers"] if k and k.startswith(("human", "pad"))]
        if len(duplicates) != len(set(duplicates)):
            ui.text(screen, "small", "Note: two cars share the same controls", C_PINK, 123, 58, "midtop")
        ui.text(screen, "small", "UP/DOWN choose row    LEFT/RIGHT change    ENTER start    ESC back",
                C_HUD_DIM, WORLD_W / 2, 86, "center")


class ControlsScreen(Screen):
    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key in ACCEPT + BACK:
            self.app.show(MainMenu(self.app))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "CONTROLS", C_HUD_ACCENT, 8, 5, shadow=True)
        y = 16.0
        for x, head in ((8, "PLAYER"), (40, "LEFT"), (62, "RIGHT"), (84, "THROTTLE"), (110, "BRAKE / REVERSE")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        y += 4
        for i, b in enumerate(game_input.bindings()):
            ui.text(screen, "mid", f"{i + 1}  {b['name'].upper()}", C_HUD_TEXT, 8, y)
            for x, action in ((40, "left"), (62, "right"), (84, "throttle"), (110, "brake")):
                ui.text(screen, "mid", str(b[action]).upper(), C_CYAN, x, y)
            y += 6
        y += 2
        pads = [label for key, label in driver_types() if key.startswith("pad")]
        lines = [
            "Gamepads: " + (", ".join(pads) if pads else "none detected (plug in before starting the game)"),
            "Gamepad: left stick steers, right trigger or A accelerates, left trigger or B brakes.",
            "During a race:  P or ESC pause    F1 debug overlay    F5 reload tuning    F11 fullscreen",
            "Hold brake when stopped to reverse.",
            "Change keys by editing config/controls.json (pygame key names).",
        ]
        for line in lines:
            ui.text(screen, "small", line, C_HUD_TEXT, 8, y)
            y += 4
        ui.text(screen, "small", "ENTER or ESC to go back", C_HUD_DIM, WORLD_W / 2, 86, "center")


class ReplayScreen(Screen):
    """Lists saved replays, newest first."""

    def __init__(self, app):
        super().__init__(app)
        self.files = sorted(REPLAY_DIR.glob("*.replay.gz"), key=lambda p: p.stat().st_mtime,
                            reverse=True)[:10] if REPLAY_DIR.exists() else []
        self.selected = 0
        self.message = ""

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in BACK:
            self.app.show(MainMenu(self.app))
        elif not self.files:
            if event.key in ACCEPT:
                self.app.show(MainMenu(self.app))
        elif event.key in UP:
            self.selected = (self.selected - 1) % len(self.files)
            self.app.audio.play("blip")
        elif event.key in DOWN:
            self.selected = (self.selected + 1) % len(self.files)
            self.app.audio.play("blip")
        elif event.key in ACCEPT:
            try:
                recording = Recording.load(self.files[self.selected])
                self.app.audio.play("select")
                self.app.show(RaceScreen(self.app, recording.make_race(), recording=recording))
            except Exception as exc:  # corrupt or foreign file: report, stay in the menu
                self.message = f"Could not open replay: {exc}"

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "REPLAYS", C_HUD_ACCENT, 8, 5, shadow=True)
        if not self.files:
            ui.text(screen, "mid", "No saved replays yet.", C_HUD_TEXT, 8, 20)
            ui.text(screen, "small", "Finish a race and choose SAVE REPLAY on the results screen.",
                    C_HUD_DIM, 8, 27)
        else:
            draw_list(ui, screen, [p.name.replace(".replay.gz", "") for p in self.files],
                      self.selected, 12, 17, 5.5, "mid")
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 8, 78)
        ui.text(screen, "small", "ENTER watch    ESC back", C_HUD_DIM, WORLD_W / 2, 86, "center")


# ------------------------------------------------------------------- race

class RaceScreen(Screen):
    """Runs a Race with the fixed-timestep loop and draws it.

    Real time is accumulated and the sim is stepped in exact 1/120 s ticks;
    drawing blends between the last two sim states.  With `recording` set
    this is a replay: the drivers feed back recorded controls.
    """

    PAUSE_ITEMS = ["RESUME", "RESTART", "QUIT TO MENU"]

    def __init__(self, app, race: Race, recording: Recording | None = None):
        super().__init__(app)
        self.race = race
        self.recording = recording
        self.renderer = app.renderer_for(race.track)
        self.renderer.clear_skids()
        self.accumulator = 0.0
        self.alpha = 1.0
        self.paused = False
        self.menu_index = 0
        self.debug = False
        self.message = ""
        self.saved_path = None
        self.problems = recording.compatibility_problems(race.track) if recording else []

    # ------------------------------------------------------------- helpers

    @property
    def is_replay(self) -> bool:
        return self.recording is not None

    @property
    def over(self) -> bool:
        return self.race.phase == race_module.FINISHED

    def result_items(self) -> list[str]:
        if self.is_replay:
            return ["WATCH AGAIN", "BACK TO MENU"]
        return ["RACE AGAIN", "WATCH REPLAY", "SAVE REPLAY", "BACK TO MENU"]

    def restart(self) -> None:
        self.race.restart()
        self.renderer.clear_skids()
        self.accumulator = 0.0
        self.paused = False
        self.menu_index = 0
        self.message = ""
        self.saved_path = None
        self.app.audio.silence()

    def leave(self) -> None:
        self.app.audio.silence()
        self.app.show(MainMenu(self.app))

    def focus_car(self) -> int:
        for i, key in enumerate(self.race.driver_keys):
            if key.startswith(("human", "pad")):
                return i
        return 0

    def save_replay(self) -> None:
        if self.saved_path is None:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"{stamp}-{self.race.track.key}.replay.gz"
            try:
                self.saved_path = Recording.from_race(self.race).save(REPLAY_DIR / name)
            except OSError as exc:
                self.message = f"Could not save: {exc}"
                return
        self.message = f"Saved replays/{self.saved_path.name}"

    # --------------------------------------------------------------- input

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_F1:
            self.debug = not self.debug
        elif event.key == pygame.K_F5 and not self.is_replay:
            importlib.reload(tuning)
            self.restart()
            self.message = "Tuning reloaded"
        elif self.over:
            self.menu_key(event.key, self.result_items(), self.choose_result)
        elif self.paused:
            if event.key in BACK or event.key == pygame.K_p:
                self.paused = False
            else:
                self.menu_key(event.key, self.PAUSE_ITEMS, self.choose_pause)
        elif event.key in (pygame.K_ESCAPE, pygame.K_p):
            self.paused = True
            self.menu_index = 0
            self.app.audio.silence()

    def menu_key(self, key, items, choose) -> None:
        if key in UP:
            self.menu_index = (self.menu_index - 1) % len(items)
            self.app.audio.play("blip")
        elif key in DOWN:
            self.menu_index = (self.menu_index + 1) % len(items)
            self.app.audio.play("blip")
        elif key in ACCEPT:
            self.app.audio.play("select")
            choose(items[self.menu_index])

    def choose_pause(self, item: str) -> None:
        if item == "RESUME":
            self.paused = False
        elif item == "RESTART":
            self.restart()
        else:
            self.leave()

    def choose_result(self, item: str) -> None:
        if item in ("RACE AGAIN", "WATCH AGAIN"):
            self.restart()
        elif item == "WATCH REPLAY":
            recording = Recording.from_race(self.race)
            self.app.audio.silence()
            self.app.show(RaceScreen(self.app, recording.make_race(), recording=recording))
        elif item == "SAVE REPLAY":
            self.save_replay()
        else:
            self.leave()

    # -------------------------------------------------------------- update

    def tick(self) -> None:
        events = self.race.step()
        if self.race.phase != race_module.COUNTDOWN:
            self.renderer.add_skid_marks(self.race.world)
        self.app.audio.handle_events(events)

    def update(self, seconds: float) -> None:
        if self.paused or self.over:
            self.alpha = 1.0
            self.app.audio.update_race(self.race.world, running=False)
            return
        if self.is_replay and pygame.key.get_pressed()[pygame.K_f]:
            seconds *= 4.0                       # fast-forward
        self.accumulator += min(seconds, MAX_FRAME_TIME)
        while self.accumulator >= tuning.DT and not self.over:
            self.tick()
            self.accumulator -= tuning.DT
        self.alpha = 1.0 if self.over else self.accumulator / tuning.DT
        self.app.audio.update_race(self.race.world, running=not self.over)

    # ---------------------------------------------------------------- draw

    def draw(self, screen) -> None:
        ui = self.app.ui
        race = self.race
        screen.fill((0, 0, 0))
        racing = race.phase == race_module.RACING
        self.renderer.draw_world(screen, race.world, self.alpha if racing else 1.0)
        banner = "REPLAY    hold F to fast-forward    ESC pause" if self.is_replay else ""
        if self.message and not self.over:
            banner = self.message
        self.renderer.draw_hud(screen, race, banner)
        self.renderer.draw_countdown(screen, race)
        if self.debug:
            self.renderer.draw_debug(screen, race.world, self.focus_car())
        if self.over:
            self.draw_results(screen)
        elif self.paused:
            ui.dim(screen)
            ui.panel(screen, 50, 26, 60, 42)
            ui.text(screen, "big", "PAUSED", C_HUD_ACCENT, 80, 32, "center")
            draw_list(ui, screen, self.PAUSE_ITEMS, self.menu_index, 62, 40, 7, "mid")

    def draw_results(self, screen) -> None:
        ui = self.app.ui
        ui.dim(screen)
        ui.panel(screen, 22, 13, 116, 72)
        title = "REPLAY FINISHED" if self.is_replay else "RACE RESULTS"
        ui.text(screen, "big", title, C_HUD_ACCENT, 80, 18.5, "center")
        y = 24.5
        for x, head in ((28, "POS"), (42, "CAR"), (62, "DRIVER"), (96, "RACE TIME"), (118, "BEST LAP")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        y += 3.6
        for row in self.race.results():
            colour = CAR_COLOURS[row["slot"] % 4]
            ui.text(screen, "mid", PLACES[row["place"] - 1], colour, 28, y)
            ui.text(screen, "mid", CAR_NAMES[row["slot"] % 4], colour, 42, y)
            ui.text(screen, "mid", row["driver"].upper()[:18], C_HUD_TEXT, 62, y)
            total = format_time(row["time"]) if row["finished"] else f"DNF ({row['laps']} laps)"
            ui.text(screen, "mid", total, C_HUD_TEXT, 96, y)
            ui.text(screen, "mid", format_time(row["best_lap"]), C_HUD_ACCENT, 118, y)
            y += 5.2
        if self.is_replay:
            same = self.race.final_hash == self.recording.final_hash
            if same:
                note, colour = "Replay matched the recorded race exactly.", C_CYAN
            else:
                why = "; ".join(self.problems) or "unknown reason"
                note, colour = f"Replay differs from the recording ({why}).", C_PINK
            ui.text(screen, "small", note, colour, 80, 51.5, "center")
        elif self.message:
            ui.text(screen, "small", self.message, C_CYAN, 80, 51.5, "center")
        draw_list(ui, screen, self.result_items(), self.menu_index, 62, 56, 6.2, "mid")
