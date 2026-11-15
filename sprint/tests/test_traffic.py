import json

import numpy as np

from ai import brain, evolve, migrate
from ai.brain import DEFAULT_ARCH, n_weights, with_notes
from sim.race import Race
from sim.traffic import TrafficDriver, parse


def test_a_card_whose_brain_was_left_behind_is_repaired(tmp_path):
    """The old upgrade skipped brains with track notes: card current, weights old."""
    old_arch = with_notes(dict(DEFAULT_ARCH, inputs=6))
    rng = np.random.default_rng(0)
    weights = rng.normal(0, 0.3, (1, brain.genome_size(old_arch)))
    house = tmp_path / "house" / "rivals"
    house.mkdir(parents=True)
    np.savez_compressed(house / "x.npz", pop=weights.astype(np.float32))
    (house / "x.json").write_text(json.dumps({"name": "X", "arch": dict(old_arch, inputs=brain.INPUT_VERSION)}))
    assert migrate.ensure(tmp_path) >= 1
    card = json.loads((house / "x.json").read_text())
    pop = np.load(house / "x.npz")["pop"]
    assert pop.shape[1] == brain.genome_size(card["arch"])
    fixed, arch = brain.align(weights[0], dict(old_arch, inputs=brain.INPUT_VERSION))
    assert np.allclose(pop[0], fixed, atol=1e-5) and arch["inputs"] == brain.INPUT_VERSION


def test_backmarkers_hold_back_and_keep_their_style():
    cars = [(k, TrafficDriver(slot=k, **parse(f"traffic:0.80:{style}"))) for k, style in
            enumerate(["line", "defend", "wander"])]
    race = Race("oval", cars + [(3, "scripted")], laps=3, rolling=True)
    while race.world.time < 20.0:
        race.step()
    for k in range(3):
        car = race.world.cars[k]
        assert car.speed <= 0.80 * car.params.top_speed + 2.0


def test_drills_appear_in_racing_school_and_score_clean_passes():
    config = {"seed": 5, "tracks": ["oval", "speedway"], "races_per_track": 10, "partners": None, "car": None}
    scenarios = evolve.make_scenarios(config, 30, 1, list(range(1, 30)))
    drills = [s for s in scenarios if s.get("drill")]
    assert 0 < len(drills) < len(scenarios)
    d = drills[0]
    assert d["slot"] == evolve.DRILL_FIELD - 1 and len(d["rivals"]) == evolve.DRILL_FIELD - 1
    assert all(r.startswith("traffic:") for r in d["rivals"])
    base = {"place": [8], "field": [8], "laps": [2.0], "damage": [0.0], "fault": [0], "suffered": [0],
            "walls": [0], "overtakes": [3], "passed": [0], "clean_passes": [0], "draft": [0.0]}
    clean = dict(base, clean_passes=[3], place=[5])
    dirty = dict(base, place=[5], fault=[3], damage=[0.2])
    assert evolve.drill_score(clean)[0] > evolve.drill_score(dirty)[0] > evolve.drill_score(dirty)[0] - 1
    weights = np.random.default_rng(1).normal(0, 0.3, (2, n_weights(DEFAULT_ARCH)))
    result = evolve.test_race(weights, DEFAULT_ARCH, dict(d, seconds=8.0))
    assert result["field"] == [8, 8] and "clean_passes" in result


def test_the_traffic_test_reports_clean_passes():
    weights = np.random.default_rng(2).normal(0, 0.3, n_weights(DEFAULT_ARCH))
    r = evolve.traffic_test(weights, DEFAULT_ARCH)
    assert r["of"] == 8 and 1 <= r["place"] <= 8 and 0 <= r["clean_passes"] <= r["passes"]


def test_drills_start_easy_and_get_harder():
    base = {"seed": 5, "tracks": ["oval"], "races_per_track": 20, "partners": None, "car": None}
    easy = [s for s in evolve.make_scenarios(dict(base, drill_level=0.0), 30, 1, list(range(1, 30))) if s.get("drill")]
    hard = [s for s in evolve.make_scenarios(dict(base, drill_level=1.0), 30, 1, list(range(1, 30))) if s.get("drill")]
    assert easy and hard
    assert all(len(s["rivals"]) == 2 and s["slot"] == 2 for s in easy)
    assert all(r.endswith(":line") and float(r.split(":")[1]) <= evolve.DRILL_EASY[1] for s in easy for r in s["rivals"])
    assert all(len(s["rivals"]) == evolve.DRILL_FIELD - 1 for s in hard)
    assert evolve.drill_level([]) == 0.0
    tests = [{"traffic": {"clean_passes": 3}}] * 10
    assert evolve.drill_level(tests) == 1.0


def test_catching_a_car_counts_towards_a_drill():
    base = {"place": [3], "field": [3], "laps": [2.0], "damage": [0.0], "fault": [0], "suffered": [0],
            "walls": [0], "overtakes": [0], "passed": [0], "clean_passes": [0], "draft": [0.0]}
    assert evolve.drill_score(dict(base, reached=[2]))[0] > evolve.drill_score(dict(base, reached=[0]))[0]
