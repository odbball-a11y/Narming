"""The stable: create, train, upskill and race named AI racers.

In workshop mode (python -m game --workshop) the same screens make house
rivals: racers there can train against the existing house rivals and can be
published into house/rivals/, which ships with the game.
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame

from ai import championship, rating, records, stable
from ai import livery as liv
from sim import cartraits, tuning as sim_tuning
from sim.race import Race
from sim.track import Track

from .render import (C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK, WORLD_W, format_time,
                     make_car_sprite)
from .screens import ACCEPT, DOWN, LEFT, RIGHT, UP, RaceScreen, Screen

NAME_LIMIT = 18
_chips: dict = {}


STAR_GOLD = (255, 214, 10)
STAR_EDGE = (160, 112, 0)


def draw_stars(ui, screen, count: int, x: float, y: float, size: float = 2.4, max_shown: int = 5) -> float:
    """One gold star per championship won, with its top-left at world (x, y);
    more than `max_shown` shows that many and "+N".  Returns the width used."""
    if count <= 0:
        return 0.0
    shown = min(count, max_shown)
    step = size * 1.2
    for k in range(shown):
        cx, cy = ui.px(x + size / 2 + k * step, y + size / 2)
        outer, inner = size / 2 * ui.unit, size / 2 * ui.unit * 0.42
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = outer if i % 2 == 0 else inner
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        pygame.draw.polygon(screen, STAR_GOLD, points)
        pygame.draw.polygon(screen, STAR_EDGE, points, max(1, int(ui.unit * 0.15)))
    width = shown * step
    if count > shown:
        rect = ui.text(screen, "small", f"+{count - shown}", C_HUD_ACCENT, x + width + 0.2, y - 0.1)
        width += rect.width / ui.unit + 0.5
    return width


def text_width(ui, font: str, string: str) -> float:
    """Width of text in world units."""
    return ui.fonts[font].size(string)[0] / ui.unit


def draw_chip(ui, screen, livery, x, y, width=6.0) -> None:
    """A small picture of a racer's car in its livery (grey if it has none)."""
    look = livery or {"colour": "white", "trim": "stripe", "trim_colour": "dark"}
    key = (look["colour"], look.get("trim"), look.get("trim_colour"), round(ui.unit, 2), width)
    if key not in _chips:
        sprite = make_car_sprite(liv.rgb(look["colour"]), ui.unit, look.get("trim", "stripe"), liv.trim_rgb(look))
        w = max(4, int(width * ui.unit))
        _chips[key] = pygame.transform.smoothscale(sprite, (w, max(2, int(w * sprite.get_height() / sprite.get_width()))))
    screen.blit(_chips[key], ui.px(x, y))


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
        hall = ["hall"]
        champ = [] if self.app.workshop else ["championship", "ratings"]
        return ["new", "breed"] + champ + self.racers + hall + ["back"]

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
            elif choice == "championship":
                if championship.active(self.app.stable_root):
                    self.app.show(ChampionshipHub(self.app))
                elif championship.eligible(self.app.stable_root):
                    self.app.show(ChampionshipSetupScreen(self.app))
            elif choice == "ratings":
                self.app.show(RatingsScreen(self.app))
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
            elif row == "championship":
                ch = championship.active(self.app.stable_root)
                if ch:
                    label, ok = f"> CONTINUE CHAMPIONSHIP  (race {len(ch['races']) + 1} of {len(ch['tracks'])})", True
                else:
                    ok = bool(championship.eligible(self.app.stable_root))
                    label = "+ ENTER A CHAMPIONSHIP"
                ui.text(screen, "mid", label, colour if ok else C_HUD_DIM, 7, y, shadow=ok)
                if not ok:
                    ui.text(screen, "small", "needs a trained racer that is still racing", C_HUD_DIM, 60, y + 4.2)
                y += 7
            elif row == "ratings":
                ui.text(screen, "mid", "RATINGS", colour, 7, y, shadow=True)
                y += 6
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y + 1, shadow=True)
            elif row == "hall":
                ui.text(screen, "mid", "HALL OF FAME", colour, 7, y + 1, shadow=True)
                y += 5
            else:
                racer = stable.load(row)
                draw_chip(ui, screen, stable.livery_of(row), 7, y + 0.3, 5.5)
                ui.text(screen, "mid", racer["name"].upper(), colour, 14, y, shadow=True)
                draw_stars(ui, screen, racer["career"].get("titles", 0), 15.5 + text_width(ui, "mid", racer["name"].upper()),
                           y + 0.6, 2.4, 4)
                text, tint = status_text(self.app, row)
                ui.text(screen, "small", text, tint, 60, y + 0.8)
                career = racer["career"]
                skill = rating.summary(self.app.stable_root, f"racer:{row.name}")
                ui.text(screen, "small", f"{career['races']} races, {career['wins']} wins"
                        + (f"   RATING {skill['rating']:.0f}" if skill else "   RATING 1000"), C_HUD_DIM, 60,
                        y + 3.3)
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
        note = "train against them here" if self.app.workshop else "you meet them in the championship"
        ui.text(screen, "small", note, C_HUD_DIM, 107, 19.5)
        y = 24.0
        for rival in self.rivals:
            draw_chip(ui, screen, rival.get("livery"), 107, y + 0.4, 5.5)
            ui.text(screen, "mid", rival["name"].upper(), C_HUD_TEXT, 114, y)
            draw_stars(ui, screen, rating.titles_of(self.app.stable_root, f"house:{rival['id']}"),
                       115.5 + text_width(ui, "mid", rival["name"].upper()), y + 0.6, 2.2, 3)
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
        self.left = stable.training_left(racer_dir) if racer else (None if app.workshop else stable.TRAINING_BUDGET)
        self.generations = 20
        self.focus = None                      # None = train on all five tracks
        self.traits = dict(racer.get("traits") or cartraits.default()) if racer else cartraits.default()
        exclude = racer["id"] if racer else None
        options = stable.generation_choices(self.left)
        self.generations = 20 if 20 in options else options[-1] if options else 0
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
                + ["focus", "generations", "start", "back"])

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
            elif row == "focus":
                options = [None] + list(championship.TRACK_ORDER)
                i = options.index(self.focus) + (1 if key in RIGHT else -1)
                self.focus = options[i % len(options)]
            elif row == "generations":
                choices = stable.generation_choices(self.left)
                if choices:
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
        if self.generations <= 0:
            self.message = "No training generations left for this racer."
            return
        if not self.racer_dir and self.stars_left() != 0:
            self.message = f"Spend all {sim_tuning.TRAIT_BUDGET} car stars ({self.stars_left()} left)."
            return
        if self.app.training_dir():
            self.message = "Another racer is training. Wait for it, or stop it from its card."
            return
        partners = [p for p in self.partners if p["key"] in self.chosen]
        if self.racer_dir:
            stable.upskill(self.racer_dir, self.aggression, self.caution, partners, self.generations,
                           self.focus)
            racer_dir = self.racer_dir
        else:
            racer_dir = stable.create(self.app.stable_root, self.name, self.aggression, self.caution,
                                      partners, self.generations, traits=self.traits, focus=self.focus)
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
            elif row == "focus":
                y += 1.0
                ui.text(screen, "mid", "TRAINING ON", C_HUD_DIM, 7, y)
                name = "ALL TRACKS" if self.focus is None else stable.TRACK_NAMES[self.focus].upper()
                ui.text(screen, "mid", f"<  {name}  >", colour, 40, y)
                ui.text(screen, "small", "all-rounder" if self.focus is None else "builds a specialist",
                        C_HUD_DIM, 75, y + 0.8)
                y += 5.0
            elif row == "generations":
                ui.text(screen, "mid", "GENERATIONS", C_HUD_DIM, 7, y)
                minutes = self.generations * 0.7
                ui.text(screen, "mid", f"<  {self.generations}  >", colour, 40, y)
                ui.text(screen, "small", f"about {minutes:.0f} min", C_HUD_DIM, 62, y + 0.8)
                if self.left is not None:
                    ui.text(screen, "small", f"{self.left} of {stable.TRAINING_BUDGET} left for this racer's whole "
                            "life", C_HUD_DIM if self.left else C_PINK, 40, y + 4.2)
                    y += 3.5
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

        ui.panel(screen, 100, 13, 56, 74)
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
        for head, colour, text in (("TRAINING ON", C_HUD_ACCENT, "All tracks makes an all-rounder. One track,"),
                                   ("", C_HUD_ACCENT, "for the same generations, makes a specialist."),
                                   ("THE CAR", C_HUD_ACCENT, f"{sim_tuning.TRAIT_BUDGET} stars over four traits, 1-5 each."),
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
            out.append("race" if self.app.workshop else "championship")
        if training_me:
            out.append("stop")
        elif stable.needs_training(self.racer_dir) and stable.can_train(self.racer_dir):
            out.append("resume")
        left = stable.training_left(self.racer_dir)
        if trained and not training_me and stable.can_train(self.racer_dir) and (left is None or left > 0):
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
        track = self.app.setup["track"]
        laps = Track.load(track).default_laps
        race = Race(track, entries, laps=laps, seed=self.app.race_counter, rolling=True)
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
        elif event.key in LEFT + RIGHT and rows[self.row] == "race":
            tracks = Track.available()
            step = 1 if event.key in RIGHT else -1
            self.app.setup["track"] = tracks[(tracks.index(self.app.setup["track"]) + step) % len(tracks)]
            self.app.audio.play("blip")
        elif event.key in ACCEPT:
            self.app.audio.play("select")
            choice = rows[self.row]
            if choice == "back":
                self.leave()
            elif choice == "race":
                self.race()
            elif choice == "championship":
                if championship.active(self.app.stable_root):
                    self.app.show(ChampionshipHub(self.app))
                else:
                    self.app.show(ChampionshipSetupScreen(self.app, preselect=self.racer_dir))
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
        look = stable.livery_of(self.racer_dir)
        draw_chip(ui, screen, look, 143, 3, 12)
        ui.text(screen, "small", f"#{look['number']}  {look['colour']}, {look['trim']}", C_HUD_DIM, 149, 11.5,
                "midtop")
        entry = rating.summary(self.app.stable_root, f"racer:{Path(self.racer_dir).name}")
        ui.text(screen, "mid", f"RATING {entry['rating']:.0f}" if entry else "RATING 1000", C_HUD_ACCENT,
                149, 15, "midtop", shadow=True)
        ui.text(screen, "small", f"+/-{entry['sigma']:.0f}, {entry['races']} rated races" if entry
                else "no rated races yet", C_HUD_DIM, 149, 19.5, "midtop")
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
        ui.text(screen, "small", "TRAINING: " + stable.specialty_text(self.racer_dir).upper(), C_CYAN, 52, 21)

        # Measured racecraft (latest exam: time trial + race from last v three scripted cars)
        exam = self.history[-1]["exam"] if self.history else None
        y = 24.5
        ui.text(screen, "small", "MEASURED  (latest test on every track: alone, then 3 laps from last v three scripted cars)",
                C_HUD_ACCENT, 6, y)
        if exam:
            e = stable.exam_average(exam)
            items = [("pace", stable.pace_text(stable.pace(exam))), ("avg place", f"{e['race_place']:.1f}"),
                     ("passes", f"{e['race_overtakes']:.1f}"), ("hits caused", f"{e['race_fault']:.1f}"),
                     ("damage", f"{e['race_damage'] * 100:.0f}%"), ("in a tow", f"{e['race_draft'] * 100:.0f}%")]
            x = 6
            for k, (label, value) in enumerate(items):
                ui.text(screen, "small", label, C_HUD_DIM, x, y + 3)
                ui.text(screen, "small" if k == 0 else "mid", value, C_HUD_TEXT, x, y + 5.6)
                x += 34 if k == 0 else 20
            laps = "   ".join(f"{stable.TRACK_NAMES.get(t, t)} {format_time(r['solo_best_lap'])}"
                             for t, r in exam.items())
            ui.text(screen, "small", "best laps alone: " + laps, C_HUD_DIM, 6, y + 9.4)
        else:
            ui.text(screen, "small", "not trained yet", C_HUD_DIM, 6, y + 3)

        # Career
        c = racer["career"]
        y = 39
        ui.text(screen, "small", "CAREER", C_HUD_ACCENT, 6, y)
        best = ", ".join(f"{t} {format_time(b)}" for t, b in c["best_laps"].items()) or "-"
        titles = c.get("titles", 0)
        ui.text(screen, "mid", f"{c['races']} races   {c['wins']} wins   {c['podiums']} podiums", C_HUD_TEXT, 6, y + 3)
        left = stable.training_left(self.racer_dir)
        if left is not None:
            ui.text(screen, "small", "training", C_HUD_DIM, 70, y + 3.6)
            bar(ui, screen, 82, y + 3.8, 30, min(1.0, stable.training_planned(self.racer_dir)
                                                 / stable.TRAINING_BUDGET), C_CYAN)
            ui.text(screen, "small", f"{stable.training_planned(self.racer_dir)} of {stable.TRAINING_BUDGET}"
                    + ("  fully trained" if left == 0 else ""), C_HUD_DIM, 114, y + 3.6)
        if titles:
            used = draw_stars(ui, screen, titles, 20, y - 0.2, 3.0, 6)
            ui.text(screen, "small", f"{titles} championship{'s' if titles != 1 else ''}", C_HUD_ACCENT,
                    21 + used, y + 0.4)
        kids = stable.offspring(Path(self.racer_dir).parent, racer["id"])
        family = f"   offspring: {', '.join(kids)}" if kids else ""
        ui.text(screen, "small", f"best race laps: {best}{family}"[:110], C_HUD_DIM, 6, y + 7.5)
        if entry and entry["tracks"]:
            ui.text(screen, "small", "track ratings: " + "   ".join(
                f"{stable.TRACK_NAMES[t]} {v:.0f}" for t, v in entry["tracks"].items()
                if t in stable.TRACK_NAMES), C_HUD_DIM, 6, y + 11)
        if stable.careers_enabled(Path(self.racer_dir).parent) and racer.get("status", "racing") == "racing":
            ui.text(screen, "small", "career", C_HUD_DIM, 70, y + 0.2)
            bar(ui, screen, 82, y + 0.4, 30, min(1.0, c["races"] / stable.CAREER_RACES), C_HUD_ACCENT)

        # Charts over every generation trained
        if self.history:
            xs = list(range(1, len(self.history) + 1))
            paces = [None if stable.pace(h["exam"]) is None else (1 - stable.pace(h["exam"])) * 100
                     for h in self.history]
            avgs = [stable.exam_average(h["exam"]) for h in self.history]
            passes = [a["race_overtakes"] for a in avgs]
            hits = [a["race_fault"] for a in avgs]
            starts = [k + 1 for k, h in enumerate(self.history) if k and h["version"] != self.history[k - 1]["version"]]
            marker = (starts[-1], "upskill") if starts else None
            ui.chart(screen, 4, 54, 52, 33, "PACE (% quicker than scripted)", xs, [("pace", C_CYAN, paces)],
                     "{:.0f}", marker)
            ui.chart(screen, 58, 54, 52, 33, "TEST RACES (avg)", xs,
                     [("passes", C_CYAN, passes), ("hits caused", C_PINK, hits)], "{:.1f}", marker, floor=0.0)

        labels = {"certificate": "BREEDING CERTIFICATE", "resume_breeding": "RESUME BREEDING",
                  "race": "TEST RACE", "championship": "ENTER CHAMPIONSHIP", "stop": "STOP",
                  "resume": "RESUME TRAINING",
                  "upskill": "UPSKILL", "retire": "RETIRE TO STUD", "publish": "PUBLISH AS HOUSE RIVAL",
                  "back": "BACK"}
        rows = self.rows()
        y = 48.0
        for i, row in enumerate(rows):
            selected = i == min(self.row, len(rows) - 1)
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 112, y)
            ui.text(screen, "mid", labels[row], C_HUD_ACCENT if selected else C_HUD_TEXT, 115, y, shadow=True)
            if row == "race":
                y += 4.2
                name = stable.TRACK_NAMES.get(self.app.setup["track"], self.app.setup["track"])
                ui.text(screen, "small", f"at  <  {name.upper()}  >", C_HUD_DIM, 117, y)
                y += 2.0
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
            ui.text(screen, "small", f"{p.get('wins', 0)} wins in {p.get('races', 0)} races, {lap}"
                    + (f", RATING {p['rating']['rating']:.0f}" if p.get("rating") else ""),
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
        target = (f"target: {stable.pace_text(cert['target_pace'])}" if "target_pace" in cert
                  else f"target {cert.get('target_lap', 0):.2f}s")
        ui.text(screen, "small", f"THE LITTER: {cert['litter']} foals, {cert['shortlist']} shortlisted.  "
                f"Picked by: {cert['criterion_text']} ({target})", C_HUD_ACCENT, 7, y)
        y += 3.6
        for x, head in ((9, "FOAL"), (24, "ROUND 1"), (40, "PACE V SCRIPTED"), (68, "GENS TO TARGET"),
                        (92, "AVG PLACE"), (110, "PASSES"), (126, "HITS"), (140, "DAMAGE")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        for c in cert["candidates"]:
            y += 3.4
            colour = C_HUD_ACCENT if c["chosen"] else C_HUD_TEXT
            if c["chosen"]:
                ui.text(screen, "small", ">", C_PINK, 6, y)
            if "pace" in c:
                lap = f"{(1 - c['pace']) * 100:+.0f}%" if c["pace"] else "-"
            else:
                lap = f"{c['best_lap']:.2f}s" if c.get("best_lap") else "-"
            gens = str(c["gens_to_target"]) if c["gens_to_target"] else "not reached"
            place = f"{c['race_place']:.1f}" if isinstance(c["race_place"], float) else f"P{c['race_place']}"
            for x, value in ((9, f"no. {c['foal']}"), (24, f"{c['trial_rank']} of {cert['litter']}"), (40, lap),
                             (68, gens), (92, place), (110, str(c["passes"])),
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
    """Track records, past champions, and the racers who have died."""

    def __init__(self, app):
        super().__init__(app)
        root = app.stable_root
        self.legends = stable.hall_of_fame(root)
        self.records = records.load(root)
        self.champions = championship.past_champions(root)
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
        # Track records (left) and champions (right)
        ui.panel(screen, 3, 13, 76, 30)
        ui.text(screen, "small", "TRACK RECORDS (fastest race lap)", C_HUD_ACCENT, 6, 14.5)
        y = 19.0
        for track in championship.TRACK_ORDER:
            ui.text(screen, "small", stable.TRACK_NAMES[track].upper(), C_HUD_TEXT, 6, y + 0.6)
            rec = self.records.get(track)
            if rec:
                ui.text(screen, "mid", format_time(rec["time"]), C_HUD_ACCENT, 28, y)
                if rec.get("livery"):
                    draw_chip(ui, screen, rec["livery"], 47, y + 0.2, 4)
                ui.text(screen, "small", rec["name"].upper()[:16], C_HUD_TEXT, 52, y + 0.6)
            else:
                ui.text(screen, "small", "no record yet", C_HUD_DIM, 28, y + 0.6)
            y += 4.8
        ui.panel(screen, 82, 13, 75, 30)
        ui.text(screen, "small", "CHAMPIONS", C_HUD_ACCENT, 85, 14.5)
        y = 19.0
        for c in self.champions[:5]:
            ui.text(screen, "small", f"SEASON {c['season']}", C_HUD_DIM, 85, y + 0.6)
            draw_chip(ui, screen, c["livery"], 105, y + 0.2, 4)
            ui.text(screen, "small", f"{c['name'].upper()[:16]}  {c['points']} pts", C_HUD_TEXT, 110, y + 0.6)
            y += 4.8
        if not self.champions:
            ui.text(screen, "small", "No season finished yet.", C_HUD_DIM, 85, y)
        # Legends
        y = 46.0
        ui.text(screen, "small", "LEGENDS", C_HUD_ACCENT, 6, y)
        for x, head in ((50, "RACES"), (62, "WINS"), (72, "TITLES"), (84, "PEAK"),
                        (98, "BEST LAP"), (116, "FOALS"), (127, "DIED")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        y += 4.2
        root = self.app.stable_root
        shown = self.legends[:6]
        for i, d in enumerate(shown + ["back"]):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 3, y)
            if d == "back":
                ui.text(screen, "mid", "BACK", colour, 8, y + 1)
                break
            r = stable.load(d)
            c = r["career"]
            best = min(c["best_laps"].values()) if c["best_laps"] else None
            skill = rating.summary(root, f"racer:{r['id']}")
            for x, value in ((8, r["name"].upper()[:18]), (50, str(c["races"])), (62, str(c["wins"])),
                             (84, f"{skill['peak']:.0f}" if skill else "-"),
                             (98, format_time(best)), (116, str(len(stable.offspring(root, r["id"]))))):
                ui.text(screen, "small", value, colour, x, y + 0.6)
            ui.text(screen, "small", r.get("death_cause", ""), C_HUD_DIM, 127, y + 0.6)
            draw_stars(ui, screen, c.get("titles", 0), 72, y + 0.4, 2.2, 4)
            y += 4.6
        if not self.legends:
            ui.text(screen, "small", "No racer has died yet.", C_HUD_DIM, 8, y + 6)


# -------------------------------------------------------------- championship

class ChampionshipSetupScreen(Screen):
    """Choose one or two of your racers for a new championship."""

    def __init__(self, app, preselect=None):
        super().__init__(app)
        self.candidates = championship.eligible(app.stable_root)
        self.chosen = [Path(preselect)] if preselect and Path(preselect) in self.candidates else []
        self.row = 0
        self.message = ""

    def rows(self) -> list:
        return self.candidates + ["start", "back"]

    def handle_event(self, event) -> None:
        from .screens import BACK
        if event.type != pygame.KEYDOWN:
            return
        rows = self.rows()
        if event.key in BACK:
            self.app.show(StableScreen(self.app))
        elif event.key in UP:
            self.row = (self.row - 1) % len(rows)
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(rows)
        elif event.key in ACCEPT or event.key in LEFT + RIGHT:
            choice = rows[self.row]
            if choice == "back":
                self.app.show(StableScreen(self.app))
            elif choice == "start":
                self.start()
            elif choice in self.chosen:
                self.chosen.remove(choice)
            elif len(self.chosen) >= championship.MAX_OWN:
                self.message = f"At most {championship.MAX_OWN} of your racers can enter."
            else:
                self.chosen.append(choice)
                self.message = ""
            self.app.audio.play("blip")

    def start(self) -> None:
        if not self.chosen:
            self.message = "Tick at least one racer to enter."
            return
        championship.start(self.app.stable_root, self.chosen)
        self.app.audio.play("select")
        self.app.show(ChampionshipHub(self.app))

    def field(self) -> list[dict]:
        """Who would be on the grid: the entered racers, then house rivals, then scripted cars."""
        out = [{"name": stable.load(d)["name"], "livery": stable.livery_of(d), "kind": "yours",
                "titles": stable.load(d)["career"].get("titles", 0)} for d in self.chosen]
        for rival in stable.house_rivals():
            if len(out) < championship.FIELD:
                out.append({"name": rival["name"], "livery": rival["livery"], "kind": "house rival",
                            "titles": rating.titles_of(self.app.stable_root, f"house:{rival['id']}")})
        n = 1
        while len(out) < championship.FIELD:
            out.append({"name": f"Scripted {n}", "livery": None, "kind": "scripted"})
            n += 1
        return out

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "ENTER A CHAMPIONSHIP", C_HUD_ACCENT, 6, 4, shadow=True)
        ui.text(screen, "small", "Five races, one per track. Pick one or two of your racers.", C_HUD_DIM, 6, 11)
        y = 17.0
        for i, row in enumerate(self.rows()):
            selected = i == self.row
            colour = C_HUD_ACCENT if selected else C_HUD_TEXT
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 4, y)
            if row == "start":
                ui.text(screen, "big", "START THE CHAMPIONSHIP", colour, 7, y + 1, shadow=True)
                y += 8
            elif row == "back":
                ui.text(screen, "mid", "BACK", colour, 7, y)
            else:
                tick = "[x]" if row in self.chosen else "[ ]"
                draw_chip(ui, screen, stable.livery_of(row), 16, y + 0.2, 5.5)
                ui.text(screen, "mid", f"{tick}  {stable.load(row)['name'].upper()}", colour, 24, y)
                draw_stars(ui, screen, stable.load(row)["career"].get("titles", 0),
                           25.5 + text_width(ui, "mid", f"{tick}  {stable.load(row)['name'].upper()}"), y + 0.5, 2.4, 4)
                career = stable.load(row)["career"]
                ui.text(screen, "small", f"race {career['races']} of {stable.CAREER_RACES}", C_HUD_DIM, 80, y + 0.8)
                y += 6
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 7, 87.5, "bottomleft")
        ui.panel(screen, 104, 13, 52, 60)
        ui.text(screen, "mid", "THE FIELD", C_HUD_ACCENT, 107, 15)
        y = 21.0
        for entry in self.field():
            draw_chip(ui, screen, entry["livery"], 107, y, 6)
            ui.text(screen, "small", entry["name"].upper(), C_HUD_TEXT, 115, y - 0.2)
            draw_stars(ui, screen, entry.get("titles", 0), 116.5 + text_width(ui, "small", entry["name"].upper()),
                       y - 0.4, 2.0, 3)
            ui.text(screen, "small", entry["kind"], C_HUD_DIM, 115, y + 2.6)
            y += 6.5
        ui.text(screen, "small", "TRACKS", C_HUD_ACCENT, 107, y + 1)
        ui.text(screen, "small", ", ".join(stable.TRACK_NAMES[t] for t in championship.TRACK_ORDER), C_HUD_DIM,
                107, y + 4)
        ui.text(screen, "small", f"{championship.RACE_LAPS} laps each. 10-7-5-3 points, +1 fastest lap.", C_HUD_DIM,
                107, y + 8)
        ui.text(screen, "small", "Reverse grid: the leader starts last.", C_HUD_DIM, 107, y + 11)


