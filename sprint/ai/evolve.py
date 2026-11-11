"""Neuroevolution: breed better drivers generation by generation.

Each generation is a population of small networks.  Every driver is tested,
the best survive, and the next generation is made from mutated copies of the
good ones.  Two kinds of test:

  solo  the whole population drives the track at once as ghosts (no contact
        between cars); score = distance covered in a fixed time.
  race  each driver runs a real four-car race with collisions, damage and
        drafting against scripted cars and champions of earlier generations.

Everything is seeded: the same seed gives the same run.
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

from .brain import DECISION_TICKS, N_HIDDEN, N_INPUTS, N_OUTPUTS, N_WEIGHTS, NeuralDriver, Population, \
    observe, to_controls, unpack

RUNS_DIR = Path(__file__).resolve().parent.parent / "training"

# Seconds each driver gets per track.  About two laps for a good driver.
TEST_SECONDS = {"speedway": 30.0, "technical": 46.0}
DEFAULT_TEST_SECONDS = 40.0

# A driver that makes no forward progress for this long is retired early.
STALL_SECONDS = 2.5

_tracks: dict[str, Track] = {}


def get_track(name: str) -> Track:
    if name not in _tracks:
        _tracks[name] = Track.load(name)
    return _tracks[name]


def random_population(rng: np.random.Generator, size: int) -> np.ndarray:
    pop = rng.normal(0.0, 0.5, (size, N_WEIGHTS))
    # Start with a bias toward pressing the throttle, so generation 1 moves.
    pop[:, -1] += 0.8
    return pop


# ------------------------------------------------------------------- tests

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


class PackRun:
    """A whole population on the track at once, as ghosts.

    Used for the solo test and, one tick per call, for the game's live view
    of a generation, so what you watch is exactly what was scored.
    """

    def __init__(self, weights: np.ndarray, track_name: str, seconds: float | None = None):
        self.track = get_track(track_name)
        self.count = len(weights)
        self.world = World(self.track, slots=[0] * self.count, ghost=True, laps=10 ** 9)
        self.brains = Population(weights)
        self.progress = _Progress(self.world, range(self.count))
        self.ticks = int((seconds or TEST_SECONDS.get(track_name, DEFAULT_TEST_SECONDS))
                         * tuning.TICK_RATE)
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
            obs = np.array([idle if cars[i].retired else observe(world, i)
                            for i in range(self.count)])
            self.controls = [to_controls(s, p) for s, p in self.brains.act(obs).tolist()]
        world.step(self.controls)
        if world.tick >= self.ticks:
            self.progress.update(retire=False)
            self.done = True


def test_solo(weights: np.ndarray, track_name: str, seconds: float | None = None) -> dict:
    """Run every driver in `weights` on the track at once, as ghosts."""
    run = PackRun(weights, track_name, seconds)
    while not run.done:
        run.step()
    cars = run.world.cars
    return {
        "laps": run.laps(),
        "damage": [car.damage for car in cars],
        "best_lap": [car.best_lap for car in cars],
    }


def test_race(weights: np.ndarray, track_name: str, rivals: list, slot: int,
              seconds: float | None = None) -> dict:
    """One real four-car race per driver, all stepped together.

    `rivals` is a list of three opponents, each "scripted" or a weight
    vector (an earlier champion).  The driver under test starts from `slot`.
    """
    track = get_track(track_name)
    count = len(weights)
    brains = Population(weights)
    order = [s for s in range(4) if s != slot]
    worlds, opponents, trackers = [], [], []
    for _ in range(count):
        world = World(track, slots=[slot] + order, laps=10 ** 9)
        drivers = []
        for k, rival in enumerate(rivals):
            if isinstance(rival, str):
                drivers.append(create_driver(rival, slot=order[k]))
            else:
                drivers.append(NeuralDriver(rival))
            drivers[-1].reset(world, k + 1)
        worlds.append(world)
        opponents.append(drivers)
        trackers.append(_Progress(world, range(4)))
    ticks = int((seconds or TEST_SECONDS.get(track_name, DEFAULT_TEST_SECONDS) * 0.7) * tuning.TICK_RATE)
    mine = [Controls()] * count
    hits = [0] * count
    idle = [0.0] * N_INPUTS
    for tick in range(ticks):
        if tick % DECISION_TICKS == 0:
            for tracker in trackers:
                tracker.update(retire=False)
            obs = np.array([observe(w, 0) for w in worlds])
            mine = [to_controls(s, p) for s, p in brains.act(obs).tolist()]
        for k, world in enumerate(worlds):
            controls = [mine[k]] + [d.act(world, j + 1) for j, d in enumerate(opponents[k])]
            for event in world.step(controls):
                if (event[0] == "wall" and event[1] == 0) or (event[0] == "car" and 0 in event[1:3]):
                    hits[k] += 1
    laps, damage, beaten = [], [], []
    for k, world in enumerate(worlds):
        trackers[k].update(retire=False)
        total = trackers[k].total
        # Everyone started at a different grid place; compare distance gained.
        laps.append(total[0] / track.length)
        beaten.append(sum(1 for j in range(1, 4) if total[0] > total[j]))
        damage.append(world.cars[0].damage)
    return {"laps": laps, "damage": damage, "beaten": beaten, "hits": hits,
            "best_lap": [w.cars[0].best_lap for w in worlds]}


def _job(args):
    kind, weights, track_name, extra = args
    if kind == "solo":
        return test_solo(weights, track_name)
    return test_race(weights, track_name, *extra)


RIVAL_BLOCK = 5               # generations between changes of rivals
RACE_TEST_FRACTION = 0.7     # race tests are this fraction of the solo test time


def test_race_timed(weights, track_name, rivals, slot):
    seconds = TEST_SECONDS.get(track_name, DEFAULT_TEST_SECONDS) * RACE_TEST_FRACTION
    return test_race(weights, track_name, rivals, slot, seconds)


def _job(args):
    kind, weights, track_name, extra = args
    if kind == "solo":
        return test_solo(weights, track_name)
    return test_race_timed(weights, track_name, *extra)


def score_population(pop: np.ndarray, tracks: list[str], mode: str, pool=None,
                     rivals=None, slot: int = 0, chunks: int = 1) -> tuple[np.ndarray, dict]:
    """Fitness for every driver (higher is better) and the raw results.

    solo mode: laps covered in the test time, averaged over the tracks, less
    a penalty for damage.

    race mode: half that solo score (raw pace, and it is noise-free), half a
    race score: laps covered in traffic, a bonus per rival beaten, and
    penalties for damage and for every collision.
    """
    pieces = np.array_split(np.arange(len(pop)), max(1, min(chunks, len(pop))))
    kinds = ["solo", "race"] if mode == "race" else ["solo"]
    jobs = []
    for kind in kinds:
        for t, name in enumerate(tracks):
            for piece in pieces:
                extra = (rivals, (slot + t) % 4) if kind == "race" else None
                jobs.append((kind, pop[piece], name, extra))
    results = list(pool.map(_job, jobs)) if pool else [_job(j) for j in jobs]
    scores = {}
    detail = {}
    k = 0
    for kind in kinds:
        total = np.zeros(len(pop))
        for name in tracks:
            merged: dict = {}
            for piece in pieces:
                for key, values in results[k].items():
                    merged.setdefault(key, []).extend(values)
                k += 1
            detail[f"{kind}:{name}"] = merged
            laps, damage = np.array(merged["laps"]), np.array(merged["damage"])
            if kind == "solo":
                total += laps - 0.25 * damage
            else:
                total += (laps / RACE_TEST_FRACTION - 0.6 * damage
                          + 0.08 * np.array(merged["beaten"]) - 0.015 * np.array(merged["hits"]))
        scores[kind] = total / len(tracks)
    fitness = scores["solo"] if mode == "solo" else 0.5 * scores["solo"] + 0.5 * scores["race"]
    return fitness, detail


# ---------------------------------------------------------------- breeding

def breed(sorted_pop: np.ndarray, rng: np.random.Generator, size: int, elites: int) -> np.ndarray:
    """Next generation from a population sorted best first.

    The best `elites` go through unchanged.  Every other child is a copy of
    a good parent (sometimes mixed with a second parent) with random changes;
    some children get small changes, to refine, and some large, to explore.
    """
    parents = max(2, len(sorted_pop) // 4)
    children = [sorted_pop[i].copy() for i in range(min(elites, len(sorted_pop)))]
    while len(children) < size:
        a = sorted_pop[min(rng.integers(0, parents, 2))]       # 2-way tournament
        child = a.copy()
        if rng.random() < 0.3:
            b = sorted_pop[min(rng.integers(0, parents, 2))]
            mask = rng.random(N_WEIGHTS) < 0.5
            child[mask] = b[mask]
        sigma = rng.choice([0.02, 0.05, 0.1, 0.2])
        touched = rng.random(N_WEIGHTS) < rng.choice([0.1, 0.3, 1.0])
        child += rng.normal(0.0, sigma, N_WEIGHTS) * touched
        children.append(child)
    return np.array(children)


# ------------------------------------------------------------------- exams

def exam(weights: np.ndarray, tracks: list[str]) -> dict:
    """Standard report card for one driver, the same for every generation so
    generations can be compared: a solo time trial and a race against three
    scripted cars on each track."""
    from sim.race import Race
    report = {}
    for name in tracks:
        solo = test_solo(weights[None, :], name)
        race = Race(name, [(0, NeuralDriver(weights, "Evolved")), (1, "scripted"),
                           (2, "scripted"), (3, "scripted")], laps=3)
        hits = 0

        def count(r, event):
            nonlocal hits
            if (event[0] == "wall" and event[1] == 0) or (event[0] == "car" and 0 in event[1:3]):
                hits += 1

        race.run(max_seconds=150.0, on_event=count)
        car = race.world.cars[0]
        row = next(r for r in race.results() if r["car"] == 0)
        report[name] = {
            "solo_laps": round(solo["laps"][0], 3),
            "solo_best_lap": solo["best_lap"][0],
            "solo_damage": round(solo["damage"][0], 3),
            "race_place": row["place"],
            "race_finished": row["finished"],
            "race_laps": row["laps"],
            "race_time": row["time"],
            "race_best_lap": row["best_lap"],
            "race_hits": hits,
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


def load_history(run_dir: Path) -> list[dict]:
    path = Path(run_dir) / "history.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []      # caught mid-write by the trainer; try again next time


def list_runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted(p.name for p in RUNS_DIR.iterdir() if (p / "history.json").exists())


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def train(run: str = "default", generations: int = 50, population: int = 80, elites: int = 6,
          seed: int = 0, tracks: list[str] | None = None, race_from: int | None = None,
          workers: int = 0, on_generation=None) -> Path:
    """Train (or continue) a run.  Writes one file per generation plus
    history.json into training/<run>/, which the game reads while this runs.

    Solo ghost tests are used until generation `race_from`, real races from
    then on.  `race_from=None` switches automatically once the champion can
    cover the solo test cleanly.
    """
    run_dir = RUNS_DIR / run
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {"population": population, "elites": elites, "seed": seed,
                  "tracks": tracks or Track.available(), "race_from": race_from,
                  "inputs": N_INPUTS, "hidden": N_HIDDEN, "outputs": N_OUTPUTS,
                  "tuning_id": tuning.physics_fingerprint()}
        _write_json(config_path, config)
    size, tracks, seed = config["population"], config["tracks"], config["seed"]
    history = load_history(run_dir)
    done = list_generations(run_dir)
    history = [h for h in history if h["gen"] in done]
    start = (done[-1] + 1) if done else 1
    if done:
        last = load_generation(run_dir, done[-1])
        pop = breed(last["pop"], np.random.default_rng([seed, done[-1]]), size, config["elites"])
    else:
        pop = random_population(np.random.default_rng([seed, 0]), size)
    race_start = config.get("race_from")
    if race_start is None:
        race_start = next((h["gen"] for h in history if h["mode"] == "race"), None)

    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    try:
        for gen in range(start, start + generations):
            ready = history and all(
                t["solo_laps"] >= 1.9 and t["solo_damage"] <= 0.05 for t in history[-1]["exam"].values())
            if race_start is None and ready:
                race_start = gen
            mode = "race" if race_start is not None and gen >= race_start else "solo"
            rivals = None
            if mode == "race":
                # Rivals: one scripted car and two earlier champions.  They
                # and the grid slot change only every few generations, so a
                # generation is compared with its parents on the same test.
                rng = np.random.default_rng([seed, (gen - race_start) // RIVAL_BLOCK, 7])
                block_start = race_start + ((gen - race_start) // RIVAL_BLOCK) * RIVAL_BLOCK
                past = [g for g in list_generations(run_dir) if g < block_start][-12:]
                picks = rng.choice(past, 2, replace=len(past) < 2)
                rivals = ["scripted"] + [load_generation(run_dir, int(g))["pop"][0] for g in picks]
                slot = int(rng.integers(0, 4))
            else:
                slot = 0
            fitness, detail = score_population(pop, tracks, mode, pool, rivals, slot,
                                               chunks=max(1, workers))
            order = np.argsort(-fitness, kind="stable")
            pop, fitness = pop[order], fitness[order]
            np.savez_compressed(gen_path(run_dir, gen), pop=pop.astype(np.float32), fitness=fitness)
            # Carry on from exactly what was saved (float32), so stopping and
            # continuing a run gives the same result as never stopping.
            pop = load_generation(run_dir, gen)["pop"]
            champion = pop[0]
            entry = {
                "gen": gen, "mode": mode,
                "best": round(float(fitness[0]), 4),
                "mean": round(float(fitness.mean()), 4),
                "median": round(float(np.median(fitness)), 4),
                "exam": exam(champion, tracks),
            }
            history.append(entry)
            _write_json(run_dir / "history.json", history)
            if on_generation:
                on_generation(entry)
            pop = breed(pop, np.random.default_rng([seed, gen]), size, config["elites"])
    finally:
        if pool:
            pool.shutdown()
    return run_dir
