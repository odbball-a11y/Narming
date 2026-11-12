"""Track records: the fastest race lap ever set on each track in the
championship, and who set it.  Saved in `<root>/records.json`, keyed by track:

    {"speedway": {"time": 12.31, "name": "Dangerous Dave", "livery": {...}, "season": 3}}
"""
from __future__ import annotations

import json
from pathlib import Path


def path(root) -> Path:
    return Path(root) / "records.json"


def load(root) -> dict:
    try:
        return json.loads(path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def update(root, track: str, lap: float | None, entrant: dict, season: int) -> bool:
    """Set the record for `track` if `lap` beats it.  True when it did."""
    if lap is None:
        return False
    records = load(root)
    old = records.get(track)
    if old and old["time"] <= lap:
        return False
    records[track] = {"time": round(lap, 3), "name": entrant["name"], "livery": entrant.get("livery"),
                      "season": season}
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, indent=1), encoding="utf-8")
    tmp.replace(p)
    return True
