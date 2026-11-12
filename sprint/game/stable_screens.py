"""The stable: create, train, upskill and race named AI racers.

In workshop mode (python -m game --workshop) the same screens make house
rivals: racers there can train against the existing house rivals and can be
published into house/rivals/, which ships with the game.
"""
from __future__ import annotations

import pygame

from ai import stable
from sim.race import Race
from sim.track import Track

from .render import CAR_COLOURS, C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK, WORLD_W, format_time
from .screens import ACCEPT, DOWN, LEFT, RIGHT, UP, RaceScreen, Screen

NAME_LIMIT = 18


def bar(ui, screen, x, y, w, value, colour) -> None:
    """A 0..1 value as a filled bar."""
    frame = ui.rect(x, y, w, 1.8)
    pygame.draw.rect(screen, (50, 44, 80), frame)
    if value > 0:
        pygame.draw.rect(screen, colour, pygame.Rect(frame.left, frame.top, max(1, int(frame.width * value)),
                                                     frame.height))
    pygame.draw.rect(screen, C_HUD_DIM, frame, 1)


def status_text(app, racer_dir) -> tuple[str, tuple]:
    p = stable.progress(racer_dir)
    if app.training_dir() == str(racer_dir):
        return f"TRAINING  gen {p['done']}/{p['target']}", C_CYAN
    if p["done"] < p["target"]:
        if p["done"] == 0 and p["version"] == 1:
            return "NOT TRAINED YET", C_PINK
        return f"PAUSED  gen {p['done']}/{p['target']}", C_PINK
    return "READY TO RACE", C_HUD_ACCENT


class StableScreen(Screen):
    """Your racers (or, in the workshop, house rivals in the making) and the
    house rivals they are built to beat."""

    def __init__(self, app):
        super().__init__(app)
        self.row = 0
        self.timer = 0.0
        self.reload()

    def reload(self) -> None:
        self.racers = stable.list_racers(self.app.stable_root)
        self.rivals = stable.house_rivals()

    def rows(self) -> list:
        return ["new"] + self.racers + ["back"]

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer > 1.0:
            self.timer = 0.0
            self.reload()

    def handle_event(self, event) -> None:
        from .screens import BACK, MainMenu
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows()
        if event.key in BACK:
            self.app.show(MainMenu(self.app))
        elif event.key in UP:
            self.row = (self.row - 1) % len(rows)
            self.app.audio.play("blip")
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
            self.app.audio.play("blip")
        elif event.key in ACCEPT:
            self.app.audio.play("select")
            choice = rows[self.row]
            if choice == "new":
                self.app.show(CreateScreen(self.app))
            elif choice == "back":
                self.app.show(MainMenu(self.app))
            else:
                self.app.show(RacerScreen(self.app, choice))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        title = "WORKSHOP: MAKE HOUSE RIVALS" if self.app.workshop else "YOUR STABLE"
        ui.text(screen, "big", title, C_HUD_ACCENT, 6, 4, shadow=True)
        rows = self.rows()
        y = 15.0
        for i, row in enumerate(rows):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 4, y)
            if row == "new":
                ui.text(screen, "mid", "+ CREATE A RACER", colour, 7, y, shadow=True)
                y += 7
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y + 1, shadow=True)
            else:
                racer = stable.load(row)
                ui.text(screen, "mid", racer["name"].upper(), colour, 7, y, shadow=True)
                text, tint = status_text(self.app, row)
                ui.text(screen, "small", text, tint, 60, y + 0.8)
                career = racer["career"]
                ui.text(screen, "small", f"{career['races']} races, {career['wins']} wins", C_HUD_DIM, 60, y + 3.3)
                bar(ui, screen, 7, y + 4.4, 20, racer["aggression"], C_PINK)
                bar(ui, screen, 29, y + 4.4, 20, racer["caution"], C_CYAN)
                y += 8
        if not self.racers:
            ui.text(screen, "small", "No racers yet. Create one: give it a name and a personality, then train it.",
                    C_HUD_DIM, 7, y)
            y += 5
        ui.text(screen, "small", "bars: aggression (pink), caution (blue)", C_HUD_DIM, 7, 84)

        ui.panel(screen, 104, 13, 52, 66)
        ui.text(screen, "mid", "HOUSE RIVALS", C_HUD_ACCENT, 107, 15)
        note = "train against them here" if self.app.workshop else "race them; you cannot train against them"
        ui.text(screen, "small", note, C_HUD_DIM, 107, 19.5)
        y = 24.0
        for rival in self.rivals:
            ui.text(screen, "mid", rival["name"].upper(), C_HUD_TEXT, 107, y)
            bar(ui, screen, 107, y + 4.2, 20, rival.get("aggression", 0), C_PINK)
            bar(ui, screen, 130, y + 4.2, 20, rival.get("caution", 0), C_CYAN)
            y += 8.5
        if not self.rivals:
            ui.text(screen, "small", "none yet", C_HUD_DIM, 107, y)
        training = self.app.training_dir()
        if training:
            p = stable.progress(training)
            ui.text(screen, "small", f"Training {stable.load(training)['name']}: gen {p['done']}/{p['target']}. "
                    "It stops if you quit the game and carries on when you resume it.", C_CYAN, 6, 88.6,
                    "bottomleft")


