"""Track records: the fastest race lap ever set on each track in the
championship, and who set it.  Saved in `<root>/records.json`, keyed by track:

    {"speedway": {"time": 12.31, "name": "Dangerous Dave", "livery": {...}, "season": 3}}
"""
from __future__ import annotations

import json
from . import jsonio
from pathlib import Path


def path(root) -> Path:
    return Path(root) / "records.json"


PHYSICS = 4     # records set under other physics (1 = classic, 2 = scrub only, 3 = front grip 1.2) are kept aside


def load(root) -> dict:
    try:
        data = jsonio.read_json(path(root))
    except (OSError, ValueError):
        return {}
    if data.get("_physics", 1) != PHYSICS:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def update(root, track: str, lap: float | None, entrant: dict, season: int) -> bool:
    """Set the record for `track` if `lap` beats it.  True when it did."""
    if lap is None:
        return False
    records = load(root)
    p0 = path(root)
    if p0.exists() and not records:                    # old-physics records: keep them in a side file
        try:
            old_physics = json.loads(p0.read_text(encoding="utf-8")).get("_physics", 1)
            if old_physics != PHYSICS:
                p0.replace(p0.with_name("records.classic.json" if old_physics == 1
                                        else f"records.physics{old_physics}.json"))
        except (OSError, ValueError):
            pass
    old = records.get(track)
    if old and old["time"] <= lap:
        return False
    records[track] = {"time": round(lap, 3), "name": entrant["name"], "livery": entrant.get("livery"),
                      "season": season}
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    jsonio.write_json(p, dict(records, _physics=PHYSICS))
    return True