def _names(ch: dict) -> list[str]:
    return [e["name"] for e in ch["entrants"]]


def draw_table(ui, screen, ch, x, y, width, rows, with_arrows=True, elo=None) -> float:
    """The championship table (points and Elo); returns the y below it.
    `elo` maps entrant index -> (rating, change or None)."""
    for hx, head in ((2, "POS"), (20, "RACER"), (width - 24, "PTS"), (width - 12, "RATING")):
        ui.text(screen, "small", head, C_HUD_DIM, x + hx, y)
    y += 3.6
    for row in rows:
        e = ch["entrants"][row["entrant"]]
        mine = e["kind"] == "racer"
        colour = C_HUD_ACCENT if mine else C_HUD_TEXT
        ui.text(screen, "mid", str(row["position"]), colour, x + 2, y)
        if with_arrows and row["moved"]:
            ui.text(screen, "small", ("+" if row["moved"] > 0 else "-") + str(abs(row["moved"])),
                    C_CYAN if row["moved"] > 0 else C_PINK, x + 7, y + 0.8)
        draw_chip(ui, screen, e["livery"], x + 13, y + 0.2, 5)
        ui.text(screen, "mid", e["name"].upper()[:14], colour, x + 20, y)
        ui.text(screen, "mid", str(row["points"]), C_HUD_ACCENT, x + width - 24, y)
        if elo and row["entrant"] in elo:
            value, change = elo[row["entrant"]]
            ui.text(screen, "mid", f"{value:.0f}", C_HUD_TEXT, x + width - 12, y)
            if change is not None:
                ui.text(screen, "small", f"{change:+.0f}", C_CYAN if change >= 0 else C_PINK,
                        x + width - 12, y + 3.7)
        y += 6.2
    return y


