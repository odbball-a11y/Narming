"""The fastest laps ever driven on each track, by anyone (you included), and
what they teach.

Laps come from `sim.telemetry.LapRecorder` (every Race records them): the
game submits practice and championship laps, training submits its
champion's test laps.  Each track keeps its KEEP fastest laps overall plus
the fastest in each car weight, in `telemetry/<track>.json`, tagged with the
physics they were driven under (laps from other physics are set aside).

`reference(track, weight)` turns the best lap into "reference notes": for
every corner, how its apex speed, line and getting back on the power compare
with the ideal line, in the same three fields as a driver's own track notes.
Every AI driver sees its own notes plus these, so its notes become personal
tweaks on top of the proven lap.  `corner_report` gives the same numbers in
plain units (braking point, apex speed, apex line, power-on point) for the
telemetry screen.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np

from sim import tuning
from sim.telemetry import SPACING

from . import jsonio

PROJECT = Path(__file__).resolve().parent.parent
DIR = PROJECT / "telemetry"
KEEP = 5
WEIGHTS = ("light", "medium", "heavy")
POWER_ON = 0.8          # throttle at which the car counts as back on the power
NOMINAL_POWER = 12.0    # units after the apex where getting on the power counts as normal
_cache: dict = {}


def path(key: str) -> Path:
    return DIR / f"{key}.json"


def load(key: str) -> dict:
    """{"physics": fingerprint, "laps": [best first]} (empty if none or other physics)."""
    p = path(key)
    data = jsonio.read_json(p) if p.exists() else {}
    if data.get("physics") != tuning.physics_fingerprint():
        return {"physics": tuning.physics_fingerprint(), "laps": []}
    return data


def weight_of(params) -> str:
    """The weight class of a car from its parameters."""
    traits = getattr(params, "traits", None)
    if traits and len(traits) >= 5:
        return {-1.0: "light", 1.0: "heavy"}.get(float(traits[4]), "medium")
    return "medium"


def submit(track_key: str, entries: list[dict]) -> bool:
    """Add laps: entries are {"lap", "driver", "kind" ("ai"/"human"), "car" (traits or None),
    "weight"}.  Keeps the fastest KEEP plus the fastest of each weight.  True if the
    track record fell."""
    if not entries:
        return False
    data = load(track_key)
    before = list(data["laps"])
    laps = list(before)
    record = laps[0]["time"] if laps else None
    stamp = time.strftime("%Y-%m-%d %H:%M")
    for e in entries:
        lap = dict(e["lap"], driver=e.get("driver", "?"), kind=e.get("kind", "ai"), car=e.get("car"),
                   weight=e.get("weight", "medium"), date=stamp)
        laps.append(lap)
    laps.sort(key=lambda l: l["time"])
    keep = laps[:KEEP]
    for w in WEIGHTS:
        best = next((l for l in laps if l.get("weight") == w), None)
        if best is not None and best not in keep:
            keep.append(best)
    if [l["time"] for l in keep] == [l["time"] for l in before]:
        return False
    data["laps"] = keep
    jsonio.write_json(path(track_key), data)
    for k in [k for k in _cache if k[0] == track_key]:
        del _cache[k]
    return record is None or keep[0]["time"] < record


def submit_race(race, kinds=None, labels=None) -> list[str]:
    """Submit every flying lap a Race recorded.  Returns the tracks whose record fell."""
    entries = []
    for i, lap in getattr(getattr(race, "telemetry", None), "laps", []):
        driver = race.drivers[i]
        kind = (kinds[i] if kinds else ("human" if type(driver).__name__ in ("KeyboardDriver", "GamepadDriver")
                                        else "ai"))
        params = race.world.cars[i].params
        traits = getattr(driver, "car_traits", None)
        entries.append({"lap": lap, "driver": labels[i] if labels else getattr(driver, "label", "?"),
                        "kind": kind, "car": traits, "weight": weight_of(params)})
    return [race.track.key] if submit(race.track.key, entries) else []


def best(track_key: str, weight: str | None = None) -> dict | None:
    laps = load(track_key)["laps"]
    if weight:
        same = [l for l in laps if l.get("weight") == weight]
        if same:
            return same[0]
    return laps[0] if laps else None


def corner_report(track, lap: dict) -> list[dict]:
    """Per corner of `track`: where the lap braked, its apex speed and line,
    and where it got back on the power, against the ideal line's numbers."""
    from .brain import GRIP_PLAN
    corners = track.corners()
    off, curv = track.ideal()
    grip = tuning.CarParams().grip * GRIP_PLAN
    n = len(lap["speed"])
    out = []
    for apex in corners["apex"]:
        k = min(n - 1, int(apex * track.ds / SPACING))
        safe = math.sqrt(grip / max(curv[apex], 1e-4))
        brake_at = None
        for j in range(k, max(-1, k - int(80 / SPACING)), -1):     # back from the apex to where it lifted or braked
            if lap["brake"][j % n] > 0.1 or lap["throttle"][j % n] < 0.5:
                brake_at = j
            elif brake_at is not None:
                break
        power_at = next((j for j in range(k, k + int(60 / SPACING)) if lap["throttle"][j % n] >= POWER_ON), None)
        out.append({
            "apex": apex,
            "apex_speed": lap["speed"][k], "ideal_speed": min(safe, 60.0),
            "apex_line": lap["lateral"][k], "ideal_line": off[apex], "half_width": track._hw[apex],
            "brake_before": None if brake_at is None else (k - brake_at) * SPACING,
            "power_after": None if power_at is None else (power_at - k) * SPACING,
        })
    return out


def reference(track, weight: str = "medium") -> np.ndarray | None:
    """Reference notes (corners, 3) from the best lap of this weight (or any), or None."""
    from .brain import NOTE_LINE, NOTE_SPEED
    key = (track.key, weight)
    if key in _cache:
        return _cache[key]
    lap = best(track.key, weight)
    notes = None
    if lap and len(lap.get("speed", [])) >= int(track.length / SPACING) - 2:
        rows = []
        for c in corner_report(track, lap):
            speed = (c["apex_speed"] / c["ideal_speed"] - 1.0) / NOTE_SPEED
            line = (c["apex_line"] - c["ideal_line"]) / (NOTE_LINE * c["half_width"])
            power = c["power_after"] if c["power_after"] is not None else 2 * NOMINAL_POWER
            throttle = (NOMINAL_POWER - power) / NOMINAL_POWER
            rows.append([speed, line, throttle])
        notes = np.clip(np.array(rows, dtype=np.float64), -1.0, 1.0)
    _cache[key] = notes
    return notes
