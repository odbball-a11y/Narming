"""The racing stable: named AI racers that the player creates, trains,
upskills and races (and, later, breeds).

Folders (all under the project folder):

  house/graduate.npz + .json   the starting brain every new racer trains on
                               from (a racing-school graduate), shipped
  house/rivals/<id>.npz + .json  house rivals: shipped opponents, race-only
  stable/<id>/                 the player's racers (not in git)
  workshop/<id>/               racers being made into house rivals with
                               `python -m game --workshop` (not in git)

A racer folder holds racer.json (name, personality, training versions,
career) and one training run per version: v1/, v2/, ...  Version 1 trains
on from the graduate; each upskill trains on from the previous version.
The racer's brain is the champion of its latest trained generation.

Training is run from the game in a separate process:

    python -m ai.stable train stable/<id> [--workers N]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path

import numpy as np

from sim.driver import register_driver, unregister_drivers

from . import evolve
from .brain import NeuralDriver

HOUSE_DIR = evolve.PROJECT / "house"
RIVALS_DIR = HOUSE_DIR / "rivals"
GRADUATE = HOUSE_DIR / "graduate"
STABLE_DIR = evolve.PROJECT / "stable"
WORKSHOP_DIR = evolve.PROJECT / "workshop"

POPULATION = 80
GENERATION_CHOICES = [10, 20, 40, 80]
CAREER_RACES = 20       # races before a racer retires to stud (step 4)

# Personality sliders, each 0..1, and the race scoring at their ends.
# (0, 0) is the balanced scoring; aggression 1 is Dangerous Dave's upbringing,
# caution 1 is Careful Keith's.
_BALANCED = {"place": [3.0, 2.0, 1.0, 0.0], "damage": 2.0, "fault": 0.25, "walls": 0.03,
             "overtake": 0.0, "passed": 0.0, "draft": 0.0}
_PUSH = {
    "aggression": evolve.STYLES["aggressive"],
    "caution": evolve.STYLES["cautious"],
}


def sliders_to_weights(aggression: float, caution: float) -> dict:
    """Race scoring for a personality: start balanced and move toward the
    aggressive and cautious scorings by the slider amounts."""
    weights = dict(evolve.RACE_WEIGHTS)
    for key, base in _BALANCED.items():
        value = np.asarray(base, dtype=float)
        for slider, amount in (("aggression", aggression), ("caution", caution)):
            target = np.asarray(_PUSH[slider].get(key, base), dtype=float)
            value = value + amount * (target - np.asarray(base, dtype=float))
        value = np.maximum(value, 0.0)
        weights[key] = value.round(4).tolist() if value.ndim else round(float(value), 4)
    return weights


# ------------------------------------------------------------------ files

def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def graduate() -> dict:
    """Settings of the starting brain: arch, tracks, race length, races."""
    return _read(GRADUATE.with_suffix(".json"))


def slug(name: str, root: Path) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "racer"
    candidate, k = base, 2
    while (Path(root) / candidate).exists():
        candidate, k = f"{base}-{k}", k + 1
    return candidate


def load(racer_dir) -> dict:
    return _read(Path(racer_dir) / "racer.json")


def save(racer_dir, racer: dict) -> None:
    _write(Path(racer_dir) / "racer.json", racer)


def list_racers(root: Path) -> list[Path]:
    """Racer folders in a stable or workshop, oldest first."""
    root = Path(root)
    if not root.exists():
        return []
    dirs = [p for p in root.iterdir() if (p / "racer.json").exists()]
    return sorted(dirs, key=lambda p: (load(p).get("created", ""), p.name))


# --------------------------------------------------------------- versions

def version_dir(racer_dir, index: int | None = None) -> Path:
    racer = load(racer_dir)
    v = racer["versions"][-1 if index is None else index]
    return Path(racer_dir) / v["run"]


def progress(racer_dir) -> dict:
    """{"version": n, "done": gens trained, "target": gens wanted} for the
    latest version."""
    racer = load(racer_dir)
    v = racer["versions"][-1]
    done = len(evolve.list_generations(Path(racer_dir) / v["run"]))
    return {"version": len(racer["versions"]), "done": done, "target": v["generations"]}


def needs_training(racer_dir) -> bool:
    p = progress(racer_dir)
    return p["done"] < p["target"]


def brain_file(racer_dir) -> Path | None:
    """The latest trained generation of the racer, or None if untrained."""
    racer = load(racer_dir)
    for v in reversed(racer["versions"]):
        gens = evolve.list_generations(Path(racer_dir) / v["run"])
        if gens:
            return evolve.gen_path(Path(racer_dir) / v["run"], gens[-1])
    return None


def history(racer_dir) -> list[dict]:
    """Every trained generation of every version, in order, each tagged
    with its version number."""
    out = []
    for k, v in enumerate(load(racer_dir)["versions"], start=1):
        for entry in evolve.load_history(Path(racer_dir) / v["run"]):
            out.append(dict(entry, version=k))
    return out


def latest_exam(racer_dir) -> dict | None:
    h = history(racer_dir)
    return h[-1]["exam"] if h else None


# ---------------------------------------------------------------- partners

def partner_options(root: Path, exclude: str | None = None, include_house: bool = False) -> list[dict]:
    """Who a racer can train against: scripted cars, its own earlier
    versions, the other trained racers in the same stable, and (in the
    workshop only) the house rivals."""
    options = [{"key": "scripted", "name": "Scripted car", "kind": "scripted"},
               {"key": "self", "name": "Itself (its own best so far)", "kind": "self"}]
    for d in list_racers(root):
        if d.name == exclude:
            continue
        f = brain_file(d)
        if f is not None:
            options.append({"key": f"racer:{d.name}", "name": load(d)["name"], "kind": "file",
                            "file": evolve.project_path(f)})
    if include_house:
        for rival in house_rivals():
            options.append({"key": f"house:{rival['id']}", "name": rival["name"], "kind": "file",
                            "file": evolve.project_path(rival["file"])})
    return options


# ------------------------------------------------------- create / upskill

def _new_version(racer: dict, aggression: float, caution: float, partners: list[dict],
                 generations: int, track: str) -> dict:
    return {"run": f"v{len(racer['versions']) + 1}", "generations": int(generations),
            "aggression": round(float(aggression), 2), "caution": round(float(caution), 2),
            "partners": [{k: p[k] for k in ("name", "kind", "file") if k in p} for p in partners],
            "track": track}


def create(root: Path, name: str, aggression: float, caution: float, partners: list[dict],
           generations: int, track: str = "speedway") -> Path:
    """Register a new racer; train it with `train`."""
    name = name.strip()
    if not name:
        raise ValueError("a racer needs a name")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    racer_dir = root / slug(name, root)
    racer_dir.mkdir()
    racer = {"id": racer_dir.name, "name": name,
             "created": datetime.date.today().isoformat(),
             "aggression": round(float(aggression), 2), "caution": round(float(caution), 2),
             "parents": [], "versions": [],
             "career": {"races": 0, "wins": 0, "podiums": 0, "best_laps": {}}}
    racer["versions"].append(_new_version(racer, aggression, caution, partners or [{"name": "Scripted car",
                                                                                   "kind": "scripted"}],
                                          generations, track))
    save(racer_dir, racer)
    return racer_dir


def upskill(racer_dir, aggression: float, caution: float, partners: list[dict], generations: int) -> None:
    """Add a training version that carries on from the racer's current brain,
    possibly with a new personality and new partners."""
    if brain_file(racer_dir) is None:
        raise ValueError("train the racer before upskilling it")
    racer = load(racer_dir)
    racer["versions"].append(_new_version(racer, aggression, caution, partners,
                                          generations, racer["versions"][-1]["track"]))
    racer["aggression"], racer["caution"] = round(float(aggression), 2), round(float(caution), 2)
    save(racer_dir, racer)


def train(racer_dir, workers: int = 0, on_generation=None, population: int = POPULATION) -> None:
    """Train the racer's latest version up to its target (resumable)."""
    racer_dir = Path(racer_dir)
    racer = load(racer_dir)
    index = len(racer["versions"]) - 1
    v = racer["versions"][index]
    remaining = v["generations"] - progress(racer_dir)["done"]
    if remaining <= 0:
        return
    if index == 0:
        start = GRADUATE.with_suffix(".npz")
    else:
        prev = racer_dir / racer["versions"][index - 1]["run"]
        start = evolve.gen_path(prev, evolve.list_generations(prev)[-1])
    grad = graduate()
    track = v["track"]
    evolve.train(run=v["run"], root=racer_dir, generations=remaining, population=population,
                 seed=index, tracks=[track], arch=grad["arch"], races_per_track=grad["races_per_track"],
                 race_bonuses=False, start_file=str(start), race_seconds={track: grad["race_seconds"][track]},
                 race_weights=sliders_to_weights(v["aggression"], v["caution"]),
                 partners=v["partners"], name=racer["name"], workers=workers,
                 on_generation=on_generation, log=lambda m: None)