class ChampionshipHub(Screen):
    """The season: table, the next race, and whether to watch or simulate it."""

    ROWS = ["watch", "sim", "abandon"]

    def __init__(self, app):
        super().__init__(app)
        self.root = app.stable_root
        self.ch = championship.active(self.root)
        self.row = 0
        self.confirm = False
        self.thumb = None
        self.next = championship.next_race(self.ch) if self.ch else None
        self.track = Track.load(self.next["track"]) if self.next else None

    def handle_event(self, event) -> None:
        from .screens import BACK
        if event.type != pygame.KEYDOWN:
            return
        if event.key in BACK or self.ch is None:
            self.app.show(StableScreen(self.app))
        elif event.key in UP:
            self.row = (self.row - 1) % len(self.ROWS)
            self.confirm = False
        elif event.key in DOWN:
            self.row = (self.row + 1) % len(self.ROWS)
            self.confirm = False
        elif event.key in ACCEPT:
            choice = self.ROWS[self.row]
            if choice == "abandon":
                if self.confirm:
                    championship.abandon(self.root)
                    self.app.show(StableScreen(self.app))
                self.confirm = True
            else:
                self.app.audio.play("select")
                self.run_race(watch=choice == "watch")

    def run_race(self, watch: bool) -> None:
        app, root, ch = self.app, self.root, self.ch
        race = championship.build_race(root, ch)
        k = len(ch["races"])

        def on_over(finished) -> list[str]:
            championship.finish_race(root, ch, finished)      # scores it and updates careers
            return []

        def to_standings() -> None:
            app.show(StandingsScreen(app, ch, k))

        if watch:
            app.show(RaceScreen(app, race, on_over=on_over, on_continue=to_standings,
                                back=lambda a: ChampionshipHub(a)))
        else:
            race.run(max_seconds=400)
            on_over(race)
            to_standings()

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ch = self.ch
        if ch is None or self.next is None:
            ui.text(screen, "mid", "No championship under way. Press Esc.", C_HUD_TEXT, 8, 20)
            return
        ui.text(screen, "big", f"CHAMPIONSHIP: SEASON {ch['season']}", C_HUD_ACCENT, 6, 4, shadow=True)
        rows = championship.standings(ch)
        ui.text(screen, "small", f"after {len(ch['races'])} of {len(ch['tracks'])} races", C_HUD_DIM, 6, 10.5)
        current = {i: (rating.rating_of(self.root, e), None) for i, e in enumerate(ch["entrants"])}
        y = draw_table(ui, screen, ch, 4, 15, 84, rows, elo=current)
        nxt = self.next
        ui.text(screen, "mid", f"NEXT: RACE {nxt['number']} OF {len(ch['tracks'])}", C_HUD_ACCENT, 6, y + 3)
        ui.text(screen, "mid", f"{stable.TRACK_NAMES[nxt['track']].upper()}  ({championship.RACE_LAPS} laps)",
                C_HUD_TEXT, 6, y + 8)
        ui.text(screen, "small", "STARTING GRID  (front to back)", C_HUD_DIM, 6, y + 13.5)
        gy = y + 17
        for slot, e in enumerate(nxt["grid"], start=1):
            ent = ch["entrants"][e]
            cx, cy = 6 + ((slot - 1) % 2) * 42, gy + ((slot - 1) // 2) * 5.5
            draw_chip(ui, screen, ent["livery"], cx, cy, 5)
            ui.text(screen, "small", f"{slot}. {ent['name'][:16]}", C_HUD_TEXT, cx + 7, cy + 0.6)
        size = (int(ui.unit * 62), int(ui.unit * 36))
        if self.thumb is None or self.thumb[0] != size:
            self.thumb = (size, self.app.track_thumbnail(self.track, size))
        frame = ui.panel(screen, 90, 13, 66, 38)
        screen.blit(self.thumb[1], self.thumb[1].get_rect(center=frame.center))
        labels = {"watch": "WATCH THE RACE", "sim": "SIMULATE THE RACE",
                  "abandon": "ABANDON THE CHAMPIONSHIP" if not self.confirm else "PRESS AGAIN TO CONFIRM"}
        y = 56.0
        for i, row in enumerate(self.ROWS):
            selected = i == self.row
            if selected:
                ui.text(screen, "mid", ">", C_PINK, 90, y)
            ui.text(screen, "mid", labels[row], (C_PINK if row == "abandon" else C_HUD_ACCENT) if selected
                    else C_HUD_TEXT, 94, y, shadow=True)
            y += 6
        ui.text(screen, "small", "Simulating skips the visuals and shows the result.", C_HUD_DIM, 94, y + 1)
        ui.text(screen, "small", "ESC leaves; the season is saved.", C_HUD_DIM, 94, y + 4.5)


class StandingsScreen(Screen):
    """After every race: how it went, and the championship table."""

    def __init__(self, app, ch: dict, k: int):
        super().__init__(app)
        self.ch = ch
        self.k = k
        self.record = ch["races"][k]
        self.table = championship.standings(ch, k + 1)       # the table as it stood after this race
        self.done = bool(ch.get("done")) and k + 1 == len(ch["tracks"])

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key in ACCEPT + (pygame.K_ESCAPE,):
            self.app.audio.play("select")
            if self.done:
                self.app.show(StableScreen(self.app))
            else:
                self.app.show(ChampionshipHub(self.app))

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ch, rec = self.ch, self.record
        total = len(ch["tracks"])
        ui.text(screen, "big", f"RACE {self.k + 1} OF {total}: {stable.TRACK_NAMES[rec['track']].upper()}",
                C_HUD_ACCENT, 6, 3, shadow=True)
        # The race
        ui.panel(screen, 3, 12, 68, 40)
        ui.text(screen, "small", "RESULT", C_HUD_ACCENT, 6, 13.5)
        for hx, head in ((2, "POS"), (15, "RACER"), (55, "PTS")):
            ui.text(screen, "small", head, C_HUD_DIM, 3 + hx, 17.5)
        y = 20.0
        for res in sorted(rec["results"], key=lambda r: r["place"]):
            e = ch["entrants"][res["entrant"]]
            colour = C_HUD_ACCENT if e["kind"] == "racer" else C_HUD_TEXT
            ui.text(screen, "mid", str(res["place"]), colour, 5, y)
            draw_chip(ui, screen, e["livery"], 11, y + 0.2, 5)
            ui.text(screen, "mid", e["name"].upper()[:15], colour, 18, y)
            when = format_time(res["time"]) if res["finished"] else "did not finish"
            ui.text(screen, "small", f"started {res['grid']}   {when}", C_HUD_DIM, 18, y + 4)
            pts = f"+{res['points']}" + (" *" if res["fastest"] else "")
            ui.text(screen, "mid", pts, C_HUD_ACCENT if res["points"] else C_HUD_DIM, 58, y)
            y += 6.4
        quick = next((r for r in rec["results"] if r["fastest"]), None)
        if quick:
            e = ch["entrants"][quick["entrant"]]
            line = f"FASTEST LAP  {e['name'].upper()}  {format_time(quick['best_lap'])}"
            draw_chip(ui, screen, e["livery"], 6, 45.8, 3.6)
            ui.text(screen, "small", line, C_HUD_ACCENT, 11, 46.4)
            if quick.get("track_record"):
                ui.text(screen, "small", "NEW TRACK RECORD", C_PINK, 11, 49.6)
            else:
                best = records.load(self.app.stable_root).get(rec["track"])
                if best:
                    ui.text(screen, "small", f"record {format_time(best['time'])} {best['name']}",
                            C_HUD_DIM, 11, 49.6)
        # The table
        ui.panel(screen, 74, 12, 83, 40)
        ui.text(screen, "small", "CHAMPIONSHIP TABLE", C_HUD_ACCENT, 77, 13.5)
        elo = {r["entrant"]: (r["rating"][1], r["rating"][1] - r["rating"][0]) for r in rec["results"]
               if "rating" in r}
        draw_table(ui, screen, ch, 75, 17.5, 81, self.table, elo=elo)
        # What next
        y = 57.0
        if self.done:
            champ = ch["entrants"][ch["champion"]]
            ui.panel(screen, 3, 55, 154, 28, border=C_HUD_ACCENT)
            draw_chip(ui, screen, champ["livery"], 8, 58, 12)
            ui.text(screen, "big", f"CHAMPION: {champ['name'].upper()}", C_HUD_ACCENT, 24, 58, shadow=True)
            draw_stars(ui, screen, championship.titles_of(self.app.stable_root, champ),
                       26 + text_width(ui, "big", f"CHAMPION: {champ['name'].upper()}"), 58.6, 4.0, 6)
            ny = 66.0
            for line in ch.get("news", [])[1:6]:
                ui.text(screen, "small", line, C_HUD_TEXT, 24, ny)
                ny += 3.4
            ui.text(screen, "mid", "CONTINUE", C_HUD_ACCENT, 128, 75, shadow=True)
        else:
            nxt = championship.next_race(ch)
            ui.panel(screen, 3, 55, 154, 28)
            ui.text(screen, "mid", f"NEXT: RACE {nxt['number']}  {stable.TRACK_NAMES[nxt['track']].upper()}",
                    C_HUD_ACCENT, 8, y)
            ui.text(screen, "small", "Starting order (leader of the table starts last):", C_HUD_DIM, 8, y + 6)
            for slot, e in enumerate(nxt["grid"], start=1):
                ent = ch["entrants"][e]
                draw_chip(ui, screen, ent["livery"], 8 + (slot - 1) * 36, y + 11, 6)
                ui.text(screen, "small", f"{slot}. {ent['name'][:11]}", C_HUD_TEXT, 15.5 + (slot - 1) * 36, y + 12)
            for line in ch.get("news", [])[:2]:
                ui.text(screen, "small", line, C_PINK, 8, y + 18)
            ui.text(screen, "mid", "CONTINUE", C_HUD_ACCENT, 128, 75, shadow=True)


class RatingsScreen(Screen):
    """Every rated car, scripted ones included, best first (Up/Down scrolls)."""

    PAGE = 9

    def __init__(self, app):
        super().__init__(app)
        self.rows = rating.table(app.stable_root)
        self.racers = {d.name: d for d in stable.list_racers(app.stable_root, include_dead=True)}
        self.top = 0

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in UP:
            self.top = max(0, self.top - 1)
        elif event.key in DOWN:
            self.top = max(0, min(len(self.rows) - self.PAGE, self.top + 1))
        elif event.key in ACCEPT + (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.app.show(StableScreen(self.app))

    def kind_text(self, row) -> str:
        if row["kind"] == "racer":
            racer_dir = self.racers.get(row["key"].split(":", 1)[1])
            return "yours" + (f", {stable.status(racer_dir)}" if racer_dir else "")
        return {"house": "house rival", "scripted": "scripted"}.get(row["kind"], row["kind"])

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", "RATINGS", C_HUD_ACCENT, 6, 4, shadow=True)
        ui.text(screen, "small", "TrueSkill: every car starts at 1000 and every championship race moves everyone "
                "in it. The +/- is how unsure the rating still is.", C_HUD_DIM, 6, 10.5)
        if not self.rows:
            ui.text(screen, "mid", "No rated races yet. Enter a championship.", C_HUD_TEXT, 8, 22)
            return
        for x, head in ((4, "#"), (20, "CAR"), (66, "RATING"), (86, "PEAK"), (97, "RACES"), (109, "BEST TRACK")):
            ui.text(screen, "small", head, C_HUD_DIM, x, 15)
        y = 19.0
        for pos, row in enumerate(self.rows[self.top:self.top + self.PAGE], start=self.top + 1):
            colour = C_HUD_ACCENT if row["kind"] == "racer" else C_HUD_TEXT
            ui.text(screen, "mid", str(pos), colour, 4, y)
            draw_chip(ui, screen, row["livery"], 12, y + 0.4, 5)
            ui.text(screen, "mid", row["name"].upper()[:15], colour, 20, y)
            ui.text(screen, "small", self.kind_text(row), C_HUD_DIM, 20, y + 4.0)
            draw_stars(ui, screen, stable.titles_for_key(self.app.stable_root, row["key"]),
                       21.5 + text_width(ui, "small", self.kind_text(row)), y + 4.0, 2.2, 5)
            ui.text(screen, "mid", f"{row['rating']:.0f}", colour, 66, y)
            ui.text(screen, "small", f"+/-{row['sigma']:.0f}", C_HUD_DIM, 66, y + 4.0)
            ui.text(screen, "small", f"{row['peak']:.0f}", C_HUD_DIM, 86, y + 0.8)
            ui.text(screen, "small", str(row["races"]), C_HUD_DIM, 97, y + 0.8)
            if row["tracks"]:
                best = max(row["tracks"], key=row["tracks"].get)
                ui.text(screen, "small", f"{stable.TRACK_NAMES.get(best, best)} {row['tracks'][best]:.0f}",
                        C_HUD_DIM, 109, y + 0.8)
            y += 7.3
        more = len(self.rows) - self.PAGE
        hint = "UP/DOWN scroll    " if more > 0 else ""
        ui.text(screen, "small", hint + "ENTER or ESC to go back", C_HUD_DIM, 80, 88, "midbottom")
