"""Learned drivers: inputs, network, both training phases, saved runs, and
the AI lab screens."""
import json

import numpy as np
import pygame
import pytest

from ai import brain, evolve, roster
from ai.brain import N_INPUTS, Brain, NeuralDriver, Population, n_weights, observe, random_weights
from sim import tuning
from sim.driver import create_driver, driver_types
from sim.race import FINISHED, Race
from sim.replay import Recording
from sim.world import World

from helpers import make_world, put_on_track

ARCH = {"hidden": [8, 6], "memory": 2, "inputs": brain.INPUT_VERSION}
FLAT = {"hidden": [8], "memory": 0, "inputs": brain.INPUT_VERSION}


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    """A tiny real run: 3 driving-school generations then 3 racing-school ones."""
    root = tmp_path_factory.mktemp("training")
    old = evolve.RUNS_DIR
    evolve.RUNS_DIR = root
    evolve.train(run="tiny", generations=6, population=8, elites=2, seed=1, tracks=["speedway"],
                 phase2_from=4, arch=ARCH, races_per_track=2)
    yield root / "tiny"
    evolve.RUNS_DIR = old


# --------------------------------------------------------------- inputs

def test_observation_has_the_documented_shape():
    world = make_world(cars=4)
    for i in range(4):
        obs = observe(world, i)
        assert len(obs) == N_INPUTS == len(brain.INPUT_NAMES)
        assert all(np.isfinite(obs))
    alone = dict(zip(brain.INPUT_NAMES, observe(make_world(), 0)))
    traffic = ["tow I give", "ahead1 gap", "ahead1 side", "ahead1 closing", "ahead2 gap", "ahead2 side",
               "ahead2 closing", "behind gap", "behind side", "behind closing", "left car near",
               "left car along", "right car near", "right car along", "race place"]
    assert [alone[k] for k in traffic] == [0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0,
                                           0.0, 0.0, 0.0]


def test_version_2_inputs_walls_place_race_left_and_far_bends():
    world = make_world()
    me = world.cars[0]
    track = world.track
    put_on_track(world, me, 40.0, lateral=2.0, speed=20.0)
    obs = dict(zip(brain.INPUT_NAMES, observe(world, 0)))
    limit = track.limit[me.idx] - me.params.radius
    assert obs["room to barrier right"] == pytest.approx((limit - 2.0) / 6.0, abs=0.02)
    assert obs["room to barrier left"] == pytest.approx((limit + 2.0) / 6.0, abs=0.02)
    far = track.curvature_ahead(me.s, 120.0) * 8.0
    assert obs["curvature 120 ahead"] == pytest.approx(far, abs=0.05)
    # Rolling start, car 0 second in the file: it is behind, early in the race.
    race = World(track, slots=[1, 0], laps=2, rolling=True)
    behind = dict(zip(brain.INPUT_NAMES, observe(race, 0)))
    ahead = dict(zip(brain.INPUT_NAMES, observe(race, 1)))
    assert behind["race place"] == 1.0 and ahead["race place"] == 0.0
    assert 0.9 < behind["race left"] <= 1.0
    timed = make_world(laps=10 ** 9)
    timed.end_tick = 1000
    timed.tick = 250
    assert dict(zip(brain.INPUT_NAMES, observe(timed, 0)))["race left"] == pytest.approx(0.75)


