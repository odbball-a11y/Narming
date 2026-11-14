"""pytest set-up: make `sim` and `game` importable, and never open a window."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_driver_registry():
    """Trained-driver entries registered by one test must not leak into the next."""
    yield
    from sim.driver import unregister_drivers
    unregister_drivers("evo:")


@pytest.fixture(autouse=True)
def _own_telemetry(tmp_path, monkeypatch):
    """Each test keeps its own lap telemetry (never the project's real records),
    so one test's laps cannot change how drivers see the track in another."""
    from ai import telemetry
    monkeypatch.setattr(telemetry, "DIR", tmp_path / "telemetry")
    telemetry._cache.clear()
    yield
    telemetry._cache.clear()


# Fixtures shared by the stable and car-trait tests.
from tests.test_stable import app, dirs  # noqa: E402,F401
