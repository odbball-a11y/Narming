"""What a learned driver sees, the neural network that drives, and the Driver
that plugs a trained network into any car slot.

The network shape is a per-run choice (an "arch" dict):

    {"hidden": [24, 16], "memory": 4}

`hidden` lists the hidden layer sizes.  `memory` is a number of extra outputs
that are fed back in as extra inputs at the next decision, so the driver can
carry information from one moment to the next (e.g. "I am setting up a pass").
Evolution does not need gradients, so this costs nothing extra to train.

All weights of one driver are one flat vector, layer by layer: W (out, in)
then b (out).
"""
from __future__ import annotations

import math

import numpy as np

from sim.driver import Controls, Driver

# Distances ahead (track units) at which the driver is told the curvature.
LOOK_AHEAD = (4.0, 9.0, 16.0, 25.0, 36.0, 50.0)

# A bend tighter than this (1/radius) ends a "straight".
STRAIGHT_CURVATURE = 0.035
STRAIGHT_SCAN = 70.0

# Further look-ahead points, added in input version 2 so drivers see long
# straights and hairpins coming (about 20 and 30 car lengths).
FAR_AHEAD = (80.0, 120.0)

# The inputs, by version.  New inputs are only ever appended, so an older
# brain can be upgraded by wiring the new inputs in with zero strength: it
# then drives exactly as before until training puts the new inputs to use.
_INPUTS_V1 = (
    ["forward speed", "sideways speed", "offset from centre", "heading error"]
    + [f"curvature {int(d)} ahead" for d in LOOK_AHEAD]
    + ["track half-width", "straight ahead", "damage", "my tow", "tow I give"]
    + ["ahead1 gap", "ahead1 side", "ahead1 closing",
       "ahead2 gap", "ahead2 side", "ahead2 closing",
       "behind gap", "behind side", "behind closing",
       "left car near", "left car along", "right car near", "right car along"]
)
_INPUTS_V2 = _INPUTS_V1 + [f"curvature {int(d)} ahead" for d in FAR_AHEAD] + [
    "room to barrier left", "room to barrier right", "race place", "race left"]
INPUT_VERSIONS = {1: _INPUTS_V1, 2: _INPUTS_V2}
INPUT_VERSION = 2
INPUT_NAMES = INPUT_VERSIONS[INPUT_VERSION]
N_INPUTS = len(INPUT_NAMES)
N_CONTROLS = 2          # steering; throttle (+) / brake (-)

DEFAULT_ARCH = {"hidden": [24, 16], "memory": 4, "inputs": INPUT_VERSION}

# The network decides every DECISION_TICKS sim ticks (30 times a second) and
# holds its controls in between.  Training and racing must use the same value.
DECISION_TICKS = 4

AHEAD_RANGE = 30.0
BEHIND_RANGE = 15.0
SIDE_RANGE = 5.0        # along-track window that counts as "alongside"
SIDE_WIDTH = 6.0        # lateral distance at which an alongside car stops mattering


# ------------------------------------------------------------ observation

