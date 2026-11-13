"""Skill ratings for every car in the championships, scripted ones included.

Uses TrueSkill (the rating system built for several players finishing in
order), through a bundled copy of the `trueskill` package (ai/vendor/).
Every car has a skill estimate with an uncertainty; everyone starts the same,
and every championship race moves everyone in it, so racing sorts the
ratings out.  Scripted cars and house rivals are rated too, so the pool stays
anchored and the numbers mean something against the house.

How a race is rated: the finishers are ranked by finishing place and the cars
that did not finish share last place (a tie).  TrueSkill moves every car's
estimate by how surprising its result was given everyone's ratings, and
shrinks the uncertainty of every car that raced.  There is an overall rating
and one per track (a specialist shows as a high rating on its track).

Shown to the player as a number that starts at 1000 (`START`), with a plus or
minus for the uncertainty: rating = 1000 + 40 x (skill - 25), uncertainty =
40 x sigma.  Ratings live in <stable>/ratings.json, keyed "racer:<id>",
"house:<id>" and "scripted:<id>".
"""
from __future__ import annotations

import json
from pathlib import Path

from . import jsonio
from .vendor import trueskill

ENV = trueskill.TrueSkill(draw_probability=0.10)
START = 1000.0
SCALE = 40.0            # displayed points per unit of TrueSkill skill
LOOSEN = 2.5            # how much a racer's uncertainty grows when it is trained again


def show(mu: float) -> float:
    return START + SCALE * (mu - ENV.mu)


def path(root) -> Path:
    return Path(root) / "ratings.json"


def load(root) -> dict:
    p = path(root)
    return jsonio.read_json(p) if p.exists() else {}


def _save(root, data: dict) -> None:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    jsonio.write_json(p, data)


def key(entrant: dict) -> str:
    return f"{entrant['kind']}:{entrant['id']}"


def _fresh(entrant: dict) -> dict:
    return {"name": entrant["name"], "kind": entrant["kind"], "livery": entrant.get("livery"),
            "overall": {"mu": ENV.mu, "sigma": ENV.sigma, "races": 0, "peak": START}, "tracks": {}}


def add_title(root, entrant: dict) -> None:
    """A championship won by a car that is not one of your racers (those keep
    their titles in their career): the house rivals and scripted cars."""
    data = load(root)
    entry = data.setdefault(key(entrant), _fresh(entrant))
    entry["titles"] = entry.get("titles", 0) + 1
    _save(root, data)


def titles_of(root, k: str) -> int:
    return load(root).get(k, {}).get("titles", 0)


def summary(root, k: str) -> dict | None:
    """What to show for a car: rating, uncertainty, rated races, peak and
    per-track ratings (None if it has never raced a rated race)."""
    entry = load(root).get(k)
    if not entry:
        return None
    o = entry["overall"]
    return {"rating": show(o["mu"]), "sigma": SCALE * o["sigma"], "races": o["races"], "peak": o["peak"],
            "tracks": {t: show(v["mu"]) for t, v in entry["tracks"].items()}}


def rating_of(root, entrant: dict, track: str | None = None) -> float:
    """Current displayed rating of an entrant (overall, or on a track)."""
    entry = load(root).get(key(entrant))
    if not entry:
        return START
    if track is None:
        return show(entry["overall"]["mu"])
    return show(entry["tracks"][track]["mu"]) if track in entry["tracks"] else START


def update(root, entrants: list[dict], results: list[dict], track: str) -> dict[int, dict]:
    """Rate one race.  `results` are the championship race's result rows
    (entrant index, place, finished).  Returns, per entrant index,
    {"before", "after", "sigma", "track_before", "track_after"} (displayed values)."""
    data = load(root)
    for res in results:
        e = entrants[res["entrant"]]
        entry = data.setdefault(key(e), _fresh(e))
        entry["name"], entry["livery"] = e["name"], e.get("livery") or entry.get("livery")
    entries = [data[key(entrants[r["entrant"]])] for r in results]
    ranked = sorted(r["place"] for r in results if r["finished"])
    last = len(ranked)                                   # cars that did not finish share last place
    ranks = [r["place"] - 1 if r["finished"] else last for r in results]

    def rate(groups):
        return [g[0] for g in ENV.rate([(r,) for r in groups], ranks=ranks)]

    overall = [ENV.create_rating(e["overall"]["mu"], e["overall"]["sigma"]) for e in entries]
    on_track = []
    for e in entries:
        t = e["tracks"].get(track)
        on_track.append(ENV.create_rating(t["mu"], t["sigma"]) if t else ENV.create_rating())
    new_overall, new_track = rate(overall), rate(on_track)
    changes = {}
    for res, e, old_o, new_o, old_t, new_t in zip(results, entries, overall, new_overall, on_track, new_track):
        tr = e["tracks"].setdefault(track, {"mu": ENV.mu, "sigma": ENV.sigma, "races": 0})
        changes[res["entrant"]] = {"before": show(old_o.mu), "after": show(new_o.mu), "sigma": SCALE * new_o.sigma,
                                   "track_before": show(old_t.mu), "track_after": show(new_t.mu)}
        e["overall"].update(mu=new_o.mu, sigma=new_o.sigma, races=e["overall"]["races"] + 1,
                            peak=max(e["overall"]["peak"], show(new_o.mu)))
        tr.update(mu=new_t.mu, sigma=new_t.sigma, races=tr["races"] + 1)
    _save(root, data)
    return changes


def loosen(root, k: str, amount: float = LOOSEN) -> None:
    """A racer that has been trained again may have changed: make its rating
    less certain, so the next races move it faster."""
    data = load(root)
    entry = data.get(k)
    if not entry:
        return
    for part in [entry["overall"]] + list(entry["tracks"].values()):
        part["sigma"] = min(ENV.sigma, part["sigma"] + amount)
    _save(root, data)


def table(root) -> list[dict]:
    """Every rated car, best first: key, name, kind, livery, rating, sigma,
    races, peak and per-track ratings."""
    rows = []
    for k, e in load(root).items():
        o = e["overall"]
        rows.append({"key": k, "name": e["name"], "kind": e["kind"], "livery": e.get("livery"),
                     "rating": show(o["mu"]), "sigma": SCALE * o["sigma"], "races": o["races"],
                     "peak": o["peak"], "titles": e.get("titles", 0),
                     "tracks": {t: show(v["mu"]) for t, v in e["tracks"].items()}})
    return sorted(rows, key=lambda r: (-r["rating"], r["name"]))
