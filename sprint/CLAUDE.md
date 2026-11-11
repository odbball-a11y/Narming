# AI Sprint Racing: notes for whoever picks this up

Top-down arcade racer. Stage 1 (this code) is the human-playable game.
Stage 2 adds AI drivers (rule-based, then PPO). The architecture rules below
exist so Stage 2 is easy; do not break them.

Work from this `sprint/` directory. The repo root also holds an unrelated
poker project (`holdem/`, `web/`, root `tests/`); leave it alone.

## Commands

```
python -m game [--driver human|scripted] [--track speedway]
python headless.py [--track T] [--cars N] [--laps N] [--bench STEPS]
python render_frames.py --out DIR --seconds 0 5 10 [--debug]   # PNGs, no window
python -m pytest
```

Stack: Python 3.13, pygame-ce 2.5.8, NumPy 2.5.3, pytest 9.2.0. Target OS for
the user is Windows; nothing here is platform specific. No ML packages are
installed and none may be added in Stage 1.

## Status

Milestone 1 (done): one car, Speedway, keyboard, physics, camera, headless
runner, tests. Waiting for the user's feedback on driving feel.

Milestone 2 (to do, in order): Technical track (`tracks/technical.json`:
hairpin, chicane, narrow section, ~25 s lap); scripted driver verified on
both; four-car races; `sim/race.py` race management (countdown, finish,
results); menus (track, per-slot driver via the registry, key bindings shown),
HUD position display, pause, results screen; synthesised sound that survives
a missing audio device; replay recording and exact playback of per-tick
controls; gamepad if cheap; full test pass.

## Architecture rules

1. `sim/` never imports pygame, `game`, `time` or `datetime`
   (`tests/test_architecture.py`). `game/` imports `sim/`, never the reverse.
2. Every car is driven through `sim.driver.Driver.act(world, car_index) ->
   Controls(steering -1..1, throttle 0..1, brake 0..1)`, once per tick. Physics
   does not know the source. Human smoothing lives in `game/input.py`.
3. Fixed 120 Hz step (`tuning.DT`). No wall clock and no unseeded randomness
   in `sim/`; `World.rng` is a seeded `random.Random` for anything that needs
   it. Same seed + same controls => identical `World.state_hash()`.
   The renderer blends `car.prev_*` to `car.*` with the loop's alpha.
4. The sim runs with no window (`headless.py`).
5. `register_driver(key, label, factory)` / `create_driver(key, slot)` /
   `driver_types()` is the registry; `factory(slot=int)` returns a Driver.
   "scripted" is registered by importing `sim.scripted`, "human" by importing
   `game.input`.
6. Replays (milestone 2) are the seed, track, slots and the per-tick Controls.
   They are only valid for the tuning values they were recorded with.

All tunable numbers live in `sim/tuning.py`, including input smoothing and
scripted-driver values. Read values as `tuning.NAME` at use time (not
`from tuning import NAME`) so F5 hot reload works; `World.reset()` re-reads
car parameters.

## Conventions

- World is 160 x 90 units, x right, **y down**. The top 11 units are the HUD
  strip; tracks must keep their barriers inside x 1..159, y 12..89.
- Heading = atan2(dy, dx). Positive steering, positive curvature, positive
  lateral offset and positive heading error all mean **right** of the
  direction of travel.
- A car is a circle (`params.radius`) for all collisions.
- Time is `world.tick * DT`. Lap times use the sub-tick crossing fraction.

## Track (`sim/track.py`)

JSON: `points` = closed list of `[x, y, width]` in driving order, first point
is the start line; `verge`, `checkpoints`, `laps`, optional
`racing_line_offsets` (lateral offset per control point; null = centreline).
Closed Catmull-Rom, resampled to uniform spacing `ds` (about 0.5), so index
and distance convert by multiplication.

Derived: `center, tangent, normal, heading, curvature, half_width, limit`
(barrier distance), `left/right_edge`, `left/right_wall`, `racing_line`,
`checkpoints` (gate 0 = start line), `grid`.

Queries (the Stage 2 observation building blocks, already used by the
scripted driver): `nearest_index(x, y, hint)`, `frenet(x, y, idx) -> (s,
lateral)`, `locate`, `heading_error(heading, s)`, `curvature_at(s)`,
`curvature_ahead(s, d)`, `racing_line_point(s)`, `half_width_at(s)`,
`raycasts(x, y, angles, max_dist, boundary="barrier"|"tarmac")`.
Each car caches `idx, s, lateral, surface`, updated every tick.

Surface and barrier are decided by lateral offset from the car's tracked
centreline index: within `half_width` = tarmac, up to `limit` = grass, beyond
= barrier. This needs corner radius > `limit` and separate road sections not
to share a verge; `Track.report()` and `tests/test_track.py` check both for
every track file.

## Physics (`sim/car.py`, `sim/world.py`)

Velocity is separate from heading. Per tick: steering sets a yaw rate that
falls with speed; velocity is split into forward and lateral parts in the car
frame; engine, brake, rolling friction and drag act on the forward part; grip
removes lateral speed at a limited rate (`grip`, scaled by surface, throttle
and brake). Turning faster than grip can follow leaves lateral speed = a
slide. Brake reverses when nearly stopped with no throttle.

`World.step(controls)` returns events: `("wall", i, impact)`, `("car", a, b,
impact)`, `("lap", i, time)`, `("finish", i, time)`.

Laps: gates must be crossed forwards, in order. The first crossing of gate 0
starts lap 1 (timed from tick 0); later crossings of gate 0 complete laps.

## Stage 2 plan

1. `sim/env.py`: a Gymnasium `Env` wrapping `World` for one learning car
   (other slots filled from the registry). Observation from the track queries
   above: speed, forward/lateral velocity, lateral offset / half width,
   heading error, curvature at several distances ahead, ray distances, maybe
   nearest-car relative position. Action = the three Controls values.
   Reward = progress along `s` per tick, penalties for grass and wall events.
   Seed via `World.reset(seed)`.
2. Better rule-based driver: fill `racing_line_offsets` (or compute a
   minimum-curvature line) and reuse `ScriptedDriver`.
3. PPO with Stable-Baselines3; save checkpoints during training.
4. A `PolicyDriver(Driver)` that loads a checkpoint and is registered per
   saved model, so the existing menu can put any saved driver in any slot;
   a "watch training progress" mode that races checkpoints against each other.
5. Speed: one car steps at ~90k ticks/s, four at ~27k (pure Python). The ray
   cast is vectorised NumPy over all boundary segments; if it dominates the
   env step, restrict it to segments near the car's index.
