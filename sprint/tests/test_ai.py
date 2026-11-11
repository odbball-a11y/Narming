"""Learned drivers: inputs, network, evolution, saved runs, and the AI lab."""
import numpy as np
import pygame
import pytest

from ai import brain, evolve, roster
from ai.brain import N_INPUTS, N_WEIGHTS, NeuralDriver, Population, observe
from sim.driver import create_driver, driver_types
from sim.race import FINISHED, Race
from sim.replay import Recording
from sim.track import Track
from sim.world import World

from helpers import make_world


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    """A tiny real training run: 3 solo generations then 2 race generations."""
    root = tmp_path_factory.mktemp("training")
    old = evolve.RUNS_DIR
    evolve.RUNS_DIR = root
    evolve.train(run="tiny", generations=5, population=10, elites=2, seed=1,
                 tracks=["speedway"], race_from=4)
    yield root / "tiny"
    evolve.RUNS_DIR = old


def test_observation_has_the_documented_shape():
    world = make_world(cars=3)
    for i in range(3):
        obs = observe(world, i)
        assert len(obs) == N_INPUTS == len(brain.INPUT_NAMES)
        assert all(np.isfinite(obs))
    # Traffic inputs read "nobody there" for ghosts and for a car alone.
    alone = observe(make_world(), 0)
    assert alone[-5:] == [1.0, 0.0, 0.0, 1.0, 0.0]
    assert observe(world, 1)[-5] < 1.0             # someone is ahead of car 1 on the grid


def test_batched_population_matches_single_driver():
    rng = np.random.default_rng(0)
    weights = evolve.random_population(rng, 5)
    assert weights.shape == (5, N_WEIGHTS)
    world = make_world()
    obs = np.array([observe(world, 0)] * 5)
    batch = Population(weights).act(obs)
    for k in range(5):
        single = NeuralDriver(weights[k]).act(world, 0)
        expected = brain.to_controls(float(batch[k, 0]), float(batch[k, 1]))
        assert single == pytest.approx(expected)
        assert -1 <= single.steering <= 1 and 0 <= single.throttle <= 1 and 0 <= single.brake <= 1
        assert single.throttle == 0 or single.brake == 0


def test_neural_driver_holds_its_controls_between_decisions():
    weights = evolve.random_population(np.random.default_rng(2), 1)[0]
    world = make_world()
    driver = NeuralDriver(weights)
    seen = []
    for _ in range(brain.DECISION_TICKS * 3):
        controls = driver.act(world, 0)
        seen.append(controls)
        world.step([controls])
    for k in range(0, len(seen), brain.DECISION_TICKS):
        assert len(set(seen[k:k + brain.DECISION_TICKS])) == 1


def test_solo_test_is_deterministic_and_independent_of_chunking():
    pop = evolve.random_population(np.random.default_rng(3), 9)
    a, _ = evolve.score_population(pop, ["speedway"], "solo", chunks=1)
    b, _ = evolve.score_population(pop, ["speedway"], "solo", chunks=4)
    assert np.array_equal(a, b)
    # One driver tested alone scores the same as in a pack: ghosts do not interact.
    alone = evolve.test_solo(pop[4:5], "speedway")["laps"][0]
    assert alone == evolve.test_solo(pop, "speedway")["laps"][4]


def test_breeding_keeps_the_elites_and_is_seeded():
    pop = evolve.random_population(np.random.default_rng(4), 12)
    a = evolve.breed(pop, np.random.default_rng(9), 12, elites=3)
    b = evolve.breed(pop, np.random.default_rng(9), 12, elites=3)
    assert a.shape == pop.shape and np.array_equal(a, b)
    assert np.array_equal(a[:3], pop[:3])
    assert not np.array_equal(a[3:], pop[3:])


def test_training_run_writes_generations_and_history(run_dir):
    assert evolve.list_generations(run_dir) == [1, 2, 3, 4, 5]
    history = evolve.load_history(run_dir)
    assert [h["gen"] for h in history] == [1, 2, 3, 4, 5]
    assert [h["mode"] for h in history] == ["solo", "solo", "solo", "race", "race"]
    solo = [h["best"] for h in history[:3]]
    assert solo == sorted(solo)                     # elites survive: never gets worse
    exam = history[-1]["exam"]["speedway"]
    assert {"solo_best_lap", "race_place", "race_hits", "race_damage"} <= set(exam)
    data = evolve.load_generation(run_dir, 3)
    assert data["pop"].shape == (10, N_WEIGHTS)
    assert list(data["fitness"]) == sorted(data["fitness"], reverse=True)


