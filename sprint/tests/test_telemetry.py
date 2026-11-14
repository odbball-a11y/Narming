"""Lap telemetry: recording laps, keeping the fastest, and reference notes."""
import numpy as np

import sim.scripted  # noqa: F401
from ai import brain, telemetry
from sim import telemetry as laps
from sim.race import Race
from sim.track import Track


def race_laps(track="speedway", laps_=3):
    race = Race(track, [(0, "scripted"), (1, "scripted")], laps=laps_, rolling=True).run()
    return race


def test_every_race_records_each_cars_flying_laps():
    race = race_laps()
    recorded = race.telemetry.laps
    assert len(recorded) == 4                                     # laps 2 and 3 of two cars
    for i, lap in recorded:
        assert abs(lap["time"] - race.world.cars[i].lap_times[1 if lap is recorded[i][1] else 2]) < 1.0
        n = int(race.track.length / laps.SPACING)
        assert all(len(lap[f]) == n for f in laps.FIELDS)
        assert lap["speed"][n // 2] > 10.0
    i, lap = recorded[0]
    assert laps.pose_at(lap, lap["time"] / 2) is not None and laps.pose_at(lap, lap["time"] + 5) is None


def test_the_store_keeps_the_fastest_laps_and_says_when_the_record_falls():
    race = race_laps()
    assert telemetry.submit_race(race) == ["speedway"]             # the first lap ever is a record
    kept = telemetry.load("speedway")["laps"]
    assert [l["time"] for l in kept] == sorted(l["time"] for l in kept) and len(kept) == 4
    assert kept[0]["kind"] == "ai" and kept[0]["weight"] == "medium" and kept[0]["type"]
    assert telemetry.submit_race(race) == []                       # nothing new: no change
    from sim import tuning
    params = tuning.car_params(0)
    slow = dict(kept[0], time=99.0)
    assert not telemetry.submit("speedway", [telemetry.entry(slow, "Slow", "human", params)])
    fast = dict(kept[0], time=1.0)
    assert telemetry.submit("speedway", [telemetry.entry(fast, "You", "human", params)])
    assert telemetry.best("speedway")["driver"] == "You"


def test_the_best_lap_becomes_reference_notes_that_drivers_see():
    from sim import tuning
    track = Track.load("speedway")
    params = tuning.car_params(0)
    assert telemetry.reference(track, params) is None              # nothing recorded yet
    race = Race(track, [(0, "scripted")], laps=3, rolling=True).run()
    telemetry.submit_race(race)
    ref = telemetry.reference(track, race.world.cars[0].params)
    assert ref.shape == (track.corners()["count"], brain.NOTE_FIELDS)
    assert np.all(np.abs(ref) <= 1.0)
    report = telemetry.corner_report(track, telemetry.best("speedway"))
    assert len(report) == track.corners()["count"] and all(r["apex_speed"] > 5 for r in report)


def test_a_car_only_learns_from_laps_in_its_own_kind_of_car():
    from sim import cartraits
    track = Track.load("oval")
    light = cartraits.params_for(dict(cartraits.default(), weight="light"))
    near = cartraits.params_for(dict(cartraits.default(), top_speed=4, braking=2))   # one star moved
    far = cartraits.params_for({"top_speed": 5, "accel": 5, "handling": 1, "braking": 1, "weight": "heavy"})
    standard = cartraits.params_for(cartraits.default())
    lap = race_laps("oval").telemetry.laps[0][1]
    telemetry.submit("oval", [telemetry.entry(dict(lap, time=10.0), "Light", "ai", light),
                              telemetry.entry(dict(lap, time=11.0), "Near", "ai", near)])
    assert telemetry.best("oval", light)["driver"] == "Light"       # its own type
    assert telemetry.best("oval", standard)["driver"] == "Near"     # nearest type, not the faster light car
    assert telemetry.best("oval", far) is None                      # nothing close: no reference at all
    assert telemetry.reference(track, far) is None
    kept = {l["type"] for l in telemetry.load("oval")["laps"]}
    assert telemetry.car_type(light) in kept and telemetry.car_type(near) in kept
