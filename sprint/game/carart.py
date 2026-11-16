"""Car body styles (looks only: physics and collisions never change).

`STYLE` is the style every car is drawn in: "classic" (the original little
racer, drawn in render.make_car_sprite), "gt3" or "formula".  The player
picks it on the main menu (C); it is remembered in settings.json.
`draw(style, ...)` returns a sprite pointing right, the same size and margin
as the classic one (2 px all round), in the car's livery: body colour, trim
(stripe | twin | nose | wing | band), trim colour and number.
"""
from __future__ import annotations

import json
from pathlib import Path

import pygame

STYLES = ["classic", "gt3", "formula"]
NAMES = {"classic": "CLASSIC", "gt3": "GT3", "formula": "FORMULA"}
STYLE = "classic"
SETTINGS = Path(__file__).resolve().parent.parent / "settings.json"
M = 2
TYRE, GLASS, WHITE, CARBON, INK = (22, 22, 26), (22, 28, 44), (246, 246, 246), (34, 35, 40), (15, 15, 20)


def load() -> str:
    global STYLE
    try:
        style = json.loads(SETTINGS.read_text(encoding="utf-8")).get("car_style")
    except (OSError, ValueError):
        style = None
    STYLE = style if style in STYLES else "classic"
    return STYLE


def cycle() -> str:
    """Switch to the next style and remember it."""
    global STYLE
    STYLE = STYLES[(STYLES.index(STYLE) + 1) % len(STYLES)]
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    except (OSError, ValueError):
        data = {}
    try:
        SETTINGS.write_text(json.dumps(dict(data, car_style=STYLE), indent=1), encoding="utf-8")
    except OSError:
        pass
    return STYLE


