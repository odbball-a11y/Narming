"""Race management, the scripted driver on both tracks, and replays."""
import math

import pytest

import sim.scripted  # noqa: F401
from sim import tuning
from sim.driver import Controls, Driver, create_driver
from sim.race import COUNTDOWN, FINISHED, RACING, Race
from sim.replay import Recording
from sim.track import Track

from helpers import make_world, put_on_track

# Target lap times from the brief (seconds), with the band we accept.
LAP_BANDS = {"speedway": (11.0, 19.0), "technical": (19.0, 31.0),
             "esses": (14.0, 21.0), "grandprix": (21.0, 30.0), "oval": (9.5, 15.0)}


def scripted_race(track, cars=1, laps=3):
    return Race(track, [(slot, "scripted") for slot in range(cars)], laps=laps)


def test_countdown_then_go():
    race = scripted_race("speedway")
    step = int(tuning.COUNTDOWN_STEP * tuning.TICK_RATE)
    seen = []
    start = race.world.state_hash()
    for tick in range(3 * step):
        assert race.phase == COUNTDOWN
        assert race.countdown_number == 3 - tick // step
        for event in race.step():
            seen.append((tick, event))
    assert race.phase == RACING and race.countdown_number == 0
    assert seen == [(0, ("count", 3)), (step, ("count", 2)), (2 * step, ("count", 1)),
                    (3 * step - 1, ("go",))]
    assert race.world.state_hash() == start      # nothing moved during the countdown
    assert race.world.tick == 0                  # lap 1 is timed from the green light


@pytest.mark.parametrize("track", Track.available())
def test_scripted_driver_completes_three_clean_laps(track):
    race = scripted_race(track)
    events = []
    race.run(max_seconds=200, on_event=lambda r, e: events.append(e))
    car = race.world.cars[0]
    assert race.phase == FINISHED
    assert car.finished and car.laps == 3 and len(car.lap_times) == 3
    lo, hi = LAP_BANDS[track]
    assert all(lo < t < hi for t in car.lap_times), car.lap_times
    assert not [e for e in events if e[0] == "wall"]          # never touched a barrier
    assert events[-1] == ("race_over",)


@pytest.mark.parametrize("track", Track.available())
def test_scripted_driver_never_leaves_the_tarmac(track):
    race = scripted_race(track, laps=2)
    grass = 0
    while race.phase != FINISHED and race.world.tick < 120 * 120:
        race.step()
        grass += race.world.cars[0].surface
    assert race.phase == FINISHED
    assert grass == 0


@pytest.mark.parametrize("track", Track.available())
def test_four_scripted_cars_all_finish(track):
    race = scripted_race(track, cars=4).run(max_seconds=300)
    rows = race.results()
    assert [r["place"] for r in rows] == [1, 2, 3, 4]
    assert all(r["finished"] and r["laps"] == 3 for r in rows)
    times = [r["time"] for r in rows]
    assert times == sorted(times)
    assert all(r["best_lap"] == min(r["lap_times"]) for r in rows)


def test_scripted_driver_recovers_when_parked_against_a_barrier():
    world = make_world(laps=1)
    car = world.cars[0]
    lateral = world.track.limit[world.track.index_at(40.0)] - car.params.radius
    put_on_track(world, car, 40.0, lateral=lateral, heading_offset=math.pi / 2)   # nose on the wall
    driver = create_driver("scripted")
    driver.reset(world, 0)
    start = car.checkpoints_passed
    for _ in range(120 * 25):
        world.step([driver.act(world, 0)])
    assert car.checkpoints_passed - start >= 3     # got going again and made progress


def test_finished_cars_stop_and_slow_cars_get_a_grace_period(monkeypatch):
    class Parked(Driver):
        label = "Parked"

    monkeypatch.setattr(tuning, "FINISH_GRACE", 2.0)
    race = Race("speedway", [(0, "scripted"), (1, Parked())], laps=1).run(max_seconds=120)
    rows = race.results()
    assert race.phase == FINISHED
    assert rows[0]["slot"] == 0 and rows[0]["finished"]
    assert rows[1]["slot"] == 1 and not rows[1]["finished"] and rows[1]["time"] is None
    winner = race.world.cars[0]
    assert race.world.time == pytest.approx(winner.finish_time + 2.0 + tuning.COOLDOWN, abs=0.05)
    assert winner.retired and winner.speed == 0.0   # braked to a stop and parked