# ------------------------------------------------------------------ racing

def champion(racer_dir, label: str | None = None) -> NeuralDriver:
    """The racer as a Driver.  It carries its folder so results can be
    added to its career."""
    racer = load(racer_dir)
    f = brain_file(racer_dir)
    if f is None:
        raise ValueError(f"{racer['name']} has not been trained yet")
    with np.load(f) as data:
        weights = data["pop"][0].astype(np.float64)
    driver = NeuralDriver(weights, graduate()["arch"], label or racer["name"])
    driver.racer_dir = str(racer_dir)
    return driver


def house_rivals() -> list[dict]:
    """Shipped opponents: [{"id", "name", "file", ...card data}]."""
    if not RIVALS_DIR.exists():
        return []
    out = []
    for meta in sorted(RIVALS_DIR.glob("*.json")):
        data = _read(meta)
        data["id"] = meta.stem
        data["file"] = meta.with_suffix(".npz")
        out.append(data)
    return out


def house_driver(rival_id: str) -> NeuralDriver:
    meta = _read(RIVALS_DIR / f"{rival_id}.json")
    with np.load(RIVALS_DIR / f"{rival_id}.npz") as data:
        weights = data["pop"][0].astype(np.float64)
    return NeuralDriver(weights, meta["arch"], meta["name"])