class CreateScreen(Screen):
    """Name, personality, training partners and length; then train.  With
    `racer_dir` it is an upskill of that racer instead."""

    def __init__(self, app, racer_dir=None):
        super().__init__(app)
        self.racer_dir = racer_dir
        racer = stable.load(racer_dir) if racer_dir else None
        self.name = racer["name"] if racer else ""
        self.aggression = racer["aggression"] if racer else 0.3
        self.caution = racer["caution"] if racer else 0.3
        self.generations = 20
        exclude = racer["id"] if racer else None
        self.partners = stable.partner_options(app.stable_root, exclude, include_house=app.workshop)
        if not racer:
            self.partners = [p for p in self.partners if p["kind"] != "self"]   # nothing of its own yet
        self.chosen = {p["key"] for p in self.partners if p["kind"] in ("scripted", "self")}
        self.row = 1 if racer else 0
        self.message = ""
        if not racer:
            pygame.key.start_text_input()

    def rows(self) -> list:
        return (["name", "aggression", "caution"] + [p["key"] for p in self.partners]
                + ["generations", "start", "back"])

    def back(self) -> None:
        pygame.key.stop_text_input()
        if self.racer_dir:
            self.app.show(RacerScreen(self.app, self.racer_dir))
        else:
            self.app.show(StableScreen(self.app))

    def handle_event(self, event) -> None:
        rows = self.rows()
        row = rows[self.row]
        if event.type == pygame.TEXTINPUT:
            if row == "name" and not self.racer_dir and len(self.name) < NAME_LIMIT:
                self.name += event.text
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key == pygame.K_ESCAPE:
            self.back()
        elif key == pygame.K_BACKSPACE:
            if row == "name" and not self.racer_dir:
                self.name = self.name[:-1]
        elif key in UP:
            self.row = (self.row - 1) % len(rows)
        elif key in DOWN or (key == pygame.K_TAB):
            self.row = (self.row + 1) % len(rows)
        elif key in LEFT + RIGHT:
            step = 0.1 if key in RIGHT else -0.1
            if row == "aggression":
                self.aggression = round(min(1.0, max(0.0, self.aggression + step)), 1)
            elif row == "caution":
                self.caution = round(min(1.0, max(0.0, self.caution + step)), 1)
            elif row == "generations":
                choices = stable.GENERATION_CHOICES
                i = choices.index(self.generations) + (1 if key in RIGHT else -1)
                self.generations = choices[max(0, min(len(choices) - 1, i))]
            elif row in self.chosen or row in {p["key"] for p in self.partners}:
                self.toggle(row)
        elif key in ACCEPT:
            if row == "start":
                self.start()
            elif row == "back":
                self.back()
            elif row in {p["key"] for p in self.partners}:
                self.toggle(row)
            elif row == "name":
                self.row += 1

    def toggle(self, key: str) -> None:
        if key in self.chosen:
            self.chosen.discard(key)
        else:
            self.chosen.add(key)
        self.app.audio.play("blip")

    def start(self) -> None:
        if not self.racer_dir and not self.name.strip():
            self.message = "Give your racer a name first."
            return
        if not self.chosen:
            self.message = "Pick at least one training partner."
            return
        if self.app.training_dir():
            self.message = "Another racer is training. Wait for it, or stop it from its card."
            return
        partners = [p for p in self.partners if p["key"] in self.chosen]
        if self.racer_dir:
            stable.upskill(self.racer_dir, self.aggression, self.caution, partners, self.generations)
            racer_dir = self.racer_dir
        else:
            racer_dir = stable.create(self.app.stable_root, self.name, self.aggression, self.caution,
                                      partners, self.generations)
        pygame.key.stop_text_input()
        self.app.audio.play("select")
        self.app.start_training(racer_dir)
        self.app.show(RacerScreen(self.app, racer_dir))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        racer = stable.load(self.racer_dir) if self.racer_dir else None
        title = f"UPSKILL {racer['name'].upper()}" if racer else "CREATE A RACER"
        ui.text(screen, "big", title, C_HUD_ACCENT, 6, 4, shadow=True)
        rows = self.rows()
        y = 15.0
        for i, row in enumerate(rows):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 4, y)
            if row == "name":
                ui.text(screen, "mid", "NAME", C_HUD_DIM, 7, y)
                cursor = "_" if selected and not racer and (pygame.time.get_ticks() // 400) % 2 else ""
                ui.text(screen, "mid", (self.name or ("type a name" if not selected else "")) + cursor,
                        colour if self.name else C_HUD_DIM, 40, y)
                y += 6.5
            elif row in ("aggression", "caution"):
                value = self.aggression if row == "aggression" else self.caution
                ui.text(screen, "mid", row.upper(), C_HUD_DIM, 7, y)
                bar(ui, screen, 40, y + 0.6, 40, value, C_PINK if row == "aggression" else C_CYAN)
                ui.text(screen, "mid", f"{value:.1f}", colour, 84, y)
                y += 5.5
                if row == "caution":
                    y += 2.0
                    ui.text(screen, "small", "TRAINING PARTNERS  (Enter or Left/Right to tick)", C_HUD_DIM, 7, y)
                    y += 3.5
            elif row == "generations":
                y += 1.5
                ui.text(screen, "mid", "GENERATIONS", C_HUD_DIM, 7, y)
                minutes = self.generations * 0.5
                ui.text(screen, "mid", f"<  {self.generations}  >", colour, 40, y)
                ui.text(screen, "small", f"about {minutes:.0f} min", C_HUD_DIM, 62, y + 0.8)
                y += 7
            elif row == "start":
                ui.text(screen, "big", "START TRAINING", colour, 7, y, shadow=True)
                y += 7
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y)
            else:
                partner = next(p for p in self.partners if p["key"] == row)
                tick = "[x]" if row in self.chosen else "[ ]"
                ui.text(screen, "mid", f"{tick}  {partner['name']}", colour, 9, y)
                y += 4.6
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 7, 87.5, "bottomleft")

        ui.panel(screen, 100, 13, 56, 50)
        lines = [
            ("AGGRESSION", C_PINK, "Training rewards places, passes and slipstreaming;"),
            ("", C_PINK, "damage is cheap.  Dangerous Dave is 1.0."),
            ("CAUTION", C_CYAN, "Training makes damage and collisions you cause"),
            ("", C_CYAN, "very costly.  Careful Keith is 1.0."),
            ("PARTNERS", C_HUD_ACCENT, "Who it races in training.  You get more as"),
            ("", C_HUD_ACCENT, "your stable grows."),
        ]
        y = 16.0
        for head, colour, text in lines:
            if head:
                ui.text(screen, "small", head, colour, 103, y)
                y += 2.8
            ui.text(screen, "small", text, C_HUD_TEXT, 103, y)
            y += 3.4
        ui.text(screen, "small", "Racers start from a racing-school graduate", C_HUD_DIM, 103, y + 2)
        ui.text(screen, "small", "that can already lap Speedway.", C_HUD_DIM, 103, y + 5)


