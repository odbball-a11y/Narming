"""The stable: create, train, upskill and race named AI racers.

In workshop mode (python -m game --workshop) the same screens make house
rivals: racers there can train against the existing house rivals and can be
published into house/rivals/, which ships with the game.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from ai import stable
from sim import cartraits, tuning as sim_tuning
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


STAGES = {"waiting": "waiting to start", "litter": "breeding the litter",
          "trial": "round 1: trialling all the foals", "camp": "round 2: mini-camps",
          "done": "done"}


def status_text(app, racer_dir) -> tuple[str, tuple]:
    if stable.is_breeding(racer_dir):
        b = stable.breeding_progress(racer_dir) or {"stage": "waiting"}
        if app.training_dir() != str(racer_dir):
            return "BREEDING PAUSED: resume it from its card", C_PINK
        extra = f" {b['done'] + 1}/{b['of']}" if b["stage"] == "camp" else ""
        return f"BREEDING: {STAGES.get(b['stage'], b['stage'])}{extra}", C_CYAN
    racer = stable.load(racer_dir)
    state = racer.get("status", "racing")
    if state == "dead":
        return f"IN THE HALL OF FAME: died {racer.get('death_cause', '')}", C_HUD_DIM
    if state == "stud":
        return (f"AT STUD: {racer.get('breedings', 0)}/{stable.STUD_BREEDINGS} litters, "
                f"{stable.stud_life_left(racer_dir)} races left to live"), C_HUD_ACCENT
    p = stable.progress(racer_dir)
    if app.training_dir() == str(racer_dir):
        return f"TRAINING  gen {p['done']}/{p['target']}", C_CYAN
    if p["done"] < p["target"]:
        if p["done"] == 0 and p["version"] == 1:
            return "NOT TRAINED YET", C_PINK
        return f"PAUSED  gen {p['done']}/{p['target']}", C_PINK
    if not stable.careers_enabled(Path(racer_dir).parent):
        return "READY TO RACE", C_HUD_ACCENT
    return f"RACING: race {racer['career']['races']} of {stable.CAREER_RACES}", C_HUD_ACCENT


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
        hall = ["hall"] if stable.hall_of_fame(self.app.stable_root) else []
        return ["new", "breed"] + self.racers + hall + ["back"]

    def breedable(self) -> list:
        return [d for d in self.racers if stable.can_breed(d)]

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
            elif choice == "breed":
                if len(self.breedable()) >= 2:
                    self.app.show(BreedScreen(self.app))
            elif choice == "back":
                self.app.show(MainMenu(self.app))
            elif choice == "hall":
                self.app.show(HallScreen(self.app))
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
                y += 5.5
            elif row == "breed":
                ok = len(self.breedable()) >= 2
                ui.text(screen, "mid", "+ BREED TWO RACERS", colour if ok else C_HUD_DIM, 7, y, shadow=ok)
                if not ok:
                    need = ("needs two trained racers" if self.app.workshop
                            else "needs two racers at stud")
                    ui.text(screen, "small", need, C_HUD_DIM, 60, y + 0.8)
                y += 7
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y + 1, shadow=True)
            elif row == "hall":
                ui.text(screen, "mid", "HALL OF FAME", colour, 7, y + 1, shadow=True)
                y += 5
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
        self.traits = dict(racer.get("traits") or cartraits.default()) if racer else cartraits.default()
        exclude = racer["id"] if racer else None
        self.partners = stable.partner_options(app.stable_root, exclude, include_house=app.workshop)
        if not racer:
            self.partners = [p for p in self.partners if p["kind"] != "self"]   # nothing of its own yet
        basic = [p for p in self.partners if p["kind"] != "file"]
        others = [p for p in self.partners if p["kind"] == "file"]
        self.partners = basic + others[-8:]           # the 8 most recent racers fit on screen
        self.chosen = {p["key"] for p in self.partners if p["kind"] in ("scripted", "self")}
        self.row = 1 if racer else 0
        self.message = ""
        if not racer:
            pygame.key.start_text_input()

    def rows(self) -> list:
        car = [] if self.racer_dir else list(cartraits.STARS) + ["weight"]    # a car is for life
        return (["name", "aggression", "caution"] + car + [p["key"] for p in self.partners]
                + ["generations", "start", "back"])

    def stars_left(self) -> int:
        return sim_tuning.TRAIT_BUDGET - cartraits.stars_used(self.traits)

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
            elif row in cartraits.STARS:
                value = self.traits[row] + (1 if key in RIGHT else -1)
                if cartraits.MIN_STARS <= value <= cartraits.MAX_STARS and (key in LEFT or self.stars_left() > 0):
                    self.traits[row] = value
            elif row == "weight":
                i = cartraits.WEIGHTS.index(self.traits["weight"]) + (1 if key in RIGHT else -1)
                self.traits["weight"] = cartraits.WEIGHTS[i % 3]
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
        if not self.racer_dir and self.stars_left() != 0:
            self.message = f"Spend all {sim_tuning.TRAIT_BUDGET} car stars ({self.stars_left()} left)."
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
                                      partners, self.generations, traits=self.traits)
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
        y = 12.5
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
                if row == "caution" and not racer:
                    y += 1.0
                    left = self.stars_left()
                    ui.text(screen, "small", f"THE CAR  (stars left to spend: {left})",
                            C_HUD_DIM if left == 0 else C_PINK, 7, y)
                    y += 3.5
                if row == "caution" and racer:
                    y += 2.0
                    ui.text(screen, "small", f"CAR (for life): {cartraits.describe(self.traits)}", C_HUD_DIM, 7, y)
                    y += 3.5
                if row == "caution" and racer:
                    ui.text(screen, "small", "TRAINING PARTNERS  (Enter or Left/Right to tick)", C_HUD_DIM, 7, y)
                    y += 3.5
            elif row in cartraits.STARS:
                ui.text(screen, "small", cartraits.LABELS[row], C_HUD_DIM, 9, y + 0.3)
                stars = self.traits[row]
                ui.text(screen, "mid", "*" * stars + "." * (cartraits.MAX_STARS - stars), colour, 40, y - 0.4)
                y += 3.6
            elif row == "weight":
                ui.text(screen, "small", "WEIGHT", C_HUD_DIM, 9, y + 0.3)
                ui.text(screen, "mid", f"<  {self.traits['weight'].upper()}  >", colour, 40, y - 0.4)
                y += 5.0
                ui.text(screen, "small", "TRAINING PARTNERS  (Enter or Left/Right to tick)", C_HUD_DIM, 7, y)
                y += 3.5
            elif row == "generations":
                y += 1.0
                ui.text(screen, "mid", "GENERATIONS", C_HUD_DIM, 7, y)
                minutes = self.generations * 0.5
                ui.text(screen, "mid", f"<  {self.generations}  >", colour, 40, y)
                ui.text(screen, "small", f"about {minutes:.0f} min", C_HUD_DIM, 62, y + 0.8)
                y += 5.5
            elif row == "start":
                ui.text(screen, "big", "START TRAINING", colour, 7, y, shadow=True)
                y += 6
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y)
            else:
                partner = next(p for p in self.partners if p["key"] == row)
                tick = "[x]" if row in self.chosen else "[ ]"
                ui.text(screen, "small", f"{tick}  {partner['name']}", colour, 9, y + 0.3)
                y += 3.0
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 7, 87.5, "bottomleft")

        ui.panel(screen, 100, 13, 56, 66)
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
        for head, colour, text in (("THE CAR", C_HUD_ACCENT, f"{sim_tuning.TRAIT_BUDGET} stars over four traits, 1-5 each."),
                                   ("", C_HUD_ACCENT, "Weight is free: heavy shoves harder but is"),
                                   ("", C_HUD_ACCENT, "slower to speed up and stop; light the reverse."),
                                   ("", C_HUD_ACCENT, "A racer keeps its car for life.")):
            if head:
                ui.text(screen, "small", head, colour, 103, y)
                y += 2.8
            ui.text(screen, "small", text, C_HUD_TEXT, 103, y)
            y += 3.4


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
        if stable.is_breeding(self.racer_dir):
            return (["stop"] if training_me else ["resume_breeding"]) + ["back"]
        if "certificate" in self.racer:
            out.append("certificate")
        if stable.can_race(self.racer_dir):
            out.append("race")
        if training_me:
            out.append("stop")
        elif stable.needs_training(self.racer_dir) and stable.can_train(self.racer_dir):
            out.append("resume")
        if trained and not training_me and stable.can_train(self.racer_dir):
            out.append("upskill")
        if (trained and not training_me and stable.status(self.racer_dir) == "racing"
                and stable.careers_enabled(Path(self.racer_dir).parent)):
            out.append("retire")
        if self.app.workshop and trained:
            out.append("publish")
        out.append("back")
        return out

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer > 1.0:
            self.timer = 0.0
            self.reload()

    def leave(self) -> None:
        if stable.status(self.racer_dir) == "dead":
            self.app.show(HallScreen(self.app))
        else:
            self.app.show(StableScreen(self.app))

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
            self.leave()
        elif event.key in UP:
            self.row = (self.row - 1) % len(rows)
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
        elif event.key in ACCEPT:
            self.app.audio.play("select")
            choice = rows[self.row]
            if choice == "back":
                self.leave()
            elif choice == "race":
                self.race()
            elif choice == "stop":
                self.app.stop_training()
            elif choice == "resume":
                if self.app.training_dir():
                    self.message = "Another racer is training. Stop it first."
                else:
                    self.app.start_training(self.racer_dir)
            elif choice == "resume_breeding":
                if self.app.training_dir():
                    self.message = "Another racer is training. Stop it first."
                else:
                    self.app.start_breeding(self.racer_dir)
            elif choice == "certificate":
                self.app.show(CertificateScreen(self.app, self.racer_dir))
            elif choice == "retire":
                stable.retire(self.racer_dir)
                self.message = f"{self.racer['name']} retires to stud."
                self.row = 0
                self.reload()
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
        born = ""
        if racer.get("parents"):
            names = [stable.load(Path(self.racer_dir).parent / p)["name"] if (Path(self.racer_dir).parent / p
                     / "racer.json").exists() else p for p in racer["parents"]]
            born = f"   by {names[0]} out of {names[1]}"
        ui.text(screen, "small", f"created {racer['created']}   version {len(v)}{born}", C_HUD_DIM, 40, 9.5)

        # Personality
        ui.text(screen, "small", "AGGRESSION", C_HUD_DIM, 6, 14)
        bar(ui, screen, 26, 14.2, 22, racer["aggression"], C_PINK)
        ui.text(screen, "small", "CAUTION", C_HUD_DIM, 6, 17.5)
        bar(ui, screen, 26, 17.7, 22, racer["caution"], C_CYAN)
        partners = ", ".join(p["name"] for p in v[-1]["partners"])
        ui.text(screen, "small", f"trained against: {partners}"[:80], C_HUD_DIM, 52, 14)
        ui.text(screen, "small", "CAR: " + cartraits.describe(stable.traits_of(self.racer_dir)).upper(),
                C_HUD_TEXT, 52, 17.5)

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
        kids = stable.offspring(Path(self.racer_dir).parent, racer["id"])
        family = f"   offspring: {', '.join(kids)}" if kids else ""
        ui.text(screen, "small", f"best race laps: {best}{family}"[:110], C_HUD_DIM, 6, y + 7.5)
        if stable.careers_enabled(Path(self.racer_dir).parent) and racer.get("status", "racing") == "racing":
            ui.text(screen, "small", "career", C_HUD_DIM, 70, y + 0.2)
            bar(ui, screen, 82, y + 0.4, 30, min(1.0, c["races"] / stable.CAREER_RACES), C_HUD_ACCENT)

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

        labels = {"certificate": "BREEDING CERTIFICATE", "resume_breeding": "RESUME BREEDING",
                  "race": "RACE THE HOUSE RIVALS", "stop": "STOP", "resume": "RESUME TRAINING",
                  "upskill": "UPSKILL", "retire": "RETIRE TO STUD", "publish": "PUBLISH AS HOUSE RIVAL",
                  "back": "BACK"}
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


class BreedScreen(Screen):
    """Pick a sire and a dam, name the foal and choose how the best foal of
    the litter is picked."""

    def __init__(self, app):
        super().__init__(app)
        self.parents = [d for d in stable.list_racers(app.stable_root) if stable.can_breed(d)]
        self.sire, self.dam = 0, 1
        self.name = ""
        self.criterion = "fastest"
        self.row = 0
        self.message = ""
        pygame.key.start_text_input()

    ROWS = ["sire", "dam", "name", "criterion", "start", "back"]

    def back(self) -> None:
        pygame.key.stop_text_input()
        self.app.show(StableScreen(self.app))

    def cycle(self, which: str, step: int) -> None:
        n = len(self.parents)
        value = getattr(self, which)
        other = self.dam if which == "sire" else self.sire
        value = (value + step) % n
        if value == other:
            value = (value + step) % n
        setattr(self, which, value)

    def handle_event(self, event) -> None:
        row = self.ROWS[self.row]
        if event.type == pygame.TEXTINPUT:
            if row == "name" and len(self.name) < NAME_LIMIT:
                self.name += event.text
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key == pygame.K_ESCAPE:
            self.back()
        elif key == pygame.K_BACKSPACE:
            if row == "name":
                self.name = self.name[:-1]
        elif key in UP:
            self.row = (self.row - 1) % len(self.ROWS)
        elif key in DOWN or key == pygame.K_TAB:
            self.row = (self.row + 1) % len(self.ROWS)
        elif key in LEFT + RIGHT:
            step = 1 if key in RIGHT else -1
            if row in ("sire", "dam"):
                self.cycle(row, step)
            elif row == "criterion":
                self.criterion = "learner" if self.criterion == "fastest" else "fastest"
        elif key in ACCEPT:
            if row == "start":
                self.start()
            elif row == "back":
                self.back()
            else:
                self.row += 1

    def start(self) -> None:
        if not self.name.strip():
            self.message = "Name the foal first."
            return
        if self.app.training_dir():
            self.message = "Another racer is training. Wait for it, or stop it from its card."
            return
        foal = stable.mate(self.app.stable_root, self.parents[self.sire], self.parents[self.dam],
                           self.name, self.criterion)
        pygame.key.stop_text_input()
        self.app.audio.play("select")
        self.app.start_breeding(foal)
        self.app.show(RacerScreen(self.app, foal))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "BREED TWO RACERS", C_HUD_ACCENT, 6, 4, shadow=True)
        sire, dam = stable.load(self.parents[self.sire]), stable.load(self.parents[self.dam])
        y = 15.0
        for i, row in enumerate(self.ROWS):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 4, y)
            if row in ("sire", "dam"):
                parent = sire if row == "sire" else dam
                ui.text(screen, "mid", row.upper(), C_HUD_DIM, 7, y)
                ui.text(screen, "mid", f"<  {parent['name'].upper()}  >", colour, 30, y)
                bar(ui, screen, 30, y + 4.4, 18, parent["aggression"], C_PINK)
                bar(ui, screen, 51, y + 4.4, 18, parent["caution"], C_CYAN)
                c = parent["career"]
                ui.text(screen, "small", f"{c['races']} races, {c['wins']} wins", C_HUD_DIM, 72, y + 4.0)
                y += 9
            elif row == "name":
                ui.text(screen, "mid", "FOAL'S NAME", C_HUD_DIM, 7, y)
                cursor = "_" if selected and (pygame.time.get_ticks() // 400) % 2 else ""
                ui.text(screen, "mid", (self.name or ("type a name" if not selected else "")) + cursor,
                        colour if self.name else C_HUD_DIM, 40, y)
                y += 7
            elif row == "criterion":
                ui.text(screen, "mid", "PICK BY", C_HUD_DIM, 7, y)
                ui.text(screen, "mid", "<  FASTEST LAP  >" if self.criterion == "fastest"
                        else "<  QUICKEST LEARNER  >", colour, 40, y)
                ui.text(screen, "small", stable.CRITERIA[self.criterion], C_HUD_DIM, 40, y + 4.2)
                y += 10
            elif row == "start":
                ui.text(screen, "big", "BREED", colour, 7, y, shadow=True)
                y += 7
            else:
                ui.text(screen, "mid", "BACK", colour, 7, y)
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 7, 87.5, "bottomleft")
        a = (sire["aggression"] + dam["aggression"]) / 2
        c = (sire["caution"] + dam["caution"]) / 2
        ui.panel(screen, 100, 13, 56, 56)
        lines = [
            ("THE FOAL", C_HUD_ACCENT, ""),
            ("", C_HUD_TEXT, f"Personality near aggression {a:.1f}, caution {c:.1f}"),
            ("", C_HUD_TEXT, "(its parents' average, give or take)."),
            ("HOW IT IS PICKED", C_HUD_ACCENT, ""),
            ("", C_HUD_TEXT, f"A litter of {stable.LITTER} foals, each mixing whole"),
            ("", C_HUD_TEXT, "neurons from both parents."),
            ("", C_HUD_TEXT, f"Round 1: all {stable.LITTER} drive and race once;"),
            ("", C_HUD_TEXT, f"the best {stable.SHORTLIST} go through."),
            ("", C_HUD_TEXT, f"Round 2: {stable.CAMP_GENERATIONS} generations of training each;"),
            ("", C_HUD_TEXT, "the winner is your foal."),
            ("", C_HUD_DIM, "Takes a few minutes, in the background."),
        ]
        y = 16.0
        for head, colour, text in lines:
            if head:
                ui.text(screen, "small", head, colour, 103, y)
            else:
                ui.text(screen, "small", text, colour, 103, y)
            y += 3.4


class CertificateScreen(Screen):
    """The foal's breeding certificate."""

    def __init__(self, app, racer_dir):
        super().__init__(app)
        self.racer_dir = racer_dir

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key in ACCEPT + (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.show(RacerScreen(self.app, self.racer_dir))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        racer = stable.load(self.racer_dir)
        cert = racer["certificate"]
        ui.panel(screen, 3, 2, 154, 86, border=C_HUD_ACCENT)
        ui.text(screen, "big", f"BREEDING CERTIFICATE: {racer['name'].upper()}", C_HUD_ACCENT, 80, 4.5, "midtop")

        # Pedigree
        y = 12.5
        ui.text(screen, "small", "PEDIGREE", C_HUD_ACCENT, 7, y)
        for k, role in enumerate(("sire", "dam")):
            p = cert[role]
            x = 7 + k * 50
            ui.text(screen, "mid", f"{role.upper()}: {p['name']}", C_HUD_TEXT, x, y + 3)
            lap = f"{p['lap_alone']:.2f}s alone" if p.get("lap_alone") else "no lap time"
            ui.text(screen, "small", f"{p.get('wins', 0)} wins in {p.get('races', 0)} races, {lap}",
                    C_HUD_DIM, x, y + 7)
            grand = cert["grandparents"].get(p["name"]) or []
            ui.text(screen, "small", "by " + " out of ".join(grand) if grand else "a founder",
                    C_HUD_DIM, x, y + 9.8)
        if cert.get("traits"):
            src = cert.get("traits_from", {})
            parts = [f"{cartraits.LABELS[k]} {cert['traits'][k]}"
                     f"{' (' + src[k][0].upper() + ')' if k in src else ''}" for k in cartraits.STARS]
            weight = cert["traits"]["weight"]
            parts.append(weight + (f" ({src['weight'][0].upper()})" if "weight" in src else ""))
            ui.text(screen, "small", "CAR  (S = from sire, D = from dam): " + "  ".join(parts), C_HUD_TEXT, 7, 25)
        t = cert["temperament"]
        ui.text(screen, "small", "TEMPERAMENT", C_HUD_ACCENT, 110, y)
        ui.text(screen, "small", "aggression", C_HUD_DIM, 110, y + 3.4)
        bar(ui, screen, 126, y + 3.6, 26, t["aggression"], C_PINK)
        ui.text(screen, "small", "caution", C_HUD_DIM, 110, y + 6.6)
        bar(ui, screen, 126, y + 6.8, 26, t["caution"], C_CYAN)

        # Litter
        y = 29.5
        ui.text(screen, "small", f"THE LITTER: {cert['litter']} foals, {cert['shortlist']} shortlisted.  "
                f"Picked by: {cert['criterion_text']} (target {cert['target_lap']:.2f}s)", C_HUD_ACCENT, 7, y)
        y += 3.6
        for x, head in ((9, "FOAL"), (24, "ROUND 1"), (42, "BEST LAP"), (62, "GENS TO TARGET"),
                        (90, "TEST RACE"), (110, "PASSES"), (126, "HITS"), (140, "DAMAGE")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        for c in cert["candidates"]:
            y += 3.4
            colour = C_HUD_ACCENT if c["chosen"] else C_HUD_TEXT
            if c["chosen"]:
                ui.text(screen, "small", ">", C_PINK, 6, y)
            lap = f"{c['best_lap']:.2f}s" if c["best_lap"] else "-"
            gens = str(c["gens_to_target"]) if c["gens_to_target"] else "not reached"
            for x, value in ((9, f"no. {c['foal']}"), (24, f"{c['trial_rank']} of {cert['litter']}"), (42, lap),
                             (62, gens), (90, f"P{c['race_place']}"), (110, str(c["passes"])),
                             (126, f"{c['hits']:g}"), (140, f"{c['damage'] * 100:.0f}%")):
                ui.text(screen, "small", value, colour, x, y)

        # Expectations
        y += 6
        ui.text(screen, "small", "WHAT TO EXPECT  (predictions from the family; its races will tell)",
                C_HUD_ACCENT, 7, y)
        for note in cert["expectations"]:
            y += 3.4
            ui.text(screen, "small", "- " + note, C_HUD_TEXT, 7, y)
        ui.text(screen, "small", "ENTER or ESC to go back", C_HUD_DIM, 80, 86.5, "midbottom")


class HallScreen(Screen):
    """Racers who have died: their records and their families."""

    def __init__(self, app):
        super().__init__(app)
        self.legends = stable.hall_of_fame(app.stable_root)
        self.row = 0

    def handle_event(self, event) -> None:
        from .screens import BACK
        if event.type != pygame.KEYDOWN:
            return
        rows = self.legends + ["back"]
        if event.key in BACK:
            self.app.show(StableScreen(self.app))
        elif event.key in UP:
            self.row = (self.row - 1) % len(rows)
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
        elif event.key in ACCEPT:
            choice = rows[self.row]
            if choice == "back":
                self.app.show(StableScreen(self.app))
            else:
                self.app.show(RacerScreen(self.app, choice))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "HALL OF FAME", C_HUD_ACCENT, 6, 4, shadow=True)
        y = 15.0
        for x, head in ((8, "RACER"), (52, "RACES"), (66, "WINS"), (78, "PODIUMS"), (94, "BEST LAP"),
                        (112, "FOALS"), (124, "DIED")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        y += 4
        root = self.app.stable_root
        for i, d in enumerate(self.legends + ["back"]):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 4, y)
            if d == "back":
                ui.text(screen, "mid", "BACK", colour, 8, y + 1)
                break
            r = stable.load(d)
            c = r["career"]
            best = min(c["best_laps"].values()) if c["best_laps"] else None
            for x, value in ((8, r["name"].upper()), (52, str(c["races"])), (66, str(c["wins"])),
                             (78, str(c["podiums"])), (94, format_time(best)),
                             (112, str(len(stable.offspring(root, r["id"]))))):
                ui.text(screen, "mid", value, colour, x, y)
            ui.text(screen, "small", r.get("death_cause", ""), C_HUD_DIM, 124, y + 0.8)
            y += 5.5
        if not self.legends:
            ui.text(screen, "mid", "Nobody yet.", C_HUD_DIM, 8, y)
