import numpy as np

from ai import evolve
from ai.brain import DEFAULT_ARCH, n_weights


def test_place_points_spread_over_any_field_and_match_four_car_races():
    table = evolve.RACE_WEIGHTS["place"]
    assert list(evolve.place_points([1, 2, 3, 4], [4] * 4, table)) == table          # unchanged for four
    eight = evolve.place_points(list(range(1, 9)), [8] * 8, table)
    assert eight[0] == table[0] and eight[-1] == table[-1]
    assert all(a > b for a, b in zip(eight, eight[1:]))                              # every place counts


def test_training_races_can_have_any_number_of_cars():
    config = {"seed": 1, "tracks": ["oval"], "races_per_track": 8, "partners": None, "car": None, "field": 8}
    scenarios = evolve.make_scenarios(config, 30, 1, list(range(1, 30)))
    assert all(len(s["rivals"]) == 7 for s in scenarios)
    assert sorted(s["slot"] for s in scenarios) == list(range(8))                   # every grid place
    sc = dict(scenarios[0], rivals=[r if isinstance(r, str) else "scripted" for r in scenarios[0]["rivals"]],
              seconds=10.0)
    weights = np.random.default_rng(0).normal(0, 0.3, (3, n_weights(DEFAULT_ARCH)))
    result = evolve.test_race(weights, DEFAULT_ARCH, sc)
    assert result["field"] == [8, 8, 8] and all(1 <= p <= 8 for p in result["place"])
    assert len(evolve.race_score(result, 0.5)) == 3


def test_a_run_remembers_its_field(tmp_path, monkeypatch):
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path)
    evolve.train(run="six", generations=1, population=4, elites=1, tracks=["oval"], phase2_from=1,
                 races_per_track=1, field=6, record_laps=False, log=lambda m: None)
    assert evolve.load_config(tmp_path / "six")["field"] == 6
    assert len(evolve.load_history(tmp_path / "six")[0]["scenarios"][0]["rivals"]) == 5