def test_finished_cars_park_and_never_reverse_into_the_race():
    class Slow(Driver):
        label = "Slow"

        def __init__(self):
            self.inner = create_driver("scripted")

        def act(self, world, i):
            c = self.inner.act(world, i)
            return Controls(c.steering, min(c.throttle, 0.45), c.brake)

    race = Race("speedway", [(0, "scripted"), (1, Slow())], laps=1)
    winner = race.world.cars[0]
    hits_after_flag = 0
    while race.phase != FINISHED and race.world.tick < 120 * 200:
        events = race.step()
        if winner.finished:
            assert winner.forward_speed > -0.01          # never rolls backwards
            hits_after_flag += sum(1 for e in events if e[0] == "car")
    assert race.phase == FINISHED
    assert winner.retired and winner.speed == 0.0        # parked, and no longer solid
    assert hits_after_flag == 0
    assert all(r["finished"] for r in race.results())
    race.restart()
    assert not race.world.cars[0].retired


def test_rolling_start_is_single_file_at_speed_and_in_the_tow():
    race = Race("speedway", [(slot, "scripted") for slot in range(4)], laps=1, rolling=True)
    cars = race.world.cars
    track = race.track
    for k, car in enumerate(cars):
        assert car.speed == pytest.approx(tuning.ROLLING_START_SPEED)
        assert abs(car.lateral) < 0.2 and car.surface == 0            # single file on the road
        assert car.s > track.length / 2                               # behind the line
        if k:
            gap = cars[k - 1].s - car.s
            assert gap == pytest.approx(tuning.ROLLING_START_GAP, abs=0.6)
            assert gap < tuning.DRAFT_LENGTH
    before = race.world.state_hash()
    for _ in range(3 * tuning.TICK_RATE):                             # frozen during the countdown
        race.step()
    assert race.world.state_hash() == before
    for _ in range(30):
        race.step()
    assert all(car.draft > 0.2 for car in cars[1:]) and cars[0].draft == 0.0
    race.run(max_seconds=120)
    assert race.phase == FINISHED and all(r["finished"] for r in race.results())
    replay = Recording.from_race(race)
    assert replay.rolling and replay.make_race().run(max_seconds=120).final_hash == race.final_hash


def test_restart_gives_the_same_race_again():
    race = scripted_race("speedway", cars=2, laps=1).run()
    first = race.final_hash
    race.restart()
    assert race.phase == COUNTDOWN and race.world.tick == 0 and race.controls_log == []
    assert race.run().final_hash == first


# ------------------------------------------------------------------ replays

def wobbly_race():
    """A race whose controls are not trivially reproducible from the driver:
    a seeded random driver plus scripted cars that collide with it."""
    import random

    class Wobbly(Driver):
        label = "Wobbly"

        def reset(self, world, car_index):
            self.rng = random.Random(99)

        def act(self, world, car_index):
            return Controls(self.rng.uniform(-0.4, 0.4), self.rng.random(), 0.0)

    return Race("speedway", [(0, Wobbly()), (1, "scripted"), (3, "scripted")], laps=1, seed=5)


def test_recording_replays_to_the_identical_final_state(tmp_path):
    race = wobbly_race().run(max_seconds=120)
    assert race.phase == FINISHED
    recording = Recording.from_race(race)
    assert len(recording.controls) == race.world.tick
    path = recording.save(tmp_path / "race.replay.gz")

    loaded = Recording.load(path)
    assert loaded.controls == recording.controls            # floats survive the file exactly
    assert loaded.slots == [0, 1, 3] and loaded.laps == 1 and loaded.seed == 5
    assert loaded.compatibility_problems() == []
    replay = loaded.make_race().run(max_seconds=120)
    assert replay.final_hash == race.final_hash
    assert replay.world.state() == race.world.state()
    assert [r["time"] for r in replay.results()] == [r["time"] for r in race.results()]
    assert [d.label for d in replay.drivers] == ["Wobbly", "Scripted", "Scripted"]
    assert loaded.verify()


def test_replay_matches_at_every_tick():
    race = wobbly_race()
    hashes = []
    while race.phase != FINISHED:
        race.step()
        hashes.append(race.world.state_hash())
    replay = Recording.from_race(race).make_race()
    for expected in hashes:
        replay.step()
        assert replay.world.state_hash() == expected


def test_tampered_recording_is_detected(tmp_path):
    race = scripted_race("speedway", laps=1).run()
    recording = Recording.from_race(race)
    row = list(recording.controls[200])
    row[0] = 1.0 if row[0] <= 0 else -1.0
    recording.controls[200] = tuple(row)
    assert not recording.verify()


def test_changed_tuning_is_reported(monkeypatch):
    race = scripted_race("speedway", laps=1).run()
    recording = Recording.from_race(race)
    monkeypatch.setattr(tuning, "GRASS_GRIP", tuning.GRASS_GRIP * 0.5)
    assert recording.compatibility_problems() == ["physics tuning has changed"]


def test_identical_races_save_identical_files(tmp_path):
    a = Recording.from_race(scripted_race("speedway", laps=1).run()).save(tmp_path / "a.replay.gz")
    b = Recording.from_race(scripted_race("speedway", laps=1).run()).save(tmp_path / "b.replay.gz")
    assert a.read_bytes() == b.read_bytes()
