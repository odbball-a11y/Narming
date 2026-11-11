"""Track geometry: a closed centreline spline with a width at every point.

Conventions (shared by the whole sim):

* World is 160 x 90 units, x to the right, y DOWN (same as the screen).
* Heading is the angle of the direction of travel, atan2(dy, dx).  Because y
  is down, a positive change of heading is a turn to the RIGHT on screen.
* "Right" of the track direction is the normal (-ty, tx).  Lateral offsets are
  positive to the right, curvature is positive in right-hand bends, and
  positive steering turns right, so all signs agree.

The centreline is resampled at a uniform spacing `ds` (about half a unit), so
"sample index" and "distance along the lap" convert by a multiplication.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

TRACK_DIR = Path(__file__).resolve().parent.parent / "tracks"

TARMAC = 0
GRASS = 1

_TARGET_DS = 0.5


def wrap_angle(a: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    return a


def _catmull_rom_closed(ctrl: np.ndarray, per_segment: int = 48) -> np.ndarray:
    """Dense samples of a closed uniform Catmull-Rom spline through `ctrl`.

    `ctrl` is (P, D); every column (x, y, width, ...) is interpolated alike.
    """
    p0 = np.roll(ctrl, 1, axis=0)
    p1 = ctrl
    p2 = np.roll(ctrl, -1, axis=0)
    p3 = np.roll(ctrl, -2, axis=0)
    t = (np.arange(per_segment) / per_segment)[None, :, None]
    p0, p1, p2, p3 = (p[:, None, :] for p in (p0, p1, p2, p3))
    out = 0.5 * (
        2.0 * p1
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t
    )
    return out.reshape(-1, ctrl.shape[1])


def _resample_closed(dense: np.ndarray, target_ds: float):
    """Resample a closed dense polyline at uniform arc length."""
    closed = np.vstack([dense, dense[:1]])
    seg = np.hypot(np.diff(closed[:, 0]), np.diff(closed[:, 1]))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    length = float(cum[-1])
    n = int(round(length / target_ds))
    s = np.arange(n) * (length / n)
    cols = [np.interp(s, cum, closed[:, k]) for k in range(closed.shape[1])]
    return np.stack(cols, axis=1), length


class Track:
    """Immutable track geometry plus the queries drivers and physics need."""

    def __init__(self, data: dict):
        self.name: str = data["name"]
        self.key: str = data.get("key", self.name.lower())
        self.verge: float = float(data.get("verge", 3.0))
        self.default_laps: int = int(data.get("laps", 3))
        ctrl = np.asarray(data["points"], dtype=float)
        if ctrl.ndim != 2 or ctrl.shape[1] != 3 or len(ctrl) < 4:
            raise ValueError("track 'points' must be at least 4 rows of [x, y, width]")
        self.control_points = ctrl

        # Optional racing line: lateral offset (units, + = right) at each
        # control point.  Missing means "drive the centreline".
        rl = data.get("racing_line_offsets")
        rl_col = np.zeros(len(ctrl)) if rl is None else np.asarray(rl, dtype=float)
        if rl_col.shape != (len(ctrl),):
            raise ValueError("racing_line_offsets needs one value per control point")

        dense = _catmull_rom_closed(np.column_stack([ctrl, rl_col]))
        samples, length = _resample_closed(dense, _TARGET_DS)
        # Second pass so the spacing is uniform along the final polyline.
        samples, length = _resample_closed(samples, _TARGET_DS)

        self.n: int = len(samples)
        self.length: float = length
        self.ds: float = length / self.n

        center = samples[:, :2]
        tangent = np.roll(center, -1, axis=0) - np.roll(center, 1, axis=0)
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
        normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])  # points right
        heading = np.arctan2(tangent[:, 1], tangent[:, 0])
        dh = np.roll(heading, -1) - np.roll(heading, 1)
        dh = (dh + np.pi) % (2 * np.pi) - np.pi
        curvature = dh / (2.0 * self.ds)
        # Light smoothing: removes resampling noise, keeps corner shape.
        kernel = np.ones(7) / 7.0
        padded = np.concatenate([curvature[-3:], curvature, curvature[:3]])
        curvature = np.convolve(padded, kernel, mode="valid")

        half_w = samples[:, 2] / 2.0
        limit = half_w + self.verge  # distance from centreline to the barrier

        self.center = center
        self.tangent = tangent
        self.normal = normal
        self.heading = heading
        self.curvature = curvature
        self.half_width = half_w
        self.limit = limit
        self.right_edge = center + normal * half_w[:, None]
        self.left_edge = center - normal * half_w[:, None]
        self.right_wall = center + normal * limit[:, None]
        self.left_wall = center - normal * limit[:, None]
        self.racing_offset = samples[:, 3]
        self.racing_line = center + normal * self.racing_offset[:, None]

        # Plain Python lists for the per-tick hot path (much faster than
        # indexing NumPy arrays one element at a time).
        self._px = center[:, 0].tolist()
        self._py = center[:, 1].tolist()
        self._tx = tangent[:, 0].tolist()
        self._ty = tangent[:, 1].tolist()
        self._hw = half_w.tolist()
        self._lim = limit.tolist()
        self._heading = heading.tolist()
        self._curv = curvature.tolist()
        self._rlx = self.racing_line[:, 0].tolist()
        self._rly = self.racing_line[:, 1].tolist()

        # Boundary segments for ray casts: (M, 2) starts and (M, 2) deltas.
        self._ray_sets = {}
        for name, loops in (
            ("barrier", (self.left_wall, self.right_wall)),
            ("tarmac", (self.left_edge, self.right_edge)),
        ):
            a = np.vstack(loops)
            b = np.vstack([np.roll(loop, -1, axis=0) for loop in loops])
            self._ray_sets[name] = (a, b - a)

        # Checkpoints: gates across the full width (barrier to barrier),
        # evenly spaced.  Gate 0 is the start/finish line.
        count = int(data.get("checkpoints", 12))
        self.checkpoint_indices = [int(round(k * self.n / count)) % self.n for k in range(count)]
        self.checkpoints = []
        for idx in self.checkpoint_indices:
            ax, ay = self.left_wall[idx]
            bx, by = self.right_wall[idx]
            self.checkpoints.append((float(ax), float(ay), float(bx), float(by),
                                     self._tx[idx], self._ty[idx]))

        # Start grid: two columns, staggered, behind the line.
        self.grid = []
        for slot in range(int(data.get("grid_slots", 4))):
            s = -(5.0 + 4.5 * slot)
            idx = int(round(s / self.ds)) % self.n
            lat = self._hw[idx] * 0.42 * (-1.0 if slot % 2 == 0 else 1.0)
            x = self._px[idx] - self._ty[idx] * lat
            y = self._py[idx] + self._tx[idx] * lat
            self.grid.append((x, y, self._heading[idx]))

    # ------------------------------------------------------------------ I/O

    @classmethod
    def load(cls, name_or_path) -> "Track":
        path = Path(name_or_path)
        if not path.suffix:
            path = TRACK_DIR / f"{name_or_path}.json"
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("key", path.stem)
        return cls(data)

    @staticmethod
    def available() -> list[str]:
        return sorted(p.stem for p in TRACK_DIR.glob("*.json"))

    # ------------------------------------------------------------ locating

    def nearest_index(self, x: float, y: float, hint: int | None = None) -> int:
        """Index of the nearest centreline sample.

        With `hint` (the car's index last tick) this walks along the track
        from there, which is fast and keeps a car attached to the piece of
        road it is on even where two sections run close together.  Without a
        hint it searches the whole lap.
        """
        if hint is None:
            d2 = (self.center[:, 0] - x) ** 2 + (self.center[:, 1] - y) ** 2
            return int(np.argmin(d2))
        px, py, n = self._px, self._py, self.n
        i = hint % n
        best = (px[i] - x) ** 2 + (py[i] - y) ** 2
        for step in (1, -1):
            moved = False
            for _ in range(n):
                j = (i + step) % n
                d2 = (px[j] - x) ** 2 + (py[j] - y) ** 2
                if d2 < best:
                    best, i, moved = d2, j, True
                else:
                    break
            if moved:
                break
        return i

    def frenet(self, x: float, y: float, idx: int) -> tuple[float, float]:
        """(progress along lap, lateral offset) of a point near sample `idx`.

        Progress is in [0, length).  Lateral offset is positive to the right
        of the direction of travel.
        """
        dx = x - self._px[idx]
        dy = y - self._py[idx]
        tx, ty = self._tx[idx], self._ty[idx]
        along = dx * tx + dy * ty
        lateral = -dx * ty + dy * tx
        return (idx * self.ds + along) % self.length, lateral

    def locate(self, x: float, y: float, hint: int | None = None):
        """Convenience: (index, progress, lateral offset)."""
        idx = self.nearest_index(x, y, hint)
        s, lat = self.frenet(x, y, idx)
        return idx, s, lat

    def index_at(self, s: float) -> int:
        return int(round(s / self.ds)) % self.n

    # ------------------------------------------------- queries by distance

    def point_at(self, s: float) -> tuple[float, float]:
        i = self.index_at(s)
        return self._px[i], self._py[i]

    def racing_line_point(self, s: float) -> tuple[float, float]:
        i = self.index_at(s)
        return self._rlx[i], self._rly[i]

    def heading_at(self, s: float) -> float:
        return self._heading[self.index_at(s)]

    def half_width_at(self, s: float) -> float:
        return self._hw[self.index_at(s)]

    def curvature_at(self, s: float) -> float:
        """Signed curvature (1/radius, + = right-hand bend) at distance s."""
        return self._curv[self.index_at(s)]

    def curvature_ahead(self, s: float, distance: float) -> float:
        """Signed curvature `distance` units further round the lap."""
        return self._curv[self.index_at(s + distance)]

    def heading_error(self, heading: float, s: float) -> float:
        """Car heading minus track direction, wrapped to (-pi, pi].

        Positive means the car points to the right of the track direction.
        """
        return wrap_angle(heading - self._heading[self.index_at(s)])

    def surface_at(self, idx: int, lateral: float) -> int:
        return TARMAC if abs(lateral) <= self._hw[idx] else GRASS

    # ------------------------------------------------------------ ray casts

    def raycasts(self, x: float, y: float, angles, max_dist: float = 60.0,
                 boundary: str = "barrier") -> np.ndarray:
        """Distance from (x, y) to the boundary along each world angle.

        `boundary` is "barrier" (the solid wall) or "tarmac" (edge of the
        road).  Rays that hit nothing within `max_dist` return `max_dist`.
        """
        a, d = self._ray_sets[boundary]
        angles = np.atleast_1d(np.asarray(angles, dtype=float))
        rx = np.cos(angles)[:, None]
        ry = np.sin(angles)[:, None]
        ox = a[None, :, 0] - x
        oy = a[None, :, 1] - y
        dx = d[None, :, 0]
        dy = d[None, :, 1]
        denom = rx * dy - ry * dx
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (ox * dy - oy * dx) / denom      # distance along the ray
            u = (ox * ry - oy * rx) / denom      # position along the segment
        hit = (denom != 0.0) & (t >= 0.0) & (u >= 0.0) & (u <= 1.0)
        t = np.where(hit, t, max_dist)
        return np.minimum(t.min(axis=1), max_dist)

    def raycast(self, x: float, y: float, angle: float, max_dist: float = 60.0,
                boundary: str = "barrier") -> float:
        return float(self.raycasts(x, y, [angle], max_dist, boundary)[0])

    # ----------------------------------------------------------- validation

    def report(self) -> dict:
        """Geometry sanity numbers (used by tests and the track tool)."""
        kmax = float(np.max(np.abs(self.curvature)))
        # The barrier offset curve stays clean only while limit < radius.
        tightness = float(np.max(np.abs(self.curvature) * self.limit))
        walls = np.vstack([self.left_wall, self.right_wall])
        return {
            "length": self.length,
            "samples": self.n,
            "min_radius": 1.0 / kmax if kmax > 0 else math.inf,
            "max_limit_over_radius": tightness,
            "bounds": (float(walls[:, 0].min()), float(walls[:, 1].min()),
                       float(walls[:, 0].max()), float(walls[:, 1].max())),
            "min_gap_between_sections": self._min_section_gap(),
        }

    def _min_section_gap(self) -> float:
        """Smallest free space between the barriers of two different pieces
        of road (negative means their verges overlap)."""
        c = self.center
        step = 4
        sub = c[::step]
        lim = self.limit[::step]
        d = np.hypot(sub[:, None, 0] - sub[None, :, 0], sub[:, None, 1] - sub[None, :, 1])
        idx = np.arange(len(sub))
        sep = np.abs(idx[:, None] - idx[None, :])
        sep = np.minimum(sep, len(sub) - sep) * step * self.ds
        # Only compare samples that are far apart along the lap.
        far = sep > 2.0 * (lim[:, None] + lim[None, :])
        gap = d - lim[:, None] - lim[None, :]
        return float(gap[far].min()) if far.any() else math.inf