def test_old_brains_are_upgraded_and_drive_exactly_as_before(tmp_path):
    import json
    import shutil
    from ai import migrate
    v1 = {"hidden": [8, 6], "memory": 2}               # no "inputs": the old layout
    w = random_weights(np.random.default_rng(7), 3, dict(v1, inputs=1))
    assert w.shape[1] == n_weights(v1) < n_weights(dict(v1, inputs=2))
    new, arch = brain.upgrade(w, v1)
    assert arch["inputs"] == brain.INPUT_VERSION and new.shape == (3, n_weights(arch))
    world = make_world(cars=2)
    for k in range(3):
        old_driver = brain.Brain.__new__(brain.Brain)   # drive the v1 brain on the v1 inputs
        old_driver.layers = brain.unpack(w[k], v1)
        old_driver.memory_size = 2
        old_driver.memory = np.zeros((1, 2))
        obs_v1 = np.array([observe(world, 0)[:len(brain.INPUT_VERSIONS[1])]])
        new_driver = Brain(new[k], arch)
        for _ in range(3):                              # same answers, memory included
            assert np.allclose(old_driver.act(obs_v1), new_driver.act(np.array([observe(world, 0)])))
    # Files on disk: a run, a house card and a foal are upgraded once.
    run = tmp_path / "training" / "r"
    run.mkdir(parents=True)
    (run / "config.json").write_text(json.dumps({"arch": v1}))
    np.savez_compressed(run / "gen_0001.npz", pop=w.astype(np.float32), fitness=np.zeros(3))
    house = tmp_path / "house" / "rivals"
    house.mkdir(parents=True)
    (tmp_path / "house" / "graduate.json").write_text(json.dumps({"arch": v1}))
    np.savez_compressed(tmp_path / "house" / "graduate.npz", pop=w.astype(np.float32))
    (house / "x.json").write_text(json.dumps({"name": "X", "arch": v1}))
    np.savez_compressed(house / "x.npz", pop=w[:1].astype(np.float32))
    assert migrate.ensure(tmp_path) >= 4
    assert migrate.ensure(tmp_path) == 0                 # only once
    with np.load(run / "gen_0001.npz") as data:
        assert data["pop"].shape == (3, n_weights(arch)) and "fitness" in data.files
    assert json.loads((run / "config.json").read_text())["arch"]["inputs"] == brain.INPUT_VERSION


def test_observation_sees_cars_ahead_behind_and_alongside():
    world = make_world(cars=4)
    me, ahead, beside, behind = world.cars
    put_on_track(world, me, 40.0, speed=20.0)
    put_on_track(world, ahead, 50.0, speed=15.0)
    put_on_track(world, beside, 41.0, lateral=2.5, speed=20.0)
    put_on_track(world, behind, 33.0, speed=25.0)
    obs = dict(zip(brain.INPUT_NAMES, observe(world, 0)))
    assert obs["ahead1 gap"] == pytest.approx(1.0 / 30.0, abs=0.01)    # the car alongside is just ahead
    assert obs["ahead2 gap"] == pytest.approx(10.0 / 30.0, abs=0.02)
    assert obs["ahead2 closing"] == pytest.approx(5.0 / 15.0, abs=0.02)  # catching it
    assert obs["behind gap"] == pytest.approx(7.0 / 15.0, abs=0.02)
    assert obs["behind closing"] == pytest.approx(5.0 / 15.0, abs=0.02)  # it is catching me
    assert obs["right car near"] > 0.4 and obs["left car near"] == 0.0
    assert obs["straight ahead"] > 0.3                                   # on the main straight


def test_observation_reports_the_tow_i_give():
    world = make_world(cars=2)
    lead, follower = world.cars
    put_on_track(world, lead, 30.0, speed=28.0)
    put_on_track(world, follower, 24.0, speed=24.0)
    world.step([brain.to_controls(0, 1)] * 2)
    obs = dict(zip(brain.INPUT_NAMES, observe(world, 0)))
    assert obs["tow I give"] > 0.3
    assert dict(zip(brain.INPUT_NAMES, observe(world, 1)))["my tow"] > 0.3


# -------------------------------------------------------------- network

def test_weight_count_and_random_init():
    assert n_weights(FLAT) == 8 * N_INPUTS + 8 + 2 * 8 + 2
    w = random_weights(np.random.default_rng(0), 5, ARCH)
    assert w.shape == (5, n_weights(ARCH))
    assert "8 x 6 hidden, memory 2" in brain.describe(ARCH)


def test_batched_networks_agree_with_the_single_driver():
    weights = random_weights(np.random.default_rng(0), 4, ARCH)
    world = make_world()
    obs = np.array([observe(world, 0)] * 4)
    pop = Population(weights, ARCH)
    first = pop.act(obs)
    second = pop.act(obs)
    assert not np.allclose(first, second)                 # memory changes the next answer
    for k in range(4):
        b = Brain(weights[k], ARCH)
        assert np.allclose(b.act(obs[:1])[0], first[k])
        assert np.allclose(b.act(obs[:1])[0], second[k])
        driver = NeuralDriver(weights[k], ARCH)
        c = driver.act(world, 0)
        assert c == pytest.approx(brain.to_controls(*first[k]))
        assert c.throttle == 0 or c.brake == 0