def observe(world, i: int) -> list[float]:
    """The N_INPUTS inputs for car i, each scaled to roughly -1..1.

    Signs follow the sim's convention: positive = to the right.  Closing
    speeds are positive when the gap is shrinking.
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
    straight = STRAIGHT_SCAN
    step = max(1, int(2.0 / ds))
    for k in range(0, int(STRAIGHT_SCAN / ds), step):
        if abs(curv[(idx + k) % n]) > STRAIGHT_CURVATURE:
            straight = k * ds
            break
    obs.append(hw / 6.0)
    obs.append(straight / STRAIGHT_SCAN)
    obs.append(car.damage)
    obs.append(car.draft)

    giving = 0.0
    ahead: list[tuple] = []
    behind = None
    left = right = None
    if not world.ghost and len(world.cars) > 1:
        length = track.length
        half = length / 2.0
        for j, other in enumerate(world.cars):
            if j == i or other.retired:
                continue
            if other.draft_source == i and other.draft > giving:
                giving = other.draft
            gap = (other.s - car.s + half) % length - half      # + = other is ahead
            side = other.lateral - car.lateral
            if 0.0 < gap < AHEAD_RANGE:
                ahead.append((gap, side, car.speed - other.speed))
            elif -BEHIND_RANGE < gap <= 0.0 and (behind is None or -gap < behind[0]):
                behind = (-gap, side, other.speed - car.speed)
            if abs(gap) < SIDE_RANGE and abs(side) < SIDE_WIDTH:
                near = 1.0 - abs(side) / SIDE_WIDTH
                if side < 0.0 and (left is None or near > left[0]):
                    left = (near, gap / SIDE_RANGE)
                elif side >= 0.0 and (right is None or near > right[0]):
                    right = (near, gap / SIDE_RANGE)
    obs.append(giving)
    ahead.sort()
    for k in range(2):
        if k < len(ahead):
            gap, side, closing = ahead[k]
            obs += [gap / AHEAD_RANGE, side / 5.0, closing / 15.0]
        else:
            obs += [1.0, 0.0, 0.0]
    if behind:
        obs += [behind[0] / BEHIND_RANGE, behind[1] / 5.0, behind[2] / 15.0]
    else:
        obs += [1.0, 0.0, 0.0]
    obs += list(left) if left else [0.0, 0.0]
    obs += list(right) if right else [0.0, 0.0]

    # ---- input version 2 ----
    for d in FAR_AHEAD:
        obs.append(curv[(idx + int(d / ds)) % n] * 8.0)
    # Room between the car's side and the barrier, on each side.
    limit = track._lim[idx] - car.params.radius
    obs.append(min(2.0, (limit + car.lateral) / 6.0))
    obs.append(min(2.0, (limit - car.lateral) / 6.0))
    # Race place (0 = leading, 1 = last) and how much of the race is left.
    place = 0.0
    if not world.ghost and len(world.cars) > 1:
        mine = world.race_progress(car)
        rivals = [o for j, o in enumerate(world.cars) if j != i and not o.retired]
        if rivals:
            place = sum(1 for o in rivals if world.race_progress(o) > mine) / len(rivals)
    obs.append(place)
    if world.laps < 1000:
        done = world.race_progress(car) / (world.laps * track.length)
        obs.append(min(1.0, max(0.0, 1.0 - done)))
    elif getattr(world, "end_tick", None):
        obs.append(max(0.0, 1.0 - world.tick / world.end_tick))
    else:
        obs.append(1.0)
    return obs


# ---------------------------------------------------------------- network

def input_version(arch: dict) -> int:
    return int(arch.get("inputs", 1))     # brains from before versioning are version 1


def layer_sizes(arch: dict) -> list[int]:
    m = int(arch.get("memory", 0))
    n_in = len(INPUT_VERSIONS[input_version(arch)])
    return [n_in + m] + [int(h) for h in arch["hidden"]] + [N_CONTROLS + m]


def upgrade(weights: np.ndarray, arch: dict) -> tuple[np.ndarray, dict]:
    """Rewire brain(s) made for an older input version to the current one.

    New inputs get zero-strength connections, so the brain drives exactly as
    before; training can then make use of them.  `weights` may be one brain
    or a stack of them.  Returns (weights, current arch)."""
    if input_version(arch) == INPUT_VERSION:
        return weights, arch
    new_arch = dict(arch, inputs=INPUT_VERSION)
    weights = np.asarray(weights, dtype=np.float64)
    old_names = INPUT_VERSIONS[input_version(arch)]
    m = int(arch.get("memory", 0))
    old_layers = unpack(weights, arch)
    lead = weights.shape[:-1]
    out = np.zeros(lead + (n_weights(new_arch),))
    new_layers = unpack(out, new_arch)
    (w_old, b_old), (w_new, b_new) = old_layers[0], new_layers[0]
    position = {name: k for k, name in enumerate(INPUT_NAMES)}
    for k, name in enumerate(old_names):
        w_new[..., position[name]] = w_old[..., k]
    if m:
        w_new[..., N_INPUTS:] = w_old[..., len(old_names):]
    b_new[...] = b_old
    for (wo, bo), (wn, bn) in zip(old_layers[1:], new_layers[1:]):
        wn[...] = wo
        bn[...] = bo
    return out, new_arch


def n_weights(arch: dict) -> int:
    sizes = layer_sizes(arch)
    return sum(o * i + o for i, o in zip(sizes[:-1], sizes[1:]))


def describe(arch: dict) -> str:
    hidden = " x ".join(str(h) for h in arch["hidden"])
    mem = f", memory {arch['memory']}" if arch.get("memory") else ""
    return f"{hidden} hidden{mem} ({n_weights(arch)} weights)"


def unpack(weights: np.ndarray, arch: dict) -> list[tuple]:
    """Flat weight vectors (..., n) -> [(W (..., out, in), b (..., out)), ...]."""
    sizes = layer_sizes(arch)
    lead = weights.shape[:-1]
    layers, k = [], 0
    for i, o in zip(sizes[:-1], sizes[1:]):
        w = weights[..., k:k + o * i].reshape(lead + (o, i))
        k += o * i
        b = weights[..., k:k + o]
        k += o
        layers.append((w, b))
    return layers


def random_weights(rng: np.random.Generator, count: int, arch: dict) -> np.ndarray:
    """Random drivers, scaled so every layer starts in tanh's useful range,
    with a bias toward pressing the throttle so generation 1 moves."""
    sizes = layer_sizes(arch)
    parts = []
    for i, o in zip(sizes[:-1], sizes[1:]):
        parts.append(rng.normal(0.0, 2.0 / math.sqrt(i), (count, o * i)))
        parts.append(rng.normal(0.0, 0.2, (count, o)))
    weights = np.concatenate(parts, axis=1)
    weights[:, n_weights(arch) - (sizes[-1] - 1)] += 0.8   # throttle output bias
    return weights


class Population:
    """Many different networks run at once: one row of weights per driver.
    Keeps each driver's memory between decisions."""

    def __init__(self, weights: np.ndarray, arch: dict):
        weights, arch = upgrade(np.asarray(weights, dtype=np.float64), arch)
        self.arch = arch
        self.memory_size = int(arch.get("memory", 0))
        self.layers = unpack(weights, arch)
        self.memory = np.zeros((len(weights), self.memory_size))

    def act(self, obs: np.ndarray) -> np.ndarray:
        """obs (P, N_INPUTS) -> (P, 2) controls in -1..1."""
        x = np.concatenate([obs, self.memory], axis=1) if self.memory_size else obs
        for w, b in self.layers:
            x = np.tanh(np.einsum("poi,pi->po", w, x) + b)
        if self.memory_size:
            self.memory = x[:, N_CONTROLS:]
        return x[:, :N_CONTROLS]


