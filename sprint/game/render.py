"""Drawing: fixed overhead camera, procedural track, cars and HUD.

Everything is drawn with pygame primitives; there are no image files.
"""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

from ai import livery as liv

from sim import tuning
from sim.track import Track

WORLD_W = 160.0
WORLD_H = 90.0
HUD_H = 11.0          # world units reserved at the top of the screen

# 1980s arcade palette
C_BACKDROP = (26, 18, 54)
C_BACKDROP_GRID = (48, 30, 92)
C_GRASS = (38, 168, 74)
C_GRASS_DARK = (30, 146, 64)
C_TARMAC = (74, 74, 90)
C_LINE = (240, 240, 240)
C_KERB_A = (232, 48, 56)
C_KERB_B = (245, 245, 245)
C_WALL_A = (255, 214, 10)
C_WALL_B = (20, 20, 28)
C_HUD_BG = (12, 8, 28)
C_HUD_TEXT = (255, 255, 255)
C_HUD_DIM = (150, 140, 200)
C_HUD_ACCENT = (255, 214, 10)
CAR_COLOURS = [(236, 52, 60), (48, 140, 255), (255, 214, 10), (60, 220, 110)]
CAR_NAMES = ["RED", "BLUE", "YELLOW", "GREEN"]
PLACES = ["1ST", "2ND", "3RD", "4TH", "5TH", "6TH", "7TH", "8TH"]
C_PANEL = (20, 14, 44)
C_PINK = (255, 64, 160)
C_CYAN = (64, 220, 255)


def format_time(seconds) -> str:
    if seconds is None:
        return "--:--.---"
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:06.3f}"


class Camera:
    """Maps the fixed 160 x 90 world onto the window, letterboxed."""

    def __init__(self, size: tuple[int, int]):
        self.resize(size)

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        w, h = size
        self.scale = min(w / WORLD_W, h / WORLD_H)
        self.ox = (w - WORLD_W * self.scale) / 2.0
        self.oy = (h - WORLD_H * self.scale) / 2.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale

    def points(self, pts: np.ndarray, factor: float = 1.0) -> list:
        out = np.empty_like(pts)
        out[:, 0] = (self.ox + pts[:, 0] * self.scale) * factor
        out[:, 1] = (self.oy + pts[:, 1] * self.scale) * factor
        return out.tolist()


def _loop_area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return abs(float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) / 2.0)


