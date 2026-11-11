# AI Sprint Racing: notes for whoever picks this up

Top-down arcade racer. Stage 1 (this code) is the human-playable game.
Stage 2 adds AI drivers (rule-based, then PPO). The architecture rules below
exist so Stage 2 is easy; do not break them.

Work from this `sprint/` directory. The repo root also holds an unrelated
poker project (`holdem/`, `web/`, root `tests/`); leave it alone.

## Commands

```
python -m game [--track T] [--no-sound] [--fullscreen]
python headless.py [--track T] [--cars N] [--laps N] [--record F] [--replay F] [--bench STEPS]
python render_frames.py --out DIR [--track T]     # PNG of every screen, no window
python -m pytest
```

Stack: Python 3.13, pygame-ce 2.5.8, NumPy 2.5.3, pytest 9.2.0. Target OS for
the user is Windows; nothing here is platform specific. No ML packages are
installed and none may be added in Stage 1.

## Status

Stage 1 is complete: Speedway and Technical tracks, four cars, scripted
driver, race management, menus, HUD, pause, results, sound, gamepads, replays,
77 tests. The driving feel has NOT yet been judged by a human; expect tuning
requests against `sim/tuning.py`. Never run on real Windows, real audio or a
real gamepad (developed headless with SDL dummy drivers).

Reference numbers (scripted driver, 3 laps, flying lap): Speedway 13.98 s,
Technical 22.20 s. If physics tuning changes these move; the tests accept
11-19 s and 19-31 s.

Verify changes the way Stage 1 was verified: pytest, `headless.py` on both
tracks, and `render_frames.py` then look at the PNGs.

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
   "scripted" is registered by importing `sim.scripted`;
   `game.input.register_human_drivers()` adds "human1".."human4" (one per
   keyboard binding set) and "pad1".. (one per connected gamepad). The setup
   menu lists `driver_types()` plus "None", so a driver registered in Stage 2
   shows up in the menu with no UI work.
6. `Race` logs the Controls applied on every racing tick; `sim/replay.py`
   saves them (gzipped JSON) with seed, track, slots and laps, and
   `Recording.make_race()` plays them back through `ReplayDriver`s. The stored
   final `state_hash` proves playback is identical. Recordings carry
   fingerprints of the physics tuning and the track file and report a mismatch.

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

## Race and game flow

`sim/race.py` `Race(track, [(slot, driver_key_or_Driver), ...], laps, seed)`:
phases `countdown` (3 s, world does not step, so lap 1 is timed from green),
`racing`, `finished`. `race.step()` advances one tick in any phase and returns
World events plus `("count", n)`, `("go",)`, `("race_over",)`. Finished cars
are braked by the Race, not their driver. After the first finisher the rest
get `FINISH_GRACE` seconds, then are classified by distance. `race.run()` is
the headless loop; `race.results()` gives the classification.

`game/app.py` `App` owns the window, audio, a cache of track paintings and the
current screen. `game/screens.py`: `MainMenu`, `SetupScreen` (edits
`app.setup`), `ControlsScreen`, `ReplayScreen`, `RaceScreen` (accumulator loop,
pause and results overlays, replay mode). `game/audio.py` `Audio` degrades to
no-ops if the mixer cannot open. Slot index fixes colour, grid place, HUD panel
and parameter set.

## Stage 2 plan

1. `sim/env.py`: a Gymnasium `Env` wrapping `World` (or `Race` without the
   countdown) for one learning car, other slots filled from the registry.
   Observation from the track queries above: speed, forward / lateral
   velocity, lateral offset / half width, heading error, curvature at several
   distances ahead, ray distances, maybe nearest-car relative position.
   Action = the three Controls values. Reward = progress along `s` per tick
   (`World.race_progress`), penalties for grass and wall events. Seed via
   `World.reset(seed)`. Keep it pygame-free so training runs headless.
2. Better rule-based driver: fill `racing_line_offsets` in the track files
   (or compute a minimum-curvature line) and reuse `ScriptedDriver`, which
   already follows `track.racing_line_point`. It has no overtaking logic:
   scripted cars queue behind each other and bump.
3. PPO with Stable-Baselines3; save checkpoints during training.
4. A `PolicyDriver(Driver)` that loads a checkpoint; register one registry
   entry per saved model so the existing setup menu can put any saved driver
   in any slot. A "watch training progress" mode can race successive
   checkpoints against each other using the same `RaceScreen`.
5. Speed: one car steps at about 90k ticks/s, four at about 25k (pure
   Python, scripted drivers included). `Track.raycasts` is vectorised NumPy
   over all boundary segments (about 2,000 to 4,000); if it dominates the env
   step, restrict it to segments near the car's index, and consider acting
   every 4 to 6 ticks (20 to 30 Hz decisions) rather than every tick.
6. Human-vs-learned replays work already, since a replay only stores controls.
