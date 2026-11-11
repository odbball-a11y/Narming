"""Drawing: fixed overhead camera, procedural track, cars and HUD.

Everything is drawn with pygame primitives; there are no image files.
"""
from __future__ import annotations

import math

import numpy as np
import pygame

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


def make_car_sprite(colour, pixels_per_unit: float) -> pygame.Surface:
    """A little open-wheel racer pointing right (+x), drawn large for rotation."""
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
    rect(0.0, 0.10, 0.10, 0.90, dark, 0.04)               # rear wing
    rect(0.90, 0.06, 1.0, 0.94, dark, 0.04)               # front wing
    rect(0.08, 0.22, 0.94, 0.78, colour, 0.25)            # body
    rect(0.30, 0.34, 0.80, 0.66, dark, 0.14)              # shadow line
    rect(0.52, 0.30, 0.94, 0.70, colour, 0.18)            # nose
    rect(0.36, 0.36, 0.54, 0.64, (20, 20, 30), 0.12)      # cockpit
    pygame.draw.circle(surf, (250, 250, 250),
                       (int(ox + 0.44 * length), int(oy + 0.5 * width)), int(0.11 * width))  # helmet
    rect(0.56, 0.46, 0.92, 0.54, (250, 250, 250), 0.02)   # stripe
    return surf


def lerp_angle(a: float, b: float, t: float) -> float:
    d = (b - a + math.pi) % (2.0 * math.pi) - math.pi
    return a + d * t


class RaceRenderer:
    def __init__(self, track: Track, size: tuple[int, int]):
        pygame.font.init()
        self.track = track
        self.camera = Camera(size)
        self._build()

    def resize(self, size: tuple[int, int]) -> None:
        self.camera.resize(size)
        self._build()

    def _build(self) -> None:
        cam = self.camera
        self.track_surface = render_track(self.track, cam)
        self.skid_layer = pygame.Surface(cam.size, pygame.SRCALPHA)
        self.sprites = [make_car_sprite(c, cam.scale) for c in CAR_COLOURS]
        self.sprite_zoom = cam.scale * tuning.CAR_LENGTH / (self.sprites[0].get_width() - 4)
        unit = cam.scale
        self.font_big = pygame.font.Font(None, max(14, int(unit * 5.2)))
        self.font = pygame.font.Font(None, max(12, int(unit * 3.4)))
        self.font_small = pygame.font.Font(None, max(10, int(unit * 2.4)))

    def clear_skids(self) -> None:
        self.skid_layer.fill((0, 0, 0, 0))

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

    def draw_world(self, screen: pygame.Surface, world, alpha: float = 1.0) -> None:
        """`alpha` in 0..1 blends each car from its previous tick to its current one."""
        cam = self.camera
        screen.blit(self.track_surface, (0, 0))
        screen.blit(self.skid_layer, (0, 0))
        for i, car in enumerate(world.cars):
            x = car.prev_x + (car.x - car.prev_x) * alpha
            y = car.prev_y + (car.y - car.prev_y) * alpha
            heading = lerp_angle(car.prev_heading, car.heading, alpha)
            sx, sy = cam.to_screen(x, y)
            # soft shadow
            shadow = pygame.Surface((int(cam.scale * 4), int(cam.scale * 4)), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect().inflate(-cam.scale, -cam.scale * 1.6))
            shadow = pygame.transform.rotate(shadow, -math.degrees(heading))
            screen.blit(shadow, shadow.get_rect(center=(sx + cam.scale * 0.25, sy + cam.scale * 0.35)))
            sprite = self.sprites[world.slots[i] % len(self.sprites)]
            image = pygame.transform.rotozoom(sprite, -math.degrees(heading), self.sprite_zoom)
            screen.blit(image, image.get_rect(center=(sx, sy)))

    def text(self, screen, font, string, colour, pos, anchor="topleft") -> pygame.Rect:
        img = font.render(string, True, colour)
        rect = img.get_rect(**{anchor: pos})
        screen.blit(img, rect)
        return rect

    def draw_hud(self, screen: pygame.Surface, world, focus: int = 0, hint: str = "") -> None:
        cam = self.camera
        u = cam.scale
        strip = pygame.Rect(cam.ox, cam.oy, WORLD_W * u, HUD_H * u)
        pygame.draw.rect(screen, C_HUD_BG, strip)
        pygame.draw.line(screen, C_HUD_ACCENT, strip.bottomleft, strip.bottomright, max(1, int(u * 0.3)))
        car = world.cars[focus]
        colour = CAR_COLOURS[world.slots[focus] % len(CAR_COLOURS)]
        top = strip.top + u * 1.2
        low = strip.top + u * 4.4

        def field(x_units, label, value, value_colour=C_HUD_TEXT):
            x = strip.left + x_units * u
            self.text(screen, self.font_small, label, C_HUD_DIM, (x, top))
            self.text(screen, self.font_big, value, value_colour, (x, low))

        self.text(screen, self.font_small, self.track.name.upper(), C_HUD_ACCENT, (strip.left + 3 * u, top))
        self.text(screen, self.font_big, CAR_NAMES[world.slots[focus] % 4], colour, (strip.left + 3 * u, low))
        lap_now = min(car.laps + 1, world.laps)
        field(30, "LAP", f"{lap_now}/{world.laps}")
        current = car.finish_time if car.finished else world.time - car.lap_start_time
        field(48, "TIME" if not car.finished else "RACE", format_time(current))
        field(78, "LAST", format_time(car.last_lap))
        field(108, "BEST", format_time(car.best_lap), C_HUD_ACCENT)
        field(138, "SPEED", f"{int(round(car.speed * 6))}")
        if hint:
            self.text(screen, self.font_small, hint, C_HUD_DIM,
                      (cam.ox + WORLD_W * u / 2, cam.oy + (WORLD_H - 1.0) * u), "midbottom")

    def draw_debug(self, screen, world, focus: int = 0) -> None:
        car = world.cars[focus]
        cam = self.camera
        lines = [
            f"forward {car.forward_speed:6.2f}   slip {car.slip:5.2f} {'SLIDING' if car.sliding else ''}",
            f"steer {car.steering:+.2f}  throttle {car.throttle:.2f}  brake {car.brake:.2f}",
            f"s {car.s:6.1f}  lateral {car.lateral:+5.2f}  {'grass' if car.surface else 'tarmac'}",
            f"next gate {car.next_checkpoint}  tick {world.tick}",
        ]
        y = cam.oy + (HUD_H + 1.5) * cam.scale
        for line in lines:
            rect = self.text(screen, self.font_small, line, (255, 255, 255), (cam.ox + 2 * cam.scale, y))
            y = rect.bottom + 2
