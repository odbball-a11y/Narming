"""Put trained champions in the driver registry so they can be given any car
slot from the race setup menu, like any other driver."""
from __future__ import annotations

from pathlib import Path

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


def champion(run: str, gen: int, label: str | None = None) -> NeuralDriver:
    """The best driver of a generation, as a Driver."""
    key = (str(evolve.RUNS_DIR), run, gen)
    if key not in _cache:
        _cache[key] = evolve.load_generation(evolve.RUNS_DIR / run, gen)["pop"][0]
    return NeuralDriver(_cache[key], label or f"Evo gen {gen}")


def latest_run() -> str | None:
    """The run trained most recently."""
    runs = evolve.list_runs()
    if not runs:
        return None
    return max(runs, key=lambda r: (evolve.RUNS_DIR / r / "history.json").stat().st_mtime)


def register_champions(run: str | None = None, limit: int = 8) -> list[str]:
    """Refresh the registry with champions of `run` (default: the latest).
    Returns the registered keys, oldest generation first."""
    unregister_drivers(PREFIX)
    run = run or latest_run()
    if run is None:
        return []
    keys = []
    for gen in spread(evolve.list_generations(evolve.RUNS_DIR / run), limit):
        key = f"{PREFIX}{run}:{gen}"
        register_driver(key, f"Evo gen {gen}", lambda slot=0, r=run, g=gen: champion(r, g))
        keys.append(key)
    return keys
