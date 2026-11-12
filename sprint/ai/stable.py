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
import shutil
import zlib
from pathlib import Path

import numpy as np

from sim import cartraits
from sim.driver import register_driver, unregister_drivers

from . import evolve
from . import livery as liveries
from .brain import NeuralDriver, layer_sizes, unpack

HOUSE_DIR = evolve.PROJECT / "house"
RIVALS_DIR = HOUSE_DIR / "rivals"
GRADUATE = HOUSE_DIR / "graduate"
STABLE_DIR = evolve.PROJECT / "stable"
WORKSHOP_DIR = evolve.PROJECT / "workshop"

POPULATION = 80
GENERATION_CHOICES = [10, 20, 40, 80]
CAREER_RACES = 20       # races before a racer retires to stud
STUD_BREEDINGS = 5      # litters a racer at stud can sire before it dies
STUD_LIFETIME = 40      # stable races (by anyone) a racer lives for at stud

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


# A scripted car's flying lap on each track, to compare AI pace across tracks.
SCRIPTED_LAPS = {"oval": 11.48, "speedway": 13.98, "esses": 17.37, "technical": 22.20, "grandprix": 23.99}
TRACK_NAMES = {"oval": "Oval", "speedway": "Speedway", "esses": "Esses", "technical": "Technical",
               "grandprix": "Grand Prix"}


def pace(exam: dict | None) -> float | None:
    """Average lap time alone as a fraction of a scripted car's, over the
    tracks in an exam (0.92 = 8% quicker than a scripted car).  None if it
    set no lap anywhere."""
    if not exam:
        return None
    ratios = [e["solo_best_lap"] / SCRIPTED_LAPS[t] for t, e in exam.items()
              if e.get("solo_best_lap") and t in SCRIPTED_LAPS]
    return round(sum(ratios) / len(ratios), 4) if ratios else None


def pace_text(p: float | None) -> str:
    if p is None:
        return "no lap yet"
    diff = (1.0 - p) * 100
    return f"{abs(diff):.0f}% {'quicker' if diff >= 0 else 'slower'} than scripted"


def exam_average(exam: dict | None) -> dict:
    """Test-race numbers averaged over the tracks."""
    if not exam:
        return {}
    rows = list(exam.values())
    keys = ("race_place", "race_overtakes", "race_fault", "race_damage", "race_draft")
    out = {k: sum(r[k] for r in rows) / len(rows) for k in keys}
    out["race_finished"] = sum(1 for r in rows if r["race_finished"]) / len(rows)
    return out


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


def _taken_liveries(root, exclude=None) -> list[dict]:
    """Liveries already in use: living racers in `root` and the house rivals."""
    taken = [load(d)["livery"] for d in list_racers(root) if d.name != exclude and load(d).get("livery")]
    for rival in _house_cards():
        if rival.get("livery"):
            taken.append(rival["livery"])
    return taken


def livery_of(racer_dir) -> dict:
    """The racer's livery, assigned (and saved) the first time it is needed
    for racers made before liveries existed."""
    racer = load(racer_dir)
    if not racer.get("livery"):
        racer["livery"] = liveries.assign(_taken_liveries(Path(racer_dir).parent, racer["id"]))
        save(racer_dir, racer)
    return racer["livery"]


def traits_of(racer_dir) -> dict:
    """The racer's car (racers made before car traits drive the standard car)."""
    return load(racer_dir).get("traits") or cartraits.default()


def list_racers(root: Path, include_dead: bool = False) -> list[Path]:
    """Racer folders in a stable or workshop, oldest first.  The dead are
    left out unless asked for (they live on in the hall of fame)."""
    root = Path(root)
    if not root.exists():
        return []
    dirs = [p for p in root.iterdir() if (p / "racer.json").exists()]
    if not include_dead:
        dirs = [p for p in dirs if status(p) != "dead"]
    return sorted(dirs, key=lambda p: (load(p).get("created", ""), p.name))


# ----------------------------------------------------------------- careers
#
# A racer races (status "racing") for CAREER_RACES races, or until retired
# early, then stands at stud ("stud"): it can be bred from but no longer
# races or trains.  It dies ("dead") after STUD_BREEDINGS litters or after
# STUD_LIFETIME stable races at stud, whichever comes first, and joins the
# hall of fame.  The stable's clock is its total number of races.  None of
# this applies in the workshop, where house rivals are made.

