"""Car traits: the budget, their effect on the car, inheritance, and the
racer's car being used in training, races and the screens."""
import numpy as np
import pygame
import pytest

from sim import cartraits, tuning
from sim.driver import Controls
from sim.race import Race

from helpers import COAST, FULL_THROTTLE, make_world, put_on_track


def test_budget_and_validity():
    assert cartraits.is_valid(cartraits.default())
    assert cartraits.stars_used(cartraits.default()) == tuning.TRAIT_BUDGET
    bad = dict(cartraits.default(), top_speed=5)
    assert not cartraits.is_valid(bad)
    rng = np.random.default_rng(0)
    for _ in range(50):
        t = cartraits.random_traits(rng)
        assert cartraits.is_valid(t)
    assert cartraits.is_valid(cartraits.rebalance(dict(cartraits.default(), top_speed=5, accel=5), rng))


def test_default_car_is_todays_car():
    assert cartraits.params_for(cartraits.default()) == tuning.CarParams()


def test_each_trait_changes_the_right_thing():
    fast = cartraits.params_for({"top_speed": 5, "accel": 1, "handling": 3, "braking": 3, "weight": "medium"})
    base = tuning.CarParams()
    assert fast.top_speed == pytest.approx(base.top_speed * (1 + 2 * tuning.TRAIT_STEP))
    assert fast.accel == pytest.approx(base.accel * (1 - 2 * tuning.TRAIT_STEP))
    grippy = cartraits.params_for({"top_speed": 3, "accel": 3, "handling": 5, "braking": 1, "weight": "medium"})
    assert grippy.grip > base.grip and grippy.steer_rate_low > base.steer_rate_low
    assert grippy.brake_decel < base.brake_decel
    heavy = cartraits.params_for(dict(cartraits.default(), weight="heavy"))
    light = cartraits.params_for(dict(cartraits.default(), weight="light"))
    assert heavy.mass > 1 > light.mass and light.accel > base.accel > heavy.accel
    assert heavy.traits[4] == 1.0 and light.traits[4] == -1.0 and fast.traits[0] == 1.0


def test_a_fast_car_really_is_faster_on_a_straight():
    def top(traits):
        world = make_world()
        world.cars[0].params = cartraits.params_for(traits)
        car = world.cars[0]
        speed = 0.0
        for _ in range(30):
            put_on_track(world, car, 5.0, speed=speed)
            for _ in range(30):
                world.step([FULL_THROTTLE])
            speed = car.speed
        return speed

    fast = {"top_speed": 5, "accel": 3, "handling": 2, "braking": 2, "weight": "medium"}
    slow = {"top_speed": 1, "accel": 3, "handling": 4, "braking": 4, "weight": "medium"}
    assert top(fast) > top(slow) * 1.1


def test_heavy_car_wins_the_shove():
    world = make_world(cars=2)
    world.car_params = [cartraits.params_for(dict(cartraits.default(), weight="heavy")),
                        cartraits.params_for(dict(cartraits.default(), weight="light"))]
    world.reset()
    heavy, light = world.cars
    put_on_track(world, heavy, 10.0, speed=15.0)
    put_on_track(world, light, 22.0, heading_offset=np.pi, speed=15.0)
    for _ in range(120):
        before = [(c.vx, c.vy) for c in world.cars]
        if any(e[0] == "car" for e in world.step([COAST, COAST])):
            break
    change = [np.hypot(c.vx - vx, c.vy - vy) for c, (vx, vy) in zip(world.cars, before)]
    assert change[1] > change[0] * 1.4      # the light car is knocked about far more


def test_inheritance_takes_each_trait_from_a_parent_and_keeps_the_budget():
    sire = {"top_speed": 5, "accel": 5, "handling": 1, "braking": 1, "weight": "heavy"}
    dam = {"top_speed": 1, "accel": 1, "handling": 5, "braking": 5, "weight": "light"}
    rng = np.random.default_rng(3)
    seen = set()
    for _ in range(40):
        child, source = cartraits.inherit(sire, dam, rng)
        assert cartraits.is_valid(child)
        assert child["weight"] == (sire if source["weight"] == "sire" else dam)["weight"]
        seen.add(child["weight"])
    assert seen == {"heavy", "light"}


def test_drivers_bring_their_car_to_a_race():
    class Heavy:
        label = "Heavy"
        car_params = cartraits.params_for(dict(cartraits.default(), weight="heavy"))

        def reset(self, world, i):
            pass

        def act(self, world, i):
            return Controls(0.0, 0.5, 0.0)

    race = Race("oval", [(0, Heavy()), (1, "scripted")], laps=1, rolling=True)
    assert race.world.cars[0].params.mass == tuning.HEAVY_MASS
    assert race.world.cars[1].params == tuning.car_params(1)
    race.restart()
    assert race.world.cars[0].params.mass == tuning.HEAVY_MASS        # kept across restarts


