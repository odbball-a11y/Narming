import random

from sim.driver import Controls

from helpers import make_world, run_scripted


def random_controls(seed, ticks, cars):
    rng = random.Random(seed)
    seq = []
    for _ in range(ticks):
        seq.append([Controls(rng.uniform(-1, 1), rng.random(), rng.random() * (rng.random() < 0.2))
                    for _ in range(cars)])
    return seq


def play(seq, cars, seed=7):
    world = make_world(cars=cars, seed=seed)
    for controls in seq:
        world.step(controls)
    return world


def test_same_seed_and_controls_give_identical_state():
    seq = random_controls(123, 3000, 4)
    a = play(seq, 4)
    b = play(seq, 4)
    assert a.state() == b.state()
    assert a.state_hash() == b.state_hash()


def test_different_controls_give_different_state():
    a = play(random_controls(1, 600, 2), 2)
    b = play(random_controls(2, 600, 2), 2)
    assert a.state_hash() != b.state_hash()


def test_reset_restores_the_starting_state():
    world = make_world(cars=3)
    start = world.state_hash()
    for controls in random_controls(5, 500, 3):
        world.step(controls)
    assert world.state_hash() != start
    world.reset()
    assert world.state_hash() == start


def test_scripted_race_is_repeatable():
    a = run_scripted(make_world(cars=4))
    b = run_scripted(make_world(cars=4))
    assert a.state_hash() == b.state_hash()
    assert [c.lap_times for c in a.cars] == [c.lap_times for c in b.cars]
