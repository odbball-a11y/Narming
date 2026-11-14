"""Dynasty: run the stable on its own, for hours, and see which cars win.

    python dynasty.py --hours 8              # start or resume (state lives in dynasty/)
    python dynasty.py --report               # just rewrite the report from what is on disk

It founds a stable of named racers with different cars, then loops forever:
race a simulated five-race championship (your three least-raced cars + the
best house rival + scripted cars), let racers retire to stud, breed the best
studs, train each foal, and keep going.  Every event goes in the journal, and
the report says which kind of car (weight, stars, temperament, family) wins.

Everything is saved after each step, so it can be stopped and resumed; the end
time is fixed when it first starts.  Output: dynasty/ (git-ignored data) and
dynasty_report/ (journal.md, state.json, REPORT.md: small, safe to commit).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import traceback
from pathlib import Path

from ai import championship, evolve, migrate, rating, records, snapshot, stable
from sim import cartraits

HERE = Path(__file__).resolve().parent
DATA = HERE / "dynasty"
ROOT = DATA / "stable"
OUT = HERE / "dynasty_report"

RACING_CAP = 6              # foals are bred only while fewer racers than this are still racing
FOUNDER_GENERATIONS = 10
FOAL_GENERATIONS = 8        # upskill after the breeding camp
SEASONS_BETWEEN_FOALS = 1   # a season after every foal, so studs age with the stable

FOUNDERS = [   # name, aggression, caution, traits  (4 stat stars sum to 12; weight sets the car's size)
    ("Tilly Thunderbolt", 0.8, 0.2, dict(top_speed=5, accel=4, handling=2, braking=1, weight="light")),
    ("Barnaby Brick", 0.6, 0.4, dict(top_speed=3, accel=2, handling=3, braking=4, weight="heavy")),
    ("Sally Slipstream", 0.5, 0.5, dict(top_speed=4, accel=2, handling=3, braking=3, weight="medium")),
    ("Nora Nimble", 0.3, 0.6, dict(top_speed=2, accel=3, handling=5, braking=2, weight="light")),
    ("Gus Granite", 0.7, 0.3, dict(top_speed=4, accel=3, handling=2, braking=3, weight="heavy")),
    ("Vera Velvet", 0.4, 0.5, dict(top_speed=3, accel=3, handling=3, braking=3, weight="medium")),
]
FIRST_NAMES = ["Ace", "Bolt", "Cinder", "Dash", "Ember", "Flash", "Gizmo", "Hurricane", "Indigo", "Jet", "Kestrel",
               "Lightning", "Maverick", "Nitro", "Orbit", "Pepper", "Quill", "Rocket", "Sparks", "Turbo", "Ultra",
               "Viper", "Whisper", "Xena", "Yeti", "Zephyr", "Blaze", "Comet", "Drift", "Echo", "Fury", "Gale",
               "Havoc", "Ivy", "Jolt", "Karma", "Lucky", "Mischief", "Nova", "Onyx", "Pixel", "Rascal", "Storm",
               "Tango", "Vortex", "Wren", "Zigzag", "Apex", "Bandit", "Cosmo"]


# ------------------------------------------------------------------ logging

def stamp(start: float) -> str:
    return f"{(time.time() - start) / 3600:5.2f}h"


class Log:
    def __init__(self, start: float):
        OUT.mkdir(parents=True, exist_ok=True)
        self.start = start
        self.journal = OUT / "journal.md"
        self.milestones = DATA / "milestones.log"

    def write(self, line: str, milestone: bool = False) -> None:
        text = f"- `{stamp(self.start)}` {line}"
        with self.journal.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
        print(text, flush=True)
        if milestone:
            with self.milestones.open("a", encoding="utf-8") as f:
                f.write(f"{stamp(self.start)} {line}\n")


# ------------------------------------------------------------- the stable

def generation(root: Path, racer_dir: Path) -> int:
    racer = stable.load(racer_dir)
    if not racer.get("parents"):
        return 0
    return 1 + max(generation(root, root / p) for p in racer["parents"])


def alive(root: Path) -> list[Path]:
    return stable.list_racers(root)


def skill(root: Path, racer_dir: Path) -> float:
    return rating.rating_of(root, {"kind": "racer", "id": racer_dir.name})


def found(root: Path, log: Log, generations: int) -> None:
    for name, aggression, caution, traits in FOUNDERS:
        if (root / stable.slug(name, root) / "racer.json").exists() or any(
                stable.load(d)["name"] == name for d in stable.list_racers(root, include_dead=True)):
            continue
        assert cartraits.is_valid(traits), name
        d = stable.create(root, name, aggression, caution, [{"name": "Scripted car", "kind": "scripted"}],
                          generations, traits=traits)
        log.write(f"founded **{name}**: {cartraits.describe(traits)}, aggression {aggression}, caution {caution}")


def train_pending(root: Path, log: Log, workers: int, population: int) -> None:
    for d in alive(root):
        if stable.is_breeding(d):
            continue
        if stable.needs_training(d) and stable.can_train(d):
            name = stable.load(d)["name"]
            t0 = time.time()
            log.write(f"training {name} ...")
            stable.train(d, workers=workers, population=population)
            log.write(f"trained {name} in {(time.time() - t0) / 60:.1f} min; {stable.pace_text(stable.pace(stable.latest_exam(d)))}")


def run_season(root: Path, log: Log) -> None:
    ready = [d for d in alive(root) if stable.can_race(d)]
    if not ready:
        raise RuntimeError("nobody can race")
    ready.sort(key=lambda d: (stable.load(d)["career"]["races"], d.name))
    entrants = ready[:championship.MAX_OWN]
    ch = championship.active(root) or championship.start(root, entrants)
    while not ch.get("done"):
        race = championship.build_race(root, ch)
        race.run(max_seconds=800)
        championship.finish_race(root, ch, race)
    table = championship.standings(ch)
    names = [ch["entrants"][r["entrant"]]["name"] for r in table]
    champ = ch["entrants"][ch["champion"]]
    rows = " | ".join(f"{ch['entrants'][r['entrant']]['name']} {r['points']}" for r in table)
    log.write(f"season {ch['season']}: **{champ['name']}** ({champ['kind']}) wins the title. {rows}", milestone=True)
    for line in ch.get("news", [])[1:]:
        log.write(f"  news: {line}", milestone=True)


def breed_pair(root: Path):
    """The best unrelated pair of studs, or None."""
    studs = [d for d in alive(root) if stable.can_breed(d) and stable.status(d) == "stud"]
    if len(studs) < 2:
        return None
    pairs = []
    for i, a in enumerate(studs):
        for b in studs[i + 1:]:
            ra, rb = stable.load(a), stable.load(b)
            related = bool(set(ra.get("parents", [])) & set(rb.get("parents", []))) \
                or a.name in rb.get("parents", []) or b.name in ra.get("parents", [])
            seen = sum(1 for d in stable.list_racers(root, include_dead=True)
                       if sorted(stable.load(d).get("parents", [])) == sorted([a.name, b.name]))
            pairs.append((related, seen, -(skill(root, a) + skill(root, b)), a, b))
    pairs.sort(key=lambda p: p[:3])
    return pairs[0][3], pairs[0][4]


def foal_name(root: Path, sire: Path, dam: Path, rng: random.Random) -> str:
    used = {stable.load(d)["name"] for d in stable.list_racers(root, include_dead=True)}
    family = stable.load(sire if rng.random() < 0.5 else dam)["name"].split()[-1]
    for _ in range(200):
        name = f"{rng.choice(FIRST_NAMES)} {family}"
        if name not in used:
            return name
    return f"{rng.choice(FIRST_NAMES)} {family} {len(used)}"


def breed_one(root: Path, log: Log, workers: int, fast: bool, rng: random.Random, criterion: str) -> bool:
    if sum(1 for d in alive(root) if stable.can_race(d)) >= RACING_CAP:
        return False
    pair = breed_pair(root)
    if pair is None:
        return False
    sire, dam = pair
    name = foal_name(root, sire, dam, rng)
    foal = stable.mate(root, sire, dam, name, criterion)
    t0 = time.time()
    log.write(f"breeding **{name}**: {stable.load(sire)['name']} x {stable.load(dam)['name']} ({criterion})", milestone=True)
    kw = dict(litter=4, shortlist=2, camp_generations=1, camp_population=8) if fast else {}
    stable.breed(foal, workers=workers, **kw)
    racer = stable.load(foal)
    log.write(f"  born {name}: gen {generation(root, foal)}, {cartraits.describe(racer['traits'])}, "
              f"aggression {racer['aggression']}, caution {racer['caution']} ({(time.time() - t0) / 60:.1f} min)",
              milestone=True)
    return True


def upskill_foals(root: Path, log: Log, workers: int, population: int, generations: int) -> None:
    for d in alive(root):
        racer = stable.load(d)
        if racer.get("parents") and "certificate" in racer and len(racer["versions"]) == 1 \
                and stable.can_train(d) and stable.training_left(d) >= generations:
            stable.upskill(d, racer["aggression"], racer["caution"],
                           [{"name": "Scripted car", "kind": "scripted"},
                            {"name": "Itself (its own best so far)", "kind": "self"}], generations)
            t0 = time.time()
            stable.train(d, workers=workers, population=population)
            log.write(f"schooled {racer['name']} ({generations} generations, {(time.time() - t0) / 60:.1f} min)")


def train_between(root: Path, log: Log, workers: int, population: int, rng: random.Random, fast: bool) -> None:
    """Between races one racer goes back to school: a specialist course on one
    track (20 generations, enough to count as a specialist) or an all-rounder
    course (10), against scripted cars, itself and another racer."""
    short, long_ = (1, 2) if fast else (10, 20)
    candidates = [d for d in alive(root) if stable.can_race(d) and not stable.needs_training(d)
                  and stable.training_left(d) >= short]
    if not candidates:
        return
    candidates.sort(key=lambda d: (stable.training_planned(d), rng.random()))
    d = candidates[0]
    racer = stable.load(d)
    specialist = rng.random() < 0.4 and stable.training_left(d) >= long_
    focus = rng.choice(list(championship.TRACK_ORDER)) if specialist else None
    generations = long_ if specialist else short
    partners = [{"name": "Scripted car", "kind": "scripted"}, {"name": "Itself (its own best so far)", "kind": "self"}]
    others = [o for o in stable.partner_options(root, exclude=d.name) if o["kind"] == "file"]
    if others:
        partners.append(rng.choice(others))
    plan = f"a {stable.TRACK_NAMES[focus]} specialist course" if focus else "an all-rounder course"
    t0 = time.time()
    stable.upskill(d, racer["aggression"], racer["caution"], partners, generations, focus=focus)
    stable.train(d, workers=workers, population=population)
    log.write(f"between races **{racer['name']}** takes {plan} ({generations} generations, "
              f"{(time.time() - t0) / 60:.1f} min) with {', '.join(p['name'] for p in partners)}; now "
              f"{stable.specialty_text(d)}", milestone=True)


# ------------------------------------------------------------------ report

def racer_rows(root: Path) -> list[dict]:
    rows = []
    for d in stable.list_racers(root, include_dead=True):
        r = stable.load(d)
        exam = stable.latest_exam(d)
        s = rating.summary(root, f"racer:{d.name}")
        t = r.get("traits") or cartraits.default()
        rows.append({"id": d.name, "name": r["name"], "gen": generation(root, d), "status": stable.status(d),
                     "parents": [stable.load(root / p)["name"] for p in r.get("parents", [])],
                     "weight": t["weight"], "top_speed": t["top_speed"], "accel": t["accel"],
                     "handling": t["handling"], "braking": t["braking"],
                     "aggression": r["aggression"], "caution": r["caution"],
                     "rating": round(s["rating"]) if s else None, "peak": round(s["peak"]) if s else None,
                     "rated_races": s["races"] if s else 0,
                     "races": r["career"]["races"], "wins": r["career"]["wins"], "podiums": r["career"]["podiums"],
                     "titles": r["career"].get("titles", 0),
                     "specialty": stable.specialty(d)[0] or "all-rounder",
                     "tracks": s["tracks"] if s else {},
                     "pace": None if not exam or stable.pace(exam) is None else round(stable.pace(exam), 4)})
    return rows


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def fmt(x, nd=0):
    return "-" if x is None else f"{x:.{nd}f}"


def write_report(root: Path, start: float) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = racer_rows(root)
    (OUT / "state.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    rated = [r for r in rows if r["peak"] is not None and r["rated_races"] >= 5]
    lines = [f"# Dynasty report (after {(time.time() - start) / 3600:.1f} hours)", "",
             f"{len(rows)} racers so far, {stable.clock(root)} stable races, "
             f"{len(championship.past_seasons(root))} seasons.", ""]
    best = sorted(rated, key=lambda r: -r["peak"])
    lines += ["## Top 10 by peak rating", "", "| name | gen | car | stars T/A/H/B | agg/cau | kind | peak | titles | wins | races |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in best[:10]:
        lines.append(f"| {r['name']} | {r['gen']} | {r['weight']} | {r['top_speed']}/{r['accel']}/{r['handling']}/{r['braking']} "
                     f"| {r['aggression']}/{r['caution']} | {r['specialty']} | {r['peak']} | {r['titles']} | {r['wins']} | {r['races']} |")
    lines += ["", "## By generation", "", "| gen | racers | mean peak | best peak | mean pace | titles |", "|---|---|---|---|---|---|"]
    for g in sorted({r["gen"] for r in rows}):
        group = [r for r in rows if r["gen"] == g]
        peaks = [r["peak"] for r in group if r["peak"] is not None and r["rated_races"] >= 5]
        lines.append(f"| {g} | {len(group)} | {fmt(mean(peaks))} | {fmt(max(peaks) if peaks else None)} "
                     f"| {fmt(mean([r['pace'] for r in group]), 3)} | {sum(r['titles'] for r in group)} |")
    lines += ["", "## Which car wins?", "", "By car weight (racers with at least 5 rated races):", "",
              "| weight | racers | mean peak | titles | wins |", "|---|---|---|---|---|"]
    for w in ("light", "medium", "heavy"):
        group = [r for r in rated if r["weight"] == w]
        lines.append(f"| {w} | {len(group)} | {fmt(mean([r['peak'] for r in group]))} | "
                     f"{sum(r['titles'] for r in group)} | {sum(r['wins'] for r in group)} |")
    lines += ["", "Mean stars of the top third by peak rating against the rest:", "",
              "| group | top speed | accel | handling | braking | aggression | caution |", "|---|---|---|---|---|---|---|"]
    if len(best) >= 3:
        k = max(1, len(best) // 3)
        for label, group in (("top third", best[:k]), ("the rest", best[k:])):
            lines.append(f"| {label} | " + " | ".join(fmt(mean([r[key] for r in group]), 2) for key in
                         ("top_speed", "accel", "handling", "braking", "aggression", "caution")) + " |")
    lines += ["", "Specialists against all-rounders (at least 5 rated races):", "",
              "| kind | racers | mean peak | titles | wins |", "|---|---|---|---|---|"]
    for kind, group in (("all-rounder", [r for r in rated if r["specialty"] == "all-rounder"]),
                        ("specialist", [r for r in rated if r["specialty"] != "all-rounder"])):
        lines.append(f"| {kind} | {len(group)} | {fmt(mean([r['peak'] for r in group]))} | "
                     f"{sum(r['titles'] for r in group)} | {sum(r['wins'] for r in group)} |")
    lines += ["", "Best rating on each track (track kings):", "", "| track | racer | rating | kind | car |", "|---|---|---|---|---|"]
    for track in championship.TRACK_ORDER:
        field = [(r["tracks"][track], r) for r in rows if r["tracks"].get(track) and r["rated_races"] >= 3]
        if field:
            value, r = max(field, key=lambda x: x[0])
            lines.append(f"| {stable.TRACK_NAMES[track]} | {r['name']} | {value:.0f} | {r['specialty']} | {r['weight']} "
                         f"{r['top_speed']}/{r['accel']}/{r['handling']}/{r['braking']} |")
    titled = sorted([r for r in rows if r["titles"]], key=lambda r: -r["titles"])
    lines += ["", "## Champions", ""] + [f"- {r['name']} (gen {r['gen']}, {r['weight']}): {r['titles']} title(s)" for r in titled]
    rec = records.load(root)
    lines += ["", "## Track records", ""] + [f"- {t}: {v['time']:.2f} s by {v['name']} (season {v['season']})" for t, v in rec.items()]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--population", type=int, default=stable.POPULATION)
    ap.add_argument("--fast", action="store_true", help="tiny settings, to test the loop")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    meta = DATA / "run.json"
    state = json.loads(meta.read_text()) if meta.exists() else {"start": time.time(), "hours": args.hours}
    if not meta.exists():
        meta.write_text(json.dumps(state))
    start, end = state["start"], state["start"] + state["hours"] * 3600
    ROOT.mkdir(parents=True, exist_ok=True)
    migrate.ensure()
    if args.report:
        write_report(ROOT, start)
        return 0
    log = Log(start)
    log.write(f"dynasty running until hour {state['hours']}", milestone=True)
    rng = random.Random(args.seed + len(stable.list_racers(ROOT, include_dead=True)))
    population = 16 if args.fast else args.population
    founder_gens = 1 if args.fast else FOUNDER_GENERATIONS
    foal_gens = 1 if args.fast else FOAL_GENERATIONS
    failures = 0
    cycle = 0
    last_save = 0
    while time.time() < end:
        try:
            found(ROOT, log, founder_gens)
            train_pending(ROOT, log, args.workers, population)
            for d in stable.list_racers(ROOT):                    # a foal bred but never finished (a restart)
                if stable.is_breeding(d):
                    stable.breed(d, workers=args.workers)
            upskill_foals(ROOT, log, args.workers, population, foal_gens)
            if any(stable.can_race(d) for d in alive(ROOT)):
                run_season(ROOT, log)
            else:                                                  # everyone has retired: breed until someone can race
                log.write("nobody is racing; breeding the next foals first", milestone=True)
            if breed_one(ROOT, log, args.workers, args.fast, rng, "fastest" if cycle % 2 == 0 else "learner"):
                upskill_foals(ROOT, log, args.workers, population, foal_gens)
            train_between(ROOT, log, args.workers, population, rng, args.fast)
            cycle += 1
            write_report(ROOT, start)
            hour = int((time.time() - start) // 3600)
            if hour > last_save:                                       # a loadable save every hour
                last_save = hour
                snapshot.save("dynasty", ROOT)
                log.write(f"saved a loadable snapshot (saves/dynasty.zip)", milestone=True)
            failures = 0
        except Exception:                                          # keep going; log the trouble
            failures += 1
            log.write("error:\n```\n" + traceback.format_exc() + "```", milestone=True)
            if failures >= 5:
                log.write("too many errors in a row; stopping", milestone=True)
                break
            time.sleep(5)
    write_report(ROOT, start)
    log.write(f"saved {snapshot.save('dynasty-final', ROOT).name}", milestone=True)
    log.write("dynasty finished", milestone=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