def record_result(racer_dir, place: int, best_lap: float | None, track: str) -> None:
    """Add one finished race to a racer's career."""
    racer = load(racer_dir)
    career = racer["career"]
    career["races"] += 1
    career["wins"] += place == 1
    career["podiums"] += place <= 3
    if best_lap is not None:
        old = career["best_laps"].get(track)
        if old is None or best_lap < old:
            career["best_laps"][track] = round(best_lap, 3)
    save(racer_dir, racer)


def publish(racer_dir) -> Path:
    """Make a workshop racer a house rival: copy its brain and card into
    house/rivals/, which ships with the game."""
    racer = load(racer_dir)
    f = brain_file(racer_dir)
    if f is None:
        raise ValueError("train the racer before publishing it")
    RIVALS_DIR.mkdir(parents=True, exist_ok=True)
    with np.load(f) as data:
        best = data["pop"][:1].astype(np.float32)
    np.savez_compressed(RIVALS_DIR / f"{racer['id']}.npz", pop=best)
    card = {"name": racer["name"], "aggression": racer["aggression"], "caution": racer["caution"],
            "arch": graduate()["arch"], "created": racer["created"],
            "generations": sum(v["generations"] for v in racer["versions"]),
            "exam": latest_exam(racer_dir)}
    _write(RIVALS_DIR / f"{racer['id']}.json", card)
    return RIVALS_DIR / f"{racer['id']}.json"


def register(root: Path | None = None) -> list[str]:
    """Put the house rivals, and the trained racers of `root`, in the
    driver registry so race setup can use them."""
    unregister_drivers("house:")
    unregister_drivers("racer:")
    keys = []
    for rival in house_rivals():
        key = f"house:{rival['id']}"
        register_driver(key, rival["name"], lambda slot=0, r=rival["id"]: house_driver(r))
        keys.append(key)
    for d in list_racers(root) if root else []:
        if brain_file(d) is not None:
            key = f"racer:{d.name}"
            register_driver(key, load(d)["name"], lambda slot=0, p=d: champion(p))
            keys.append(key)
    return keys


# --------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ai.stable")
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train", help="train a racer's latest version")
    t.add_argument("racer_dir")
    t.add_argument("--workers", type=int, default=max(1, min(3, (os.cpu_count() or 2) - 1)))
    args = ap.parse_args(argv)
    if args.command == "train":
        def report(entry):
            exam = next(iter(entry["exam"].values()))
            lap = exam["solo_best_lap"]
            print(f"gen {entry['gen']} best {entry['best']:.2f} lap {lap:.2f}" if lap else
                  f"gen {entry['gen']} best {entry['best']:.2f}", flush=True)
        train(args.racer_dir, workers=args.workers, on_generation=report)
        print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
