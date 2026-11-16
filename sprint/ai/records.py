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


PHYSICS = 5     # records set under other physics (1 = classic, 2 = scrub only, 3 = front grip 1.2, 4 = grip 34) are kept aside


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


def reset(root=None, log=print) -> list[str]:
    """Wipe every lap record: the fastest-laps store (telemetry/) and the
    championship track records (<root>/records.json).  The old files are kept
    in a `reset-<n>` folder beside them.  Returns what was moved."""
    import shutil
    from . import stable, telemetry
    root = Path(root or stable.STABLE_DIR)
    moved = []
    for folder, files in ((telemetry.DIR, sorted(telemetry.DIR.glob("*.json")) if telemetry.DIR.exists() else []),
                          (root, [path(root)])):
        files = [f for f in files if f.exists()]
        if not files:
            continue
        n = 1
        while (folder / f"reset-{n}").exists():
            n += 1
        keep = folder / f"reset-{n}"
        keep.mkdir(parents=True)
        for f in files:
            shutil.move(str(f), str(keep / f.name))
            moved.append(str(f))
            log(f"reset {f}  (old one kept in {keep})")
    telemetry._cache.clear()
    if not moved:
        log("no lap records to reset")
    return moved


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["reset"]:
        reset()
    else:
        print("usage: python -m ai.records reset")
