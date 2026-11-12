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

from ai import evolve, roster
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
    ITEMS = ["RACE", "STABLE", "AI LAB", "CONTROLS", "REPLAYS", "QUIT"]

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
            elif choice == "STABLE":
                from .stable_screens import StableScreen
                self.app.show(StableScreen(self.app))
            elif choice == "AI LAB":
                self.app.show(LabScreen(self.app))
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
        items = ["WORKSHOP" if i == "STABLE" and self.app.workshop else i for i in self.ITEMS]
        draw_list(ui, screen, items, self.selected, 66, 31, 7.0)
        ui.text(screen, "small", "ARROWS move    ENTER select    ESC back    F11 fullscreen",
                C_HUD_DIM, WORLD_W / 2, 84, "center")


class SetupScreen(Screen):
    """Track, laps and who drives each of the four cars."""

    LAP_CHOICES = [1, 2, 3, 5, 8, 10]

    def __init__(self, app):
        super().__init__(app)
        self.tracks = Track.available()
        roster.register_champions(app.ai_run)      # trained drivers join the list
        from ai import stable
        stable.register(app.stable_root)          # house rivals and your racers too
        known = {k for k, _ in driver_types()}
        app.setup["drivers"] = [k if k in known else None for k in app.setup["drivers"]]
        self.row = 0
        self.thumb_key = None
        self.thumb = None

    @property
    def setup(self) -> dict:
        return self.app.setup

    def driver_choices(self) -> list[tuple]:
        return [(None, "None")] + driver_types()

    def rows(self) -> list[str]:
        return ["track", "laps", "grid", 0, 1, 2, 3, "start"]

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
        elif row == "grid":
            setup["rolling"] = not setup["rolling"]
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
        race = Race(self.setup["track"], entries, laps=self.setup["laps"], seed=self.setup["seed"],
                    rolling=self.setup["rolling"])
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
                y += 7
            elif row == "grid":
                ui.text(screen, "mid", "START", C_HUD_DIM, 8, y)
                ui.text(screen, "mid", "<  ROLLING, SINGLE FILE  >" if setup["rolling"] else "<  STANDING GRID  >",
                        colour, 34, y)
                y += 8
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
                y += 8.0
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

    def __init__(self, app, race: Race, recording: Recording | None = None, back=None):
        super().__init__(app)
        self.race = race
        self.recording = recording
        self.back = back or MainMenu          # screen class to return to
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
        self.app.show(self.back(self.app))

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
            self.app.show(RaceScreen(self.app, recording.make_race(), recording=recording,
                                     back=self.back))
        elif item == "SAVE REPLAY":
            self.save_replay()
        else:
            self.leave()

    # -------------------------------------------------------------- update

    def tick(self) -> None:
        events = self.race.step()
        if not self.is_replay and any(e[0] == "race_over" for e in events):
            self.app.record_race(self.race)
        if self.race.phase != race_module.COUNTDOWN:
            self.renderer.on_tick(self.race.world)
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
        for x, head in ((26, "POS"), (37, "CAR"), (55, "DRIVER"), (88, "RACE TIME"), (108, "BEST LAP"),
                        (126, "DAMAGE")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        y += 3.6
        for row in self.race.results():
            colour = CAR_COLOURS[row["slot"] % 4]
            ui.text(screen, "mid", PLACES[row["place"] - 1], colour, 26, y)
            ui.text(screen, "mid", CAR_NAMES[row["slot"] % 4], colour, 37, y)
            ui.text(screen, "mid", row["driver"].upper()[:16], C_HUD_TEXT, 55, y)
            total = format_time(row["time"]) if row["finished"] else f"DNF ({row['laps']} laps)"
            ui.text(screen, "mid", total, C_HUD_TEXT, 88, y)
            ui.text(screen, "mid", format_time(row["best_lap"]), C_HUD_ACCENT, 108, y)
            damage = self.race.world.cars[row["car"]].damage
            ui.text(screen, "mid", f"{damage * 100:.0f}%", C_PINK if damage > 0.5 else C_HUD_TEXT, 126, y)
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


# ----------------------------------------------------------------- AI lab

_reference_laps: dict = {}


def scripted_reference(track_name: str):
    """The scripted driver's best lap on a track, for comparison."""
    if track_name not in _reference_laps:
        race = Race(track_name, [(0, "scripted")], laps=2).run(max_seconds=200)
        _reference_laps[track_name] = race.world.cars[0].best_lap
    return _reference_laps[track_name]


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


class LabScreen(Screen):
    """Charts of a training run (refreshed while the trainer runs), a
    generation picker, and ways to watch that generation."""

    ROWS = ["gen", "pack", "top4", "test", "champions", "versus", "back"]
    REFRESH = 1.5

    def __init__(self, app):
        super().__init__(app)
        self.row = 1
        self.timer = 0.0
        self.message = ""
        self.picked = None          # chosen generation; None = follow the latest
        self.test_index = 0
        self.reload()

    # ------------------------------------------------------------ data

    def reload(self) -> None:
        self.runs = evolve.list_runs()
        if self.app.ai_run not in self.runs:
            self.app.ai_run = roster.latest_run()
        run = self.app.ai_run
        self.history = evolve.load_history(evolve.RUNS_DIR / run) if run else []
        self.config = evolve.load_config(evolve.RUNS_DIR / run) if run else {}

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer >= self.REFRESH:
            self.timer = 0.0
            self.reload()

    def generations(self) -> list[int]:
        return [h["gen"] for h in self.history]

    @property
    def gen(self):
        gens = self.generations()
        if not gens:
            return None
        if self.picked is None:
            return gens[-1]
        return min(gens, key=lambda g: abs(g - self.picked))

    def entry(self):
        gen = self.gen
        return next((h for h in self.history if h["gen"] == gen), None)

    def racing_start(self):
        return next((h["gen"] for h in self.history if h["mode"] == "race"), None)

    def pick(self, delta: int) -> None:
        gens = self.generations()
        if not gens:
            return
        i = max(0, min(len(gens) - 1, gens.index(self.gen) + delta))
        self.picked = None if i == len(gens) - 1 else gens[i]
        self.test_index = 0

    # ------------------------------------------------------------ races

    def start_race(self, track: str, entries: list, laps: int) -> None:
        setup = self.app.setup
        race = Race(track, entries, laps=laps, seed=setup["seed"], rolling=True)
        self.app.show(RaceScreen(self.app, race, back=LabScreen))

    def top4_race(self) -> None:
        """The four best drivers of the chosen generation.  Reverse grid:
        the best starts last, so it has to overtake."""
        run, gen = self.app.ai_run, self.gen
        entries = [(3 - rank, roster.champion(run, gen, f"G{gen} #{rank + 1}", rank=rank)) for rank in range(4)]
        self.start_race(self.app.setup["track"], entries, self.app.setup["laps"])

    def test_race(self) -> None:
        """One of the races the chosen generation was scored on, with its
        champion in the seat it was tested in."""
        entry = self.entry()
        scenarios = entry.get("scenarios") if entry else None
        if not scenarios:
            self.message = f"Gen {self.gen} was in driving school: no races yet."
            return
        sc = scenarios[self.test_index % len(scenarios)]
        run = self.app.ai_run
        others = [s for s in range(4) if s != sc["slot"]]
        entries = [(sc["slot"], roster.champion(run, self.gen, f"Gen {self.gen}"))]
        for slot, rival in zip(others, sc["rivals"]):
            entries.append((slot, "scripted" if rival == "scripted" else roster.champion(run, rival, f"Gen {rival}")))
        self.start_race(sc["track"], entries, 2)

    def champions_race(self, with_human: bool) -> None:
        gens = self.generations()
        if not gens:
            self.message = "Nothing trained yet."
            return
        run = self.app.ai_run
        picks = roster.spread(gens, 2 if with_human else 3)
        entries = [(0, "human1")] if with_human else []
        for gen in picks:
            entries.append((len(entries), roster.champion(run, gen, f"Gen {gen}")))
        entries.append((len(entries), "scripted"))
        self.start_race(self.app.setup["track"], entries[:4], self.app.setup["laps"])

    # ------------------------------------------------------------ input

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        row = self.ROWS[self.row] if self.history else "back"
        if key in BACK:
            self.app.show(MainMenu(self.app))
        elif key in UP and self.history:
            self.row = (self.row - 1) % len(self.ROWS)
            self.app.audio.play("blip")
        elif key in DOWN and self.history:
            self.row = (self.row + 1) % len(self.ROWS)
            self.app.audio.play("blip")
        elif key == pygame.K_PAGEUP:
            self.pick(10)
        elif key == pygame.K_PAGEDOWN:
            self.pick(-10)
        elif key == pygame.K_END:
            self.picked = None
        elif key == pygame.K_HOME:
            self.pick(-10 ** 6)
        elif key in LEFT + RIGHT:
            step = 1 if key in RIGHT else -1
            if row == "test":
                self.test_index += step
            else:
                self.pick(step)
            self.app.audio.play("blip")
        elif key == pygame.K_r and len(self.runs) > 1:
            self.app.ai_run = self.runs[(self.runs.index(self.app.ai_run) + 1) % len(self.runs)]
            self.picked = None
            self.reload()
        elif key == pygame.K_t:
            tracks = Track.available()
            self.app.setup["track"] = tracks[(tracks.index(self.app.setup["track"]) + 1) % len(tracks)]
        elif key in ACCEPT:
            self.app.audio.play("select")
            self.message = ""
            if row == "back":
                self.app.show(MainMenu(self.app))
            elif row == "pack":
                self.app.show(PackScreen(self.app, self.app.ai_run, self.gen))
            elif row == "top4":
                self.top4_race()
            elif row == "test":
                self.test_race()
            elif row == "champions":
                self.champions_race(with_human=False)
            elif row == "versus":
                self.champions_race(with_human=True)

    # ------------------------------------------------------------ draw

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "AI LAB", C_HUD_ACCENT, 4, 3, shadow=True)
        if not self.history:
            lines = [
                "No trained drivers yet.",
                "",
                "Open a second terminal in the sprint folder, switch on the",
                "virtual environment, and run:",
                "",
                "        py train.py",
                "",
                "Leave it running. This screen updates as each generation finishes.",
            ]
            for k, line in enumerate(lines):
                ui.text(screen, "mid", line, C_HUD_ACCENT if "train.py" in line else C_HUD_TEXT, 12, 18 + k * 5)
            draw_list(ui, screen, ["BACK"], 0, 14, 70, 6, "mid")
            return

        gens = self.generations()
        tracks = list(self.history[-1]["exam"].keys())
        colours = [C_CYAN, C_PINK, C_HUD_ACCENT, (60, 220, 110)]
        start = self.racing_start()
        marker = (start, "racing school") if start else None
        exams = [h["exam"] for h in self.history]

        def avg(key, scale=1.0):
            return [None if _mean([e[t][key] for t in e]) is None else _mean([e[t][key] for t in e]) * scale
                    for e in exams]

        ui.chart(screen, 3, 10.5, 53, 37.5, "BEST LAP ALONE (s)", gens,
                 [(t, colours[k % 4], [e[t]["solo_best_lap"] for e in exams]) for k, t in enumerate(tracks)],
                 "{:.1f}", marker)
        ui.chart(screen, 58, 10.5, 53, 37.5, "RACE FROM LAST ON GRID", gens,
                 [("place (1 = won)", C_HUD_TEXT, avg("race_place")), ("passes", C_CYAN, avg("race_overtakes")),
                  ("hits caused", C_PINK, avg("race_fault"))], "{:.0f}", marker, floor=0.0)
        ui.chart(screen, 3, 50, 53, 36, "DAMAGE AND DRAFTING (%)", gens,
                 [("damage", C_PINK, avg("race_damage", 100.0)), ("in draft", C_CYAN, avg("race_draft", 100.0))],
                 "{:.0f}", marker, floor=0.0)
        ui.chart(screen, 58, 50, 53, 36, "SCORE OF THE GENERATION", gens,
                 [("best", C_CYAN, [h["best"] for h in self.history]),
                  ("average", (150, 140, 200), [h["mean"] for h in self.history])], "{:.2f}", marker)

        # Right-hand column: run facts and the menu.
        x = 114
        entry = self.entry()
        arch = self.config.get("arch")
        name = self.config.get("name")
        title = f"{name.upper()}  ({self.config.get('style', 'balanced')})" if name else f"RUN '{self.app.ai_run}'"
        ui.text(screen, "small", title, C_HUD_ACCENT if name else C_HUD_DIM, x, 4.0)
        if arch:
            from ai.brain import describe
            ui.text(screen, "small", describe(arch), C_HUD_DIM, x, 6.6)
        school = "racing school" if entry["mode"] == "race" else "driving school"
        rows = {
            "gen": f"GEN < {self.gen} >" + ("" if self.picked else "  latest"),
            "pack": "GHOST PACK",
            "top4": "TOP 4 RACE",
            "test": f"TEST RACE < {self.test_index % max(1, len(entry.get('scenarios') or [1])) + 1}"
                    f"/{len(entry.get('scenarios') or [])} >" if entry.get("scenarios") else "TEST RACE  (none)",
            "champions": "CHAMPIONS RACE",
            "versus": "YOU v CHAMPIONS",
            "back": "BACK",
        }
        y = 12.0
        for i, row in enumerate(self.ROWS):
            selected = i == self.row
            if selected:
                ui.text(screen, "mid", ">", C_PINK, x - 3, y)
            ui.text(screen, "mid", rows[row], C_HUD_ACCENT if selected else C_HUD_TEXT, x, y, shadow=True)
            if row == "gen":
                y += 4.4
                ui.text(screen, "small", f"{school}, of {gens[-1]}", C_HUD_DIM, x, y)
                y += 4.0
            else:
                y += 5.4
        e = entry["exam"]
        y += 1.0
        ui.text(screen, "small", f"GEN {self.gen} CHAMPION", C_HUD_ACCENT, x, y)
        for t in tracks:
            y += 3.0
            lap = e[t]["solo_best_lap"]
            ref = scripted_reference(t)
            place = f"P{e[t]['race_place']}" if e[t]["race_finished"] else "DNF"
            ui.text(screen, "small", f"{t[:5]} {lap:.2f}s (ai) v {ref:.2f}s" if lap else f"{t[:5]} no lap",
                    C_HUD_TEXT, x, y)
            y += 2.6
            ui.text(screen, "small", f"  {place}, {e[t]['race_overtakes']} passes, "
                    f"{e[t]['race_fault']:g} hits", C_HUD_DIM, x, y)
        ui.text(screen, "small", f"race track {self.app.setup['track'].upper()}", C_HUD_DIM, x, 80.5)
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, x, 83.2)
        ui.text(screen, "small", "UP/DOWN choose   LEFT/RIGHT change   PGUP/PGDN gen +/-10   END latest   "
                "T track   R run   ESC back", C_HUD_DIM, WORLD_W / 2, 88.6, "midbottom")