def careers_enabled(root) -> bool:
    return Path(root).resolve() != Path(WORKSHOP_DIR).resolve()


def status(racer_dir) -> str:
    return load(racer_dir).get("status", "racing")


def clock(root) -> int:
    path = Path(root) / "stable.json"
    return _read(path).get("races", 0) if path.exists() else 0


def _tick(root) -> int:
    path = Path(root) / "stable.json"
    data = _read(path) if path.exists() else {}
    data["races"] = data.get("races", 0) + 1
    _write(path, data)
    return data["races"]


def can_race(racer_dir) -> bool:
    return status(racer_dir) == "racing" and brain_file(racer_dir) is not None and not is_breeding(racer_dir)


def can_train(racer_dir) -> bool:
    return status(racer_dir) == "racing"


def can_breed(racer_dir) -> bool:
    if brain_file(racer_dir) is None or is_breeding(racer_dir):
        return False
    if not careers_enabled(Path(racer_dir).parent):
        return True
    return status(racer_dir) == "stud"


def retire(racer_dir, reason: str = "retired early") -> None:
    """End a racer's racing career: it goes to stud."""
    racer = load(racer_dir)
    if racer.get("status", "racing") != "racing":
        return
    racer["status"] = "stud"
    racer["retired_at"] = clock(Path(racer_dir).parent)
    racer["retired_reason"] = reason
    racer.setdefault("breedings", 0)
    save(racer_dir, racer)


def stud_life_left(racer_dir) -> int:
    racer = load(racer_dir)
    return max(0, STUD_LIFETIME - (clock(Path(racer_dir).parent) - racer.get("retired_at", 0)))


def _die(racer_dir, cause: str) -> None:
    racer = load(racer_dir)
    racer["status"] = "dead"
    racer["died_at"] = clock(Path(racer_dir).parent)
    racer["died"] = datetime.date.today().isoformat()
    racer["death_cause"] = cause
    save(racer_dir, racer)


def check_deaths(root) -> list[str]:
    """Studs that have run out of breedings or years die.  Returns names."""
    if not careers_enabled(root):
        return []
    died = []
    for d in list_racers(root):
        racer = load(d)
        if racer.get("status") != "stud" or is_breeding(d):
            continue
        if racer.get("breedings", 0) >= STUD_BREEDINGS:
            _die(d, f"after {STUD_BREEDINGS} litter{'s' if STUD_BREEDINGS != 1 else ''}")
            died.append(racer["name"])
        elif stud_life_left(d) == 0:
            _die(d, "of old age")
            died.append(racer["name"])
    return died


def offspring(root, racer_id: str) -> list[str]:
    """Names of the racers bred from this one."""
    return [load(d)["name"] for d in list_racers(root, include_dead=True)
            if racer_id in load(d).get("parents", [])]


def hall_of_fame(root) -> list[Path]:
    dead = [d for d in list_racers(root, include_dead=True) if status(d) == "dead"]
    return sorted(dead, key=lambda d: load(d).get("died_at", 0))


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


def focus_of(version: dict) -> str | None:
    return version.get("focus")


def specialty(racer_dir) -> tuple[str | None, dict]:
    """(track it specialises in or None, generations trained per focus).
    A racer is a specialist at a track once more than half of its training
    generations were spent there; otherwise it is an all-rounder."""
    racer = load(racer_dir)
    spent: dict = {}
    for v in racer["versions"]:
        done = len(evolve.list_generations(Path(racer_dir) / v["run"]))
        key = focus_of(v) or "all"
        spent[key] = spent.get(key, 0) + done
    total = sum(spent.values())
    best = max((k for k in spent if k != "all"), key=lambda k: spent[k], default=None)
    if best and total and spent[best] * 2 > total:
        return best, spent
    return None, spent


def specialty_text(racer_dir) -> str:
    track, spent = specialty(racer_dir)
    if sum(spent.values()) == 0:
        return "not trained yet"
    if track:
        return f"{TRACK_NAMES[track]} specialist"
    return "all-rounder"


