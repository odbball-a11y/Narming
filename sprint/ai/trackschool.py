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


def folder(option: dict, track: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", option["name"].lower()).strip("-") or "driver"
    return DIR / f"{slug}-{track}"


def existing(option: dict, track: str) -> int | None:
    """The last generation of an earlier session for this driver and track."""
    run_dir = folder(option, track)
    if not (run_dir / "school.json").exists() or meta(run_dir).get("key") != option["key"]:
        return None
    gens = evolve.list_generations(run_path(run_dir))
    return gens[-1] if gens else None


def start(option: dict, track: str, fresh: bool = False) -> Path:
    """A practice copy of `option` for `track`; returns its folder.  An
    earlier session for the same driver and track carries on where it
    stopped, unless `fresh`."""
    run_dir = folder(option, track)
    if not fresh and existing(option, track) is not None:
        return run_dir
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    pop, arch = _source(option["key"])
    arch = with_notes(arch)
    pop = fit_genomes(pop, arch)
    np.savez_compressed(run_dir / "start.npz", pop=pop.astype(np.float32))
    info = {"name": option["name"], "key": option["key"], "track": track, "arch": arch,
            "traits": option.get("traits"), "livery": option.get("livery")}
    (run_dir / "school.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return run_dir


def best_generation(run_dir) -> dict | None:
    """The generation whose best driver set the fastest clean test lap:
    {"gen", "lap", "damage"} (None before the first generation)."""
    track = meta(run_dir)["track"]
    best = None
    for h in evolve.load_history(run_path(run_dir)):
        e = h["exam"].get(track, {})
        lap = e.get("solo_best_lap")
        if lap and e.get("solo_damage", 1.0) <= 0.05 and (best is None or lap < best["lap"]):
            best = {"gen": h["gen"], "lap": lap, "damage": e.get("solo_damage", 0.0)}
    return best


def can_save(info: dict) -> bool:
    """A house rival's or a stable racer's copy can become its championship
    driver (the graduate's cannot: it never races)."""
    return info["key"].startswith(("house:", "racer:"))


def save(run_dir, gen: int | None = None) -> dict:
    """Make the trained copy the championship driver of the car it came from."""
    if meta(run_dir)["key"].startswith("racer:"):
        return save_to_racer(run_dir, gen)
    return save_to_house(run_dir, gen)


def _pick(run_dir, gen):
    pick = best_generation(run_dir) if gen is None else {"gen": gen, "lap": None}
    if pick is None:
        raise ValueError("no generation has a clean test lap yet")
    return pick


def save_to_racer(run_dir, gen: int | None = None) -> dict:
    """The trained copy becomes the stable racer's brain, as a new version
    (its earlier versions stay).  Track school is extra training: it does not
    use the racer's training budget, and the racer is marked with a *."""
    from datetime import datetime
    from . import rating
    info = meta(run_dir)
    racer_dir = Path(info["key"][6:])
    if not stable.can_race(racer_dir):
        raise ValueError(f"{info['name']} no longer races")
    left = stable.progress(racer_dir)
    if left["done"] < left["target"]:
        raise ValueError(f"{info['name']} still has training to finish ({left['done']} of {left['target']})")
    pick = _pick(run_dir, gen)
    src = run_path(run_dir)
    racer = stable.load(racer_dir)
    last = racer["versions"][-1]
    version = {"run": f"v{len(racer['versions']) + 1}", "generations": 0,
               "aggression": last.get("aggression", racer["aggression"]), "caution": last.get("caution", racer["caution"]),
               "partners": [], "track": info["track"], "focus": info["track"],
               "track_school": {"track": info["track"], "gen": pick["gen"], "lap": pick["lap"]}}
    dest = racer_dir / version["run"]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy(src / "config.json", dest / "config.json")
    shutil.copy(evolve.gen_path(src, pick["gen"]), evolve.gen_path(dest, pick["gen"]))
    hist = [h for h in evolve.load_history(src) if h["gen"] <= pick["gen"]]
    (dest / "history.json").write_text(json.dumps(hist), encoding="utf-8")
    racer["versions"].append(version)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    racer.setdefault("track_school", []).append({"track": info["track"], "gen": pick["gen"], "lap": pick["lap"],
                                                 "date": stamp})
    stable.save(racer_dir, racer)
    rating.loosen(racer_dir.parent, f"racer:{racer['id']}")
    return {"name": racer["name"], "gen": pick["gen"], "lap": pick["lap"], "backup": None}


def save_to_house(run_dir, gen: int | None = None) -> dict:
    """Make the trained copy of a house rival the house rival itself.  The
    old one is kept in house/rivals/old/.  Uses `gen`, or the generation with
    the fastest clean test lap.  Returns {"name", "gen", "lap", "backup"}."""
    from datetime import datetime
    from . import rating
    info = meta(run_dir)
    if not info["key"].startswith("house:"):
        raise ValueError("only a house rival's copy can become the house car")
    rid = info["key"][6:]
    pick = _pick(run_dir, gen)
    best = evolve.load_generation(run_path(run_dir), pick["gen"])["pop"][:1].astype(np.float32)
    rivals = stable.RIVALS_DIR
    card = json.loads((rivals / f"{rid}.json").read_text(encoding="utf-8"))
    old = rivals / "old"
    old.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = old / f"{rid}-{stamp}"
    shutil.copy(rivals / f"{rid}.npz", backup.with_suffix(".npz"))
    shutil.copy(rivals / f"{rid}.json", backup.with_suffix(".json"))
    np.savez_compressed(rivals / f"{rid}.npz", pop=best)
    card["arch"] = info["arch"]
    card["generations"] = card.get("generations", 0) + pick["gen"]
    card.setdefault("track_school", []).append({"track": info["track"], "gen": pick["gen"], "lap": pick["lap"],
                                                "date": stamp})
    (rivals / f"{rid}.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    rating.loosen(stable.STABLE_DIR, f"house:{rid}")          # it has changed: let its rating move faster
    return {"name": card["name"], "gen": pick["gen"], "lap": pick["lap"], "backup": str(backup)}


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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "save":
        ap = argparse.ArgumentParser(description="Make a track-school copy the championship driver of its car.")
        ap.add_argument("cmd")
        ap.add_argument("dir")
        ap.add_argument("--gen", type=int, default=None, help="generation to use (default: fastest clean test lap)")
        args = ap.parse_args()
        migrate.ensure()
        done = save(args.dir, args.gen)
        lap = f", test lap {done['lap']:.2f} s" if done["lap"] else ""
        kept = f" The old one is kept as {done['backup']}.*" if done["backup"] else " Its earlier versions are kept."
        print(f"{done['name']} now races as track-school generation {done['gen']}{lap}.{kept}")
        return
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