def render_track(track: Track, camera: Camera) -> pygame.Surface:
    """Paint the whole circuit once; the result is blitted every frame."""
    ss = 2  # supersample, then smooth-scale down, for clean edges
    w, h = camera.size
    big = pygame.Surface((w * ss, h * ss))
    big.fill(C_BACKDROP)
    px = camera.scale * ss  # pixels per world unit on the big surface

    # Backdrop grid
    step = 5.0
    gx = 0.0
    while gx <= WORLD_W:
        x = (camera.ox + gx * camera.scale) * ss
        pygame.draw.line(big, C_BACKDROP_GRID, (x, 0), (x, h * ss), ss)
        gx += step
    gy = 0.0
    while gy <= WORLD_H:
        y = (camera.oy + gy * camera.scale) * ss
        pygame.draw.line(big, C_BACKDROP_GRID, (0, y), (w * ss, y), ss)
        gy += step

    def loops(a: np.ndarray, b: np.ndarray):
        return (a, b) if _loop_area(a) >= _loop_area(b) else (b, a)

    wall_w = 0.9
    off = (track.limit + wall_w)[:, None]
    band_out, band_in = loops(track.center - track.normal * off, track.center + track.normal * off)
    grass_out, grass_in = loops(track.left_wall, track.right_wall)
    road_out, road_in = loops(track.left_edge, track.right_edge)

    def fill(pts, colour):
        pygame.draw.polygon(big, colour, camera.points(pts, ss))

    # Nested fills from the outside in, then back out through the infield.
    fill(band_out, C_WALL_B)
    fill(grass_out, C_GRASS)
    fill(road_out, C_TARMAC)
    fill(road_in, C_GRASS)
    fill(grass_in, C_WALL_B)
    fill(band_in, C_BACKDROP)

    # Mown stripes on the grass: darker bands across the verge.
    stripe = max(2, int(round(3.0 / track.ds)))
    for wall, edge in ((track.left_wall, track.left_edge), (track.right_wall, track.right_edge)):
        sw = camera.points(wall, ss)
        se = camera.points(edge, ss)
        for i in range(0, track.n, stripe * 2):
            j = min(i + stripe, track.n - 1)
            pygame.draw.polygon(big, C_GRASS_DARK, [sw[i], sw[j], se[j], se[i]])

    # Barrier: yellow/black blocks.
    block = max(2, int(round(2.0 / track.ds)))
    for sign in (-1.0, 1.0):
        inner = camera.points(track.center + sign * track.normal * track.limit[:, None], ss)
        outer = camera.points(track.center + sign * track.normal * off, ss)
        for i in range(0, track.n, block * 2):
            idx = [(i + k) % track.n for k in range(block + 1)]
            poly = [inner[k] for k in idx] + [outer[k] for k in reversed(idx)]
            pygame.draw.polygon(big, C_WALL_A, poly)

    # Road edges: white line, red/white kerbs through the corners.
    kerb_w = 0.7
    kerb = max(2, int(round(1.5 / track.ds)))
    curv = np.abs(track.curvature)
    for sign, edge in ((-1.0, track.left_edge), (1.0, track.right_edge)):
        pts = camera.points(edge, ss)
        pygame.draw.lines(big, C_LINE, True, pts, max(2, int(px * 0.3)))
        inner = camera.points(edge - sign * track.normal * kerb_w, ss)
        for i in range(0, track.n, kerb):
            if curv[i] < 0.045:
                continue
            idx = [(i + k) % track.n for k in range(kerb + 1)]
            poly = [pts[k] for k in idx] + [inner[k] for k in reversed(idx)]
            colour = C_KERB_A if (i // kerb) % 2 == 0 else C_KERB_B
            pygame.draw.polygon(big, colour, poly)

    # Dashed centre line.
    centre = camera.points(track.center, ss)
    dash = max(2, int(round(2.0 / track.ds)))
    for i in range(0, track.n, dash * 3):
        j = (i + dash) % track.n
        if j > i:
            pygame.draw.line(big, (120, 120, 136), centre[i], centre[j], max(1, int(px * 0.18)))

    # Grid boxes.
    for gx, gy, heading in track.grid:
        c, s = math.cos(heading), math.sin(heading)
        front = tuning.CAR_LENGTH * 0.65
        half = tuning.CAR_WIDTH * 0.8
        corners = [(front, -half), (front, half)]
        line = [camera.to_screen(gx + c * a - s * b, gy + s * a + c * b) for a, b in corners]
        line = [(x * ss, y * ss) for x, y in line]
        pygame.draw.line(big, C_LINE, line[0], line[1], max(2, int(px * 0.25)))

    # Chequered start/finish line across the tarmac.
    idx = track.checkpoint_indices[0]
    cx, cy = track.center[idx]
    tx, ty = track.tangent[idx]
    nx, ny = track.normal[idx]
    hw = track.half_width[idx]
    size = 0.75
    cols = int(math.ceil(2 * hw / size))
    for row in range(2):
        for col in range(cols):
            a0 = -hw + col * size
            a1 = min(a0 + size, hw)
            b0 = (row - 1) * size
            b1 = b0 + size
            quad = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
            poly = []
            for a, b in quad:
                x, y = camera.to_screen(cx + nx * a + tx * b, cy + ny * a + ty * b)
                poly.append((x * ss, y * ss))
            colour = (245, 245, 245) if (row + col) % 2 == 0 else (16, 16, 20)
            pygame.draw.polygon(big, colour, poly)

    return pygame.transform.smoothscale(big, (w, h))


def make_car_sprite(colour, pixels_per_unit: float, trim: str = "stripe",
                    trim_colour=(250, 250, 250)) -> pygame.Surface:
    """A little open-wheel racer pointing right (+x), drawn large for rotation.

    `trim` is the racer's defining feature (see ai/livery.py): stripe, twin
    stripes, a coloured nose, a coloured rear wing or a band across the body."""
    k = max(pixels_per_unit, 4.0) * 3.0   # oversample; rotozoom scales it down
    length = tuning.CAR_LENGTH * k
    width = tuning.CAR_WIDTH * k
    surf = pygame.Surface((int(length) + 4, int(width) + 4), pygame.SRCALPHA)
    ox, oy = 2, 2
    dark = tuple(int(c * 0.55) for c in colour)

    def rect(x0, y0, x1, y1, col, radius=0.0):
        r = pygame.Rect(ox + x0 * length, oy + y0 * width, (x1 - x0) * length, (y1 - y0) * width)
        pygame.draw.rect(surf, col, r, border_radius=int(radius * width))

    tyre = (18, 18, 22)
    for x0, x1 in ((0.06, 0.28), (0.66, 0.86)):          # rear, front tyres
        rect(x0, 0.0, x1, 0.24, tyre, 0.06)
        rect(x0, 0.76, x1, 1.0, tyre, 0.06)
    rect(0.0, 0.10, 0.10, 0.90, trim_colour if trim == "wing" else dark, 0.04)    # rear wing
    rect(0.90, 0.06, 1.0, 0.94, dark, 0.04)               # front wing
    rect(0.05, 0.19, 0.97, 0.81, (245, 245, 245), 0.27)   # light rim, so any colour stands out
    rect(0.08, 0.22, 0.94, 0.78, colour, 0.25)            # body
    rect(0.30, 0.34, 0.80, 0.66, dark, 0.14)              # shadow line
    rect(0.52, 0.30, 0.94, 0.70, colour, 0.18)            # nose
    rect(0.36, 0.36, 0.54, 0.64, (20, 20, 30), 0.12)      # cockpit
    pygame.draw.circle(surf, (250, 250, 250),
                       (int(ox + 0.44 * length), int(oy + 0.5 * width)), int(0.11 * width))  # helmet
    if trim == "stripe":
        rect(0.56, 0.46, 0.92, 0.54, trim_colour, 0.02)
    elif trim == "twin":
        rect(0.12, 0.36, 0.40, 0.42, trim_colour, 0.02)
        rect(0.12, 0.58, 0.40, 0.64, trim_colour, 0.02)
        rect(0.56, 0.38, 0.92, 0.44, trim_colour, 0.02)
        rect(0.56, 0.56, 0.92, 0.62, trim_colour, 0.02)
    elif trim == "nose":
        rect(0.80, 0.30, 0.94, 0.70, trim_colour, 0.18)
        rect(0.90, 0.06, 1.0, 0.94, trim_colour, 0.04)
    elif trim == "band":
        rect(0.58, 0.23, 0.68, 0.77, trim_colour, 0.02)
    return surf


def lerp_angle(a: float, b: float, t: float) -> float:
    d = (b - a + math.pi) % (2.0 * math.pi) - math.pi
    return a + d * t


class UI:
    """Fonts and text helpers scaled to the window (shared by all screens)."""

    def __init__(self, size: tuple[int, int]):
        pygame.font.init()
        self.camera = Camera(size)
        u = self.camera.scale
        self.unit = u
        self.fonts = {
            "title": pygame.font.Font(None, max(20, int(u * 13))),
            "huge": pygame.font.Font(None, max(20, int(u * 22))),
            "big": pygame.font.Font(None, max(14, int(u * 5.6))),
            "mid": pygame.font.Font(None, max(12, int(u * 3.9))),
            "small": pygame.font.Font(None, max(10, int(u * 2.7))),
        }

    def px(self, x: float, y: float) -> tuple[float, float]:
        return self.camera.to_screen(x, y)

    def rect(self, x: float, y: float, w: float, h: float) -> pygame.Rect:
        sx, sy = self.px(x, y)
        return pygame.Rect(int(sx), int(sy), int(w * self.unit), int(h * self.unit))

    def text(self, screen, font: str, string: str, colour, x: float, y: float,
             anchor: str = "topleft", shadow: bool = False) -> pygame.Rect:
        """Draw text at world-unit position (x, y)."""
        f = self.fonts[font]
        pos = self.px(x, y)
        if shadow:
            img = f.render(string, True, (0, 0, 0))
            off = max(1, int(self.unit * 0.3))
            screen.blit(img, img.get_rect(**{anchor: (pos[0] + off, pos[1] + off)}))
        img = f.render(string, True, colour)
        rect = img.get_rect(**{anchor: pos})
        screen.blit(img, rect)
        return rect

    def dim(self, screen, alpha: int = 150) -> None:
        veil = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        veil.fill((8, 4, 24, alpha))
        screen.blit(veil, (0, 0))

    def panel(self, screen, x, y, w, h, border=C_HUD_ACCENT) -> pygame.Rect:
        r = self.rect(x, y, w, h)
        pygame.draw.rect(screen, C_PANEL, r, border_radius=int(self.unit * 1.2))
        pygame.draw.rect(screen, border, r, max(2, int(self.unit * 0.35)), border_radius=int(self.unit * 1.2))
        return r

    def chart(self, screen, x, y, w, h, title: str, xs: list, series: list,
              fmt="{:.1f}", marker=None, floor=None) -> None:
        """Line chart.  `series` is [(label, colour, values)], values aligned
        with `xs` and possibly None.  `marker` = (x value, label) draws a
        vertical line.  `floor` forces the bottom of the y axis."""
        self.panel(screen, x, y, w, h, border=(70, 56, 120))
        self.text(screen, "small", title, C_HUD_TEXT, x + 2, y + 1.2)
        lx = x + 2
        for label, colour, _ in series:
            r = self.text(screen, "small", label, colour, lx, y + 3.9)
            lx += r.width / self.unit + 2.5
        values = [v for _, _, vals in series for v in vals if v is not None]
        if not values or len(xs) < 1:
            self.text(screen, "small", "no data yet", C_HUD_DIM, x + w / 2, y + h / 2, "center")
            return
        lo = min(values) if floor is None else floor
        hi = max(values)
        if hi - lo < 1e-9:
            hi = lo + 1.0
        pad = (hi - lo) * 0.08
        lo, hi = (lo - pad if floor is None else lo), hi + pad
        left, right, top, bottom = x + 9, x + w - 2.5, y + 8.5, y + h - 4.5
        x0, x1 = xs[0], max(xs[-1], xs[0] + 1)

        def pos(xv, yv):
            return self.px(left + (xv - x0) / (x1 - x0) * (right - left),
                           bottom - (yv - lo) / (hi - lo) * (bottom - top))

        for frac in (0.0, 0.5, 1.0):
            yv = lo + (hi - lo) * frac
            a, b = pos(x0, yv), pos(x1, yv)
            pygame.draw.line(screen, (56, 44, 100), a, b)
            self.text(screen, "small", fmt.format(yv), C_HUD_DIM, left - 1, bottom - (bottom - top) * frac,
                      "midright")
        self.text(screen, "small", str(x0), C_HUD_DIM, left, bottom + 0.6, "midtop")
        self.text(screen, "small", f"gen {x1}", C_HUD_DIM, right, bottom + 0.6, "topright")
        if marker and x0 <= marker[0] <= x1:
            a, b = pos(marker[0], lo), pos(marker[0], hi)
            pygame.draw.line(screen, C_HUD_ACCENT, a, b)
            mx = left + (marker[0] - x0) / (x1 - x0) * (right - left)
            if mx > (left + right) / 2:     # keep the label inside the chart
                self.text(screen, "small", marker[1], C_HUD_ACCENT, mx - 0.6, bottom - 2.6, "topright")
            else:
                self.text(screen, "small", marker[1], C_HUD_ACCENT, mx + 0.6, bottom - 2.6)
        for label, colour, vals in reversed(series):
            pts = [pos(xv, v) for xv, v in zip(xs, vals) if v is not None]
            if len(pts) > 1:
                pygame.draw.lines(screen, colour, False, pts, max(2, int(self.unit * 0.35)))
            elif pts:
                pygame.draw.circle(screen, colour, pts[0], max(2, int(self.unit * 0.5)))

    def backdrop(self, screen) -> None:
        """Plain menu background: night-sky grid with a sunset stripe band."""
        screen.fill(C_BACKDROP)
        u = self.unit
        cam = self.camera
        for i in range(0, 161, 5):
            x = cam.ox + i * u
            pygame.draw.line(screen, C_BACKDROP_GRID, (x, cam.oy), (x, cam.oy + WORLD_H * u))
        for j in range(0, 91, 5):
            y = cam.oy + j * u
            pygame.draw.line(screen, C_BACKDROP_GRID, (cam.ox, y), (cam.ox + WORLD_W * u, y))


class RaceRenderer:
    def __init__(self, track: Track, size: tuple[int, int]):
        self.track = track
        self.ui = UI(size)
        self.camera = self.ui.camera
        self._build()

    def _build(self) -> None:
        cam = self.camera
        self.track_surface = render_track(self.track, cam)
        self.skid_layer = pygame.Surface(cam.size, pygame.SRCALPHA)
        self.sprite_cache: dict = {}
        self.sprite_zoom = cam.scale * tuning.CAR_LENGTH / (self.sprite_for(None).get_width() - 4)
        size = int(cam.scale * 5)
        self.shadow = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 70),
                            pygame.Rect(size * 0.08, size * 0.28, size * 0.84, size * 0.44))
        # Smoke puffs, pre-drawn at a few ages (bigger and fainter as they age).
        self.puffs = []
        for k in range(6):
            radius = max(2, int(cam.scale * (0.5 + 0.28 * k)))
            puff = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            shade = 70 + 18 * k
            pygame.draw.circle(puff, (shade, shade, shade + 6, 150 - 22 * k), (radius, radius), radius)
            self.puffs.append(puff)
        self.smoke: list[list] = []          # [x, y, vx, vy, age]
        self.fx_random = random.Random(7)    # visual only, never touches the sim
        # Ghost-pack sprites: translucent runner, bright leader, faded retiree.
        self.ghost = make_car_sprite((120, 225, 255), cam.scale)
        self.ghost.set_alpha(120)
        self.ghost_leader = make_car_sprite((255, 214, 10), cam.scale)
        self.ghost_out = make_car_sprite((150, 60, 80), cam.scale)
        self.ghost_out.set_alpha(70)

    def sprite_for(self, livery: dict | None):
        """The car sprite for a livery (cached); None = a plain red car."""
        if livery is None:
            livery = {"colour": "red", "trim": "stripe", "trim_colour": "white"}
        key = (livery["colour"], livery.get("trim", "stripe"), livery.get("trim_colour", "white"))
        if key not in self.sprite_cache:
            self.sprite_cache[key] = make_car_sprite(liv.rgb(key[0]), self.camera.scale, key[1], liv.trim_rgb(livery))
        return self.sprite_cache[key]

    def clear_skids(self) -> None:
        self.skid_layer.fill((0, 0, 0, 0))
        self.smoke = []

    def on_tick(self, world) -> None:
        """Visual effects that build up over time; call once per sim tick."""
        self.add_skid_marks(world)
        rnd = self.fx_random
        for car in world.cars:
            # Damaged cars smoke: the worse the damage, the thicker.
            if car.damage > 0.12 and rnd.random() < car.damage * 0.3:
                c, s = math.cos(car.heading), math.sin(car.heading)
                self.smoke.append([car.x - c * 1.6, car.y - s * 1.6,
                                   car.vx * 0.25 + rnd.uniform(-1.5, 1.5),
                                   car.vy * 0.25 + rnd.uniform(-1.5, 1.5) - 1.0, 0.0])
        dt = tuning.DT
        for p in self.smoke:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] += dt
        if self.smoke and self.smoke[0][4] > 0.9:
            self.smoke = [p for p in self.smoke if p[4] <= 0.9]

    def draw_effects(self, screen, world, poses) -> None:
        """Slipstream streaks and smoke, drawn over the cars."""
        cam = self.camera
        # A tow: dashes streaming from the lead car's tail to the car behind.
        for i, car in enumerate(world.cars):
            j = car.draft_source
            if car.draft <= 0.08 or j < 0 or car.finished:
                continue
            lx, ly, lh = poses[j]
            fx, fy, fh = poses[i]
            ax, ay = lx - math.cos(lh) * 2.2, ly - math.sin(lh) * 2.2
            bx, by = fx + math.cos(fh) * 2.0, fy + math.sin(fh) * 2.0
            dx, dy = bx - ax, by - ay
            dist = math.hypot(dx, dy)
            if dist < 0.5:
                continue
            nx, ny = -dy / dist, dx / dist
            phase = (world.tick * 0.035) % 1.0
            width = max(1, int(cam.scale * (0.18 + 0.25 * car.draft)))
            for lane in (-0.75, 0.0, 0.75):
                t = phase * 0.34 - 0.34
                while t < 1.0:
                    t0, t1 = max(t, 0.0), min(t + 0.17, 1.0)
                    if t1 > t0:
                        spread0 = lane * (0.6 + 0.8 * t0)
                        spread1 = lane * (0.6 + 0.8 * t1)
                        p0 = cam.to_screen(ax + dx * t0 + nx * spread0, ay + dy * t0 + ny * spread0)
                        p1 = cam.to_screen(ax + dx * t1 + nx * spread1, ay + dy * t1 + ny * spread1)
                        pygame.draw.line(screen, (190, 245, 255) if lane == 0.0 else (110, 215, 255),
                                         p0, p1, width)
                    t += 0.34
        for x, y, _, _, age in self.smoke:
            puff = self.puffs[min(int(age / 0.9 * len(self.puffs)), len(self.puffs) - 1)]
            screen.blit(puff, puff.get_rect(center=cam.to_screen(x, y)))

    def draw_pack(self, screen, world, alpha: float, leader: int) -> None:
        """A whole generation at once: translucent ghosts, the current leader
        in gold, retired drivers faded where they stopped."""
        cam = self.camera
        screen.blit(self.track_surface, (0, 0))
        cars = world.cars
        order = sorted(range(len(cars)), key=lambda i: (i == leader, not cars[i].retired))
        for i in order:
            car = cars[i]
            if car.retired:
                x, y, heading, sprite = car.x, car.y, car.heading, self.ghost_out
            else:
                x = car.prev_x + (car.x - car.prev_x) * alpha
                y = car.prev_y + (car.y - car.prev_y) * alpha
                heading = lerp_angle(car.prev_heading, car.heading, alpha)
                sprite = self.ghost_leader if i == leader else self.ghost
            image = pygame.transform.rotozoom(sprite, -math.degrees(heading), self.sprite_zoom)
            if sprite is not self.ghost_leader:
                image.set_alpha(sprite.get_alpha())
            screen.blit(image, image.get_rect(center=cam.to_screen(x, y)))

    # ------------------------------------------------------------- drawing

    def add_skid_marks(self, world) -> None:
        """Called once per sim tick: sliding cars leave rubber behind."""
        cam = self.camera
        width = max(1, int(cam.scale * 0.32))
        for car in world.cars:
            if not car.sliding:
                continue
            for side in (-1.0, 1.0):
                pts = []
                for x, y, h in ((car.prev_x, car.prev_y, car.prev_heading), (car.x, car.y, car.heading)):
                    c, s = math.cos(h), math.sin(h)
                    bx = -tuning.CAR_LENGTH * 0.32
                    by = side * tuning.CAR_WIDTH * 0.40
                    pts.append(cam.to_screen(x + c * bx - s * by, y + s * bx + c * by))
                pygame.draw.line(self.skid_layer, (20, 20, 24, 110), pts[0], pts[1], width)

    def draw_world(self, screen: pygame.Surface, world, alpha: float = 1.0, liveries=None) -> None:
        """`alpha` in 0..1 blends each car from its previous tick to its current one."""
        cam = self.camera
        screen.blit(self.track_surface, (0, 0))
        screen.blit(self.skid_layer, (0, 0))
        poses = []
        for car in world.cars:
            x = car.prev_x + (car.x - car.prev_x) * alpha
            y = car.prev_y + (car.y - car.prev_y) * alpha
            poses.append((x, y, lerp_angle(car.prev_heading, car.heading, alpha)))
        for x, y, heading in poses:
            sx, sy = cam.to_screen(x, y)
            shadow = pygame.transform.rotate(self.shadow, -math.degrees(heading))
            screen.blit(shadow, shadow.get_rect(center=(sx + cam.scale * 0.3, sy + cam.scale * 0.4)))
        # Parked (finished) cars first and faded: they are no longer solid.
        for i in sorted(range(len(poses)), key=lambda k: not world.cars[k].retired):
            x, y, heading = poses[i]
            sprite = self.sprite_for(liveries[i] if liveries else
                                     {"colour": liv.SLOT_COLOURS[world.slots[i] % 4], "trim": "stripe",
                                      "trim_colour": "white"})
            # Heavy cars are drawn bigger and light cars smaller.
            mass = world.cars[i].params.mass
            size = 1.12 if mass > 1.1 else 0.9 if mass < 0.9 else 1.0
            image = pygame.transform.rotozoom(sprite, -math.degrees(heading), self.sprite_zoom * size)
            if world.cars[i].retired:
                image.set_alpha(90)
            screen.blit(image, image.get_rect(center=cam.to_screen(x, y)))
        self.draw_effects(screen, world, poses)

    def draw_hud(self, screen: pygame.Surface, race, banner: str = "", liveries=None) -> None:
        """Top strip: a timing screen.  One row per car in race order (1st,
        2nd, ... down the left column, then the right), each with its colour,
        name, lap, the lap it is on (or its finishing time), last lap, best
        lap and damage.  The race's fastest lap so far is shown in pink."""
        ui = self.ui
        world = race.world
        strip = ui.rect(0, 0, WORLD_W, HUD_H)
        pygame.draw.rect(screen, C_HUD_BG, strip)
        pygame.draw.line(screen, C_HUD_ACCENT, strip.bottomleft, strip.bottomright, max(1, int(ui.unit * 0.3)))
        order = world.standings()
        per_column = max(2, (len(order) + 1) // 2)
        row_h = (HUD_H - 1.0) / per_column
        col_w = WORLD_W / 2.0
        laps = [c.best_lap for c in world.cars if c.best_lap]
        fastest = min(laps) if laps else None
        for place, i in enumerate(order):
            car = world.cars[i]
            slot = world.slots[i]
            look = liveries[i] if liveries else {"colour": liv.SLOT_COLOURS[slot % 4], "number": slot + 1}
            colour = liv.rgb(look["colour"])
            x0 = (place // per_column) * col_w + 1.0
            y = 0.5 + (place % per_column) * row_h
            ty = y + (row_h - 2.7) / 2.0                      # small text centred in the row
            if place % 2:
                pygame.draw.rect(screen, (30, 26, 52), ui.rect(x0 - 0.6, y, col_w - 0.8, row_h))
            ui.text(screen, "small", PLACES[place] if place < len(PLACES) else f"{place + 1}TH", colour, x0, ty)
            pygame.draw.rect(screen, colour, ui.rect(x0 + 6.0, y + 0.4, 1.2, row_h - 0.8))
            name = race.drivers[i].label.upper()[:15]
            towed = car.draft > 0.08 and not car.finished           # in a tow: the name turns cyan
            ui.text(screen, "small", name, C_CYAN if towed else C_HUD_TEXT, x0 + 8.4, ty)
            lap_now = min(car.laps + 1, world.laps)
            ui.text(screen, "small", "FIN" if car.finished else f"L{lap_now}/{world.laps}", C_HUD_ACCENT,
                    x0 + 30.0, ty)
            if car.finished:
                ui.text(screen, "small", format_time(car.finish_time), C_CYAN, x0 + 37.0, ty)
            else:
                ui.text(screen, "small", format_time(max(0.0, world.time - car.lap_start_time)), C_HUD_TEXT,
                        x0 + 37.0, ty)
            ui.text(screen, "small", "last", C_HUD_DIM, x0 + 47.0, ty)
            ui.text(screen, "small", format_time(car.last_lap), C_HUD_TEXT, x0 + 51.5, ty)
            ui.text(screen, "small", "best", C_HUD_DIM, x0 + 60.0, ty)
            best_colour = C_PINK if car.best_lap and car.best_lap == fastest else C_HUD_ACCENT
            ui.text(screen, "small", format_time(car.best_lap), best_colour, x0 + 64.5, ty)
            # Damage bar: green to red as the car is wrecked.
            bar = ui.rect(x0 + 73.0, y + row_h / 2.0 - 0.6, 5.0, 1.2)
            pygame.draw.rect(screen, (50, 44, 80), bar)
            if car.damage > 0.0:
                d = car.damage
                fill = pygame.Rect(bar.left, bar.top, max(1, int(bar.width * d)), bar.height)
                pygame.draw.rect(screen, (int(90 + 165 * min(1.0, d * 2)), int(220 - 180 * d), 60), fill)
            pygame.draw.rect(screen, C_HUD_DIM, bar, 1)
        pygame.draw.line(screen, C_HUD_DIM, ui.px(col_w, 0.6), ui.px(col_w, HUD_H - 0.6), 1)
        if banner:
            ui.text(screen, "small", banner, C_HUD_TEXT, WORLD_W / 2, WORLD_H - 0.8, "midbottom", shadow=True)

    def draw_countdown(self, screen, race) -> None:
        """Start lights and the 3-2-1-GO numerals."""
        ui = self.ui
        number = race.countdown_number
        go = number == 0 and race.world.time < 0.9
        if number == 0 and not go:
            return
        lit = 4 - number if number else 3
        cx, cy = WORLD_W / 2, 30.0
        ui.panel(screen, cx - 17, cy - 6.5, 34, 13, border=(60, 60, 80))
        for k in range(3):
            centre = ui.px(cx - 10 + k * 10, cy)
            if go:
                colour = (60, 240, 110)
            else:
                colour = (255, 48, 56) if k < lit else (60, 24, 32)
            pygame.draw.circle(screen, colour, centre, int(ui.unit * 3.6))
            pygame.draw.circle(screen, (0, 0, 0), centre, int(ui.unit * 3.6), max(1, int(ui.unit * 0.3)))
        ui.text(screen, "huge", "GO!" if go else str(number), (60, 240, 110) if go else C_HUD_ACCENT,
                cx, 52, "center", shadow=True)

    def draw_debug(self, screen, world, focus: int = 0) -> None:
        car = world.cars[focus]
        lines = [
            f"forward {car.forward_speed:6.2f}   slip {car.slip:5.2f} {'SLIDING' if car.sliding else ''}",
            f"steer {car.steering:+.2f}  throttle {car.throttle:.2f}  brake {car.brake:.2f}",
            f"s {car.s:6.1f}  lateral {car.lateral:+5.2f}  {'grass' if car.surface else 'tarmac'}",
            f"next gate {car.next_checkpoint}  tick {world.tick}",
        ]
        y = HUD_H + 1.5
        for line in lines:
            self.ui.text(screen, "small", line, (255, 255, 255), 2, y, shadow=True)
            y += 2.6
