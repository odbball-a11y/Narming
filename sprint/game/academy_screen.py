"""The Racing Academy screen: enrol a driver, watch its progress, read its
report and, when the candidate has really improved, promote it.

Drivers are the house rivals and your stable's trained racers.  The course
(`ai/academy.py`) runs in a separate process; its files live in
`academy/<driver>/`.  The original brain is never changed unless you promote
the candidate (press P twice), and promotion is only offered when the
improvement is larger than the testing noise.
"""
from __future__ import annotations

import pygame

from ai import academy, stable

from .render import C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK
from .screens import ACCEPT, BACK, DOWN, UP, Screen

C_GOOD = (60, 220, 110)
C_BAD = (240, 90, 90)


def drivers(root) -> list[dict]:
    """{"name", "id", "kind"} for every house rival and trained stable racer."""
    out = [{"name": c["name"], "id": c["id"], "kind": "house rival"} for c in stable.house_rivals()]
    for d in stable.list_racers(root, include_dead=True) if root else []:
        if stable.brain_file(d) is None or stable.is_breeding(d) or stable.is_house_stud(d):
            continue
        out.append({"name": stable.load(d)["name"], "id": d.name, "kind": "your racer"})
    return out


class AcademyScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.list = drivers(app.stable_root)
        self.row = 0
        self.mode = "pick"
        self.message = ""
        self.confirm = False
        self.timer = 0.0
        self.states = {}
        self.refresh()

    def refresh(self) -> None:
        self.states = {d["id"]: academy.status(d["id"]) for d in self.list}

    def current(self) -> dict:
        return self.list[self.row]

    # -------------------------------------------------------------- input

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if self.mode == "report":
            if event.key in BACK + ACCEPT:
                self.mode, self.message, self.confirm = "pick", "", False
            elif event.key == pygame.K_p:
                self.promote()
            return
        if event.key in BACK:
            from .screens import MainMenu
            self.app.show(MainMenu(self.app))
        elif event.key in UP + DOWN and self.list:
            self.row = (self.row + (1 if event.key in DOWN else -1)) % len(self.list)
            self.message = ""
        elif event.key in ACCEPT and self.list:
            d = self.current()
            if self.states[d["id"]]["stage"] == "finished":
                self.open_report()
            else:
                self.enrol(d)
        elif event.key == pygame.K_r and self.list:
            self.open_report()
        elif event.key == pygame.K_s and self.list:           # the driver's Scouting Report
            from .scouting_screen import ScoutingScreen
            d = self.current()
            self.app.show(ScoutingScreen(self.app, d["id"], d["name"], back=lambda: AcademyScreen(self.app)))

    def open_report(self) -> None:
        s = academy.summary(self.current()["id"])
        if s is None:
            self.message = "No report yet: the original has not been tested."
            return
        self.summary, self.mode, self.message, self.confirm = s, "report", "", False

    def running(self) -> str | None:
        """The id of the driver whose course is running, if any."""
        path = self.app.training_dir()
        if not path:
            return None
        return next((d["id"] for d in self.list if str(academy.folder(d["id"])) == path), "other")

    def enrol(self, d: dict) -> None:
        busy = self.running()
        if busy == d["id"]:
            self.message = f"{d['name']} is already in the Academy."
            return
        if busy:
            self.message = "Something else is training: stop it first."
            return
        self.app.start_academy(d["name"], academy.folder(d["id"]))
        self.message = f"{d['name']} has started the Academy (about 25 minutes)."
        self.refresh()

    def promote(self) -> None:
        ok, why = academy.promotable(self.summary_id())
        if not ok:
            self.message = why
            return
        if not self.confirm:
            self.confirm = True
            self.message = f"{why}. Press P again to make the candidate {self.summary['name']}'s driver."
            return
        self.confirm = False
        try:
            self.message = academy.promote(self.summary["name"])
            stable.register(self.app.stable_root)
        except ValueError as e:
            self.message = str(e)

    def summary_id(self) -> str:
        return self.current()["id"]

    def update(self, seconds: float) -> None:
        self.timer += seconds
        if self.timer > 2.0:
            self.timer = 0.0
            self.refresh()

    # ------------------------------------------------------------ drawing

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        if self.mode == "report":
            self.draw_report(screen)
        else:
            self.draw_pick(screen)
        if self.message:
            ui.text(screen, "small", self.message, C_PINK, 6, 84.5)

    def draw_pick(self, screen) -> None:
        ui = self.app.ui
        ui.text(screen, "big", "RACING ACADEMY", C_HUD_ACCENT, 6, 4, shadow=True)
        ui.text(screen, "small", "32 challenges in 8 modules, from car control to full races. A copy of the driver "
                "trains; the original is kept unless you promote it.", C_HUD_DIM, 6, 12.5)
        running = self.running()
        y = 19.0
        top = max(0, self.row - 13)
        for k, d in enumerate(self.list[top:top + 14], start=top):
            st = self.states.get(d["id"], {})
            sel = k == self.row
            colour = C_HUD_ACCENT if sel else C_HUD_TEXT
            ui.text(screen, "mid", ("> " if sel else "") + d["name"], colour, 8, y)
            ui.text(screen, "small", d["kind"], C_HUD_DIM, 52, y + 0.8)
            stage = st.get("stage", "not enrolled")
            if stage == "enrolled" and st.get("done"):
                stage = "training"
            if stage == "training":
                text = f"training {st['done']}/{st['of']}" + ("" if running == d["id"] else " (paused)")
                tint = C_CYAN
            elif stage == "finished":
                s = academy.summary(d["id"])
                text = (f"finished: unseen {s['before']:.0%} -> {s['after']:.0%}  {s['change']}"
                        if s and s["after"] is not None else "finished")
                tint = C_GOOD if s and s["promotable"] else C_HUD_TEXT
            elif stage == "not enrolled":
                text, tint = "not enrolled", C_HUD_DIM
            else:
                text = stage + ("" if running == d["id"] else " (paused)")
                tint = C_CYAN
            ui.text(screen, "small", text, tint, 70, y + 0.8)
            y += 4.6
        ui.text(screen, "small", "Up/Down choose   Enter enrol / carry on / see the report   R report   S scouting report   Esc back",
                C_HUD_DIM, 6, 88.5, "bottomleft")

    def draw_report(self, screen) -> None:
        ui = self.app.ui
        s = self.summary
        ui.text(screen, "big", f"ACADEMY REPORT: {s['name'].upper()}", C_HUD_ACCENT, 6, 3, shadow=True)
        after = "-" if s["after"] is None else f"{s['after']:.0%}"
        ui.text(screen, "mid", f"Unseen scenarios: {s['before']:.0%} -> {after}   {s['change']}", C_HUD_TEXT, 6, 11)
        ui.text(screen, "small", f"(+-{s['margin']:.0%} each)   challenges completed {s['completed_before']} -> "
                f"{s['completed_after']} of 32   grade {s['grade_before']} -> {s['grade_after']}   "
                f"candidate = generation {s['gen']}", C_HUD_DIM, 6, 16)
        y = 21.0
        ui.text(screen, "small", "MODULE", C_HUD_DIM, 6, y)
        for x, head in ((84, "BEFORE"), (98, "AFTER"), (112, "CHANGE")):
            ui.text(screen, "small", head, C_HUD_DIM, x, y)
        for m in s["modules"]:
            y += 3.3
            ui.text(screen, "small", f"{m['module']}. {m['title']}", C_HUD_TEXT, 6, y)
            ui.text(screen, "small", f"{m['before']:.0%}", C_HUD_TEXT, 84, y)
            ui.text(screen, "small", "-" if m["after"] is None else f"{m['after']:.0%}", C_HUD_TEXT, 98, y)
            real = "real" in m["change"]
            up = m["change"].startswith("+") and real
            ui.text(screen, "small", m["change"], C_GOOD if up else C_BAD if real else C_HUD_DIM, 112, y)
        y += 5
        ui.text(screen, "small", "RACE PANEL (six cars, five laps)", C_HUD_ACCENT, 6, y)
        races = s.get("races") or {}
        for key, label in (("Original", "original"), ("Candidate", "Academy candidate")):
            if key in races:
                y += 3.3
                t = races[key]
                ui.text(screen, "small", f"{s['name']} ({label}): {t['wins']} wins in {t['races']}, avg place "
                        f"{t['place']:.2f} +- {t.get('place_se', 0):.2f}, damage {t['damage']:.0%}", C_HUD_TEXT, 6, y)
        y += 4.5
        ui.text(screen, "small", f"Strengths: {', '.join(s['strengths'])}", C_GOOD, 6, y)
        ui.text(screen, "small", f"Weaknesses: {', '.join(s['weaknesses'])}", C_BAD, 6, y + 3.3)
        ui.text(screen, "small", ("P (twice) promote the candidate" if s["promotable"] else s["why"])
                + "     Esc back", C_HUD_TEXT if s["promotable"] else C_HUD_DIM, 6, 80)