def needs_training(racer_dir) -> bool:
    if is_breeding(racer_dir):
        return False
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
    for d in list_racers(root, include_dead=True):
        if d.name == exclude:
            continue
        f = brain_file(d)
        if f is not None:
            options.append({"key": f"racer:{d.name}", "name": load(d)["name"], "kind": "file",
                            "file": evolve.project_path(f), "traits": traits_of(d)})
    if include_house:
        for rival in house_rivals():
            options.append({"key": f"house:{rival['id']}", "name": rival["name"], "kind": "file",
                            "file": evolve.project_path(rival["file"]),
                            "traits": rival.get("traits") or cartraits.default()})
    return options


# ------------------------------------------------------- create / upskill

def _new_version(racer: dict, aggression: float, caution: float, partners: list[dict],
                 generations: int, track: str, focus: str | None = None) -> dict:
    if focus is not None and focus not in TRACK_NAMES:
        raise ValueError(f"unknown track {focus!r}")
    return {"run": f"v{len(racer['versions']) + 1}", "generations": int(generations),
            "aggression": round(float(aggression), 2), "caution": round(float(caution), 2),
            "partners": [{k: p[k] for k in ("name", "kind", "file", "traits") if k in p} for p in partners],
            "track": track, "focus": focus}


def create(root: Path, name: str, aggression: float, caution: float, partners: list[dict],
           generations: int, track: str = "speedway", traits: dict | None = None,
           focus: str | None = None) -> Path:
    """Register a new racer with its car (`traits`, default the standard
    car); train it with `train`.  The car is the racer's for life."""
    name = name.strip()
    if not name:
        raise ValueError("a racer needs a name")
    traits = dict(traits or cartraits.default())
    if not cartraits.is_valid(traits):
        raise ValueError(f"car traits must use exactly {cartraits.tuning.TRAIT_BUDGET} stars, 1-5 each")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for existing in list_racers(root):          # older racers get theirs first, in order
        livery_of(existing)
    racer_dir = root / slug(name, root)
    racer_dir.mkdir()
    racer = {"id": racer_dir.name, "name": name,
             "created": datetime.date.today().isoformat(),
             "aggression": round(float(aggression), 2), "caution": round(float(caution), 2),
             "traits": traits, "livery": liveries.assign(_taken_liveries(root)),
             "parents": [], "versions": [],
             "career": {"races": 0, "wins": 0, "podiums": 0, "best_laps": {}}}
    racer["versions"].append(_new_version(racer, aggression, caution, partners or [{"name": "Scripted car",
                                                                                   "kind": "scripted"}],
                                          generations, track, focus))
    save(racer_dir, racer)
    return racer_dir


