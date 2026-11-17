"""All-time championship statistics for the Hall of Fame, worked out from the
saved seasons (stable/seasons/season_*.json) plus the season in progress.
Every car that has started a championship race is counted: your racers
(alive, retired or dead), house rivals and scripted cars.  Practice races
never count.

    stats(root) -> {key: car}   key = "racer:<id>" | "house:<id>" | "scripted:<id>"

A car: name, kind, livery, status (racing / retired / dead / house / scripted),
races, wins, podiums, dnf, points, places (sum), titles, best_lap,
win_streak, tracks {track: {races, wins, podiums, places, best_lap}},
seasons [{season, position, of, points, done}], h2h {other key: [ahead, behind]}.
"""
from __future__ import annotations

from pathlib import Path

from . import championship, jsonio, rating, stable

MIN_RACES = 5            # win % and the other rates are only shown from this many races


def seasons(root) -> list[dict]:
    """Every finished season, oldest first, then the one in progress (if it has races)."""
    out = []
    for f in sorted(championship.seasons_dir(root).glob("season_*.json"),
                    key=lambda p: int("".join(c for c in p.stem if c.isdigit()) or 0)):
        try:
            out.append(jsonio.read_json(f))
        except (OSError, ValueError):
            continue
    current = Path(championship.path(root))
    if current.exists():
        try:
            ch = jsonio.read_json(current)
            if ch.get("races") and not ch.get("done"):
                out.append(ch)
        except (OSError, ValueError):
            pass
    return out


def _status(root, entrant: dict) -> str:
    if entrant["kind"] != "racer":
        return entrant["kind"]
    d = Path(root) / entrant["id"]
    if not (d / "racer.json").exists():
        return "gone"
    return {"racing": "racing", "stud": "retired", "dead": "dead"}.get(stable.status(d), "racing")


def _blank(entrant: dict) -> dict:
    return {"name": entrant["name"].rstrip(" *"), "kind": entrant["kind"], "id": entrant["id"],
            "livery": entrant.get("livery"), "races": 0, "wins": 0, "podiums": 0, "dnf": 0, "points": 0,
            "places": 0, "titles": 0, "best_lap": None, "win_streak": 0, "_run": 0, "tracks": {},
            "seasons": [], "h2h": {}}


def stats(root) -> dict:
    cars: dict = {}
    for ch in seasons(root):
        keys = [f"{e['kind']}:{e['id']}" for e in ch["entrants"]]
        for key, e in zip(keys, ch["entrants"]):
            car = cars.setdefault(key, _blank(e))
            car["name"], car["livery"] = e["name"].rstrip(" *"), e.get("livery") or car["livery"]
        for race in ch["races"]:
            res = race["results"]
            for r in res:
                car = cars[keys[r["entrant"]]]
                win = r["finished"] and r["place"] == 1
                car["races"] += 1
                car["wins"] += win
                car["podiums"] += r["finished"] and r["place"] <= 3
                car["dnf"] += not r["finished"]
                car["points"] += r.get("points", 0)
                car["places"] += r["place"]
                car["_run"] = car["_run"] + 1 if win else 0
                car["win_streak"] = max(car["win_streak"], car["_run"])
                lap = r.get("best_lap") if r["finished"] else None
                if lap and (car["best_lap"] is None or lap < car["best_lap"]):
                    car["best_lap"] = lap
                t = car["tracks"].setdefault(race["track"], {"races": 0, "wins": 0, "podiums": 0, "places": 0,
                                                             "best_lap": None})
                t["races"] += 1
                t["wins"] += win
                t["podiums"] += r["finished"] and r["place"] <= 3
                t["places"] += r["place"]
                if lap and (t["best_lap"] is None or lap < t["best_lap"]):
                    t["best_lap"] = lap
                for o in res:                                   # head to head: who finished ahead in this race
                    if o is r:
                        continue
                    pair = car["h2h"].setdefault(keys[o["entrant"]], [0, 0])
                    pair[0 if r["place"] < o["place"] else 1] += 1
        if ch["races"]:
            table = championship.standings(ch)
            for row in table:
                car = cars[keys[row["entrant"]]]
                car["seasons"].append({"season": ch.get("season"), "position": row["position"], "of": len(table),
                                       "points": row["points"], "done": bool(ch.get("done"))})
                if ch.get("done") and row["position"] == 1:
                    car["titles"] += 1
    for key, car in cars.items():
        car.pop("_run", None)
        car["status"] = _status(root, {"kind": car["kind"], "id": car["id"]})
        skill = rating.summary(root, key)
        car["peak"] = skill["peak"] if skill else None
        car["rating"] = skill["rating"] if skill else None
    return cars


def rate(car: dict, what: str = "wins") -> float | None:
    """win % / podium % / average place / points per race, or None below MIN_RACES."""
    n = car["races"]
    if n < MIN_RACES:
        return None
    return {"wins": car["wins"] / n, "podiums": car["podiums"] / n, "place": car["places"] / n,
            "points": car["points"] / n, "dnf": car["dnf"] / n}[what]


SORTS = ["wins", "win %", "titles", "rating", "avg finish"]
FILTERS = ["all", "your racers", "house rivals", "legends", "still racing"]


def table(cars: dict, sort: str = "wins", show: str = "all") -> list[tuple[str, dict]]:
    keep = {"all": lambda c: True, "your racers": lambda c: c["kind"] == "racer",
            "house rivals": lambda c: c["kind"] == "house", "legends": lambda c: c["status"] == "dead",
            "still racing": lambda c: c["status"] in ("racing", "house", "scripted")}[show]
    rows = [(k, c) for k, c in cars.items() if keep(c)]
    key = {"wins": lambda c: (-c["wins"], -c["podiums"], c["races"]),
           "win %": lambda c: (rate(c) is None, -(rate(c) or 0), -c["wins"]),
           "titles": lambda c: (-c["titles"], -c["wins"]),
           "rating": lambda c: (c["peak"] is None, -(c["peak"] or 0)),
           "avg finish": lambda c: (rate(c, "place") is None, rate(c, "place") or 99)}[sort]
    return sorted(rows, key=lambda kc: key(kc[1]))


def champions(root) -> list[dict]:
    """Every finished season, newest first: champion, points, runner-up, margin, race wins."""
    out = []
    for ch in seasons(root):
        if not ch.get("done") or not ch["races"]:
            continue
        table_ = championship.standings(ch)
        first, second = table_[0], table_[1] if len(table_) > 1 else None
        e = ch["entrants"][first["entrant"]]
        out.append({"season": ch.get("season"), "name": e["name"], "livery": e.get("livery"),
                    "points": first["points"], "wins": first["wins"],
                    "runner_up": ch["entrants"][second["entrant"]]["name"] if second else "-",
                    "margin": first["points"] - (second["points"] if second else 0)})
    return out[::-1]
