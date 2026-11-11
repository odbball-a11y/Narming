import pytest

from helpers import make_world, run_scripted, slide_car_along


def test_scripted_driver_completes_three_clean_laps_on_speedway():
    world = run_scripted(make_world(laps=3))
    car = world.cars[0]
    assert car.finished and car.laps == 3
    assert len(car.lap_times) == 3
    assert all(8.0 < t < 25.0 for t in car.lap_times), car.lap_times
    assert car.best_lap == min(car.lap_times)
    assert car.finish_time == pytest.approx(sum(car.lap_times))


def test_scripted_driver_stays_on_the_tarmac():
    world = make_world(laps=2)
    from sim.driver import create_driver
    driver = create_driver("scripted")
    off = 0
    while not world.cars[0].finished and world.tick < 120 * 100:
        events = world.step([driver.act(world, 0)])
        off += world.cars[0].surface
        assert not any(e[0] == "wall" for e in events)
    assert world.cars[0].finished
    assert off == 0


def test_full_lap_by_hand_counts():
    world = make_world(laps=5)
    car = world.cars[0]
    L = world.track.length
    slide_car_along(world, car, -3.0, 3.0)          # cross the line: lap 1 starts
    assert car.crossed_start and car.laps == 0
    events = slide_car_along(world, car, 3.0, L + 3.0)
    assert car.laps == 1
    assert [e[0] for e in events] == ["lap"]


def test_reversing_over_the_line_does_not_count():
    world = make_world(laps=5)
    car = world.cars[0]
    slide_car_along(world, car, -3.0, 3.0)
    for _ in range(4):                               # back and forth over the line
        slide_car_along(world, car, 3.0, -3.0)
        slide_car_along(world, car, -3.0, 3.0)
    assert car.laps == 0


def test_driving_the_whole_lap_backwards_does_not_count():
    world = make_world(laps=5)
    car = world.cars[0]
    L = world.track.length
    slide_car_along(world, car, -3.0, 3.0)
    slide_car_along(world, car, 3.0, -2 * L)         # two laps the wrong way
    assert car.laps == 0
    assert car.next_checkpoint == 1


def test_shortcut_that_skips_a_checkpoint_does_not_count():
    world = make_world(laps=5)
    car = world.cars[0]
    track = world.track
    L = track.length
    gate = L / len(track.checkpoints)
    slide_car_along(world, car, -3.0, 2.5 * gate)    # through gates 0, 1, 2
    assert car.next_checkpoint == 3
    # Teleport past gates 3 and 4 (a "shortcut"), then finish the lap.
    x, y = track.point_at(5.5 * gate)
    car.x, car.y = x, y
    slide_car_along(world, car, 5.5 * gate, L + 3.0)
    assert car.laps == 0
    assert car.next_checkpoint == 3                  # still waiting for the missed gate
    # Going back for the missed gates makes the next lap count.
    x, y = track.point_at(2.5 * gate)
    car.x, car.y = x, y
    slide_car_along(world, car, 2.5 * gate, L + 3.0)
    assert car.laps == 1


def test_race_ends_after_the_set_number_of_laps():
    world = make_world(laps=2)
    car = world.cars[0]
    L = world.track.length
    events = slide_car_along(world, car, -3.0, 3 * L + 3.0)
    assert car.laps == 2 and car.finished
    assert [e[0] for e in events] == ["lap", "lap", "finish"]


def test_standings_follow_track_position():
    world = make_world(cars=4, laps=3)
    assert world.standings() == [0, 1, 2, 3]         # grid order
    world = run_scripted(world)
    order = world.standings()
    times = [world.cars[i].finish_time for i in order]
    assert times == sorted(times)