class RacerScreen(Screen):
    """A racer's card: personality, training, measured racecraft, career."""

    def __init__(self, app, racer_dir):
        super().__init__(app)
        self.racer_dir = racer_dir
        self.row = 0
        self.timer = 0.0
        self.message = ""
        self.reload()

    def reload(self) -> None:
        self.racer = stable.load(self.racer_dir)
        self.history = stable.history(self.racer_dir)

    def rows(self) -> list[str]:
        out = []
        trained = stable.brain_file(self.racer_dir) is not None
        training_me = self.app.training_dir() == str(self.racer_dir)
        if trained:
            out.append("race")
        if training_me:
            out.append("stop")
        elif stable.needs_training(self.racer_dir):
            out.append("resume")
        if trained and not training_me:
            out.append("upskill")
        if self.app.workshop and trained:
            out.append("publish")
        out.append("back")
        return out

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer > 1.0:
            self.timer = 0.0
            self.reload()

    def race(self) -> None:
        rivals = [r for r in stable.house_rivals() if r["id"] != self.racer["id"]][:3]
        drivers = [stable.champion(self.racer_dir)] + [stable.house_driver(r["id"]) for r in rivals]
        while len(drivers) < 4:
            drivers.append("scripted")
        self.app.race_counter += 1
        order = [(i + self.app.race_counter) % 4 for i in range(4)]     # starting order rotates
        entries = list(zip(order, drivers))
        track = self.racer["versions"][-1]["track"]
        race = Race(track, entries, laps=self.app.setup["laps"], seed=self.app.race_counter, rolling=True)
        racer_dir = self.racer_dir
        self.app.show(RaceScreen(self.app, race, back=lambda app: RacerScreen(app, racer_dir)))

    def handle_event(self, event) -> None:
        from .screens import BACK
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows()
        self.row = min(self.row, len(rows) - 1)
        if event.key in BACK:
            self.app.show(StableScreen(self.app))
        elif event.key in UP:
            self.row = (self.row - 1) % len(rows)
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
        elif event.key in ACCEPT:
            self.app.audio.play("select")
            choice = rows[self.row]
            if choice == "race":
                self.race()
            elif choice == "stop":
                self.app.stop_training()
            elif choice == "resume":
                if self.app.training_dir():
                    self.message = "Another racer is training. Stop it first."
                else:
                    self.app.start_training(self.racer_dir)
            elif choice == "upskill":
                self.app.show(CreateScreen(self.app, self.racer_dir))
            elif choice == "publish":
                path = stable.publish(self.racer_dir)
                self.message = f"Published as a house rival: house/rivals/{path.stem}"
            else:
                self.app.show(StableScreen(self.app))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        racer = self.racer
        ui.text(screen, "big", racer["name"].upper(), C_HUD_ACCENT, 6, 3, shadow=True)
        text, tint = status_text(self.app, self.racer_dir)
        ui.text(screen, "small", text, tint, 6, 9.5)
        v = racer["versions"]
        ui.text(screen, "small", f"created {racer['created']}   version {len(v)}   "
                f"{sum(x['generations'] for x in v)} generations planned", C_HUD_DIM, 40, 9.5)

        # Personality
        ui.text(screen, "small", "AGGRESSION", C_HUD_DIM, 6, 14)
        bar(ui, screen, 26, 14.2, 22, racer["aggression"], C_PINK)
        ui.text(screen, "small", "CAUTION", C_HUD_DIM, 6, 17.5)
        bar(ui, screen, 26, 17.7, 22, racer["caution"], C_CYAN)
        partners = ", ".join(p["name"] for p in v[-1]["partners"])
        ui.text(screen, "small", f"trained against: {partners}"[:80], C_HUD_DIM, 52, 14)

        # Measured racecraft (latest exam: time trial + race from last v three scripted cars)
        exam = self.history[-1]["exam"] if self.history else None
        y = 22.0
        ui.text(screen, "small", "MEASURED  (latest test: alone, then 3 laps from last v three scripted cars)",
                C_HUD_ACCENT, 6, y)
        if exam:
            e = next(iter(exam.values()))
            place = f"P{e['race_place']}" if e["race_finished"] else "DNF"
            items = [("best lap alone", format_time(e["solo_best_lap"])), ("test race", place),
                     ("passes", str(e["race_overtakes"])), ("hits caused", f"{e['race_fault']:g}"),
                     ("damage", f"{e['race_damage'] * 100:.0f}%"), ("in a tow", f"{e['race_draft'] * 100:.0f}%")]
            x = 6
            for label, value in items:
                ui.text(screen, "small", label, C_HUD_DIM, x, y + 3)
                ui.text(screen, "mid", value, C_HUD_TEXT, x, y + 5.6)
                x += 24
        else:
            ui.text(screen, "small", "not trained yet", C_HUD_DIM, 6, y + 3)

        # Career
        c = racer["career"]
        y = 33.5
        ui.text(screen, "small", "CAREER", C_HUD_ACCENT, 6, y)
        best = ", ".join(f"{t} {format_time(b)}" for t, b in c["best_laps"].items()) or "-"
        ui.text(screen, "mid", f"{c['races']} races   {c['wins']} wins   {c['podiums']} podiums", C_HUD_TEXT, 6, y + 3)
        ui.text(screen, "small", f"best race laps: {best}", C_HUD_DIM, 6, y + 7.5)

        # Charts over every generation trained
        if self.history:
            xs = list(range(1, len(self.history) + 1))
            laps = [next(iter(h["exam"].values()))["solo_best_lap"] for h in self.history]
            passes = [next(iter(h["exam"].values()))["race_overtakes"] for h in self.history]
            hits = [next(iter(h["exam"].values()))["race_fault"] for h in self.history]
            starts = [k + 1 for k, h in enumerate(self.history) if k and h["version"] != self.history[k - 1]["version"]]
            marker = (starts[-1], "upskill") if starts else None
            ui.chart(screen, 4, 46, 52, 40, "BEST LAP ALONE (s)", xs, [("lap", C_CYAN, laps)], "{:.1f}", marker)
            ui.chart(screen, 58, 46, 52, 40, "TEST RACE", xs,
                     [("passes", C_CYAN, passes), ("hits caused", C_PINK, hits)], "{:.0f}", marker, floor=0.0)

        labels = {"race": "RACE THE HOUSE RIVALS", "stop": "STOP TRAINING", "resume": "RESUME TRAINING",
                  "upskill": "UPSKILL", "publish": "PUBLISH AS HOUSE RIVAL", "back": "BACK"}
        rows = self.rows()
        y = 48.0
        for i, row in enumerate(rows):
            selected = i == min(self.row, len(rows) - 1)
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 112, y)
            ui.text(screen, "mid", labels[row], C_HUD_ACCENT if selected else C_HUD_TEXT, 115, y, shadow=True)
            y += 5.5
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 112, 86)
