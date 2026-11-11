"""Damage (permanent, speed only) and drafting."""
import math

import pytest

from sim import tuning
from sim.driver import Controls
from sim.track import Track
from sim.world import World

from helpers import COAST, FULL_THROTTLE, make_world, put_on_track


def crash_into_wall(speed):
    world = make_world()
    car = put_on_track(world, world.cars[0], 5.0, heading_offset=math.pi / 2, speed=speed)
    for _ in range(120):
        if any(e[0] == "wall" for e in world.step([COAST])):
            break
    return world, car


def test_hard_wall_hit_does_damage_in_proportion_to_impact():
    _, slow = crash_into_wall(12.0)
    _, fast = crash_into_wall(28.0)
    assert 0.0 < slow.damage < fast.damage < 1.0
    assert fast.damage == pytest.approx(tuning.WALL_DAMAGE * (28.0 - tuning.DAMAGE_MIN_IMPACT), rel=0.25)


def test_gentle_tap_does_no_damage():
    _, car = crash_into_wall(2.5)
    assert car.damage == 0.0


def test_damage_is_permanent_and_capped_and_cleared_by_a_new_race():
    world, car = crash_into_wall(28.0)
    hurt = car.damage
    for _ in range(600):
        world.step([COAST])
    assert car.damage == hurt                      # no repair
    car.add_damage(5.0)
    assert car.damage == 1.0
    world.reset()
    assert car.damage == 0.0


def speed_after_run(damage, draft=0.0, ticks=600):
    world = make_world()
    car = world.cars[0]
    speed = 0.0
    for _ in range(ticks // 30):                   # treadmill on the straight
        put_on_track(world, car, 5.0, speed=speed)
        car.damage = damage
        for _ in range(30):
            car.draft = draft
            world.step([FULL_THROTTLE])
        speed = car.speed
    return speed


def test_damage_cuts_top_speed_and_acceleration():
    healthy = speed_after_run(0.0)
    wrecked = speed_after_run(1.0)
    assert wrecked == pytest.approx(healthy * (1 - tuning.DAMAGE_TOP_SPEED_LOSS), rel=0.05)
    assert speed_after_run(1.0, ticks=60) < speed_after_run(0.0, ticks=60)
    assert wrecked > 15.0                          # slow, but still a car


def test_damage_does_not_affect_steering():
    def yaw(damage):
        world = make_world()
        car = put_on_track(world, world.cars[0], 10.0, speed=20.0)
        car.damage = damage
        before = car.heading
        world.step([Controls(1.0, 0.0, 0.0)])
        return car.heading - before

    assert yaw(0.0) == yaw(1.0)


def test_car_to_car_hit_damages_both():
    world = make_world(cars=2)
    a, b = world.cars
    put_on_track(world, a, 10.0, speed=15.0)
    put_on_track(world, b, 22.0, heading_offset=math.pi, speed=15.0)
    for _ in range(120):
        world.step([COAST, COAST])
    assert a.damage > 0.1 and a.damage == pytest.approx(b.damage)


# ------------------------------------------------------------------ drafting

def pair(gap, side=0.0, lead_speed=28.0, ghost=False):
    """Car 0 follows car 1 down the main straight."""
    world = World(Track.load("speedway"), num_cars=2, ghost=ghost)
    follower, lead = world.cars
    put_on_track(world, lead, 30.0, speed=lead_speed)
    put_on_track(world, follower, 30.0 - gap, lateral=side, speed=24.0)
    world.step([FULL_THROTTLE, FULL_THROTTLE])
    return world, follower, lead


def test_car_right_behind_a_fast_car_gets_a_tow():
    _, follower, lead = pair(gap=6.0)
    assert follower.draft > 0.3 and follower.draft_source == 1
    assert lead.draft == 0.0 and lead.draft_source == -1


def test_tow_fades_with_distance_and_offset_and_needs_a_fast_leader():
    close = pair(gap=5.0)[1].draft
    far = pair(gap=12.0)[1].draft
    assert close > far > 0.0
    assert pair(gap=tuning.DRAFT_LENGTH + 2.0)[1].draft == 0.0
    assert pair(gap=6.0, side=1.2)[1].draft < pair(gap=6.0)[1].draft
    assert pair(gap=6.0, side=4.5)[1].draft == 0.0
    assert pair(gap=6.0, lead_speed=tuning.DRAFT_MIN_SPEED - 2.0)[1].draft == 0.0


def test_tow_makes_the_follower_faster():
    def follower_speed(side):
        world, follower, lead = pair(gap=7.0, side=side)
        for _ in range(100):
            world.step([FULL_THROTTLE, FULL_THROTTLE])
        return follower.speed

    assert follower_speed(0.0) > follower_speed(4.5) + 0.5
    assert speed_after_run(0.0, draft=1.0) > speed_after_run(0.0) * 1.05


def test_ghost_cars_pass_through_each_other_with_no_tow():
    world = World(Track.load("speedway"), slots=[0, 0, 0], ghost=True)
    for _ in range(240):
        events = world.step([FULL_THROTTLE] * 3)
        assert not [e for e in events if e[0] == "car"]
    a, b, c = world.cars
    assert (a.x, a.y) == (b.x, b.y) == (c.x, c.y)   # same slot, same inputs, never pushed apart
    assert a.draft == 0.0 and a.speed > 15.0


def test_retired_cars_are_not_simulated():
    world = make_world(cars=2)
    world.cars[1].retired = True
    before = world.cars[1].state()
    for _ in range(200):
        world.step([FULL_THROTTLE, FULL_THROTTLE])
    assert world.cars[1].state() == before
    assert world.cars[0].speed > 10.0