def test_no_memory_means_same_answer_every_time():
    weights = random_weights(np.random.default_rng(1), 2, FLAT)
    obs = np.array([observe(make_world(), 0)] * 2)
    pop = Population(weights, FLAT)
    assert np.allclose(pop.act(obs), pop.act(obs))


def test_neural_driver_holds_controls_between_decisions_and_resets_memory():
    weights = random_weights(np.random.default_rng(2), 1, ARCH)[0]
    world = make_world()
    driver = NeuralDriver(weights, ARCH)
    seen = []
    for _ in range(brain.DECISION_TICKS * 3):
        seen.append(driver.act(world, 0))
        world.step([seen[-1]])
    for k in range(0, len(seen), brain.DECISION_TICKS):
        assert len(set(seen[k:k + brain.DECISION_TICKS])) == 1
    world.reset()
    driver.reset(world, 0)
    assert driver.act(world, 0) == seen[0]


# ------------------------------------------------------- driving school

def test_solo_test_is_deterministic_and_independent_of_chunking():
    pop = random_weights(np.random.default_rng(3), 9, ARCH)
    a, _ = evolve.score_population(pop, ARCH, ["speedway"], chunks=1)
    b, _ = evolve.score_population(pop, ARCH, ["speedway"], chunks=4)
    assert np.array_equal(a, b)
    alone = evolve.test_solo(pop[4:5], ARCH, "speedway")["laps"][0]
    assert alone == evolve.test_solo(pop, ARCH, "speedway")["laps"][4]   # ghosts do not interact


def test_driving_tests_rotate_grid_box_and_starting_damage():
    setups = [evolve.solo_setup(g) for g in range(1, 13)]
    assert [s["slot"] for s in setups[:4]] == [0, 1, 2, 3]
    assert {s["damage"] for s in setups} == set(evolve.SOLO_DAMAGE)
    pop = random_weights(np.random.default_rng(6), 3, ARCH)
    run = evolve.PackRun(pop, ARCH, "speedway", seconds=1.0, slot=2, damage=0.5)
    assert all(car.damage == 0.5 for car in run.world.cars)
    result = evolve.test_solo(pop, ARCH, "speedway", seconds=1.0, slot=2, damage=0.5)
    assert all(d >= 0.0 for d in result["damage"]) and min(result["damage"]) < 0.5   # only new damage counts
    car = run.world.cars[0]
    assert (car.x, car.y) == run.track.rolling_start(2)[:2]      # third in the rolling file
    assert car.speed == pytest.approx(tuning.ROLLING_START_SPEED)


def test_breeding_keeps_the_elites_and_is_seeded():
    pop = random_weights(np.random.default_rng(4), 12, ARCH)
    a = evolve.breed(pop, np.random.default_rng(9), 12, elites=3)
    b = evolve.breed(pop, np.random.default_rng(9), 12, elites=3)
    assert a.shape == pop.shape and np.array_equal(a, b)
    assert np.array_equal(a[:3], pop[:3]) and not np.array_equal(a[3:], pop[3:])