def _sh(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class _Pen:
    def __init__(self, length: float, width: float):
        self.L, self.W = length, width
        self.s = pygame.Surface((int(length) + 2 * M, int(width) + 2 * M), pygame.SRCALPHA)

    def pt(self, p):
        return (M + p[0] * self.L, M + p[1] * self.W)

    def poly(self, pts, col, sym=False):
        pygame.draw.polygon(self.s, col, [self.pt(p) for p in pts])
        if sym:
            pygame.draw.polygon(self.s, col, [self.pt((x, 1 - y)) for x, y in pts])

    def line(self, a, b, col, w, sym=False):
        width = max(1, int(w * self.W))
        pygame.draw.line(self.s, col, self.pt(a), self.pt(b), width)
        if sym:
            pygame.draw.line(self.s, col, self.pt((a[0], 1 - a[1])), self.pt((b[0], 1 - b[1])), width)

    def rr(self, x0, y0, x1, y1, col, rad=0.05, sym=False):
        for a, b in ([(y0, y1), (1 - y1, 1 - y0)] if sym else [(y0, y1)]):
            pygame.draw.rect(self.s, col, pygame.Rect(M + x0 * self.L, M + a * self.W, (x1 - x0) * self.L,
                                                      (b - a) * self.W), border_radius=int(rad * self.W))

    def ell(self, x0, y0, x1, y1, col):
        pygame.draw.ellipse(self.s, col, pygame.Rect(M + x0 * self.L, M + y0 * self.W, (x1 - x0) * self.L,
                                                     (y1 - y0) * self.W))

    def tyre(self, x0, x1, y0, y1):
        for a, b in ((y0, y1), (1 - y1, 1 - y0)):
            self.rr(x0, a, x1, b, TYRE, 0.07)
            self.rr(x0 + 0.01, a + 0.02, x1 - 0.01, a + 0.06, (48, 48, 54), 0.02)
            for k in range(1, 5):
                x = x0 + (x1 - x0) * k / 5
                self.line((x, a + 0.01), (x, b - 0.01), (10, 10, 12), 0.012)

    def number(self, n, cx, cy, r):
        if n is None or self.W < 40:
            return
        self.ell(cx - r / 2, cy - r * 0.95, cx + r / 2, cy + r * 0.95, WHITE)
        pygame.font.init()
        font = pygame.font.Font(None, max(8, int(r * 1.9 * self.W)))
        text = pygame.transform.rotate(font.render(str(n), True, INK), -90)
        self.s.blit(text, text.get_rect(center=self.pt((cx, cy))))

    def done(self) -> pygame.Surface:
        """The drawing with a thin dark outline, so it stands out on any surface."""
        out = pygame.Surface(self.s.get_size(), pygame.SRCALPHA)
        edge = pygame.mask.from_surface(self.s, 40).to_surface(setcolor=(12, 12, 16, 255), unsetcolor=(0, 0, 0, 0))
        o = max(1, int(self.W * 0.012))
        for dx, dy in ((o, 0), (-o, 0), (0, o), (0, -o)):
            out.blit(edge, (dx, dy))
        out.blit(self.s, (0, 0))
        return out


def _gt3(p: _Pen, col, trim, trim_col, number) -> None:
    dark, lite = _sh(col, 0.62), _mix(col, WHITE, 0.30)
    bonnet = trim_col if trim == "nose" else lite
    p.tyre(0.13, 0.29, 0.01, 0.20)
    p.tyre(0.68, 0.84, 0.01, 0.20)
    p.poly([(0.86, 0.05), (0.995, 0.20), (1.0, 0.5), (0.995, 0.80), (0.86, 0.95)], CARBON)          # splitter
    p.poly([(0.01, 0.20), (0.06, 0.12), (0.06, 0.88), (0.01, 0.80)], CARBON)                        # diffuser
    p.poly([(0.03, 0.18), (0.08, 0.09), (0.20, 0.055), (0.31, 0.07), (0.40, 0.115), (0.60, 0.115), (0.68, 0.06),
            (0.82, 0.05), (0.92, 0.10), (0.975, 0.24), (0.985, 0.5), (0.975, 0.76), (0.92, 0.90), (0.82, 0.95),
            (0.68, 0.94), (0.60, 0.885), (0.40, 0.885), (0.31, 0.93), (0.20, 0.945), (0.08, 0.91), (0.03, 0.82)], col)
    p.poly([(0.05, 0.17), (0.09, 0.105), (0.20, 0.075), (0.31, 0.09), (0.40, 0.135), (0.60, 0.135), (0.60, 0.19),
            (0.05, 0.22)], _sh(col, 0.74), True)                                                 # flanks
    p.poly([(0.66, 0.085), (0.82, 0.07), (0.91, 0.115), (0.955, 0.24), (0.66, 0.20)], _sh(col, 0.85), True)
    p.poly([(0.64, 0.24), (0.93, 0.28), (0.965, 0.5), (0.93, 0.72), (0.64, 0.76), (0.67, 0.5)], bonnet)
    p.poly([(0.66, 0.30), (0.92, 0.33), (0.945, 0.5), (0.92, 0.67), (0.66, 0.70), (0.69, 0.5)],
           _sh(bonnet, 0.92) if trim == "nose" else _mix(col, WHITE, 0.12))
    p.poly([(0.72, 0.31), (0.86, 0.335), (0.86, 0.40), (0.72, 0.385)], (16, 16, 20), True)          # bonnet vents
    for k in range(3):
        x = 0.745 + k * 0.04
        p.line((x, 0.325), (x + 0.01, 0.395), dark, 0.012, True)
    p.poly([(0.50, 0.185), (0.635, 0.245), (0.665, 0.5), (0.635, 0.755), (0.50, 0.815), (0.545, 0.5)], (10, 10, 14))
    p.poly([(0.515, 0.215), (0.625, 0.265), (0.65, 0.5), (0.625, 0.735), (0.515, 0.785), (0.555, 0.5)], GLASS)
    p.poly([(0.535, 0.26), (0.61, 0.29), (0.625, 0.42), (0.56, 0.40)], (70, 90, 130))               # glint
    p.poly([(0.27, 0.215), (0.515, 0.20), (0.555, 0.5), (0.515, 0.80), (0.27, 0.785)], _sh(col, 0.92))   # roof
    p.poly([(0.30, 0.25), (0.50, 0.24), (0.53, 0.5), (0.50, 0.76), (0.30, 0.75)], col)
    p.poly([(0.16, 0.25), (0.27, 0.215), (0.27, 0.785), (0.16, 0.75)], (10, 10, 14))                 # rear window
    p.poly([(0.175, 0.27), (0.26, 0.24), (0.26, 0.76), (0.175, 0.73)], GLASS)
    for k in range(4):
        y = 0.32 + k * 0.12
        p.line((0.18, y), (0.26, y), (40, 46, 64), 0.012)
    p.poly([(0.29, 0.15), (0.515, 0.145), (0.50, 0.195), (0.29, 0.205)], GLASS, True)                # side windows
    if trim == "stripe":
        p.poly([(0.27, 0.455), (0.985, 0.47), (0.985, 0.53), (0.27, 0.545)], trim_col)
    elif trim == "twin":
        p.poly([(0.27, 0.37), (0.975, 0.40), (0.975, 0.45), (0.27, 0.43)], trim_col, True)
    elif trim == "band":
        p.poly([(0.36, 0.13), (0.46, 0.13), (0.46, 0.87), (0.36, 0.87)], trim_col)
    p.rr(0.36, 0.44, 0.42, 0.56, (16, 16, 20), 0.02)                                                # roof hatch
    p.poly([(0.07, 0.38), (0.16, 0.36), (0.16, 0.64), (0.07, 0.62)], dark)                           # engine deck
    for k in range(3):
        y = 0.42 + k * 0.08
        p.line((0.08, y), (0.15, y), (16, 16, 20), 0.018)
    p.line((0.06, 0.30), (0.13, 0.31), CARBON, 0.03, True)                                          # wing stays
    p.rr(0.0, 0.04, 0.075, 0.96, CARBON, 0.03)                                                      # rear wing
    p.rr(0.012, 0.09, 0.062, 0.91, trim_col if trim == "wing" else _sh(col, 0.9), 0.02)
    p.line((0.555, 0.20), (0.585, 0.12), CARBON, 0.02, True)                                        # mirrors
    p.rr(0.565, 0.085, 0.605, 0.135, col, 0.015, True)
    p.poly([(0.925, 0.175), (0.965, 0.25), (0.972, 0.34), (0.935, 0.30)], (255, 248, 200), True)     # headlights
    p.poly([(0.035, 0.20), (0.06, 0.19), (0.06, 0.32), (0.035, 0.31)], (240, 40, 40), True)          # tail lights
    p.number(number, 0.40, 0.24, 0.10)
    p.number(number, 0.40, 0.76, 0.10)
    p.number(number, 0.82, 0.5, 0.09)


def _formula(p: _Pen, col, trim, trim_col, number) -> None:
    dark, lite = _sh(col, 0.55), _mix(col, WHITE, 0.35)
    p.tyre(0.07, 0.27, 0.0, 0.27)
    p.tyre(0.70, 0.87, 0.02, 0.24)
    for a, b in (((0.72, 0.22), (0.66, 0.42)), ((0.84, 0.22), (0.78, 0.45)), ((0.78, 0.22), (0.74, 0.44))):
        p.line(a, b, CARBON, 0.03, True)                                                           # wishbones
    for a, b in (((0.12, 0.26), (0.16, 0.42)), ((0.24, 0.26), (0.24, 0.40))):
        p.line(a, b, CARBON, 0.03, True)
    p.poly([(0.18, 0.30), (0.62, 0.22), (0.62, 0.78), (0.18, 0.70)], CARBON)                        # floor
    p.rr(0.0, 0.10, 0.10, 0.90, CARBON, 0.03)                                                      # rear wing
    p.rr(0.015, 0.14, 0.075, 0.86, trim_col if trim == "wing" else col, 0.02)
    front = trim_col if trim == "nose" else col
    p.poly([(0.89, 0.03), (0.99, 0.07), (1.0, 0.5), (0.99, 0.93), (0.89, 0.97)], CARBON)            # front wing
    p.poly([(0.905, 0.07), (0.975, 0.10), (0.975, 0.40), (0.905, 0.40)], front, True)
    p.poly([(0.06, 0.40), (0.22, 0.34), (0.32, 0.22), (0.44, 0.19), (0.57, 0.22), (0.64, 0.34), (0.70, 0.40),
            (0.97, 0.455), (0.985, 0.5), (0.97, 0.545), (0.70, 0.60), (0.64, 0.66), (0.57, 0.78), (0.44, 0.81),
            (0.32, 0.78), (0.22, 0.66), (0.06, 0.60)], col)
    p.poly([(0.34, 0.24), (0.44, 0.215), (0.56, 0.24), (0.61, 0.33), (0.34, 0.33)], _sh(col, 0.72), True)
    p.poly([(0.53, 0.235), (0.575, 0.25), (0.615, 0.33), (0.56, 0.33)], (14, 14, 18), True)         # inlets
    p.poly([(0.08, 0.455), (0.36, 0.41), (0.40, 0.5), (0.36, 0.59), (0.08, 0.545)], dark)           # engine cover
    p.poly([(0.10, 0.485), (0.34, 0.47), (0.34, 0.53), (0.10, 0.515)], _sh(col, 0.4))
    if trim == "nose":
        p.poly([(0.80, 0.425), (0.97, 0.455), (0.985, 0.5), (0.97, 0.545), (0.80, 0.575)], trim_col)
    else:
        p.poly([(0.62, 0.42), (0.96, 0.47), (0.96, 0.485), (0.62, 0.455)], lite)                    # highlight
    if trim == "stripe":
        p.poly([(0.62, 0.47), (0.975, 0.488), (0.975, 0.512), (0.62, 0.53)], trim_col)
    elif trim == "twin":
        p.poly([(0.36, 0.25), (0.54, 0.25), (0.54, 0.29), (0.36, 0.29)], trim_col, True)
        p.poly([(0.64, 0.43), (0.94, 0.47), (0.94, 0.485), (0.64, 0.455)], trim_col, True)
    elif trim == "band":
        p.poly([(0.62, 0.36), (0.68, 0.40), (0.68, 0.60), (0.62, 0.64)], trim_col)
    p.ell(0.385, 0.35, 0.60, 0.65, (10, 10, 14))                                                   # cockpit
    p.ell(0.40, 0.37, 0.585, 0.63, GLASS)
    p.ell(0.43, 0.395, 0.535, 0.605, WHITE)                                                        # helmet
    p.ell(0.47, 0.42, 0.54, 0.58, trim_col)
    p.ell(0.50, 0.44, 0.545, 0.56, (30, 34, 50))                                                   # visor
    pygame.draw.arc(p.s, CARBON, pygame.Rect(M + 0.44 * p.L, M + 0.355 * p.W, 0.18 * p.L, 0.29 * p.W),
                    -1.25, 1.25, max(2, int(p.W * 0.04)))                                           # halo
    p.line((0.60, 0.5), (0.66, 0.5), CARBON, 0.035)
    p.line((0.60, 0.33), (0.62, 0.27), CARBON, 0.02, True)                                         # mirrors
    p.rr(0.61, 0.25, 0.64, 0.29, col, 0.01, True)
    p.number(number, 0.74, 0.5, 0.075)
    p.rr(0.035, 0.47, 0.055, 0.53, (255, 60, 60), 0.01)                                            # rain light


def draw(style: str, colour, length: float, width: float, trim: str, trim_colour, number=None) -> pygame.Surface:
    pen = _Pen(length, width)
    (_gt3 if style == "gt3" else _formula)(pen, tuple(colour), trim, tuple(trim_colour), number)
    return pen.done()
