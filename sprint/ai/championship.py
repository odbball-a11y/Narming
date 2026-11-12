"""Championships: five races, one per track, with a points table.

A season is entered from the stable with one or two of your racers; the
field is filled up to four cars with the house rivals and then scripted cars.
Every race counts, and a season is saved as it goes, so it can be resumed
after quitting.  Rules:

  points      10, 7, 5, 3 for 1st to 4th (more places for bigger fields),
              nothing for not finishing, +1 for the fastest lap among the
              finishers; ties go to most wins, then best finishing places
  laps        5 on every track
  grid        race 1 is drawn (seeded); after that the field starts in
              reverse championship order, so the leader starts last
  damage      resets between races
  ratings     every car, scripted ones too, has a TrueSkill rating that
              every race moves (see ai/rating.py)
  careers     each race counts towards a racer's career (20 races = four
              seasons); a racer reaching its limit mid-season finishes the
              season and then goes to stud

The saved file is stable/championship.json while a season is running; a
finished season moves to stable/seasons/season_NNN.json.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import sim.scripted  # noqa: F401  (registers "scripted")
from sim.race import Race
from sim.track import Track

from . import livery as liveries
from . import rating
from . import stable
from sim import tuning
from sim.driver import create_driver

POINTS = [10, 7, 5, 3, 2, 1, 0, 0]
FASTEST_LAP_POINT = 1
MAX_OWN = 2
FIELD = 4
RACE_LAPS = 5          # every championship race, on every track
TRACK_ORDER = ["oval", "speedway", "esses", "technical", "grandprix"]


def path(root) -> Path:
    return Path(root) / "championship.json"


def seasons_dir(root) -> Path:
    return Path(root) / "seasons"


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(p)


def active(root) -> dict | None:
    """The season under way, or None."""
    p = path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def past_seasons(root) -> list[dict]:
    d = seasons_dir(root)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("season_*.json"))] if d.exists() else []


def abandon(root) -> None:
    """Throw the season away (results already added to careers stay)."""
    p = path(root)
    if p.exists():
        p.unlink()


def eligible(root) -> list[Path]:
    """Your racers that can enter: trained and still racing."""
    return [d for d in stable.list_racers(root) if stable.can_race(d)]


def start(root, racer_dirs) -> dict:
    """Begin a season with one or two of your racers."""
    root = Path(root)
    if active(root):
        raise ValueError("a championship is already under way")
    dirs = [Path(d) for d in racer_dirs]
    if not 1 <= len(dirs) <= MAX_OWN:
        raise ValueError(f"enter one or two racers (not {len(dirs)})")
    entrants = []
    for d in dirs:
        if not stable.can_race(d):
            raise ValueError(f"{stable.load(d)['name']} cannot race (untrained, retired or breeding)")
        entrants.append({"kind": "racer", "id": d.name, "name": stable.load(d)["name"],
                         "livery": stable.livery_of(d)})
    for rival in stable.house_rivals():
        if len(entrants) < FIELD:
            entrants.append({"kind": "house", "id": rival["id"], "name": rival["name"],
                             "livery": rival["livery"]})
    n = 1
    while len(entrants) < FIELD:           # scripted cars keep one look all season
        entrants.append({"kind": "scripted", "id": f"scripted{n}", "name": f"Scripted {n}",
                         "livery": liveries.assign([e["livery"] for e in entrants if e["livery"]])})
        n += 1
    season = len(past_seasons(root)) + 1
    ch = {"season": season, "seed": 1000 + season * 7919 + sum(map(ord, "".join(e["id"] for e in entrants))),
          "entrants": entrants, "tracks": list(TRACK_ORDER), "races": [], "done": False}
    _write(path(root), ch)
    return ch


# --------------------------------------------------------------- standings

def standings(ch: dict, upto: int | None = None) -> list[dict]:
    """The table after the first `upto` races (default: all so far), best
    first.  Each row: entrant, position, points, wins, podiums, places, last
    (points from the latest race), moved (places gained since the race before)."""
    races = ch["races"] if upto is None else ch["races"][:upto]
    rows = {i: {"entrant": i, "points": 0, "wins": 0, "podiums": 0, "places": [], "last": 0}
            for i in range(len(ch["entrants"]))}
    for race in races:
        for res in race["results"]:
            row = rows[res["entrant"]]
            row["points"] += res["points"]
            row["wins"] += int(res["finished"] and res["place"] == 1)
            row["podiums"] += int(res["finished"] and res["place"] <= 3)
            row["places"].append(res["place"])
            row["last"] = res["points"]
    order = sorted(rows.values(), key=lambda r: (-r["points"], -r["wins"], sum(r["places"]), r["entrant"]))
    for position, row in enumerate(order, start=1):
        row["position"] = position
        row["moved"] = 0
    if len(races) >= 2:
        before = {r["entrant"]: r["position"] for r in standings(ch, len(races) - 1)}
        for row in order:
            row["moved"] = before[row["entrant"]] - row["position"]
    return order


def grid(ch: dict, k: int) -> list[int]:
    """Entrants in starting order for race k (index 0 starts in front):
    drawn for race 1, then reverse championship order (the leader last)."""
    n = len(ch["entrants"])
    if k == 0:
        order = list(range(n))
        random.Random(ch["seed"]).shuffle(order)
        return order
    return [row["entrant"] for row in reversed(standings(ch, k))]


def next_race(ch: dict) -> dict | None:
    """The coming race: its number, track and starting order."""
    k = len(ch["races"])
    if k >= len(ch["tracks"]):
        return None
    return {"number": k + 1, "track": ch["tracks"][k], "grid": grid(ch, k)}


# ------------------------------------------------------------------- races

def _driver(root, entrant: dict, slot: int):
    if entrant["kind"] == "racer":
        return stable.champion(Path(root) / entrant["id"])
    if entrant["kind"] == "house":
        return stable.house_driver(entrant["id"])
    identity = int(entrant["id"][-1]) % 4          # Scripted 1, 2, 3: each its own fixed skill and car
    driver = create_driver("scripted", slot=identity)
    driver.car_params = tuning.car_params(identity)
    driver.label = entrant["name"]
    driver.livery = entrant["livery"]
    return driver


def build_race(root, ch: dict) -> Race:
    """The coming race, ready to run (sim or watched)."""
    nxt = next_race(ch)
    if nxt is None:
        raise ValueError("the championship is over")
    entries = [(slot, _driver(root, ch["entrants"][e], slot)) for slot, e in enumerate(nxt["grid"])]
    track = Track.load(nxt["track"])
    return Race(track, entries, laps=RACE_LAPS, seed=ch["seed"] + nxt["number"], rolling=True)


def finish_race(root, ch: dict, race: Race) -> dict:
    """Score a finished race into the season (once) and save.  Returns the
    race record; when it was the last, `complete` news is in ch["news"]."""
    k = len(ch["races"])
    order = grid(ch, k)
    career_news = stable.record_race(race, defer_retire=True)   # a racer at its limit finishes the season
    rows = race.results()
    laps = [r["best_lap"] for r in rows if r["finished"] and r["best_lap"]]
    fastest = min(laps) if laps else None
    results = []
    for r in rows:
        points = POINTS[min(r["place"], len(POINTS)) - 1] if r["finished"] else 0
        quick = bool(fastest is not None and r["finished"] and r["best_lap"] == fastest)
        results.append({"entrant": order[r["car"]], "place": r["place"], "finished": r["finished"],
                        "time": r["time"], "best_lap": r["best_lap"], "fastest": quick,
                        "points": points + (FASTEST_LAP_POINT if quick else 0),
                        "grid": r["car"] + 1, "damage": round(race.world.cars[r["car"]].damage, 3)})
    changes = rating.update(root, ch["entrants"], results, race.track.key)     # every car is rated
    for res in results:
        ch_ = changes[res["entrant"]]
        res["rating"] = [round(ch_["before"], 1), round(ch_["after"], 1)]
        res["track_rating"] = [round(ch_["track_before"], 1), round(ch_["track_after"], 1)]
        res["sigma"] = round(ch_["sigma"], 1)
    record = {"track": race.track.key, "order": order, "results": results}
    ch["races"].append(record)
    ch["news"] = career_news
    if len(ch["races"]) >= len(ch["tracks"]):
        ch["news"] = complete(root, ch) + career_news
    else:
        _write(path(root), ch)
    return record


def complete(root, ch: dict) -> list[str]:
    """End of season: crown the champion, add titles, retire racers who hit
    their career limit, and file the season away.  Returns the news."""
    root = Path(root)
    table = standings(ch)
    champion = table[0]["entrant"]
    ch["done"] = True
    ch["champion"] = champion
    news = [f"{ch['entrants'][champion]['name']} is the champion!"]
    for i, e in enumerate(ch["entrants"]):
        if e["kind"] != "racer":
            if i == champion:
                rating.add_title(root, e)              # house rivals and scripted cars collect titles too
            continue
        racer_dir = root / e["id"]
        racer = stable.load(racer_dir)
        if i == champion:
            racer["career"]["titles"] = racer["career"].get("titles", 0) + 1
            stable.save(racer_dir, racer)
        if stable.status(racer_dir) == "racing" and racer["career"]["races"] >= stable.CAREER_RACES:
            stable.retire(racer_dir, f"after {stable.CAREER_RACES} races")
            news.append(f"{racer['name']} retires to stud after {stable.CAREER_RACES} races.")
    news += [f"{name} has died. Remembered in the hall of fame." for name in stable.check_deaths(root)]
    ch["news"] = news
    _write(seasons_dir(root) / f"season_{ch['season']:03d}.json", ch)
    abandon(root)
    return news


def titles(racer_dir) -> int:
    return stable.load(racer_dir)["career"].get("titles", 0)


def titles_of(root, entrant: dict) -> int:
    """Championships won by an entrant: your racers keep them in their
    career, the others in the ratings file."""
    if entrant["kind"] == "racer":
        racer_dir = Path(root) / entrant["id"]
        return titles(racer_dir) if (racer_dir / "racer.json").exists() else 0
    return rating.titles_of(root, rating.key(entrant))
