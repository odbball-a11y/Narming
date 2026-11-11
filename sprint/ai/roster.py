"""Put trained champions in the driver registry so they can be given any car
slot from the race setup menu, like any other driver."""
from __future__ import annotations

from sim.driver import register_driver, unregister_drivers

from . import evolve
from .brain import NeuralDriver

PREFIX = "evo:"
_cache: dict = {}


def spread(generations: list[int], limit: int) -> list[int]:
    """Up to `limit` generations, evenly spread, always with first and last."""
    if len(generations) <= limit:
        return list(generations)
    last = len(generations) - 1
    picks = {round(k * last / (limit - 1)) for k in range(limit)}
    return [generations[i] for i in sorted(picks)]


def weights(run: str, gen: int, rank: int = 0):
    """(weights, arch) of the driver ranked `rank` (0 = champion) in a generation."""
    key = (str(evolve.RUNS_DIR), run, gen)
    if key not in _cache:
        run_dir = evolve.RUNS_DIR / run
        _cache[key] = (evolve.load_generation(run_dir, gen)["pop"], evolve.load_config(run_dir)["arch"])
    pop, arch = _cache[key]
    return pop[min(rank, len(pop) - 1)], arch


def display_name(run: str) -> str | None:
    """The racer name given to a run (e.g. "Dangerous Dave"), if any."""
    try:
        return evolve.load_config(evolve.RUNS_DIR / run).get("name")
    except (OSError, ValueError):
        return None


def default_label(run: str, gen: int) -> str:
    name = display_name(run)
    return f"{name} g{gen}" if name else f"Evo gen {gen}"


def champion(run: str, gen: int, label: str | None = None, rank: int = 0) -> NeuralDriver:
    """A driver of a generation (the best by default), as a Driver."""
    w, arch = weights(run, gen, rank)
    return NeuralDriver(w, arch, label or default_label(run, gen))


def latest_run() -> str | None:
    """The run trained most recently."""
    runs = evolve.list_runs()
    if not runs:
        return None
    return max(runs, key=lambda r: (evolve.RUNS_DIR / r / "history.json").stat().st_mtime)


def register_champions(run: str | None = None, limit: int = 8) -> list[str]:
    """Refresh the registry with champions of `run` (default: the latest),
    plus the latest champion of every named racer.  Returns the keys."""
    unregister_drivers(PREFIX)
    run = run or latest_run()
    keys = []
    if run is not None:
        for gen in spread(evolve.list_generations(evolve.RUNS_DIR / run), limit):
            key = f"{PREFIX}{run}:{gen}"
            register_driver(key, default_label(run, gen), lambda slot=0, r=run, g=gen: champion(r, g))
            keys.append(key)
    for other in evolve.list_runs():
        name = display_name(other)
        gens = evolve.list_generations(evolve.RUNS_DIR / other)
        key = f"{PREFIX}{other}:{gens[-1]}" if gens else None
        if name and key and key not in keys:
            register_driver(key, name, lambda slot=0, r=other, g=gens[-1]: champion(r, g, name))
            keys.append(key)
    return keys