class PackScreen(Screen):
    """Watch a whole generation drive at once, as ghosts, exactly as it was
    tested in driving school, and step through the generations."""

    def __init__(self, app, run: str, gen: int | None = None):
        super().__init__(app)
        self.run = run
        self.run_dir = evolve.RUNS_DIR / run
        self.arch = evolve.load_config(self.run_dir)["arch"]
        self.track_name = app.setup["track"]
        self.auto = True
        self.accumulator = 0.0
        self.alpha = 1.0
        self.wait = 0.0
        self.gens = evolve.list_generations(self.run_dir)
        self.load(gen if gen is not None else self.gens[0])

    def load(self, gen: int) -> None:
        self.gens = evolve.list_generations(self.run_dir)
        gen = min(self.gens, key=lambda g: abs(g - gen))
        self.gen = gen
        data = evolve.load_generation(self.run_dir, gen)
        setup = evolve.solo_setup(gen)          # the conditions it was tested in
        self.pack = evolve.PackRun(data["pop"], self.arch, self.track_name, slot=setup["slot"],
                                   damage=setup["damage"])
        self.renderer = self.app.renderer_for(self.pack.track)
        self.accumulator = 0.0
        self.wait = 0.0

    def step_generation(self, delta: int) -> None:
        i = self.gens.index(self.gen) + delta
        self.load(self.gens[max(0, min(len(self.gens) - 1, i))])

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in BACK:
            self.app.show(LabScreen(self.app))
        elif event.key in RIGHT:
            self.step_generation(1)
        elif event.key in LEFT:
            self.step_generation(-1)
        elif event.key == pygame.K_PAGEUP:
            self.step_generation(10)
        elif event.key == pygame.K_PAGEDOWN:
            self.step_generation(-10)
        elif event.key == pygame.K_HOME:
            self.load(self.gens[0])
        elif event.key == pygame.K_END:
            self.load(evolve.list_generations(self.run_dir)[-1])
        elif event.key == pygame.K_a:
            self.auto = not self.auto
        elif event.key == pygame.K_t:
            tracks = Track.available()
            self.track_name = tracks[(tracks.index(self.track_name) + 1) % len(tracks)]
            self.app.setup["track"] = self.track_name
            self.load(self.gen)
        elif event.key in ACCEPT:
            self.load(self.gen)

    def update(self, seconds: float) -> None:
        if self.pack.done:
            # Pause on the final positions, then move on.
            self.alpha = 1.0
            self.wait += seconds
            if self.wait > 1.5:
                self.gens = evolve.list_generations(self.run_dir)
                later = [g for g in self.gens if g > self.gen]
                if self.auto and later:
                    self.load(later[0])
                elif self.auto:
                    self.load(self.gen)       # newest one: run it again while we wait
            return
        if pygame.key.get_pressed()[pygame.K_f]:
            seconds *= 4.0
        self.accumulator += min(seconds, MAX_FRAME_TIME)
        while self.accumulator >= tuning.DT and not self.pack.done:
            self.pack.step()
            self.accumulator -= tuning.DT
        self.alpha = self.accumulator / tuning.DT

    def on_resize(self) -> None:
        self.renderer = self.app.renderer_for(self.pack.track)

    def draw(self, screen) -> None:
        ui = self.app.ui
        pack = self.pack
        world = pack.world
        totals = pack.progress.total
        leader = max(range(pack.count), key=lambda i: totals[i])
        screen.fill((0, 0, 0))
        self.renderer.draw_pack(screen, world, self.alpha, leader)
        strip = ui.rect(0, 0, WORLD_W, HUD_H)
        pygame.draw.rect(screen, (12, 8, 28), strip)
        pygame.draw.line(screen, C_HUD_ACCENT, strip.bottomleft, strip.bottomright, max(1, int(ui.unit * 0.3)))
        ui.text(screen, "small", "GENERATION", C_HUD_DIM, 3, 1.0)
        ui.text(screen, "big", f"{self.gen}", C_HUD_ACCENT, 3, 3.6)
        ui.text(screen, "small", f"of {self.gens[-1]}", C_HUD_DIM, 15, 5.4)
        ui.text(screen, "small", "STILL DRIVING", C_HUD_DIM, 34, 1.0)
        ui.text(screen, "big", f"{pack.alive}/{pack.count}", C_CYAN, 34, 3.6)
        ui.text(screen, "small", "LEADER HAS DONE", C_HUD_DIM, 64, 1.0)
        ui.text(screen, "big", f"{max(totals[leader], 0.0) / pack.track.length:.2f} laps", C_HUD_ACCENT, 64, 3.6)
        laps = [car.best_lap for car in world.cars if car.best_lap is not None]
        ui.text(screen, "small", "BEST LAP SO FAR", C_HUD_DIM, 100, 1.0)
        ui.text(screen, "big", format_time(min(laps) if laps else None), C_HUD_TEXT, 100, 3.6)
        setup = evolve.solo_setup(self.gen)
        ui.text(screen, "small", f"start place {setup['slot'] + 1}, starting damage {setup['damage'] * 100:.0f}%",
                C_HUD_DIM, 64, 8.2)
        ui.text(screen, "small", "TIME", C_HUD_DIM, 136, 1.0)
        ui.text(screen, "big", f"{world.time:4.1f}s", C_HUD_TEXT, 136, 3.6)
        mode = "AUTO: next generation follows" if self.auto else "AUTO OFF"
        ui.text(screen, "small", f"LEFT/RIGHT generation   PGUP/PGDN jump 10   T track   A {mode}   "
                "hold F fast   ESC back", C_HUD_TEXT, WORLD_W / 2, WORLD_H - 0.8, "midbottom", shadow=True)
