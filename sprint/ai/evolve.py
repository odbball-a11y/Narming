"""Neuroevolution in two phases: driving school, then racing school.

Each generation is a population of neural-network drivers.  Every driver is
tested, the best survive, and the next generation is bred from mutated copies
of the good ones.

Phase 1, driving school: the whole population drives the track at once as
ghosts (no contact between cars).  Score = distance covered in a fixed time,
less damage.  It ends when the champion laps every track cleanly; that
generation is the "base driver".

Phase 2, racing school: every driver runs several real four-car races per
generation, with collisions, damage and drafting, from every grid position.
All drivers in a generation face the same races, so they are compared fairly.
Rivals start as scripted cars, then include the driver's own recent
champions (self-play) and a hall of fame of older ones.  Score = finishing
place, distance, damage and collisions it caused; optionally, early on, small
bonuses for overtakes, not being overtaken and time in the draft, fading out.

Everything is seeded: the same settings and seed give the same run.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import sim.scripted  # noqa: F401
from sim import tuning
from sim.driver import Controls, create_driver
from sim.track import Track
from sim.world import World

from .brain import (DECISION_TICKS, DEFAULT_ARCH, N_INPUTS, Brain, NeuralDriver, Population,
                    n_weights, observe, random_weights, to_controls)

RUNS_DIR = Path(__file__).resolve().parent.parent / "training"
FORMAT = 2

# Seconds per test: about two laps for a good driver.  Training races must be
# long enough for damage to cost real time, or barging pays.
SOLO_SECONDS = {"speedway": 30.0, "technical": 46.0}
RACE_SECONDS = {"speedway": 30.0, "technical": 46.0}
# Roughly how long a good lap takes, to turn --race-laps into seconds.
LAP_SECONDS = {"speedway": 14.0, "technical": 23.0}
DEFAULT_SECONDS = 40.0

# Driving-school score: laps covered minus this per unit of damage picked up.
# At 0.25 drivers learned to bounce off the barriers on Technical rather
# than brake (about 50% damage in a clean-air time trial).
SOLO_DAMAGE_WEIGHT = 1.0

# Starting damage used in driving tests, rotating by generation.
SOLO_DAMAGE = (0.0, 0.25, 0.5)

# A ghost that makes no forward progress for this long is retired early.
STALL_SECONDS = 2.5

# Driving school ends when the champion covers this many laps of every
# track in the solo test with at most this much damage.
PHASE1_LAPS = 1.9
PHASE1_DAMAGE = 0.05

# Racing school curriculum: scripted rivals only for the first generations,
# then a mix.  Chances for each rival seat once the mix starts:
SCRIPTED_ONLY_GENS = 10
RIVAL_MIX = (("scripted", 0.4), ("recent", 0.4), ("hall", 0.2))
RECENT_GENS = 6          # "recent" = champions of the last few generations
HALL_EVERY = 10          # every 10th racing-school champion joins the hall of fame

# Optional shaping bonuses fade to nothing over this many racing generations.
BONUS_FADE = 60

# In racing school, how much of the score is the solo test (keeps it fast).
SOLO_SHARE = 0.2

_tracks: dict[str, Track] = {}


def get_track(name: str) -> Track:
    if name not in _tracks:
        _tracks[name] = Track.load(name)
    return _tracks[name]


# ---------------------------------------------------------------- progress

class _Progress:
    """Distance each car has really covered along the lap (forwards counts
    up, backwards counts down), plus early retirement of stuck cars."""

    def __init__(self, world: World, indices):
        self.world = world
        self.indices = list(indices)
        self.length = world.track.length
        self.last_s = [world.cars[i].s for i in self.indices]
        self.total = [0.0] * len(self.indices)
        self.best = [0.0] * len(self.indices)
        self.best_tick = [0] * len(self.indices)
        self.stall_ticks = int(STALL_SECONDS * tuning.TICK_RATE)

    def update(self, retire: bool = True) -> None:
        world, half = self.world, self.length / 2.0
        for k, i in enumerate(self.indices):
            car = world.cars[i]
            if car.retired:
                continue
            d = car.s - self.last_s[k]
            if d > half:
                d -= self.length
            elif d < -half:
                d += self.length
            self.last_s[k] = car.s
            self.total[k] += d
            if self.total[k] > self.best[k] + 1.0:
                self.best[k] = self.total[k]
                self.best_tick[k] = world.tick
            elif retire and world.tick - self.best_tick[k] > self.stall_ticks:
                car.retired = True


# --------------------------------------------------------- phase 1 (solo)

class PackRun:
    """A whole population on the track at once, as ghosts.

    Used for the solo test and, one tick per call, for the game's live view
    of a generation, so what you watch is exactly what was scored.
    """

    def __init__(self, weights: np.ndarray, arch: dict, track_name: str, seconds: float | None = None,
                 slot: int = 0, damage: float = 0.0):
        self.track = get_track(track_name)
        self.count = len(weights)
        self.world = World(self.track, slots=[slot] * self.count, ghost=True, laps=10 ** 9)
        for car in self.world.cars:
            car.damage = damage
        self.brains = Population(weights, arch)
        self.progress = _Progress(self.world, range(self.count))
        self.ticks = int((seconds or SOLO_SECONDS.get(track_name, DEFAULT_SECONDS)) * tuning.TICK_RATE)
        self.controls = [Controls()] * self.count
        self.done = False

    @property
    def alive(self) -> int:
        return sum(1 for car in self.world.cars if not car.retired)

    def laps(self) -> list[float]:
        return [p / self.track.length for p in self.progress.total]

    def step(self) -> None:
        if self.done:
            return
        world, cars = self.world, self.world.cars
        if world.tick % DECISION_TICKS == 0:
            self.progress.update()
            if all(car.retired for car in cars):
                self.done = True
                return
            idle = [0.0] * N_INPUTS
            obs = np.array([idle if cars[i].retired else observe(world, i) for i in range(self.count)])
            self.controls = [to_controls(s, p) for s, p in self.brains.act(obs).tolist()]
        world.step(self.controls)
        if world.tick >= self.ticks:
            self.progress.update(retire=False)
            self.done = True


def test_solo(weights: np.ndarray, arch: dict, track_name: str, seconds: float | None = None,
              slot: int = 0, damage: float = 0.0) -> dict:
    """Run every driver in `weights` on the track at once, as ghosts, from
    grid `slot` with `damage` already on the car."""
    run = PackRun(weights, arch, track_name, seconds, slot, damage)
    while not run.done:
        run.step()
    cars = run.world.cars
    return {"laps": run.laps(), "damage": [car.damage - damage for car in cars],
            "best_lap": [car.best_lap for car in cars]}


# --------------------------------------------------------- phase 2 (race)

class RaceStats:
    """Racecraft numbers for car 0 of a world: collisions it caused and
    suffered, wall hits, overtakes made, times overtaken, time in the draft."""

    MARGIN = 1.0    # a pass counts once the cars are this far apart

    def __init__(self, world: World, me: int = 0):
        self.world = world
        self.me = me
        self.others = [j for j in range(len(world.cars)) if j != me]
        self.fault = 0.0
        self.suffered = 0.0
        self.walls = 0
        self.overtakes = 0
        self.passed = 0
        self.draft_ticks = 0
        self.ticks = 0
        self.ahead = {j: self._diff(j) > 0.0 for j in self.others}

    def _diff(self, j: int) -> float:
        w = self.world
        return w.race_progress(w.cars[self.me]) - w.race_progress(w.cars[j])

    def on_tick(self, events) -> None:
        world, me = self.world, self.me
        car = world.cars[me]
        self.ticks += 1
        if car.draft > 0.1:
            self.draft_ticks += 1
        for event in events:
            if event[0] == "wall" and event[1] == me:
                self.walls += 1
            elif event[0] == "car" and me in event[1:3]:
                other = world.cars[event[2] if event[1] == me else event[1]]
                half = world.track.length / 2.0
                gap = (other.s - car.s + half) % world.track.length - half
                if gap > 1.5:          # I ran into the back of them
                    self.fault += 1.0
                elif gap < -1.5:       # they ran into me
                    self.suffered += 1.0
                else:                  # side by side: shared
                    self.fault += 0.5
                    self.suffered += 0.5
        if world.tick % DECISION_TICKS == 0:
            for j in self.others:
                d = self._diff(j)
                if not self.ahead[j] and d > self.MARGIN:
                    self.ahead[j] = True
                    self.overtakes += 1
                elif self.ahead[j] and d < -self.MARGIN:
                    self.ahead[j] = False
                    self.passed += 1

    def place(self) -> int:
        """1 = leading.  Ties count against me."""
        return 1 + sum(1 for j in self.others if self._diff(j) <= 0.0)

    def draft_share(self) -> float:
        return self.draft_ticks / self.ticks if self.ticks else 0.0


def test_race(weights: np.ndarray, arch: dict, scenario: dict) -> dict:
    """One real four-car race per driver in `weights`, all stepped together.

    scenario: {"track", "slot" (the learner's grid place), "rivals": three
    entries, each "scripted" or a weight vector, "seconds"}.
    """
    track = get_track(scenario["track"])
    slot = scenario["slot"]
    count = len(weights)
    learners = Population(weights, arch)
    others = [s for s in range(4) if s != slot]
    worlds, scripted, stats = [], [], []
    for _ in range(count):
        world = World(track, slots=[slot] + others, laps=10 ** 9)
        drivers = {}
        for k, rival in enumerate(scenario["rivals"]):
            if isinstance(rival, str):
                drivers[k + 1] = create_driver(rival, slot=others[k])
                drivers[k + 1].reset(world, k + 1)
        worlds.append(world)
        scripted.append(drivers)
        stats.append(RaceStats(world))
    brains = {k + 1: Brain(r, arch, batch=count)
              for k, r in enumerate(scenario["rivals"]) if not isinstance(r, str)}
    progress = [_Progress(w, [0]) for w in worlds]
    seconds = scenario.get("seconds") or RACE_SECONDS.get(track.key, DEFAULT_SECONDS)
    ticks = int(seconds * tuning.TICK_RATE)
    mine = [Controls()] * count
    theirs = {k: [Controls()] * count for k in brains}
    for tick in range(ticks):
        if tick % DECISION_TICKS == 0:
            for p in progress:
                p.update(retire=False)
            obs = np.array([observe(w, 0) for w in worlds])
            mine = [to_controls(s, p) for s, p in learners.act(obs).tolist()]
            for k, brain in brains.items():
                out = brain.act(np.array([observe(w, k) for w in worlds]))
                theirs[k] = [to_controls(s, p) for s, p in out.tolist()]
        for n, world in enumerate(worlds):
            controls = [mine[n]]
            for k in (1, 2, 3):
                controls.append(theirs[k][n] if k in brains else scripted[n][k].act(world, k))
            stats[n].on_tick(world.step(controls))
    for p in progress:
        p.update(retire=False)
    return {
        "place": [s.place() for s in stats],
        "laps": [p.total[0] / track.length for p in progress],
        "damage": [w.cars[0].damage for w in worlds],
        "fault": [s.fault for s in stats],
        "suffered": [s.suffered for s in stats],
        "walls": [s.walls for s in stats],
        "overtakes": [s.overtakes for s in stats],
        "passed": [s.passed for s in stats],
        "draft": [s.draft_share() for s in stats],
    }


# How a racing-school race is scored.  Saved in each run's config, so a run
# keeps the weights it was started with.  Lesson from the first trial: with a
# damage weight of 0.8 and a caused-collision weight of 0.08, drivers learned
# to win by barging (place went up, damage and collisions did not come down).
RACE_WEIGHTS = {
    "place": [1.0, 0.6, 0.3, 0.0],   # points for finishing 1st..4th
    "laps": 0.5,                     # per lap covered
    "damage": 2.0,                   # per unit of damage (1 = wrecked)
    "fault": 0.25,                   # per collision it caused
    "walls": 0.03,                   # per barrier hit
    "bonus_overtake": 0.06,          # optional, fading: per pass made
    "bonus_passed": 0.06,            # optional, fading: per time overtaken
    "bonus_draft": 0.3,              # optional, fading: per share of time in a tow
}


def race_score(result: dict, bonus: float, weights: dict | None = None) -> np.ndarray:
    """Score of each driver in one race (higher is better).

    Results: finishing place, distance covered, damage, collisions caused.
    `bonus` (0..1) scales the optional shaping terms.
    """
    w = weights or RACE_WEIGHTS
    r = {k: np.asarray(v, dtype=float) for k, v in result.items()}
    score = (np.asarray(w["place"])[r["place"].astype(int) - 1] + w["laps"] * r["laps"]
             - w["damage"] * r["damage"] - w["fault"] * r["fault"] - w["walls"] * r["walls"])
    if bonus:
        score += bonus * (w["bonus_overtake"] * r["overtakes"] - w["bonus_passed"] * r["passed"]
                          + w["bonus_draft"] * r["draft"])
    return score


# --------------------------------------------------------------- scoring

def _job(args):
    kind, weights, arch, task = args
    if kind == "solo":
        name, setup = task
        return test_solo(weights, arch, name, slot=setup["slot"], damage=setup["damage"])
    return test_race(weights, arch, task)


def solo_setup(gen: int) -> dict:
    """Driving-test conditions for a generation (the same for all its
    drivers): the grid box and the damage the car starts with rotate, so
    drivers learn to cope with any start and with a damaged car.  Without
    this they only ever practised from box 1 with a perfect car, and drove
    badly the first time either changed."""
    return {"slot": (gen - 1) % 4, "damage": SOLO_DAMAGE[(gen - 1) // 4 % len(SOLO_DAMAGE)]}


def score_population(pop: np.ndarray, arch: dict, tracks: list[str], scenarios=None,
                     bonus: float = 0.0, pool=None, chunks: int = 1,
                     weights: dict | None = None, setup: dict | None = None) -> tuple[np.ndarray, dict]:
    """Fitness for every driver (higher is better) and per-driver averages.

    No scenarios: driving school (solo only).  With scenarios: racing school,
    SOLO_SHARE of the solo score plus the rest from the races.
    """
    pieces = np.array_split(np.arange(len(pop)), max(1, min(chunks, len(pop))))
    setup = setup or {"slot": 0, "damage": 0.0}
    jobs = [("solo", pop[p], arch, (name, setup)) for name in tracks for p in pieces]
    for scenario in scenarios or []:
        jobs += [("race", pop[p], arch, scenario) for p in pieces]
    results = list(pool.map(_job, jobs)) if pool else [_job(j) for j in jobs]

    def merged(start: int) -> dict:
        out: dict = {}
        for k in range(len(pieces)):
            for key, values in results[start + k].items():
                out.setdefault(key, []).extend(values)
        return out

    solo = np.zeros(len(pop))
    k = 0
    for _ in tracks:
        part = merged(k)
        solo += np.array(part["laps"]) - SOLO_DAMAGE_WEIGHT * np.array(part["damage"])
        k += len(pieces)
    solo /= len(tracks)
    if not scenarios:
        return solo, {}
    race = np.zeros(len(pop))
    totals: dict = {}
    for _ in scenarios:
        part = merged(k)
        race += race_score(part, bonus, weights)
        for key in ("place", "damage", "fault", "overtakes", "passed", "draft"):
            totals[key] = totals.get(key, 0.0) + np.asarray(part[key], dtype=float)
        k += len(pieces)
    race /= len(scenarios)
    averages = {key: value / len(scenarios) for key, value in totals.items()}
    return SOLO_SHARE * solo + (1.0 - SOLO_SHARE) * race, averages


# ---------------------------------------------------------------- breeding

def breed(sorted_pop: np.ndarray, rng: np.random.Generator, size: int, elites: int) -> np.ndarray:
    """Next generation from a population sorted best first.

    The best `elites` go through unchanged.  Every other child is a copy of
    a good parent (sometimes mixed with a second parent) with random changes;
    some children get small changes, to refine, and some large, to explore.
    """
    n = sorted_pop.shape[1]
    parents = max(2, len(sorted_pop) // 4)
    children = [sorted_pop[i].copy() for i in range(min(elites, len(sorted_pop)))]
    while len(children) < size:
        child = sorted_pop[min(rng.integers(0, parents, 2))].copy()     # 2-way tournament
        if rng.random() < 0.3:
            other = sorted_pop[min(rng.integers(0, parents, 2))]
            mask = rng.random(n) < 0.5
            child[mask] = other[mask]
        sigma = rng.choice([0.02, 0.05, 0.1, 0.2])
        touched = rng.random(n) < rng.choice([0.05, 0.2, 1.0])
        child += rng.normal(0.0, sigma, n) * touched
        children.append(child)
    return np.array(children)


# ------------------------------------------------------------------- exams

def exam(weights: np.ndarray, arch: dict, tracks: list[str]) -> dict:
    """Standard report card for one driver, the same for every generation so
    generations can be compared: a solo time trial, and a three-lap race
    against three scripted cars starting from the back of the grid."""
    from sim.race import FINISHED, Race
    report = {}
    for name in tracks:
        solo = test_solo(weights[None, :], arch, name)
        race = Race(name, [(3, NeuralDriver(weights, arch, "Evolved")), (0, "scripted"),
                           (1, "scripted"), (2, "scripted")], laps=3)
        stats = RaceStats(race.world)
        limit = int(150.0 * tuning.TICK_RATE)
        while race.phase != FINISHED and race.world.tick < limit:
            events = race.step()
            if race.phase != "countdown" and not race.world.cars[0].finished:
                stats.on_tick(events)
        row = next(r for r in race.results() if r["car"] == 0)
        car = race.world.cars[0]
        report[name] = {
            "solo_laps": round(solo["laps"][0], 3),
            "solo_best_lap": solo["best_lap"][0],
            "solo_damage": round(solo["damage"][0], 3),
            "race_place": row["place"],
            "race_finished": row["finished"],
            "race_laps": row["laps"],
            "race_time": row["time"],
            "race_best_lap": row["best_lap"],
            "race_hits": stats.fault + stats.suffered + stats.walls,
            "race_fault": stats.fault,
            "race_walls": stats.walls,
            "race_overtakes": stats.overtakes,
            "race_passed": stats.passed,
            "race_draft": round(stats.draft_share(), 3),
            "race_damage": round(car.damage, 3),
        }
    return report


# -------------------------------------------------------------------- runs

def gen_path(run_dir: Path, gen: int) -> Path:
    return Path(run_dir) / f"gen_{gen:04d}.npz"


def list_generations(run_dir: Path) -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in Path(run_dir).glob("gen_*.npz"))


def load_generation(run_dir: Path, gen: int) -> dict:
    """{'pop': drivers sorted best first, 'fitness': their scores}."""
    with np.load(gen_path(run_dir, gen)) as data:
        return {"pop": data["pop"].astype(np.float64), "fitness": data["fitness"]}


def load_config(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "config.json").read_text(encoding="utf-8"))


def load_history(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "history.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []      # caught mid-write by the trainer; try again next time


def list_runs() -> list[str]:
    """Runs this version can read (older formats are skipped)."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for p in sorted(RUNS_DIR.iterdir()):
        try:
            if (p / "history.json").exists() and load_config(p).get("format") == FORMAT:
                runs.append(p.name)
        except (OSError, ValueError):
            continue
    return runs


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def _archive_old_run(run_dir: Path) -> Path:
    """Move a run made by an older version aside (nothing is deleted)."""
    k = 1
    target = run_dir.with_name(f"{run_dir.name}-v1")
    while target.exists():
        k += 1
        target = run_dir.with_name(f"{run_dir.name}-v1-{k}")
    run_dir.rename(target)
    return target


def phase2_start(config: dict, history: list[dict]) -> int | None:
    if config.get("phase2_start"):
        return config["phase2_start"]
    return next((h["gen"] for h in history if h["mode"] == "race"), None)


def make_scenarios(config: dict, gen: int, start: int, history_gens: list[int]) -> list[dict]:
    """The racing-school races for generation `gen` (the same for every
    driver in it).  Rivals are "scripted" or the generation number of a
    champion whose weights to use."""
    rng = np.random.default_rng([config["seed"], gen, 7])
    tracks = config["tracks"]
    count = config["races_per_track"] * len(tracks)
    rel = gen - start
    base = start - 1
    recent = [g for g in history_gens if start <= g < gen][-RECENT_GENS:]
    hall = [g for g in history_gens if g == base or (g >= start and (g - start) % HALL_EVERY == 0 and g < gen)]
    slots = list(rng.permutation(4))
    scenarios = []
    for k in range(count):
        rivals = []
        for _ in range(3):
            kind = "scripted"
            if rel >= SCRIPTED_ONLY_GENS:
                pick = rng.random()
                for name, chance in RIVAL_MIX:
                    if pick < chance:
                        kind = name
                        break
                    pick -= chance
            pool = {"recent": recent, "hall": hall}.get(kind)
            rivals.append(int(rng.choice(pool)) if pool else "scripted")
        scenarios.append({"track": tracks[k % len(tracks)], "slot": int(slots[k % 4]), "rivals": rivals,
                          "seconds": config.get("race_seconds", RACE_SECONDS).get(
                              tracks[k % len(tracks)], DEFAULT_SECONDS)})
        if k % 4 == 3:
            slots = list(rng.permutation(4))
    return scenarios


def train(run: str = "default", generations: int = 50, population: int = 80, elites: int = 6,
          seed: int = 0, tracks: list[str] | None = None, phase2_from: int | None = None,
          arch: dict | None = None, races_per_track: int = 2, race_bonuses: bool = True,
          race_laps: float | None = None,
          workers: int = 0, on_generation=None, log=print) -> Path:
    """Train (or continue) a run.  Writes one file per generation plus
    history.json into training/<run>/, which the game reads while this runs.

    Settings are fixed when a run is created; continuing a run uses the saved
    ones.  `phase2_from=None` starts racing school automatically once the
    champion laps every track cleanly.
    """
    run_dir = RUNS_DIR / run
    config_path = run_dir / "config.json"
    if config_path.exists() and load_config(run_dir).get("format") != FORMAT:
        moved = _archive_old_run(run_dir)
        log(f"note: '{run}' was made by an older version; moved it to {moved.name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        config = load_config(run_dir)
    else:
        config = {"format": FORMAT, "population": population, "elites": elites, "seed": seed,
                  "tracks": tracks or Track.available(), "phase2_from": phase2_from,
                  "phase2_start": phase2_from, "arch": arch or dict(DEFAULT_ARCH),
                  "races_per_track": races_per_track, "race_bonuses": race_bonuses,
                  "race_weights": dict(RACE_WEIGHTS),
                  "race_seconds": ({t: round(race_laps * LAP_SECONDS.get(t, DEFAULT_SECONDS / 2), 1)
                                    for t in (tracks or Track.available())}
                                   if race_laps else dict(RACE_SECONDS)),
                  "inputs": N_INPUTS, "tuning_id": tuning.physics_fingerprint()}
        _write_json(config_path, config)
    arch, size, tracks, seed = config["arch"], config["population"], config["tracks"], config["seed"]
    history = load_history(run_dir)
    done = list_generations(run_dir)
    history = [h for h in history if h["gen"] in done]
    start_gen = (done[-1] + 1) if done else 1
    if done:
        last = load_generation(run_dir, done[-1])
        pop = breed(last["pop"], np.random.default_rng([seed, done[-1]]), size, config["elites"])
    else:
        pop = random_weights(np.random.default_rng([seed, 0]), size, arch)
    assert pop.shape[1] == n_weights(arch)
    champions: dict[int, np.ndarray] = {}

    def champion_of(gen: int) -> np.ndarray:
        if gen not in champions:
            champions[gen] = load_generation(run_dir, gen)["pop"][0]
        return champions[gen]

    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        for gen in range(start_gen, start_gen + generations):
            start = phase2_start(config, history)
            if start is None and history and all(
                    t["solo_laps"] >= PHASE1_LAPS and t["solo_damage"] <= PHASE1_DAMAGE
                    for t in history[-1]["exam"].values()):
                start = gen
                config["phase2_start"] = gen
                _write_json(config_path, config)
            racing = start is not None and gen >= start
            scenarios, resolved, bonus = [], None, 0.0
            if racing:
                scenarios = make_scenarios(config, gen, start, [h["gen"] for h in history])
                resolved = [dict(s, rivals=[r if r == "scripted" else champion_of(r) for r in s["rivals"]])
                            for s in scenarios]
                if config["race_bonuses"]:
                    bonus = max(0.0, 1.0 - (gen - start) / BONUS_FADE)
            fitness, averages = score_population(pop, arch, tracks, resolved, bonus, pool,
                                                 chunks=max(1, workers),
                                                 weights=config.get("race_weights"),
                                                 setup=solo_setup(gen))
            order = np.argsort(-fitness, kind="stable")
            fitness = fitness[order]
            np.savez_compressed(gen_path(run_dir, gen), pop=pop[order].astype(np.float32), fitness=fitness)
            # Carry on from exactly what was saved (float32), so stopping and
            # continuing a run gives the same result as never stopping.
            pop = load_generation(run_dir, gen)["pop"]
            entry = {
                "gen": gen, "mode": "race" if racing else "solo",
                "best": round(float(fitness[0]), 4),
                "mean": round(float(fitness.mean()), 4),
                "median": round(float(np.median(fitness)), 4),
                "bonus": round(bonus, 3),
                "solo_setup": solo_setup(gen),
                "exam": exam(pop[0], arch, tracks),
            }
            if racing:
                best = order[0]
                entry["training"] = {key: round(float(values[best]), 3) for key, values in averages.items()}
                entry["scenarios"] = scenarios
            history.append(entry)
            _write_json(run_dir / "history.json", history)
            if on_generation:
                on_generation(entry)
            pop = breed(pop, np.random.default_rng([seed, gen]), size, config["elites"])
    finally:
        if pool:
            pool.shutdown()
    return run_dir