def upskill(racer_dir, aggression: float, caution: float, partners: list[dict], generations: int,
            focus: str | None = None) -> None:
    """Add a training version that carries on from the racer's current brain,
    possibly with a new personality, new partners and a new training focus
    (one track, to specialise, or None for all five)."""
    if brain_file(racer_dir) is None:
        raise ValueError("train the racer before upskilling it")
    if not can_train(racer_dir):
        raise ValueError("only racers still racing can be trained")
    racer = load(racer_dir)
    racer["versions"].append(_new_version(racer, aggression, caution, partners,
                                          generations, racer["versions"][-1]["track"], focus))
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
    focus = v.get("focus")
    tracks = [focus] if focus else list(grad["tracks"])
    # The same effort either way: a single track gets as many races per
    # generation as all five together, so it trains harder on that track.
    races = grad["races_per_track"] * len(grad["tracks"]) // len(tracks)
    evolve.train(run=v["run"], root=racer_dir, generations=remaining, population=population,
                 seed=index, tracks=tracks, exam_tracks=list(grad["tracks"]), arch=grad["arch"],
                 races_per_track=races,
                 race_bonuses=False, start_file=str(start), race_seconds=dict(grad["race_seconds"]),
                 race_weights=sliders_to_weights(v["aggression"], v["caution"]),
                 partners=v["partners"], name=racer["name"], workers=workers, car=traits_of(racer_dir),
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
    driver.car_params = cartraits.params_for(traits_of(racer_dir))
    driver.livery = livery_of(racer_dir)
    return driver


def _house_cards() -> list[dict]:
    if not RIVALS_DIR.exists():
        return []
    out = []
    for meta in sorted(RIVALS_DIR.glob("*.json")):
        data = _read(meta)
        data["id"] = meta.stem
        data["file"] = meta.with_suffix(".npz")
        out.append(data)
    return out


def house_rivals() -> list[dict]:
    """Shipped opponents: [{"id", "name", "file", "livery", ...card data}].
    A rival with no livery of its own gets one that nobody else has."""
    cards = _house_cards()
    given = [c["livery"] for c in cards if c.get("livery")]
    for card in cards:
        if not card.get("livery"):
            card["livery"] = liveries.assign(given)
            given.append(card["livery"])
    return cards


def house_driver(rival_id: str) -> NeuralDriver:
    meta = next((r for r in house_rivals() if r["id"] == rival_id), None) or _read(RIVALS_DIR / f"{rival_id}.json")
    with np.load(RIVALS_DIR / f"{rival_id}.npz") as data:
        weights = data["pop"][0].astype(np.float64)
    driver = NeuralDriver(weights, meta["arch"], meta["name"])
    driver.car_params = cartraits.params_for(meta.get("traits") or cartraits.default())
    driver.livery = meta.get("livery")
    return driver


def record_result(racer_dir, place: int, best_lap: float | None, track: str,
                  defer_retire: bool = False, tick: bool = True) -> list[str]:
    """Add one finished race to a racer's career; the stable's clock moves
    on (once per race: `tick`).  Returns news: retirements and deaths.
    `defer_retire` leaves a racer that reaches its limit racing until the
    end of its championship."""
    racer_dir = Path(racer_dir)
    root = racer_dir.parent
    news = []
    if careers_enabled(root):
        if status(racer_dir) != "racing":
            return news
        if tick:
            _tick(root)
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
    if careers_enabled(root):
        if career["races"] >= CAREER_RACES and not defer_retire:
            retire(racer_dir, f"after {CAREER_RACES} races")
            news.append(f"{racer['name']} retires to stud after {CAREER_RACES} races.")
        for name in check_deaths(root):
            news.append(f"{name} has died. Remembered in the hall of fame.")
    return news


def record_race(race, defer_retire: bool = False) -> list[str]:
    """Add a finished race to the careers of any stable racers in it; the
    stable's clock ticks once for the race.  Returns news: retirements and
    deaths.  (`defer_retire`: championships retire racers at the season's end.)"""
    news = []
    first = True
    for row in race.results():
        racer_dir = getattr(race.drivers[row["car"]], "racer_dir", None)
        if racer_dir and row["finished"]:
            news += record_result(racer_dir, row["place"], row["best_lap"], race.track.key,
                                  defer_retire=defer_retire, tick=first)
            first = False
    return news


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
            "traits": traits_of(racer_dir), "livery": livery_of(racer_dir),
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
        if can_race(d):
            key = f"racer:{d.name}"
            register_driver(key, load(d)["name"], lambda slot=0, p=d: champion(p))
            keys.append(key)
    return keys


# ----------------------------------------------------------------- breeding

LITTER = 20             # foals bred per mating
SHORTLIST = 5           # foals that go on to a mini training camp
CAMP_GENERATIONS = 3    # length of each mini-camp
CAMP_POPULATION = 16
TEMPERAMENT_SPREAD = 0.08   # how far a foal's personality strays from its parents' average
CRITERIA = {"fastest": "Fastest pace over the five tracks after its mini-camp",
            "learner": "Quickest learner: fewest generations to match its parents' pace"}


def brain(racer_dir) -> np.ndarray:
    """The racer's own weights (its champion)."""
    with np.load(brain_file(racer_dir)) as data:
        return data["pop"][0].astype(np.float64)


def crossover(a: np.ndarray, b: np.ndarray, arch: dict, rng: np.random.Generator) -> np.ndarray:
    """A child brain made of whole neurons from each parent.

    Every neuron (its incoming weights and bias, in every layer including the
    outputs) is copied whole from one parent or the other, so working units
    such as "react to a car on my left" are kept rather than blurred.  This
    only makes sense because all racers descend from the same graduate, so
    the parents' neurons line up.  A few small mutations follow.
    """
    child = np.empty_like(a)
    la, lb, lc = unpack(a, arch), unpack(b, arch), unpack(child, arch)
    for (wa, ba), (wb, bb), (wc, bc) in zip(la, lb, lc):
        pick = rng.random(len(ba)) < 0.5
        wc[:] = np.where(pick[:, None], wa, wb)
        bc[:] = np.where(pick, ba, bb)
    mask = rng.random(len(child)) < 0.2
    return child + rng.normal(0.0, 0.02, len(child)) * mask


def breeding_progress(foal_dir) -> dict | None:
    path = Path(foal_dir) / "breeding.json"
    return _read(path) if path.exists() else None


def _progress(foal_dir, **state) -> None:
    _write(Path(foal_dir) / "breeding.json", state)


def is_breeding(racer_dir) -> bool:
    """A foal whose litter has not been decided yet."""
    racer = load(racer_dir)
    return "breeding" in racer and "certificate" not in racer


def mate(root: Path, sire_dir, dam_dir, name: str, criterion: str = "fastest") -> Path:
    """Register a foal; `breed` then makes the litter and picks it."""
    if Path(sire_dir) == Path(dam_dir):
        raise ValueError("pick two different parents")
    if criterion not in CRITERIA:
        raise ValueError(f"criterion must be one of {sorted(CRITERIA)}")
    sire, dam = load(sire_dir), load(dam_dir)
    for parent in (sire, dam):
        if brain_file(Path(root) / parent["id"]) is None:
            raise ValueError(f"{parent['name']} must be trained before breeding")
        if not can_breed(Path(root) / parent["id"]):
            raise ValueError(f"{parent['name']} must be retired to stud before breeding")
    seed = zlib.crc32(f"{sire['id']}|{dam['id']}|{name}".encode())
    rng = np.random.default_rng(seed)

    def blend(key):
        value = (sire[key] + dam[key]) / 2 + rng.normal(0.0, TEMPERAMENT_SPREAD)
        return round(float(min(1.0, max(0.0, value))), 2)

    aggression, caution = blend("aggression"), blend("caution")
    traits, traits_from = cartraits.inherit(sire.get("traits") or cartraits.default(),
                                            dam.get("traits") or cartraits.default(), rng)
    foal_dir = create(root, name, aggression, caution, [{"name": "Scripted car", "kind": "scripted"}],
                      CAMP_GENERATIONS, sire["versions"][-1]["track"], traits=traits)
    racer = load(foal_dir)
    racer["livery"] = liveries.inherit(livery_of(sire_dir), livery_of(dam_dir),
                                       _taken_liveries(root, racer["id"]))
    racer["parents"] = [sire["id"], dam["id"]]
    racer["breeding"] = {"sire": sire["id"], "dam": dam["id"], "criterion": criterion, "seed": seed,
                         "traits_from": traits_from}
    save(foal_dir, racer)
    _progress(foal_dir, stage="waiting")
    if careers_enabled(root):
        for parent_dir in (sire_dir, dam_dir):
            parent = load(parent_dir)
            parent["breedings"] = parent.get("breedings", 0) + 1
            save(parent_dir, parent)
    return foal_dir


def _parent_summary(root: Path, racer_id: str) -> dict:
    d = Path(root) / racer_id
    if not (d / "racer.json").exists():
        return {"id": racer_id, "name": racer_id}
    r = load(d)
    exam = latest_exam(d)
    avg = exam_average(exam)
    by_track = {t: round(x["solo_best_lap"] / SCRIPTED_LAPS[t], 4) for t, x in (exam or {}).items()
                if x.get("solo_best_lap") and t in SCRIPTED_LAPS}
    return {"id": r["id"], "name": r["name"], "aggression": r["aggression"], "caution": r["caution"],
            "traits": r.get("traits") or cartraits.default(),
            "races": r["career"]["races"], "wins": r["career"]["wins"], "podiums": r["career"]["podiums"],
            "best_laps": r["career"]["best_laps"], "parents": r.get("parents", []),
            "pace": pace(exam), "track_pace": by_track, "passes": avg.get("race_overtakes"),
            "hits": avg.get("race_fault"), "damage": avg.get("race_damage")}


def expectations(sire: dict, dam: dict, foal: dict) -> list[str]:
    """Plain-language predictions from the parents' records (labelled as
    expectations: the foal's own races will tell)."""
    notes = []
    paces = [p["pace"] for p in (sire, dam) if p.get("pace")]
    if paces:
        notes.append(f"Pace: its parents are {' and '.join(pace_text(x) for x in paces)}; "
                     "expect similar speed.")
    a, c = foal["aggression"], foal["caution"]
    if a >= 0.6 and c < 0.5:
        notes.append("Style: likely an attacker. Expect passes, and some knocks.")
    elif c >= 0.6 and a < 0.5:
        notes.append("Style: likely careful. Expect clean races and few collisions.")
    elif a >= 0.5 and c >= 0.5:
        notes.append("Style: bold but tidy, if the mix works. Could be special, could be confused.")
    else:
        notes.append("Style: balanced; no strong leaning either way.")
    passes = [p["passes"] for p in (sire, dam) if p.get("passes") is not None]
    if passes and sum(passes) / len(passes) >= 2:
        notes.append("Overtaking: both sides of the family pass well in traffic.")
    hits = [p["hits"] for p in (sire, dam) if p.get("hits") is not None]
    if hits and max(hits) <= 0.5:
        notes.append("Consistency: neither parent causes many collisions; should race cleanly.")
    car = foal.get("traits") or {}
    best = max(cartraits.STARS, key=lambda k: car.get(k, 3)) if car else None
    if best and car.get(best, 3) >= 4:
        suits = {"top_speed": "Oval and Speedway", "accel": "Grand Prix and Technical",
                 "handling": "Esses and the hairpins", "braking": "Grand Prix"}[best]
        notes.append(f"Car: strongest at {cartraits.LABELS[best].lower()}; should suit {suits}.")
    if car.get("weight") == "heavy":
        notes.append("Car: heavy. Wins shoving matches, slower to accelerate and stop.")
    elif car.get("weight") == "light":
        notes.append("Car: light. Quick to accelerate and stop, but easily pushed around.")
    wins = sire.get("wins", 0) + dam.get("wins", 0)
    if wins:
        notes.append(f"Winning stock: its parents have {wins} wins between them.")
    family = {}
    for p in (sire, dam):
        for t, r in (p.get("track_pace") or {}).items():
            family.setdefault(t, []).append(r)
    if len(family) >= 2:
        avg = {t: sum(v) / len(v) for t, v in family.items()}
        best, worst = min(avg, key=avg.get), max(avg, key=avg.get)
        notes.append(f"Tracks: the family is quickest, against a scripted car, at {TRACK_NAMES.get(best, best)}"
                     f" and least quick at {TRACK_NAMES.get(worst, worst)}.")
    shared = set(sire.get("parents", [])) & set(dam.get("parents", []))
    if shared:
        notes.append("Close relatives: the parents share a parent. Expect little variety.")
    return notes


def breed(foal_dir, workers: int = 0, litter: int = LITTER, shortlist: int = SHORTLIST,
          camp_generations: int = CAMP_GENERATIONS, camp_population: int = CAMP_POPULATION) -> dict:
    """Make the litter, trial it in two rounds, keep the best foal as this
    racer's version 1 and write its breeding certificate."""
    from concurrent.futures import ProcessPoolExecutor

    foal_dir = Path(foal_dir)
    root = foal_dir.parent
    racer = load(foal_dir)
    info = racer["breeding"]
    rng = np.random.default_rng(info["seed"])
    grad = graduate()
    arch = grad["arch"]
    tracks = grad["tracks"]
    sire_w, dam_w = brain(root / info["sire"]), brain(root / info["dam"])
    litter_dir = foal_dir / "litter"
    if litter_dir.exists():
        shutil.rmtree(litter_dir)
    litter_dir.mkdir()

    # The litter.
    _progress(foal_dir, stage="litter", done=0, of=litter)
    foals = np.array([crossover(sire_w, dam_w, arch, rng) for _ in range(litter)])

    # Round 1: every foal straight from breeding, alone and in one race,
    # all scored the same (balanced) way so the comparison is fair.
    _progress(foal_dir, stage="trial", done=0, of=litter)
    traits = racer.get("traits") or cartraits.default()
    trial = [{"track": t, "slot": 3, "rivals": ["scripted"] * 3, "seconds": grad["race_seconds"][t],
              "car": traits} for t in tracks]
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        score, _ = evolve.score_population(foals, arch, tracks, trial, 0.0, pool, chunks=max(1, workers),
                                           weights=sliders_to_weights(0.0, 0.0),
                                           setup={"slot": 0, "damage": 0.0, "car": traits})
    finally:
        if pool:
            pool.shutdown()
    order = [int(i) for i in np.argsort(-score, kind="stable")]
    picked = order[:shortlist]

    # Round 2: a short training camp each, with the foal's own personality.
    parents = [_parent_summary(root, info["sire"]), _parent_summary(root, info["dam"])]
    paces = [p["pace"] for p in parents if p.get("pace")]
    target = round(sum(paces) / len(paces), 4) if paces else 1.0
    weights = sliders_to_weights(racer["aggression"], racer["caution"])
    candidates = []
    for k, i in enumerate(picked):
        _progress(foal_dir, stage="camp", done=k, of=len(picked))
        start = litter_dir / f"foal_{i:02d}.npz"
        np.savez_compressed(start, pop=foals[i:i + 1].astype(np.float32))
        run = f"cand_{i:02d}"
        evolve.train(run=run, root=litter_dir, generations=camp_generations, population=camp_population,
                     elites=2, seed=info["seed"] % 100000 + i, tracks=tracks, arch=arch, races_per_track=1,
                     race_bonuses=False, start_file=str(start), race_seconds=dict(grad["race_seconds"]),
                     race_weights=weights, partners=[{"name": "Scripted car", "kind": "scripted"}],
                     workers=workers, log=lambda m: None, car=traits)
        hist = evolve.load_history(litter_dir / run)
        paces_by_gen = [pace(h["exam"]) for h in hist]
        valid = [p for p in paces_by_gen if p]
        to_target = next((h["gen"] for h, p in zip(hist, paces_by_gen) if p and p <= target), None)
        last = exam_average(hist[-1]["exam"])
        candidates.append({"foal": i + 1, "trial_rank": k + 1, "trial_score": round(float(score[i]), 3),
                           "pace": min(valid) if valid else None, "gens_to_target": to_target,
                           "race_place": round(last["race_place"], 2), "passes": round(last["race_overtakes"], 1),
                           "hits": round(last["race_fault"], 1), "damage": round(last["race_damage"], 3),
                           "run": run})

    def key(c):
        p = c["pace"] or 9.0
        if info["criterion"] == "learner":
            return (c["gens_to_target"] or 99, p)
        return (p, -c["trial_score"])

    winner = min(candidates, key=key)
    for c in candidates:
        c["chosen"] = c is winner
    # The winner's camp becomes the foal's first version.
    v1 = foal_dir / racer["versions"][0]["run"]
    if v1.exists():
        shutil.rmtree(v1)
    shutil.move(str(litter_dir / winner["run"]), str(v1))
    kept = foal_dir / "foal.npz"
    shutil.copy(litter_dir / f"foal_{winner['foal'] - 1:02d}.npz", kept)
    config = evolve.load_config(v1)
    config["parent"] = {"file": evolve.project_path(kept)}
    _write(v1 / "config.json", config)
    shutil.rmtree(litter_dir)

    grandparents = {p["name"]: [_parent_summary(root, g)["name"] for g in p.get("parents", [])] for p in parents}
    certificate = {
        "sire": parents[0], "dam": parents[1], "grandparents": grandparents,
        "litter": litter, "shortlist": len(picked), "criterion": info["criterion"],
        "criterion_text": CRITERIA[info["criterion"]], "target_pace": target,
        "candidates": candidates, "winner": winner,
        "temperament": {"aggression": racer["aggression"], "caution": racer["caution"]},
        "traits": traits, "traits_from": info.get("traits_from", {}), "livery": racer.get("livery"),
        "expectations": expectations(parents[0], parents[1], racer),
    }
    racer = load(foal_dir)
    racer["versions"][0]["generations"] = camp_generations    # its camp is its first training
    racer["certificate"] = certificate
    save(foal_dir, racer)
    _progress(foal_dir, stage="done")
    check_deaths(root)
    return certificate


# --------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ai.stable")
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train", help="train a racer's latest version")
    t.add_argument("racer_dir")
    t.add_argument("--workers", type=int, default=max(1, min(3, (os.cpu_count() or 2) - 1)))
    b = sub.add_parser("breed", help="make a foal's litter and pick the best foal")
    b.add_argument("racer_dir")
    b.add_argument("--workers", type=int, default=max(1, min(3, (os.cpu_count() or 2) - 1)))
    args = ap.parse_args(argv)
    from . import migrate
    migrate.ensure()
    if args.command == "breed":
        cert = breed(args.racer_dir, workers=args.workers)
        w = cert["winner"]
        print(f"picked foal {w['foal']} of {cert['litter']}: pace {w['pace']}, "
              f"generations to target {w['gens_to_target']}", flush=True)
        return 0
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
