"""The Scouting Report screen: a driver's measured abilities against the
whole field (ai/assess.py).  Assessment only; nothing is trained.

Up/Down scroll, Enter: assess this driver now (about a minute, in the
background; the field is re-scored), Esc back."""
from __future__ import annotations

import json

import pygame

from ai import assess

from .render import C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK
from .screens import ACCEPT, BACK, DOWN, UP, Screen

C_GOOD = (60, 220, 110)
C_BAD = (240, 90, 90)


class ScoutingScreen(Screen):
    VISIBLE = 14

    def __init__(self, app, driver_id: str, name: str, back=None):
        super().__init__(app)
        self.driver_id, self.name, self.back = driver_id, name, back
        self.top = 0
        self.message = ""
        self.timer = 0.0
        self.load()

    def load(self) -> None:
        f = assess.OUT / "field.json"
        data = json.loads(f.read_text()) if f.exists() else {}
        self.cars = data.get("cars", 0)
        self.report = data.get("report", {}).get(self.driver_id)

    def running(self) -> bool:
        return self.app.training_dir() == str(assess.OUT / self.driver_id)

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        rows = self.report["rows"] if self.report else []
        if event.key in BACK:
            self.app.show(self.back() if self.back else __import__("game.screens", fromlist=["MainMenu"]).MainMenu(self.app))
        elif event.key in UP + DOWN and rows:
            self.top = max(0, min(len(rows) - self.VISIBLE, self.top + (1 if event.key in DOWN else -1)))
        elif event.key in ACCEPT:
            if self.app.training_dir():
                self.message = "Something is already running in the background: stop it first."
                return
            self.app.start_scouting(self.name, self.driver_id)
            self.message = f"Assessing {self.name} (about a minute) ..."

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer > 2.0:
            self.timer = 0.0
            was = self.message.startswith("Assessing")
            self.load()
            if was and not self.running():
                self.message = "Assessment finished."

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", f"SCOUTING REPORT: {self.name.upper()}", C_HUD_ACCENT, 6, 3, shadow=True)
        if not self.report:
            ui.text(screen, "mid", "Not assessed yet.  Press Enter to assess (about a minute).", C_HUD_TEXT, 6, 20)
        else:
            ui.text(screen, "small", f"Against {self.cars} cars.  Percentile: share of the field this driver does better "
                    "than.  Strength / weakness only where the measure is reliable and clearly away from the field.",
                    C_HUD_DIM, 6, 11.5)
            for x, head in ((6, "AREA"), (24, "MEASURE"), (92, "VALUE"), (106, "FIELD"), (140, "VERDICT")):
                ui.text(screen, "small", head, C_HUD_DIM, x, 16)
            y = 19.5
            for row in self.report["rows"][self.top:self.top + self.VISIBLE]:
                v, unit = row["value"], row["unit"]
                shown = f"{v:.0%}" if unit == "%" else (f"{v:.3f}" if unit == "x" else f"{v:.2f}{unit}")
                tag = row["tag"]
                colour = C_GOOD if tag == "strength" else C_BAD if tag == "weakness" else C_HUD_TEXT
                ui.text(screen, "small", row["area"].upper(), C_HUD_DIM, 6, y)
                ui.text(screen, "small", row["label"][:52], colour, 24, y)
                ui.text(screen, "small", shown, colour, 92, y)
                frame = ui.rect(106, y + 0.4, 30, 1.8)
                pygame.draw.rect(screen, (50, 44, 80), frame)
                fill = ui.rect(106, y + 0.4, 30 * row["percentile"], 1.8)
                pygame.draw.rect(screen, colour if tag else C_CYAN, fill)
                verdict = tag or ("not reliable yet" if not row["reliable"] else "")
                ui.text(screen, "small", verdict.upper() if tag else verdict, colour if tag else C_HUD_DIM, 140, y)
                y += 3.9
            strengths = [r["label"] for r in self.report["rows"] if r["tag"] == "strength"]
            weaknesses = [r["label"] for r in self.report["rows"] if r["tag"] == "weakness"]
            ui.text(screen, "small", "Strengths: " + (", ".join(strengths) or "none clear")[:150], C_GOOD, 6, 83)
            ui.text(screen, "small", "Weaknesses: " + (", ".join(weaknesses) or "none clear")[:150], C_BAD, 6, 80)
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 6, 75.5)
        ui.text(screen, "small", "Up/Down scroll   Enter assess now   Esc back", C_HUD_DIM, 6, 87)
