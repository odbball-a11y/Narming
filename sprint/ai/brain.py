"""What a learned driver sees, the small neural network that drives, and the
Driver that plugs a trained network into any car slot.

The network is tiny on purpose (one hidden layer): evolution only has to
find a few hundred numbers, and a whole population can be run in one batched
NumPy call.
"""
from __future__ import annotations

import math

import numpy as np

from sim.driver import Controls, Driver

# Distances ahead (track units) at which the driver is told the curvature.
LOOK_AHEAD = (4.0, 9.0, 16.0, 25.0, 36.0, 50.0)

N_INPUTS = 4 + len(LOOK_AHEAD) + 3 + 5
N_HIDDEN = 16
N_OUTPUTS = 2          # steering; throttle (+) / brake (-)
N_WEIGHTS = N_HIDDEN * N_INPUTS + N_HIDDEN + N_OUTPUTS * N_HIDDEN + N_OUTPUTS

# The network decides every DECISION_TICKS sim ticks (30 times a second) and
# holds its controls in between.  Training and racing must use the same value.
DECISION_TICKS = 4

INPUT_NAMES = (
    ["forward speed", "sideways speed", "offset from centre", "heading error"]
    + [f"curvature {int(d)} ahead" for d in LOOK_AHEAD]
    + ["track half-width", "damage", "draft"]
    + ["gap to car ahead", "car ahead offset", "closing speed", "gap to car behind", "car behind offset"]
)
assert len(INPUT_NAMES) == N_INPUTS


def observe(world, i: int) -> list[float]:
    """The inputs for car i, each scaled to roughly -1..1.

    Signs follow the sim's convention: positive = to the right.
    """
    car = world.cars[i]
    track = world.track
    idx = car.idx
    hw = track._hw[idx]
    herr = (car.heading - track._heading[idx] + math.pi) % (2.0 * math.pi) - math.pi
    ch, sh = math.cos(car.heading), math.sin(car.heading)
    obs = [
        (car.vx * ch + car.vy * sh) / 32.0,
        (-car.vx * sh + car.vy * ch) / 10.0,
        car.lateral / hw,
        herr,
    ]
    curv, n, ds = track._curv, track.n, track.ds
    for d in LOOK_AHEAD:
        obs.append(curv[(idx + int(d / ds)) % n] * 8.0)
    obs.append(hw / 6.0)
    obs.append(car.damage)
    obs.append(car.draft)

    ahead_gap, ahead_side, closing, behind_gap, behind_side = 1.0, 0.0, 0.0, 1.0, 0.0
    if not world.ghost and len(world.cars) > 1:
        length = track.length
        best_ahead, best_behind = 30.0, 15.0
        for j, other in enumerate(world.cars):
            if j == i or other.retired:
                continue
            gap = (other.s - car.s) % length
            if gap < best_ahead:
                best_ahead = gap
                ahead_gap = gap / 30.0
                ahead_side = (other.lateral - car.lateral) / 5.0
                closing = (car.speed - other.speed) / 15.0
            back = length - gap
            if back < best_behind:
                best_behind = back
                behind_gap = back / 15.0
                behind_side = (other.lateral - car.lateral) / 5.0
    obs += [ahead_gap, ahead_side, closing, behind_gap, behind_side]
    return obs


def unpack(weights: np.ndarray):
    """Split flat weight vectors (..., N_WEIGHTS) into the layer arrays."""
    a = N_HIDDEN * N_INPUTS
    b = a + N_HIDDEN
    c = b + N_OUTPUTS * N_HIDDEN
    lead = weights.shape[:-1]
    return (weights[..., :a].reshape(lead + (N_HIDDEN, N_INPUTS)),
            weights[..., a:b],
            weights[..., b:c].reshape(lead + (N_OUTPUTS, N_HIDDEN)),
            weights[..., c:])


class Population:
    """Runs many networks at once: one row of weights per driver."""

    def __init__(self, weights: np.ndarray):
        self.w1, self.b1, self.w2, self.b2 = unpack(np.asarray(weights, dtype=np.float64))

    def act(self, obs: np.ndarray) -> np.ndarray:
        """obs is (P, N_INPUTS); returns (P, 2) in -1..1."""
        hidden = np.tanh(np.einsum("phi,pi->ph", self.w1, obs) + self.b1)
        return np.tanh(np.einsum("poh,ph->po", self.w2, hidden) + self.b2)


def to_controls(steer: float, pedal: float) -> Controls:
    if pedal >= 0.0:
        return Controls(steer, pedal, 0.0)
    return Controls(steer, 0.0, -pedal)


class NeuralDriver(Driver):
    """A trained network driving one car through the normal Driver interface."""

    def __init__(self, weights: np.ndarray, label: str = "Evolved"):
        self.weights = np.asarray(weights, dtype=np.float64)
        self.w1, self.b1, self.w2, self.b2 = unpack(self.weights)
        self.label = label
        self.held = Controls()

    def reset(self, world, car_index: int) -> None:
        self.held = Controls()

    def act(self, world, car_index: int) -> Controls:
        if world.tick % DECISION_TICKS == 0:
            obs = np.array(observe(world, car_index))
            out = np.tanh(self.w2 @ np.tanh(self.w1 @ obs + self.b1) + self.b2)
            self.held = to_controls(float(out[0]), float(out[1]))
        return self.held