def test_stopping_and_continuing_gives_the_same_run(run_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    kwargs = dict(run="again", population=10, elites=2, seed=1, tracks=["speedway"], race_from=4)
    evolve.train(generations=2, **kwargs)
    evolve.train(generations=3, **kwargs)           # picked up where it stopped
    for gen in (1, 3, 5):
        a = evolve.load_generation(run_dir, gen)
        b = evolve.load_generation(tmp_path / "again", gen)
        assert np.array_equal(a["pop"], b["pop"]) and np.array_equal(a["fitness"], b["fitness"])


def test_evolution_actually_learns_to_drive(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    evolve.train(run="learn", generations=8, population=40, seed=0, tracks=["speedway"], race_from=99)
    history = evolve.load_history(tmp_path / "learn")
    first = history[0]["exam"]["speedway"]["solo_laps"]
    last = history[-1]["exam"]["speedway"]["solo_laps"]
    assert last > first + 0.5 and last > 1.0        # from stuck at turn one to a full lap


def test_champions_join_the_registry_and_race(run_dir, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", run_dir.parent)
    assert roster.latest_run() == "tiny"
    keys = roster.register_champions(limit=3)
    assert keys == ["evo:tiny:1", "evo:tiny:3", "evo:tiny:5"]
    assert set(keys) <= {k for k, _ in driver_types()}
    assert create_driver(keys[-1], slot=2).label == "Evo gen 5"
    race = Race("speedway", [(0, keys[0]), (1, keys[2]), (2, "scripted")], laps=1).run(max_seconds=90)
    assert race.phase == FINISHED
    replay = Recording.from_race(race).make_race().run(max_seconds=90)
    assert replay.final_hash == race.final_hash     # learned drivers replay exactly too
    roster.register_champions(run="no-such-run")
    assert not [k for k, _ in driver_types() if k.startswith("evo:")]
    assert roster.spread(list(range(1, 101)), 4) == [1, 34, 67, 100]


# ----------------------------------------------------------------- screens

@pytest.fixture
def app(run_dir, monkeypatch):
    from game.app import App
    from game.audio import Audio
    monkeypatch.setattr(evolve, "RUNS_DIR", run_dir.parent)
    pygame.display.init()
    pygame.font.init()
    return App(pygame.display.set_mode((640, 360)), Audio())


def press(app, *keys):
    for key in keys:
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
        app.draw()


def test_lab_shows_the_run_and_starts_a_champions_race(app):
    from game.screens import LabScreen, RaceScreen
    app.show(LabScreen(app))
    app.update(2.0)
    app.draw()
    lab = app.current
    assert app.ai_run == "tiny" and lab.generations() == [1, 2, 3, 4, 5]
    press(app, pygame.K_DOWN, pygame.K_RETURN)      # RACE THE CHAMPIONS
    view = app.current
    assert isinstance(view, RaceScreen)
    assert [d.label for d in view.race.drivers] == ["Gen 1", "Gen 3", "Gen 5", "Scripted"]
    for _ in range(600):
        app.update(1 / 60)
    app.draw()
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)   # quit goes back to the lab
    assert isinstance(app.current, LabScreen)
    press(app, pygame.K_DOWN, pygame.K_DOWN, pygame.K_RETURN)   # RACE AGAINST THEM
    assert app.current.race.driver_keys[0] == "human1"


def test_pack_view_runs_a_generation_and_moves_on(app):
    from game.screens import LabScreen, PackScreen
    app.show(LabScreen(app))
    press(app, pygame.K_RETURN)                     # WATCH A GENERATION
    view = app.current
    assert isinstance(view, PackScreen) and view.gen == 1 and view.pack.count == 10
    for _ in range(30):
        app.update(1 / 60)
    app.draw()
    assert view.pack.world.tick > 0
    press(app, pygame.K_RIGHT)
    assert view.gen == 2
    press(app, pygame.K_END)
    assert view.gen == 5
    press(app, pygame.K_t)
    assert view.track_name == "technical" and view.pack.track.key == "technical"
    press(app, pygame.K_HOME)
    while not view.pack.done:                       # run generation 1 to its end
        view.pack.step()
    app.update(1.0)
    app.update(1.0)                                 # auto-advance after a short pause
    assert view.gen == 2
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.current, LabScreen)


def test_lab_with_nothing_trained_explains_what_to_do(app, tmp_path, monkeypatch):
    from game.screens import LabScreen, MainMenu
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path / "empty")
    app.ai_run = None
    app.show(LabScreen(app))
    app.draw()
    assert app.current.history == []
    press(app, pygame.K_RETURN)                     # nothing to watch: stays put, no crash
    assert isinstance(app.current, LabScreen)
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.current, MainMenu)


def test_trained_drivers_appear_in_race_setup(app):
    from game.screens import SetupScreen
    app.show(SetupScreen(app))
    labels = [label for _, label in app.current.driver_choices()]
    assert "Evo gen 5" in labels and "Scripted" in labels and "None" in labels
