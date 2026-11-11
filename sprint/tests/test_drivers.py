import pygame
import pytest

from sim import tuning
from sim.driver import Controls, Driver, create_driver, driver_types, register_driver

import game.input as game_input
from helpers import make_world


def test_registry_lists_and_creates_drivers():
    keys = [k for k, _ in driver_types()]
    assert "scripted" in keys and "human" in keys
    for key in keys:
        assert isinstance(create_driver(key, slot=1), Driver)
    with pytest.raises(KeyError):
        create_driver("no-such-driver")


def test_custom_driver_can_be_registered_and_drive():
    class Floor(Driver):
        def act(self, world, car_index):
            return Controls(0.0, 1.0, 0.0)

    register_driver("floor-it", "Floor it", lambda slot=0: Floor())
    world = make_world()
    driver = create_driver("floor-it")
    for _ in range(120):
        world.step([driver.act(world, 0)])
    assert world.cars[0].speed > 10.0


def test_controls_clamp():
    assert Controls(-3, 2, -1).clamped() == Controls(-1.0, 1.0, 0.0)


def test_bindings_have_four_distinct_players():
    binds = game_input.load_bindings()
    assert len(binds) == 4
    codes = [c for b in binds for c in b["codes"].values()]
    assert len(set(codes)) == 16
    assert binds[0]["codes"]["left"] == pygame.K_LEFT
    assert binds[1]["codes"]["throttle"] == pygame.K_w


def test_keyboard_steering_is_smoothed_in_the_input_layer(monkeypatch):
    pygame.init()
    binding = game_input.load_bindings()[0]
    driver = game_input.KeyboardDriver(binding)
    held = set()

    class Keys:
        def __getitem__(self, code):
            return code in held

    monkeypatch.setattr(pygame.key, "get_pressed", lambda: Keys())
    held.add(binding["codes"]["right"])
    held.add(binding["codes"]["throttle"])
    first = driver.act(None, 0)
    assert 0.0 < first.steering < 0.2                 # ramps, does not jump to 1
    for _ in range(tuning.TICK_RATE):
        last = driver.act(None, 0)
    assert last.steering == 1.0 and last.throttle == 1.0
    held.clear()
    after = driver.act(None, 0)
    assert 0.8 < after.steering < 1.0                 # eases back to centre
    for _ in range(tuning.TICK_RATE):
        after = driver.act(None, 0)
    assert after == Controls(0.0, 0.0, 0.0)
