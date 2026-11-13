"""JSON files shared between the game and its background training process.

On Windows a file can be briefly locked while the other process replaces it
(atomic save = write a temporary file, then rename it over the old one), and
reading or renaming it at that moment fails with "Permission denied".  These
helpers wait a moment and try again instead of crashing.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

TRIES = 40          # x 25 ms = up to a second
PAUSE = 0.025


def read_text(path) -> str:
    path = Path(path)
    for attempt in range(TRIES):
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            if attempt == TRIES - 1:
                raise
            time.sleep(PAUSE)
    raise AssertionError("unreachable")


def read_json(path):
    path = Path(path)
    for attempt in range(TRIES):
        try:
            return json.loads(read_text(path))
        except ValueError:                    # caught half-written by a non-atomic writer: try again
            if attempt == TRIES - 1:
                raise
            time.sleep(PAUSE)
    raise AssertionError("unreachable")


def write_json(path, data, indent: int = 1) -> None:
    """Atomic save: write a temporary file, then rename it into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp") if path.suffix != ".tmp" else path.with_suffix(".tmp2")
    tmp.write_text(json.dumps(data, indent=indent), encoding="utf-8")
    for attempt in range(TRIES):
        try:
            tmp.replace(path)
            return
        except PermissionError:               # the other process is reading it right now
            if attempt == TRIES - 1:
                raise
            time.sleep(PAUSE)
