import sim.scripted  # noqa: F401
from sim.driver import Controls, create_driver
from sim.track import Track
from sim.world import World

FULL_THROTTLE = Controls(0.0, 1.0, 0.0)
COAST = Controls(0.0, 0.0, 0.0)


def make_world(cars=1, track="speedway", laps=3, seed=0):
    return World(Track.load(track), num_cars=cars, seed=seed, laps=laps)


def run_scripted(world, max_seconds=200.0):
    drivers = [create_driver("scripted", slot=s) for s in world.slots]
    limit = int(max_seconds * 120)
    while world.tick < limit and not all(c.finished for c in world.cars):
        world.step([d.act(world, i) for i, d in enumerate(drivers)])
    return world


def put_on_track(world, car, s, lateral=0.0, heading_offset=0.0, speed=0.0):
    """Place a car at distance s along the lap, optionally already moving."""
    import math
    track = world.track
    i = track.index_at(s)
    x = track.center[i, 0] + track.normal[i, 0] * lateral
    y = track.center[i, 1] + track.normal[i, 1] * lateral
    heading = track.heading_at(s) + heading_offset
    world.place_car(car, float(x), float(y), heading)
    car.vx = math.cos(heading) * speed
    car.vy = math.sin(heading) * speed
    car.refresh_speed()
    return car


def slide_car_along(world, car, s_from, s_to, step=0.5):
    """Move a car along the centreline by hand (no physics), running the
    checkpoint logic at every step.  s_to < s_from moves it backwards."""
    track = world.track
    direction = 1.0 if s_to >= s_from else -1.0
    s = s_from
    events = []
    while (s_to - s) * direction > 0:
        s += direction * step
        x, y = track.point_at(s)
        car.prev_x, car.prev_y = car.x, car.y
        car.x, car.y = x, y
        world.tick += 1
        world._update_checkpoints(world.cars.index(car), car, events)
    return events
