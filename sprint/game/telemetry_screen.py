"""The telemetry screen: the fastest laps on each track, and what they teach.

Left/Right picks the track, Up/Down one of its kept laps.  The map shows that
lap's line with where it lifted or braked (red) and got back on the power
(green) at every corner; the trace compares its speed around the lap with the
record lap and with what the ideal line says is safe; the table gives each
corner's numbers.  These are the numbers every AI driver's reference notes
come from.
"""
from __future__ import annotations

import math

import pygame

from ai import telemetry
from sim import tuning
from sim.telemetry import SPACING
from sim.track import Track

from .render import C_CYAN, C_HUD_ACCENT, C_HUD_DIM, C_HUD_TEXT, C_PINK, Camera, format_time
from .screens import ACCEPT, BACK, DOWN, LEFT, RIGHT, UP, Screen

TRACKS = ["oval", "speedway", "esses", "technical", "grandprix"]
NAMES = {"oval": "Oval", "speedway": "Speedway", "esses": "Esses", "technical": "Technical", "grandprix": "Grand Prix"}
C_BRAKE = (240, 70, 80)
C_POWER = (60, 220, 110)


class TelemetryScreen(Screen):
    def __init__(self, app, track: str = "speedway"):
        super().__init__(app)
        self.track_i = TRACKS.index(track) if track in TRACKS else 1
        self.lap_i = 0
        self.maps = {}
        self.load()

    def load(self) -> None:
        self.track = Track.load(TRACKS[self.track_i])
        self.laps = telemetry.load(self.track.key)["laps"]
        self.lap_i = min(self.lap_i, max(0, len(self.laps) - 1))

    def handle_event(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in LEFT + RIGHT:
            self.track_i = (self.track_i + (1 if event.key in RIGHT else -1)) % len(TRACKS)
            self.lap_i = 0
            self.load()
        elif event.key in UP and self.laps:
            self.lap_i = (self.lap_i - 1) % len(self.laps)
        elif event.key in DOWN and self.laps:
            self.lap_i = (self.lap_i + 1) % len(self.laps)
        elif event.key in BACK + ACCEPT:
            from .screens import MainMenu
            self.app.show(MainMenu(self.app))

    # ------------------------------------------------------------- drawing

    def draw(self, screen) -> None:
        ui = self.app.ui
        ui.backdrop(screen)
        ui.text(screen, "big", f"TELEMETRY:  <  {self.track.name.upper()}  >", C_HUD_ACCENT, 6, 3, shadow=True)
        if not self.laps:
            ui.text(screen, "mid", "No laps recorded on this track yet.", C_HUD_TEXT, 6, 20)
            ui.text(screen, "small", "Every flying lap in a race (yours included) and every training test is recorded.",
                    C_HUD_DIM, 6, 27)
            ui.text(screen, "small", "Left/Right: track    Esc: back", C_HUD_DIM, 6, 84)
            return
        lap = self.laps[self.lap_i]
        record = self.laps[0]
        self.draw_list(screen)
        self.draw_map(screen, lap)
        self.draw_trace(screen, lap, record)
        self.draw_corners(screen, lap)
        ui.text(screen, "small", "Left/Right: track   Up/Down: lap   Esc: back", C_HUD_DIM, 6, 88.5, "bottomleft")

    def draw_list(self, screen) -> None:
        ui = self.app.ui
        ui.panel(screen, 3, 11, 60, 30)
        ui.text(screen, "small", "FASTEST LAPS", C_HUD_ACCENT, 6, 12.3)
        y = 16.0
        for i, lap in enumerate(self.laps[:7]):
            colour = C_HUD_ACCENT if i == self.lap_i else C_HUD_TEXT
            who = "YOU" if lap.get("kind") == "human" else "AI"
            if i == self.lap_i:
                ui.text(screen, "small", ">", C_PINK, 4.2, y)
            ui.text(screen, "small", format_time(lap["time"]), colour, 6.5, y)
            ui.text(screen, "small", f"{lap.get('driver', '?')[:16]}", colour, 18, y)
            ui.text(screen, "small", f"{who} {lap.get('weight', '')}", C_HUD_DIM, 44, y)
            y += 3.4

    def draw_map(self, screen, lap: dict) -> None:
        ui = self.app.ui
        key = self.track.key
        size = (int(60 * ui.unit), int(34 * ui.unit))
        if key not in self.maps:
            self.maps[key] = self.app.track_thumbnail(self.track, size)
        x0, y0 = ui.px(3, 43)
        screen.blit(self.maps[key], (int(x0), int(y0)))
        cam = Camera(size)
        pts = [cam.to_screen(x, y) for x, y in zip(lap["x"], lap["y"])]
        pts = [(x0 + px, y0 + py) for px, py in pts]
        if len(pts) > 2:
            pygame.draw.lines(screen, C_CYAN, True, pts, max(1, int(ui.unit * 0.3)))
        n = len(lap["x"])
        for c in telemetry.corner_report(self.track, lap):
            k = int(c["apex"] * self.track.ds / SPACING)
            for dist, colour in ((-(c["brake_before"] or 0) if c["brake_before"] else None, C_BRAKE),
                                 (c["power_after"], C_POWER)):
                if dist is None:
                    continue
                j = (k + int(dist / SPACING)) % n
                px, py = cam.to_screen(lap["x"][j], lap["y"][j])
                pygame.draw.circle(screen, colour, (int(x0 + px), int(y0 + py)), max(2, int(ui.unit * 0.8)))
        ui.text(screen, "small", "line driven", C_CYAN, 4, 78.3)
        ui.text(screen, "small", "lift / brake", C_BRAKE, 20, 78.3)
        ui.text(screen, "small", "back on the power", C_POWER, 36, 78.3)

    def draw_trace(self, screen, lap: dict, record: dict) -> None:
        """Speed around the lap: this lap, the record and the ideal line's safe speed."""
        ui = self.app.ui
        x, y, w, h = 66, 11, 91, 44
        ui.panel(screen, x, y, w, h, border=(70, 56, 120))
        ui.text(screen, "small", "SPEED AROUND THE LAP", C_HUD_TEXT, x + 2, y + 1.2)
        ui.text(screen, "small", "this lap", C_CYAN, x + 34, y + 1.2)
        ui.text(screen, "small", "record", C_PINK, x + 47, y + 1.2)
        ui.text(screen, "small", "ideal line's safe speed", C_HUD_DIM, x + 58, y + 1.2)
        left, right, top, bottom = x + 3, x + w - 2, y + 5, y + h - 18
        _, curv = self.track.ideal()
        from ai.brain import GRIP_PLAN
        grip = tuning.CarParams().grip * GRIP_PLAN
        n = len(lap["speed"])
        safe = [min(38.0, math.sqrt(grip / max(curv[int(k * SPACING / self.track.ds) % self.track.n], 1e-4)))
                for k in range(n)]
        hi = max(max(lap["speed"]), max(record["speed"]), 36.0)

        def pos(k, v):
            return ui.px(left + k / max(1, n - 1) * (right - left), bottom - v / hi * (bottom - top))
        for frac in (0.5, 1.0):
            a, b = pos(0, hi * frac), pos(n - 1, hi * frac)
            pygame.draw.line(screen, (56, 44, 100), a, b)
            ui.text(screen, "small", f"{hi * frac * 6:.0f}", C_HUD_DIM, left - 0.4, bottom - (bottom - top) * frac,
                    "midright")
        for series, colour, width in ((safe, (110, 104, 140), 1), (record["speed"], C_PINK, 2),
                                      (lap["speed"], C_CYAN, 2)):
            pts = [pos(k, v) for k, v in enumerate(series[:n])]
            pygame.draw.lines(screen, colour, False, pts, max(1, int(ui.unit * 0.12 * width)))
        # throttle and brake bands under the trace
        band = bottom + 1.5
        for k in range(n):
            px, _ = pos(k, 0)
            thr, brk = lap["throttle"][k], lap["brake"][k]
            if brk > 0.1:
                colour = C_BRAKE
            elif thr >= 0.8:
                colour = C_POWER
            else:
                colour = (90, 84, 120)
            pygame.draw.rect(screen, colour, pygame.Rect(int(px), int(ui.px(0, band)[1]),
                                                         max(1, int(ui.unit * (right - left) / n) + 1),
                                                         int(ui.unit * 1.6)))
        ui.text(screen, "small", "pedals: green power, grey lift, red brake", C_HUD_DIM, left, band + 2.0)
        # Steering: how much lock, and how often it corrects (up = right, down = left).
        mid, amp = band + 9.0, 3.2
        a, b = ui.px(left, mid), ui.px(right, mid)
        pygame.draw.line(screen, (56, 44, 100), a, b)
        for series, colour in ((record["steering"], C_PINK), (lap["steering"], C_CYAN)):
            pts = [ui.px(left + k / max(1, n - 1) * (right - left), mid - max(-1.0, min(1.0, v)) * amp)
                   for k, v in enumerate(series[:n])]
            if len(pts) > 1:
                pygame.draw.lines(screen, colour, False, pts, max(1, int(ui.unit * 0.22)))
        moves = sum(abs(lap["steering"][k] - lap["steering"][k - 1]) for k in range(1, n))
        ui.text(screen, "small", f"steering (up = right): {moves:.1f} of corrections this lap"
                + (f", record {sum(abs(record['steering'][k] - record['steering'][k - 1]) for k in range(1, n)):.1f}"
                   if record is not lap else ""), C_HUD_DIM, left, mid + amp + 0.6)

    def draw_corners(self, screen, lap: dict) -> None:
        ui = self.app.ui
        x, y = 66, 57
        ui.panel(screen, x, y, 91, 30)
        ui.text(screen, "small", "CORNER BY CORNER  (against the ideal line)", C_HUD_ACCENT, x + 2, y + 1.3)
        heads = ((2, "#"), (7, "APEX SPEED"), (27, "LINE AT APEX"), (50, "LIFTS / BRAKES"), (71, "POWER ON"))
        for hx, head in heads:
            ui.text(screen, "small", head, C_HUD_DIM, x + hx, y + 4.4)
        row = y + 7.4
        for c_i, c in enumerate(telemetry.corner_report(self.track, lap)[:9]):
            gain = c["apex_speed"] / c["ideal_speed"] - 1.0
            ui.text(screen, "small", str(c_i + 1), C_HUD_TEXT, x + 2, row)
            ui.text(screen, "small", f"{c['apex_speed'] * 6:.0f}  ({gain:+.0%})",
                    C_POWER if gain > 0.02 else C_BRAKE if gain < -0.02 else C_HUD_TEXT, x + 7, row)
            shift = (c["apex_line"] - c["ideal_line"]) / max(1e-6, c["half_width"])
            ui.text(screen, "small", f"{shift:+.0%} of half-width", C_HUD_TEXT, x + 27, row)
            ui.text(screen, "small", "-" if c["brake_before"] is None else f"{c['brake_before']:.0f} before apex",
                    C_HUD_TEXT, x + 50, row)
            ui.text(screen, "small", "-" if c["power_after"] is None else f"{c['power_after']:.0f} after apex",
                    C_HUD_TEXT, x + 71, row)
            row += 2.4