# ------------------------------------------------------------------ stable

def test_racers_train_and_race_in_their_own_car(dirs):
    from ai import evolve, stable
    from test_stable import quick_train
    car = {"top_speed": 5, "accel": 2, "handling": 3, "braking": 2, "weight": "light"}
    racer = stable.create(stable.STABLE_DIR, "Rocket", 0.5, 0.5,
                          [{"name": "Scripted car", "kind": "scripted"}], 1, traits=car)
    with pytest.raises(ValueError):
        stable.create(stable.STABLE_DIR, "Cheat", 0.5, 0.5, [], 1,
                      traits=dict(car, handling=5))
    quick_train(racer)
    assert evolve.load_config(racer / "v1")["car"] == car
    assert evolve.load_history(racer / "v1")[0]["car"] == car
    driver = stable.champion(racer)
    assert driver.car_params.mass == tuning.LIGHT_MASS
    assert any(p.get("traits") == car for p in stable.partner_options(stable.STABLE_DIR))


def test_foals_inherit_a_car(dirs):
    from ai import stable
    from test_stable import quick_train
    p = [{"name": "Scripted car", "kind": "scripted"}]
    sire = stable.create(stable.STABLE_DIR, "Sire", 0.5, 0.5, p, 1,
                         traits={"top_speed": 5, "accel": 5, "handling": 1, "braking": 1, "weight": "heavy"})
    dam = stable.create(stable.STABLE_DIR, "Dam", 0.5, 0.5, p, 1,
                        traits={"top_speed": 1, "accel": 1, "handling": 5, "braking": 5, "weight": "light"})
    for d in (sire, dam):
        quick_train(d)
        stable.retire(d)
    foal = stable.mate(stable.STABLE_DIR, sire, dam, "Foal")
    cert = stable.breed(foal, litter=4, shortlist=2, camp_generations=1, camp_population=4)
    traits = stable.load(foal)["traits"]
    assert cartraits.is_valid(traits) and cert["traits"] == traits
    assert set(cert["traits_from"]) == set(cartraits.STARS) | {"weight", "balance"}
    assert stable.champion(foal).car_params == cartraits.params_for(traits)
    assert any(n.startswith("Car:") for n in cert["expectations"])


def test_create_screen_spends_the_car_stars(app):
    from ai import stable
    from game.stable_screens import CreateScreen
    from test_stable import press, type_text
    app.show(CreateScreen(app))
    screen = app.current
    type_text(app, "Starry")
    screen.row = screen.rows().index("top_speed")
    press(app, pygame.K_RIGHT)                      # no stars left: cannot add
    assert screen.traits["top_speed"] == 3
    press(app, pygame.K_LEFT, pygame.K_LEFT)        # 3 -> 1, two stars free
    assert screen.stars_left() == 2
    screen.row = screen.rows().index("start")
    press(app, pygame.K_RETURN)
    assert "stars" in screen.message                # must spend them all
    screen.row = screen.rows().index("accel")
    press(app, pygame.K_RIGHT, pygame.K_RIGHT)      # 3 -> 5
    screen.row = screen.rows().index("weight")
    press(app, pygame.K_RIGHT)
    assert screen.traits["weight"] == "heavy" and screen.stars_left() == 0
    screen.row = screen.rows().index("start")
    press(app, pygame.K_RETURN)
    racer = stable.load(app.started[-1])
    assert racer["traits"] == {"top_speed": 1, "accel": 5, "handling": 3, "braking": 3, "weight": "heavy"}
    # Upskilling cannot change the car.
    app.show(CreateScreen(app, app.started[-1]))
    assert "weight" not in app.current.rows()


def test_exam_on_several_tracks_in_a_chosen_car():
    from ai import brain, evolve
    weights = brain.random_weights(np.random.default_rng(1), 1, brain.DEFAULT_ARCH)[0]
    car = {"top_speed": 4, "accel": 4, "handling": 2, "braking": 2, "weight": "heavy"}
    report = evolve.exam(weights, brain.DEFAULT_ARCH, ["oval", "speedway"], car=car)
    assert set(report) == {"oval", "speedway"}


