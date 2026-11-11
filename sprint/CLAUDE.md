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
python train.py [--run NAME] [--generations N] [--hidden 24 16] [--memory 4] [--races 2]
                [--no-race-bonuses] [--racing-from GEN] [--population N] [--workers N]
python render_frames.py --out DIR [--track T]     # PNG of every screen, no window
python -m pytest
```

Stack: Python 3.13, pygame-ce 2.5.8, NumPy 2.5.3, pytest 9.2.0. Target OS for
the user is Windows; nothing here is platform specific. No ML packages are
installed and none may be added in Stage 1.

## Status

Done: the Stage 1 game (two tracks, four cars, menus, HUD, sound, gamepads,
replays); damage and drafting; Stage 2 AI by **neuroevolution** (the user
chose real generations over PPO); AI Lab screen with live charts, ghost-pack
view of any generation, champion races. 101 tests.

The user has driven the game on Windows and is happy with the car feel.
Damage, drafting, the AI Lab and training have NOT been tried by the user yet.
PPO is deliberately kept for later as a rival method (see the end).

Reference numbers: scripted flying lap Speedway 13.98 s, Technical 22.20 s.
A 110-generation trial (population 80, seed 0) reached champion solo laps of
about 12.8 s and 22.1 s; in the exam race against three scripted cars it won
on Speedway with 2 collisions, but on Technical still had about 11 collisions
and often failed to finish. Solo generations took about 2 s, race generations
about 8 s, on 4 cores.

Verify changes the way the rest was verified: pytest, `headless.py` on both
tracks, a short `train.py` run, and `render_frames.py` then look at the PNGs.

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

## Damage and drafting (in `sim/`)

`car.damage` 0..1: added in `World` on wall and car impacts above
`DAMAGE_MIN_IMPACT`, permanent until `World.reset`, part of `state()`. It
scales top speed and acceleration in `Car.step` and nothing else.
`car.draft` 0..1 and `car.draft_source` are recomputed at the start of every
tick by `World._update_draft` (a wedge behind any fast car) and also scale top
speed and acceleration. `World(ghost=True)` turns off car-to-car collisions
and drafting; `car.retired = True` stops a car being simulated. Both exist for
AI training. The renderer draws smoke, tow streaks and the HUD damage bar.

## AI drivers (`ai/`)

`ai/` imports `sim/` and NumPy only; `game/` imports `ai/`. Method:
neuroevolution in two phases (the user chose generations over PPO, and asked
for "learn to drive first, then learn to race").

- `brain.py`: `observe(world, i)` gives 28 inputs (`INPUT_NAMES`): speeds,
  offset, heading error, six curvatures ahead, half-width, straight length
  ahead, damage, tow received, tow given, two cars ahead / one behind (gap,
  side, closing speed), nearest car alongside left / right. Network shape is
  a per-run `arch` dict `{"hidden": [24, 16], "memory": 4}`; memory = extra
  outputs fed back as inputs at the next decision (recurrence, no gradients
  needed). `Population` (different weights per row), `Brain` (one network,
  batch of cars), `NeuralDriver` (the `Driver`; decides every
  `DECISION_TICKS` = 4 ticks, as in training; memory reset in `reset`).
- `evolve.py`:
  - Phase 1 (`mode: "solo"`): `PackRun`/`test_solo`, whole population as
    ghosts; ends when the champion's exam shows >= 1.9 laps of every track
    with <= 5% damage (`config.phase2_start` is then written).
  - Phase 2 (`mode: "race"`): `make_scenarios` gives `races_per_track` races
    per track per generation, the same for every driver, grid slots covering
    0..3; rivals scripted for `SCRIPTED_ONLY_GENS`, then a mix of scripted,
    recent champions and a hall of fame (`RIVAL_MIX`). `test_race` runs one
    real race per driver, all worlds stepped together, rivals batched.
    `RaceStats` counts collisions caused (I hit the car ahead) vs suffered,
    walls, overtakes, times passed, draft time, final place. `race_score`:
    `RACE_WEIGHTS` (saved per run): place points + 0.5 laps - 2.0 damage
    - 0.25 caused - 0.03 walls, plus
    optional bonuses (overtakes, being passed, draft) scaled by `bonus`,
    which fades to 0 over `BONUS_FADE` generations. Fitness = 0.2 solo +
    0.8 race mean.
  - `exam`: identical report card every generation (solo time trial; 3-lap
    race from the back vs three scripted cars) so the Lab charts are
    comparable across both phases.
  - `train`: runs in `training/<run>/` (git-ignored): `config.json` (format
    2, arch, settings, `phase2_start`), `history.json` (rewritten atomically;
    entries carry `exam`, and in phase 2 `training` averages and the
    `scenarios` raced, rivals as "scripted" or a generation number),
    `gen_NNNN.npz` (whole population, best first, float32). Seeded and
    resumable across the phase change (tested). Older-format runs are renamed
    `<run>-v1`, never deleted, and are ignored by `list_runs`.
- `roster.py`: `champion(run, gen, label, rank)` builds a `NeuralDriver` for
  any ranked driver of a generation; `register_champions` puts them in the
  registry as `evo:<run>:<gen>`.
- `game/screens.py` `LabScreen` (4 charts, generation picker, ghost pack,
  top-4 reverse-grid race, the champion's test races, champions race, you v
  champions) and `PackScreen`.

Results of the trial run are in Status above. Known weaknesses / next ideas:
1. Racing-school scores are noisy with 4 races per driver; `--races 3` or a
   bigger population trade time for steadier progress.
2. No ray-cast inputs (`Track.raycasts` exists).
3. Training is started from a terminal, not from the game menu.
4. One network drives both tracks; not tried on unseen tracks.

## Still to do: PPO as a rival method

The user wants PPO later, to race against the evolved drivers.

1. `ai/env.py`: a Gymnasium `Env` around `World`, reusing `brain.observe`
   for observations and the same two-value action. Reward = progress along
   `s` per decision, minus damage taken. Keep it pygame-free.
2. Train with Stable-Baselines3 PPO (needs `gymnasium`, `stable-baselines3`
   and PyTorch installed; none are installed now). Save checkpoints.
3. A `PolicyDriver(Driver)` that loads a checkpoint, registered like
   `roster.register_champions` does, so "Evolved v PPO" is just a race setup.
4. `exam` already gives a method-independent report card; reuse it so PPO
   checkpoints appear on the same AI Lab charts.
