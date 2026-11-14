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
    assert kept[0]["kind"] == "ai" and kept[0]["weight"] == "medium"
    assert telemetry.submit_race(race) == []                       # nothing new: no change
    slow = dict(kept[0], time=99.0)
    assert not telemetry.submit("speedway", [{"lap": slow, "driver": "Slow", "kind": "human"}])
    fast = dict(kept[0], time=1.0)
    assert telemetry.submit("speedway", [{"lap": fast, "driver": "You", "kind": "human"}])
    assert telemetry.best("speedway")["driver"] == "You"


def test_the_best_lap_becomes_reference_notes_that_drivers_see():
    track = Track.load("speedway")
    assert telemetry.reference(track) is None                      # nothing recorded yet
    telemetry.submit_race(race_laps())
    ref = telemetry.reference(track)
    assert ref.shape == (track.corners()["count"], brain.NOTE_FIELDS)
    assert np.all(np.abs(ref) <= 1.0)
    report = telemetry.corner_report(track, telemetry.best("speedway"))
    assert len(report) == track.corners()["count"] and all(r["apex_speed"] > 5 for r in report)