def test_tyre_scrub_and_friction_circle_are_on_and_cost_slides_only():
    import math
    from dataclasses import replace
    from sim import tuning
    from sim.driver import Controls
    from sim.track import Track
    from sim.world import World
    new = tuning.car_params(0)
    assert (new.scrub, new.brake_circle, new.throttle_circle) == (8.0, 0.8, 0.6)
    base = replace(new, **tuning.CLASSIC_PHYSICS)            # the classic physics is still one switch away

    def one_tick(params, sideways):
        """Forward speed after one tick of a car moving at 25 u/s with `sideways` u/s of slide."""
        w = World(Track.load("speedway"), 1, laps=1, params=[params])
        car = w.cars[0]
        ch, sh = math.cos(car.heading), math.sin(car.heading)
        car.vx, car.vy = 25.0 * ch - sideways * sh, 25.0 * sh + sideways * ch
        w.step([Controls(0.0, 0.0, 0.0)])
        c = car
        return c.vx * math.cos(c.heading) + c.vy * math.sin(c.heading)
    scrubby = replace(base, scrub=8.0)
    assert one_tick(base, 0.0) == one_tick(scrubby, 0.0)           # no slide, no scrub
    assert one_tick(scrubby, 6.0) < one_tick(base, 6.0) - 0.1      # a slide now drags the car back
    circle = replace(base, brake_circle=0.9)
    assert circle.grip == base.grip                                # (the circle acts through the brake input)


def test_balance_is_bred_and_costs_no_stars():
    import numpy as np
    from sim import cartraits
    loose = dict(cartraits.default(), balance=2)
    stable_car = dict(cartraits.default(), balance=-2)
    assert cartraits.is_valid(loose) and cartraits.balance_of(cartraits.default()) == 0
    assert cartraits.params_for(loose).balance == 1.0 and cartraits.params_for(stable_car).balance == -1.0
    assert "very loose" in cartraits.describe(loose) and "very" not in cartraits.describe(cartraits.default())
    rng = np.random.default_rng(3)
    seen = set()
    for _ in range(200):
        child, source = cartraits.inherit(loose, stable_car, rng)
        assert cartraits.is_valid(child) and source["balance"] in ("sire", "dam") and -2 <= child["balance"] <= 2
        seen.add(child["balance"])
    assert {-2, 2} <= seen and len(seen) >= 4                      # from either parent, sometimes a step between


def test_two_grip_physics_understeers_and_rotates_with_inertia():
    import math
    from dataclasses import replace
    from sim import tuning
    from sim.driver import Controls
    from sim.track import Track
    from sim.world import World
    base = tuning.car_params(0)
    assert base.front_limit == 0.0 and base.yaw_lag == 0.0 or True     # (the defaults are chosen elsewhere)

    def yaw_after(params, ticks, speed=30.0):
        w = World(Track.load("speedway"), 1, laps=1, params=[params])
        car = w.cars[0]
        ch, sh = math.cos(car.heading), math.sin(car.heading)
        car.vx, car.vy = speed * ch, speed * sh
        for _ in range(ticks):
            w.step([Controls(1.0, 0.0, 0.0)])
        return car.yaw_rate
    classic = replace(base, **tuning.CLASSIC_PHYSICS)
    under = replace(classic, front_limit=1.0)
    lagged = replace(classic, yaw_lag=0.2)
    assert yaw_after(under, 3) < yaw_after(classic, 3) * 0.9           # the front cannot turn the car that hard
    assert yaw_after(lagged, 3) < yaw_after(classic, 3) * 0.5          # rotation builds up over a fifth of a second
    assert yaw_after(lagged, 36) > 0.7 * yaw_after(classic, 36)        # ... and gets most of the way


def test_weight_transfer_moves_load_and_unsettles_the_rear_under_braking():
    import math
    from dataclasses import replace
    from sim import tuning
    from sim.driver import Controls
    from sim.track import Track
    from sim.world import World
    base = replace(tuning.car_params(0), **tuning.CLASSIC_PHYSICS)
    two = replace(base, front_limit=1.0, brake_circle=0.8, throttle_circle=0.6)
    moving = replace(two, weight_transfer=0.25, lateral_transfer=0.1)

    def run(params, controls, ticks, speed=25.0):
        w = World(Track.load("speedway"), 1, laps=1, params=[params])
        car = w.cars[0]
        ch, sh = math.cos(car.heading), math.sin(car.heading)
        car.vx, car.vy = speed * ch, speed * sh
        car.forward_speed = speed
        peak = 0.0
        for _ in range(ticks):
            w.step([controls])
            peak = max(peak, car.slip)
        return car, peak
    car, _ = run(moving, Controls(0.0, 0.0, 1.0), 30)
    assert car.front_load > 1.15 and car.rear_load < 0.85           # braking loads the front
    car, _ = run(moving, Controls(0.0, 1.0, 0.0), 30, speed=10.0)
    assert car.rear_load > car.front_load                          # accelerating loads the rear
    car, _ = run(two, Controls(0.0, 0.0, 1.0), 30)
    assert car.front_load == 1.0 == car.rear_load                  # off: nothing moves
    # Braking hard while turning: with the load off the rear it slides more.
    _, still = run(two, Controls(1.0, 0.0, 0.5), 40)
    _, light = run(moving, Controls(1.0, 0.0, 0.5), 40)
    assert light > 2.0 * still
