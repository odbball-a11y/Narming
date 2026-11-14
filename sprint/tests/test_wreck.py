import numpy as np

from ai import evolve
from ai.brain import DEFAULT_ARCH, n_weights
from sim.race import Race
from sim.wreck import WreckDriver, parse


def test_a_wreck_races_then_stops_on_the_track_and_stays():
    wreck = WreckDriver(slot=1, stop_after=4.0, side=1, place=0.6)
    race = Race("oval", [(0, "scripted"), (1, wreck), (2, "scripted")], laps=3, rolling=True)
    while race.world.time < 3.0:
        race.step()
    assert race.world.cars[1].speed > 10.0                    # racing at first
    while race.world.time < 12.0:
        race.step()
    car = race.world.cars[1]
    assert car.speed < 0.5 and car.surface == 0               # stopped, still on the tarmac
    assert car.draft == 0.0 and all(c.draft_source != 1 for c in race.world.cars)   # a wreck gives no tow


def test_some_training_races_have_a_wreck_and_they_run():
    config = {"seed": 3, "tracks": ["oval"], "races_per_track": 12, "partners": None, "car": None}
    scenarios = evolve.make_scenarios(config, 20, 1, list(range(1, 20)))
    wrecks = [s for s in scenarios if any(str(r).startswith("wreck:") for r in s["rivals"])]
    assert 0 < len(wrecks) < len(scenarios)
    key = next(r for r in wrecks[0]["rivals"] if str(r).startswith("wreck:"))
    assert parse(key)["stop_after"] >= 2.0
    sc = dict(wrecks[0], rivals=[r if isinstance(r, str) else "scripted" for r in wrecks[0]["rivals"]],
              seconds=12.0)
    weights = np.random.default_rng(0).normal(0, 0.3, (2, n_weights(DEFAULT_ARCH)))
    result = evolve.test_race(weights, DEFAULT_ARCH, sc)
    assert len(result["place"]) == 2


def test_drafting_is_not_rewarded_any_more():
    base = {"place": [1], "laps": [2.0], "damage": [0.0], "fault": [0], "walls": [0], "overtakes": [0],
            "passed": [0], "draft": [0.0]}
    towed = dict(base, draft=[0.8])
    weights = evolve.style_weights("aggressive")
    assert evolve.race_score(towed, 1.0, weights)[0] == evolve.race_score(base, 1.0, weights)[0]