class Brain:
    """One network applied to a batch of cars (e.g. the same rival in many
    simultaneous test races).  Each car keeps its own memory."""

    def __init__(self, weights: np.ndarray, arch: dict, batch: int = 1):
        weights, arch = upgrade(np.asarray(weights, dtype=np.float64), arch)
        self.arch = arch
        self.memory_size = int(arch.get("memory", 0))
        self.layers = unpack(weights, arch)
        self.memory = np.zeros((batch, self.memory_size))

    def act(self, obs: np.ndarray) -> np.ndarray:
        x = np.concatenate([obs, self.memory], axis=1) if self.memory_size else obs
        for w, b in self.layers:
            x = np.tanh(x @ w.T + b)
        if self.memory_size:
            self.memory = x[:, N_CONTROLS:]
        return x[:, :N_CONTROLS]


def to_controls(steer: float, pedal: float) -> Controls:
    if pedal >= 0.0:
        return Controls(steer, pedal, 0.0)
    return Controls(steer, 0.0, -pedal)


class NeuralDriver(Driver):
    """A trained network driving one car through the normal Driver interface."""

    def __init__(self, weights: np.ndarray, arch: dict, label: str = "Evolved"):
        self.weights, self.arch = upgrade(np.asarray(weights, dtype=np.float64), arch)
        self.label = label
        self.reset(None, 0)

    def reset(self, world, car_index: int) -> None:
        self.brain = Brain(self.weights, self.arch)
        self.held = Controls()

    def act(self, world, car_index: int) -> Controls:
        if world.tick % DECISION_TICKS == 0:
            out = self.brain.act(np.array([observe(world, car_index)]))[0]
            self.held = to_controls(float(out[0]), float(out[1]))
        return self.held
