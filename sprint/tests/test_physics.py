import math

import pytest

from sim import tuning
from sim.driver import Controls

from helpers import COAST, FULL_THROTTLE, make_world, put_on_track


def step_n(world, controls, n):
    events = []
    for _ in range(n):
        events += world.step([controls] * len(world.cars))
    return events


def test_car_accelerates_to_just_under_top_speed():
    world = make_world()
    car = world.cars[0]
    # Long run on the main straight is not long enough; measure on a treadmill
    # by re-placing the car while keeping its velocity.
    speed = 0.0
    for _ in range(40):
        put_on_track(world, car, 5.0, speed=speed)
        step_n(world, FULL_THROTTLE, 30)
        speed = car.speed
    assert 0.9 * car.params.top_speed < speed <= car.params.top_speed


def test_braking_stops_the_car_then_reverses():
    world = make_world()
    car = put_on_track(world, world.cars[0], 5.0, speed=25.0)
    step_n(world, Controls(0.0, 0.0, 1.0), 60)
    assert car.forward_speed < 5.0
    step_n(world, Controls(0.0, 0.0, 1.0), 240)
    assert -car.params.reverse_speed - 0.5 <= car.forward_speed < -1.0


def test_coasting_slows_down():
    world = make_world()
    car = put_on_track(world, world.cars[0], 5.0, speed=20.0)
    step_n(world, COAST, 120)
    assert 0.0 < car.speed < 20.0


def test_velocity_is_separate_from_heading_car_slides_then_recovers():
    world = make_world()
    car = put_on_track(world, world.cars[0], 10.0, speed=30.0)
    # Full lock at high speed: heading turns faster than grip can follow.
    step_n(world, Controls(1.0, 1.0, 0.0), 26)
    travel = math.atan2(car.vy, car.vx)
    drift = abs((car.heading - travel + math.pi) % (2 * math.pi) - math.pi)
    assert car.sliding
    assert car.slip > car.params.slide_threshold
    assert drift > 0.08                   # nose points inside the direction of travel
    # Lift and straighten: grip pulls the velocity back in line.
    step_n(world, COAST, 30)
    assert car.surface == 0               # still on the tarmac, so this is tyre grip
    assert not car.sliding
    assert car.slip < 0.5


def test_gentle_steering_at_low_speed_does_not_slide():
    world = make_world()
    car = put_on_track(world, world.cars[0], 10.0, speed=10.0)
    for _ in range(60):
        world.step([Controls(0.5, 0.2, 0.0)])
        assert not car.sliding


def test_steering_is_speed_sensitive_and_needs_motion():
    world = make_world()
    car = put_on_track(world, world.cars[0], 10.0)
    h0 = car.heading
    world.step([Controls(1.0, 0.0, 0.0)])
    assert car.heading == h0                       # parked car cannot rotate

    def yaw_at(speed):
        put_on_track(world, car, 10.0, speed=speed)
        before = car.heading
        world.step([Controls(1.0, 0.0, 0.0)])
        return (car.heading - before) / tuning.DT

    assert yaw_at(8.0) > yaw_at(30.0) > 0.0        # positive steering turns right (+heading)


def test_grass_has_drag_and_less_grip():
    world = make_world()
    track = world.track
    car = world.cars[0]
    on_grass = track.half_width_at(5.0) + 1.0
    put_on_track(world, car, 5.0, lateral=0.0, speed=20.0)
    step_n(world, COAST, 30)
    tarmac_speed = car.speed
    put_on_track(world, car, 5.0, lateral=on_grass, speed=20.0)
    assert car.surface == 1
    step_n(world, COAST, 30)
    assert car.speed < tarmac_speed - 3.0


def test_controls_are_clamped():
    a = make_world()
    b = make_world()
    for _ in range(200):
        a.step([Controls(5.0, 9.0, -3.0)])
        b.step([Controls(1.0, 1.0, 0.0)])
    assert a.state_hash() == b.state_hash()


def test_each_slot_has_its_own_parameters():
    world = make_world(cars=4)
    assert len({c.params for c in world.cars}) == 4
    assert world.cars[0].params is tuning.car_params(0)


# ------------------------------------------------------------- collisions

def test_barrier_stops_the_car_and_costs_speed():
    world = make_world()
    track = world.track
    car = put_on_track(world, world.cars[0], 5.0, heading_offset=math.pi / 2, speed=20.0)
    events = []
    max_out = 0.0
    for _ in range(240):
        events += world.step([FULL_THROTTLE])
        max_out = max(max_out, abs(car.lateral) + car.params.radius - track.limit[car.idx])
    assert max_out < 1e-6                           # never through the wall
    walls = [e for e in events if e[0] == "wall"]
    assert walls and walls[0][1] == 0
    assert walls[0][2] > 10.0                       # reported impact speed


def test_barrier_bounce_loses_speed():
    world = make_world()
    car = put_on_track(world, world.cars[0], 5.0, heading_offset=math.pi / 3, speed=20.0)
    hit = False
    for _ in range(240):
        before = car.speed
        events = world.step([COAST])
        if any(e[0] == "wall" for e in events):
            hit = True
            # Came back off the wall, slower, and now moving away from it.
            assert car.speed < 0.8 * before
            idx = car.idx
            toward_wall = car.vx * world.track.normal[idx, 0] + car.vy * world.track.normal[idx, 1]
            assert toward_wall < 0.0
            break
    assert hit


def test_head_on_cars_bounce_apart_and_conserve_momentum():
    world = make_world(cars=2)
    a, b = world.cars
    put_on_track(world, a, 10.0, speed=15.0)
    put_on_track(world, b, 22.0, heading_offset=math.pi, speed=15.0)
    px0 = a.vx * a.params.mass + b.vx * b.params.mass
    py0 = a.vy * a.params.mass + b.vy * b.params.mass
    hit = None
    for _ in range(120):
        events = world.step([COAST, COAST])
        hit = next((e for e in events if e[0] == "car"), None)
        if hit:
            break
    assert hit and hit[1:3] == (0, 1) and hit[3] > 20.0
    # Momentum just after the hit matches (friction only acts over time).
    px1 = a.vx * a.params.mass + b.vx * b.params.mass
    py1 = a.vy * a.params.mass + b.vy * b.params.mass
    assert px1 == pytest.approx(px0, abs=1.0)
    assert py1 == pytest.approx(py0, abs=1.0)
    dist = math.hypot(a.x - b.x, a.y - b.y)
    assert dist >= a.params.radius + b.params.radius - 1e-6
    step_n(world, COAST, 30)
    assert math.hypot(a.x - b.x, a.y - b.y) > dist  # moving apart


def test_cars_never_overlap_in_a_four_car_race():
    import sim.scripted  # noqa: F401
    from sim.driver import create_driver
    world = make_world(cars=4, laps=1)
    drivers = [create_driver("scripted", slot=i) for i in range(4)]
    for _ in range(120 * 20):
        world.step([d.act(world, i) for i, d in enumerate(drivers)])
        for i in range(4):
            for j in range(i + 1, 4):
                a, b = world.cars[i], world.cars[j]
                assert math.hypot(a.x - b.x, a.y - b.y) > a.params.radius + b.params.radius - 0.3
