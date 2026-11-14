"""Track school: watch a car learn one track, generation by generation.

A practice copy: the chosen driver (a stable racer, a house rival or the
graduate) is copied into `trackschool/<driver>-<track>/` (git-ignored) and
trained there for pure speed on that one track: solo laps only (driving
school, never racing school), its track notes free to change.  The real
racer, its training budget and its form are never touched.

The game runs `python -m ai.trackschool DIR --workers N` in the background
and, while each generation trains, shows the best driver of the last one
lapping (`game/trackschool_screen.py`).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

import numpy as np

from sim import cartraits

from . import evolve, migrate, stable
from .brain import arch_for_vector, fit_genomes, with_notes

DIR = evolve.PROJECT / "trackschool"
POPULATION = 60          # smallish, so generations come every few seconds
ELITES = 4
GENERATIONS = 100000     # runs until stopped
NEVER = 10 ** 9          # racing school never starts
HEARTBEAT = 60.0         # seconds without the game touching "alive" before training stops itself


class Stopped(Exception):
    pass


def touch(run_dir) -> None:
    """The watching screen calls this every second or so."""
    (Path(run_dir) / "alive").touch()


def watcher_gone(run_dir) -> bool:
    alive = Path(run_dir) / "alive"
    return alive.exists() and time.time() - alive.stat().st_mtime > HEARTBEAT


def options(root: Path | None = None) -> list[dict]:
    """Drivers that can go to track school: the graduate, the house rivals and
    every trained racer in the stable (retired ones and legends too)."""
    out = [{"key": "graduate", "name": "The graduate", "traits": None, "livery": None}]
    for card in stable.house_rivals():
        out.append({"key": f"house:{card['id']}", "name": card["name"], "traits": card.get("traits"),
                    "livery": card.get("livery")})
    for d in stable.list_racers(root, include_dead=True) if root else []:
        if stable.brain_file(d) is None or stable.is_breeding(d):
            continue
        racer = stable.load(d)
        out.append({"key": f"racer:{d}", "name": racer["name"], "traits": racer.get("traits"),
                    "livery": stable.livery_of(d) if hasattr(stable, "livery_of") else racer.get("livery")})
    return out


def _source(key: str) -> tuple[np.ndarray, dict]:
    """(population to start from, arch) for an option key."""
    grad = stable.graduate()
    if key == "graduate":
        pop = evolve.load_pop_file(str(stable.GRADUATE.with_suffix(".npz")))
        return pop, arch_for_vector(pop[0], grad["arch"])
    if key.startswith("house:"):
        rid = key[6:]
        card = next(c for c in stable.house_rivals() if c["id"] == rid)
        with np.load(stable.RIVALS_DIR / f"{rid}.npz") as data:
            pop = data["pop"][:1].astype(np.float64)
        return pop, arch_for_vector(pop[0], card.get("arch") or grad["arch"])
    racer_dir = Path(key[6:])
    with np.load(stable.brain_file(racer_dir)) as data:
        pop = data["pop"][:1].astype(np.float64)
    return pop, arch_for_vector(pop[0], grad["arch"])


def start(option: dict, track: str) -> Path:
    """A fresh practice copy of `option` for `track`; returns its folder."""
    slug = re.sub(r"[^a-z0-9]+", "-", option["name"].lower()).strip("-") or "driver"
    run_dir = DIR / f"{slug}-{track}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    pop, arch = _source(option["key"])
    arch = with_notes(arch)
    pop = fit_genomes(pop, arch)
    np.savez_compressed(run_dir / "start.npz", pop=pop.astype(np.float32))
    meta = {"name": option["name"], "key": option["key"], "track": track, "arch": arch,
            "traits": option.get("traits"), "livery": option.get("livery")}
    (run_dir / "school.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return run_dir


def meta(run_dir) -> dict:
    return json.loads((Path(run_dir) / "school.json").read_text(encoding="utf-8"))


def load_start(run_dir) -> np.ndarray:
    """The driver the copy started from (its best, if a whole population)."""
    with np.load(Path(run_dir) / "start.npz") as data:
        return data["pop"][0].astype(np.float64)


def run_path(run_dir) -> Path:
    """The evolve run inside a school folder."""
    return Path(run_dir) / "run"


def car_params(run_dir):
    traits = meta(run_dir).get("traits")
    return cartraits.params_for(traits or cartraits.default())


def train(run_dir, workers: int = 0, generations: int = GENERATIONS, on_generation=None) -> Path:
    """Train the copy for speed on its track until stopped (resumable)."""
    info = meta(run_dir)

    def each(entry):
        if on_generation:
            on_generation(entry)
        if watcher_gone(run_dir):               # the game quit or crashed: do not train for ever
            raise Stopped
    return evolve.train(run="run", root=Path(run_dir), generations=generations, population=POPULATION,
                        elites=ELITES, seed=7, tracks=[info["track"]], exam_tracks=[info["track"]],
                        phase2_from=NEVER, driving_school=True, arch=info["arch"],
                        start_file=str(Path(run_dir) / "start.npz"), notes=True,
                        car=info.get("traits") or cartraits.default(), workers=workers,
                        on_generation=each, log=print, name=f"{info['name']} (track school)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--generations", type=int, default=GENERATIONS)
    args = ap.parse_args()
    migrate.ensure()
    try:
        train(args.dir, workers=args.workers, generations=args.generations,
              on_generation=lambda e: print(f"gen {e['gen']}: best {e['best']:.3f}", flush=True))
    except Stopped:
        print("nobody is watching any more: stopped", flush=True)


if __name__ == "__main__":
    main()