def test_driving_school_learns_to_drive(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    evolve.train(run="learn", generations=8, population=40, seed=0, tracks=["speedway"],
                 phase2_from=99, arch=FLAT)
    history = evolve.load_history(tmp_path / "learn")
    first = history[0]["exam"]["speedway"]["solo_laps"]
    last = history[-1]["exam"]["speedway"]["solo_laps"]
    assert last > first + 0.5 and last > 1.0         # clearly better, and over a lap


# -------------------------------------------------------- racing school

def test_race_stats_count_passes_and_blame():
    world = make_world(cars=2)
    me, other = world.cars
    put_on_track(world, me, 20.0, speed=26.0)
    put_on_track(world, other, 30.0, speed=10.0)
    stats = evolve.RaceStats(world)
    assert stats.place() == 2
    for _ in range(200):                           # flat out into the back of a slow car
        stats.on_tick(world.step([brain.to_controls(0, 1), brain.to_controls(0, 0.2)]))
    assert stats.fault >= 1 and stats.suffered == 0


def test_race_test_from_every_grid_slot_and_with_neural_rivals():
    pop = random_weights(np.random.default_rng(5), 3, ARCH)
    for slot in range(4):
        scenario = {"track": "speedway", "slot": slot, "rivals": ["scripted", pop[0], "scripted"],
                    "seconds": 4.0}
        result = evolve.test_race(pop, ARCH, scenario)
        assert set(result) >= {"place", "laps", "damage", "fault", "overtakes", "passed", "draft"}
        assert all(1 <= p <= 4 for p in result["place"])
    again = evolve.test_race(pop, ARCH, scenario)
    assert again == result                           # deterministic


def test_race_score_rewards_results_and_optional_bonuses():
    base = {"place": [1, 4], "laps": [1.5, 1.5], "damage": [0.0, 0.0], "fault": [0, 0],
            "walls": [0, 0], "overtakes": [0, 0], "passed": [0, 0], "draft": [0.0, 0.0]}
    s = evolve.race_score(base, 0.0)
    assert s[0] > s[1]
    hurt = dict(base, damage=[0.5, 0.0], fault=[3, 0])
    assert evolve.race_score(hurt, 0.0)[0] < s[0]
    bold = dict(base, overtakes=[3, 0], draft=[0.4, 0.0])
    assert evolve.race_score(bold, 1.0)[0] > evolve.race_score(bold, 0.0)[0] == s[0]


def test_scenarios_cover_all_grid_slots_and_follow_the_curriculum():
    config = {"seed": 0, "tracks": ["speedway", "technical"], "races_per_track": 2}
    first = evolve.make_scenarios(config, gen=40, start=40, history_gens=list(range(1, 40)))
    assert sorted(s["slot"] for s in first) == [0, 1, 2, 3]
    assert {s["track"] for s in first} == {"speedway", "technical"}
    assert all(r == "scripted" for s in first for r in s["rivals"])   # scripted rivals first
    later = evolve.make_scenarios(config, gen=80, start=40, history_gens=list(range(1, 80)))
    rivals = [r for s in later for r in s["rivals"]]
    assert any(r != "scripted" for r in rivals)                        # then self-play
    assert all(r == "scripted" or 39 <= r < 80 for r in rivals)
    assert later == evolve.make_scenarios(config, gen=80, start=40, history_gens=list(range(1, 80)))


def test_training_run_writes_both_phases(run_dir):
    assert evolve.list_generations(run_dir) == [1, 2, 3, 4, 5, 6]
    history = evolve.load_history(run_dir)
    assert [h["mode"] for h in history] == ["solo"] * 3 + ["race"] * 3
    # The best drivers survive unchanged into the next generation (their
    # scores can still move, as each generation is tested in new conditions).
    for gen in (1, 2):
        best = evolve.load_generation(run_dir, gen)["pop"][:2]
        nxt = evolve.load_generation(run_dir, gen + 1)["pop"]
        assert all(any(np.array_equal(b, row) for row in nxt) for b in best)
    race = history[-1]
    assert len(race["scenarios"]) == 2 and {s["slot"] for s in race["scenarios"]} <= {0, 1, 2, 3}
    assert {"place", "overtakes", "fault", "damage", "draft"} <= set(race["training"])
    assert 0.0 < race["bonus"] <= 1.0
    exam = race["exam"]["speedway"]
    assert {"solo_best_lap", "race_place", "race_overtakes", "race_fault", "race_draft"} <= set(exam)
    config = evolve.load_config(run_dir)
    assert config["arch"] == ARCH and config["phase2_start"] == 4 and config["format"] == evolve.FORMAT
    data = evolve.load_generation(run_dir, 3)
    assert data["pop"].shape == (8, n_weights(ARCH))
    assert list(data["fitness"]) == sorted(data["fitness"], reverse=True)


def test_no_bonuses_and_race_length_options(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    evolve.train(run="plain", generations=2, population=4, elites=1, tracks=["speedway"],
                 phase2_from=2, arch=FLAT, races_per_track=1, race_bonuses=False, race_laps=3)
    last = evolve.load_history(tmp_path / "plain")[-1]
    assert last["bonus"] == 0.0
    assert last["scenarios"][0]["seconds"] == 3 * evolve.LAP_SECONDS["speedway"]


def test_stopping_and_continuing_gives_the_same_run(run_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    kwargs = dict(run="again", population=8, elites=2, seed=1, tracks=["speedway"], phase2_from=4,
                  arch=ARCH, races_per_track=2)
    evolve.train(generations=2, **kwargs)
    evolve.train(generations=4, **kwargs)           # picked up where it stopped, across the phase change
    for gen in (1, 3, 4, 6):
        a = evolve.load_generation(run_dir, gen)
        b = evolve.load_generation(tmp_path / "again", gen)
        assert np.array_equal(a["pop"], b["pop"]) and np.array_equal(a["fitness"], b["fitness"])


def test_personality_scoring():
    base = {"place": [2, 2], "laps": [2.0, 2.0], "damage": [0.3, 0.0], "fault": [2, 0],
            "walls": [0, 0], "overtakes": [4, 0], "passed": [0, 0], "draft": [0.3, 0.0]}
    dave = evolve.race_score(base, 0.0, evolve.style_weights("aggressive"))
    keith = evolve.race_score(base, 0.0, evolve.style_weights("cautious"))
    assert dave[0] > dave[1]           # Dave's upbringing: the bold race scores better
    assert keith[0] < keith[1]         # Keith's: the clean race scores better
    assert evolve.style_weights(None) == evolve.RACE_WEIGHTS


def test_training_camp_starts_from_another_run(run_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", run_dir.parent)
    evolve.train(run="dave-test", start_from="tiny", style="aggressive", name="Dangerous Dave",
                 generations=1, population=8, elites=2)
    camp = run_dir.parent / "dave-test"
    config = evolve.load_config(camp)
    assert config["parent"] == {"run": "tiny", "gen": 6} and config["arch"] == ARCH
    assert config["tracks"] == ["speedway"] and config["races_per_track"] == 2
    assert config["race_weights"]["overtake"] > 0 and config["race_bonuses"] is False
    assert evolve.load_history(camp)[0]["mode"] == "race"          # straight into racing school
    parent_best = evolve.load_generation(run_dir, 6)["pop"][0]
    first = evolve.load_generation(camp, 1)["pop"]
    assert any(np.array_equal(parent_best.astype(np.float32), row.astype(np.float32)) for row in first)
    assert roster.display_name("dave-test") == "Dangerous Dave"
    assert roster.champion("dave-test", 1).label == "Dangerous Dave g1"
    keys = roster.register_champions(run="tiny")
    assert "evo:dave-test:1" in keys
    assert dict(driver_types())["evo:dave-test:1"] == "Dangerous Dave"
    import shutil
    shutil.rmtree(camp)
    with pytest.raises(ValueError):
        evolve.train(run="orphan", start_from="nobody", generations=1)


def test_old_format_runs_are_moved_aside_not_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    old = tmp_path / "default"
    old.mkdir()
    (old / "config.json").write_text(json.dumps({"population": 80}))
    (old / "history.json").write_text("[]")
    assert evolve.list_runs() == []
    evolve.train(run="default", generations=1, population=4, elites=1, tracks=["speedway"], arch=FLAT,
                 log=lambda m: None)
    assert (tmp_path / "default-v1" / "config.json").exists()
    assert evolve.list_runs() == ["default"]


def test_champions_join_the_registry_race_and_replay(run_dir, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", run_dir.parent)
    assert roster.latest_run() == "tiny"
    keys = roster.register_champions(limit=3)
    assert keys == ["evo:tiny:1", "evo:tiny:3", "evo:tiny:6"]
    assert set(keys) <= {k for k, _ in driver_types()}
    assert create_driver(keys[-1], slot=2).label == "Evo gen 6"
    race = Race("speedway", [(0, keys[0]), (1, keys[2]), (2, "scripted")], laps=1).run(max_seconds=90)
    assert race.phase == FINISHED
    replay = Recording.from_race(race).make_race().run(max_seconds=90)
    assert replay.final_hash == race.final_hash     # learned drivers with memory replay exactly too
    assert roster.champion("tiny", 6, rank=3).weights.tolist() == \
        evolve.load_generation(run_dir, 6)["pop"][3].tolist()
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


def open_lab(app):
    from game.screens import LabScreen
    app.show(LabScreen(app))
    app.update(2.0)
    app.draw()
    return app.current


def select(app, row):
    lab = app.current
    lab.row = lab.ROWS.index(row)
    press(app, pygame.K_RETURN)


def test_lab_follows_latest_and_picks_generations(app):
    lab = open_lab(app)
    assert app.ai_run == "tiny" and lab.generations() == [1, 2, 3, 4, 5, 6]
    assert lab.gen == 6 and lab.racing_start() == 4
    lab.row = 0
    press(app, pygame.K_LEFT, pygame.K_LEFT)
    assert lab.gen == 4
    press(app, pygame.K_PAGEDOWN)
    assert lab.gen == 1
    press(app, pygame.K_END)
    assert lab.gen == 6 and lab.picked is None


def test_lab_watch_options(app):
    from game.screens import LabScreen, PackScreen, RaceScreen
    lab = open_lab(app)
    select(app, "top4")
    view = app.current
    assert isinstance(view, RaceScreen)
    assert [d.label for d in view.race.drivers] == ["G6 #1", "G6 #2", "G6 #3", "G6 #4"]
    assert view.race.slots == [3, 2, 1, 0]          # reverse grid: the best starts last
    assert view.race.rolling
    for _ in range(300):
        app.update(1 / 60)
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)      # quit goes back to the lab
    assert isinstance(app.current, LabScreen)

    lab = app.current
    scenario = lab.entry()["scenarios"][1]
    lab.row = lab.ROWS.index("test")
    press(app, pygame.K_RIGHT, pygame.K_RETURN)     # the champion's second test race
    view = app.current
    assert view.race.track.key == scenario["track"]
    assert view.race.slots[0] == scenario["slot"] and view.race.drivers[0].label == "Gen 6"
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)

    lab = app.current
    lab.picked = 2
    select(app, "test")                              # driving-school generation: nothing to show
    assert isinstance(app.current, LabScreen) and "driving school" in app.current.message
    select(app, "champions")
    assert [d.label for d in app.current.race.drivers] == ["Gen 1", "Gen 3", "Gen 6", "Scripted"]
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)
    select(app, "versus")
    assert app.current.race.driver_keys[0] == "human1"
    press(app, pygame.K_ESCAPE, pygame.K_UP, pygame.K_RETURN)
    app.current.picked = 3
    select(app, "pack")
    assert isinstance(app.current, PackScreen) and app.current.gen == 3


def test_pack_view_runs_a_generation_and_moves_on(app):
    from game.screens import LabScreen, PackScreen
    open_lab(app)
    app.current.picked = 1
    select(app, "pack")
    view = app.current
    assert isinstance(view, PackScreen) and view.gen == 1 and view.pack.count == 8
    for _ in range(30):
        app.update(1 / 60)
    app.draw()
    assert view.pack.world.tick > 0
    press(app, pygame.K_RIGHT)
    assert view.gen == 2
    press(app, pygame.K_END)
    assert view.gen == 6
    press(app, pygame.K_t)
    assert view.track_name == "technical" and view.pack.track.key == "technical"
    press(app, pygame.K_HOME)
    while not view.pack.done:
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
    press(app, pygame.K_DOWN, pygame.K_RETURN)      # only BACK works; no crash
    assert isinstance(app.current, MainMenu)


def test_trained_drivers_appear_in_race_setup(app):
    from game.screens import SetupScreen
    app.show(SetupScreen(app))
    labels = [label for _, label in app.current.driver_choices()]
    assert "Evo gen 6" in labels and "Scripted" in labels and "None" in labels
