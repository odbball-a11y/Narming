# AI Sprint Racing: notes for whoever picks this up

Top-down arcade racer. Stage 1 (this code) is the human-playable game.
Stage 2 adds AI drivers (rule-based, then PPO). The architecture rules below
exist so Stage 2 is easy; do not break them.

Work from this `sprint/` directory. The repo root also holds an unrelated
poker project (`holdem/`, `web/`, root `tests/`); leave it alone.

## Commands

```
python -m game [--track T] [--no-sound] [--fullscreen] [--workshop]
python -m ai.stable train stable/<id> [--workers N]   # what the game runs in the background
python headless.py [--track T] [--cars N] [--laps N] [--record F] [--replay F] [--bench STEPS]
python train.py [--run NAME] [--generations N] [--hidden 24 16] [--memory 4] [--races 2]
                [--no-race-bonuses] [--race-laps L] [--racing-from GEN] [--population N] [--workers N]
python train.py --run dave --from speedway --style aggressive --name "Dangerous Dave"   # training camp
python compare.py RUN[:GEN] RUN[:GEN] ... [--track T] [--races N] [--laps N]
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

Training trials so far (population 80, 24x16 + memory 4, 4 cores):
1. Racing school scored with damage 0.8, caused 0.08, ~1.5-lap races: the
   champion learned to win training races by barging (place 2.8 -> 1.6,
   damage and caused collisions flat or rising). -> heavier weights.
2. Damage 2.0, caused 0.25, ~2-lap races: against scripted rivals only it
   hung back (last, no damage, no passes); racing in traffic and with damage
   it hit barriers repeatedly, because driving school only ever started
   from box 1 with a perfect car. -> `solo_setup` rotation.
3. Same plus rotation: driving school rode the barriers on Technical (50%
   damage solo) because its damage weight was 0.25. -> `SOLO_DAMAGE_WEIGHT`.
4. Run "long3" (`--race-laps 3`), everything above: driving school produced
   clean fast drivers by gen 98 (12.3 s Speedway, 0 damage). In 52 racing
   generations the champion's training races improved (place 3.25 -> 2.3,
   damage 0.15-0.25, ~0.75 passes per race), but in the exam (start last,
   three scripted cars, 3 laps) it still always finished 4th, with 4-7
   barrier hits, despite being ~1.7 s/lap faster alone. Drafting is almost
   unused (1-2% of race time). Racing generations take ~25 s.
   Open problem: it has not learned to pass cleanly. Next ideas, best
   first: overtaking drills (short races starting just behind one or two
   slower cars on a straight, scored on passing cleanly); many more racing
   generations; more races per driver or a bigger population; PPO for
   the racing phase.

After trial 4 the user asked for: Speedway-only training first
(`--tracks speedway --races 4`), single-file rolling starts always
(`World(rolling=True)`: training, exam, Lab races; default in race setup), a
stronger, longer tow (`DRAFT_*` in tuning), and, later, more than four cars.
AI drivers now never practise standing starts. The user then asked that
every finishing place matter: place points went from 1/0.6/0.3/0 to 3/2/1/0.

5. Run "speedway" (`--tracks speedway --races 4 --race-laps 3`) with all of
   the above: the first trial that learned to race. Racing school began at
   gen 18. Exam (start last v three scripted, 3 laps), 10-generation
   averages: place 4.0 -> 1.6-2.0, passes 0 -> ~3, time in draft 5% ->
   20-40%, caused collisions peaked ~6 around gen 70 then fell to ~2, damage
   31% -> 12%, solo lap 16.3 -> 12.8 s. Single exam races still swing
   (a win one generation, last the next). ~20 s per racing generation.
   Not yet tried: Technical with these settings, more than four cars.

Next direction (agreed with the user): an AI-only racing stable in the spirit
of Derby Owners Club. Two founders trained from the "speedway" run:
"Dangerous Dave" (`--style aggressive`) and "Careful Keith" (`--style
cautious`); every later racer is to descend from these two by breeding.
Planned: temperament as an inherited 0..1 gene (child = parents' mean plus
noise) that sets where the foal's camp scoring sits between cautious and
aggressive; foal brain = mix of the parents' (they share an ancestor, so
crossover is viable) followed by a short, gentle camp; wet/dry specialists
(camp conditions); per-racer car traits on a fixed budget (handling, top
speed, acceleration, weight); championship over several tracks with random
weather; names, career stats, family trees, retirement.

Founder camps, 40 generations each from "speedway" gen 120 (~55 s/gen with
two camps sharing 4 cores). In their own camps the personalities were
distinct (gens 31-40: Dave damage 9%, caused 1.6, 1.4 passes; Keith damage
2%, caused 0.2, 0.7 passes). Head to head (`compare.py dave keith speedway`,
16 races, the parent champion included by accident): Dave 8 wins, avg place
1.75, caused 0.75, damage 24%, draft 8%; Keith 0 wins, place 3.0, caused 2.0,
damage 27%, draft 31%; parent 8 wins, caused 2.75, damage 14%. Keith only
trained against scripted cars and his own cautious champions, so against
aggressive cars he tails closely and runs into them when they cut in and
brake (rear contact counts as caused). Proposed next: camps whose rival pool
includes the other personalities' champions.

## The stable (built: steps 1-4 of 5)

Agreed design, from the user: an AI-only racing stable in the spirit of Derby
Owners Club. The player creates named racers (name, aggression and caution
sliders, training partners, generations), trains them in the game, upskills
them, races them against shipped **house rivals** (race-only, never training
partners), and later breeds them. Dangerous Dave and Careful Keith are the
user's own creations and the first house rivals; the user will make stronger
ones in the workshop.

- `ai/stable.py`: `house/graduate.npz/.json` (shipped start population:
  "speedway" run gen 120, all 80 drivers, plus arch, track, race length and
  races per generation), `house/rivals/<id>.npz/.json` (champion + card).
  Racer folders `stable/<id>/` or `workshop/<id>/` (git-ignored) hold
  `racer.json` (name, created, aggression, caution, parents, versions,
  career) and one `evolve` run per version (`v1/`, `v2/`...). v1 breeds on
  from the graduate, each upskill from the previous version's last
  generation. `sliders_to_weights(a, c)` interpolates the race scoring from
  balanced towards `STYLES["aggressive"]` (a=1) and `STYLES["cautious"]`
  (c=1). `partner_options` = scripted, "self" (the run's own recent
  champions, via `make_scenarios`), other trained racers in the same root,
  and in the workshop the house rivals; partners are stored as
  `{"kind": "file", "file": <gen npz>}` and resolved to `p:<i>` rivals.
  `record_result` updates careers; `publish` writes a house rival;
  `register` adds `house:` and `racer:` keys to the driver registry.
- `evolve.train` gained `root`, `start_file`, `race_weights`,
  `race_seconds` and `partners`; paths are stored relative to the project.
- `game/stable_screens.py`: `StableScreen`, `CreateScreen` (text entry via
  TEXTINPUT), `RacerScreen` (card, charts over all versions, race the house
  rivals, upskill, stop/resume training, publish in the workshop).
  `App.start_training` runs `python -m ai.stable train` as a subprocess
  (3 workers at most; log in the racer folder), `stop_training` terminates
  it (also on quit; training resumes later), `record_race` adds finished
  races to careers (not replays).

- Breeding (`ai/stable.py`): `mate(root, sire, dam, name, criterion)`
  registers the foal (temperament = parents' mean + N(0, 0.08), seed from
  the names, `racer["breeding"]`); `breed(foal_dir)` (run as `python -m
  ai.stable breed`, `App.start_breeding`) makes `LITTER` foals with
  `crossover` (each neuron's incoming weights and bias, in every layer,
  copied from one parent, then small mutations), round 1 scores all with
  `score_population` (balanced weights, solo + one race from last v three
  scripted) and keeps `SHORTLIST`, round 2 runs a `CAMP_GENERATIONS` x
  `CAMP_POPULATION` camp for each with the foal's own weights, picks by
  "fastest" (best solo lap) or "learner" (first generation whose solo lap
  beats the parents' average), moves the winner's camp to `v1/`, and saves
  `racer["certificate"]` (sire, dam, grandparents, candidates, winner,
  temperament, `expectations()`). Progress in `breeding.json`;
  `is_breeding` until the certificate exists. Full size takes ~47 s on 4
  cores. Screens: `BreedScreen`, `CertificateScreen`.

- Careers (`ai/stable.py`, not in the workshop: `careers_enabled`):
  `racer["status"]` racing -> stud -> dead. `record_result` ticks the
  stable clock (`stable/stable.json` races) and retires at `CAREER_RACES`
  (20); `retire` also works early. `can_race`/`can_train` need "racing",
  `can_breed` needs "stud"; `mate` counts `breedings` on both parents;
  `check_deaths` kills studs at `STUD_BREEDINGS` (5) or after
  `STUD_LIFETIME` (40) stable races at stud. `list_racers` hides the dead
  (`include_dead=True` for partners: legends still spar); `hall_of_fame`,
  `offspring`. News (retirements, deaths) returns from `record_result` and
  shows on the results screen. `HallScreen`; card has RETIRE TO STUD.

Tracks for the championship (user asked for 5 in the existing style; chose
"flowing esses" and "mixed grand prix", varied overtaking, spread lap
lengths, descriptive names): `tracks/esses.json` (376 long, scripted 17.4 s,
width 10.5-11, four r=14 sweeps) and `tracks/grandprix.json` (504 long,
scripted 24.0 s, width 9-9.5, three r=9 hairpins around two infield loops,
chicane, kink). Both were generated from line-and-arc paths (a small turtle
script, not kept in the repo; dense points every ~6.5 units, tighter on
small arcs, give clean splines). The fifth, chosen by the user, is
`tracks/oval.json` (drafting oval: 314 long, width 13, r=27 turns, scripted
11.5 s, 5 laps by default). All five exist now. No AI has been trained on the new tracks: the graduate and all
stable racers only know Speedway.

- Car traits (`sim/cartraits.py`, numbers in `tuning`: `TRAIT_BUDGET` 12,
  `TRAIT_STEP` 0.04, `LIGHT_MASS`/`HEAVY_MASS`, `WEIGHT_PERFORMANCE`):
  `{"top_speed", "accel", "handling", "braking": 1-5, "weight":
  light|medium|heavy}`; `params_for(traits)` -> `CarParams` (the default car
  is exactly today's car; `CarParams.traits` holds the normalised values the
  driver sees). `World(params=[...])` gives cars their own params; `Race`
  takes them from `driver.car_params`. Drivers see them as input version 3
  (5 inputs). Training: `config["car"]` = traits (a racer's own), None
  (standard) or "random" (`car_for`: a new random car each generation, for
  a graduate that can drive anything; `train.py --car random`); scenarios
  carry `car` and `rival_cars`. Stable: `racer["traits"]` (create validates
  the budget; upskill cannot change it), `cartraits.inherit` per trait from
  either parent + occasional +-1 star, rebalanced; `traits_from` on the
  certificate; heavy cars drawn 12% bigger, light 10% smaller. The user
  chose: all five traits, strict budget (no bonus stars), visible size, and
  no weather for now.

Five-track graduate (done): run "graduate5" (`train.py --run graduate5
--from speedway:120 --driving-school --tracks oval speedway esses technical
grandprix --races 1 --race-laps 3 --car random --generations 300`, ~5 s per
driving gen, ~40 s per racing gen, about 3.5 h on 4 cores). Driving school
ended at gen 57. Exam (from last v three scripted, avg of 5 tracks) place
3.1 -> 2.3, damage 36% -> 18%; per track over the last 30 gens: Oval 1.6,
Speedway 2.0, Esses 1.7, Technical 3.0 (38% damage), Grand Prix 3.2 (finished
only half, 35% damage, ~5 barrier hits). Head to head v the old Speedway
graduate + 2 scripted, 8 races each: wins Oval 6-2, Speedway 2-6, Esses 8-0,
Technical 6-0, Grand Prix 4-0 (scripted 4). Gen 300's population is now
`house/graduate.npz` (tracks: all five, races_per_track 1, 3-lap races).
Grand Prix is the weak track; more training there would help.

Stable racers now train on `graduate()["tracks"]` (all five); breeding trials
and camps use all five and judge on `pace` (mean of best solo lap / scripted
lap, `SCRIPTED_LAPS`; `pace_text`), `exam_average` for race numbers;
certificates have `target_pace` and candidate `pace` (older ones `best_lap`).
The card picks the race track (Left/Right on RACE). Dangerous Dave and
Careful Keith were trained on Speedway only and are weak elsewhere.

Still to build: (5) championship across tracks, 6-8 cars.

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

- `brain.py`: `observe(world, i)` gives 39 inputs (`INPUT_NAMES`): speeds,
  offset, heading error, six curvatures ahead, half-width, straight length
  ahead, damage, tow received, tow given, two cars ahead / one behind (gap,
  side, closing speed), nearest car alongside left / right; then (input
  version 2) curvature 80 and 120 ahead, room to the barrier left and
  right, race place (0 leading .. 1 last) and race left (by laps, or by
  `World.end_tick` in timed training races). Inputs are versioned
  (`INPUT_VERSIONS`, `arch["inputs"]`; missing = 1). New inputs are only
  appended; `upgrade(weights, arch)` rewires an older brain with
  zero-strength connections so it drives identically (tested), and
  `Population`/`Brain`/`NeuralDriver` upgrade automatically.
  `ai/migrate.py` `ensure()` upgrades saved files once (house graduate and
  rivals, every run under training/, stable/, workshop/, bred foals); it is
  called by the game, train.py, compare.py and `python -m ai.stable`.
  Network shape is a per-run `arch` dict
  `{"hidden": [24, 16], "memory": 4, "inputs": 3}` (version 3 added the
  car's five traits); memory = extra
  outputs fed back as inputs at the next decision (recurrence, no gradients
  needed). `Population` (different weights per row), `Brain` (one network,
  batch of cars), `NeuralDriver` (the `Driver`; decides every
  `DECISION_TICKS` = 4 ticks, as in training; memory reset in `reset`).
- `evolve.py`:
  - Phase 1 (`mode: "solo"`): `PackRun`/`test_solo`, whole population as
    ghosts; score laps - `SOLO_DAMAGE_WEIGHT` x damage picked up; grid box and
    starting damage rotate by generation (`solo_setup`); ends when the champion's exam shows >= 1.9 laps of every track
    with <= 5% damage (`config.phase2_start` is then written).
  - Phase 2 (`mode: "race"`): `make_scenarios` gives `races_per_track` races
    per track per generation, the same for every driver, grid slots covering
    0..3; rivals scripted for `SCRIPTED_ONLY_GENS`, then a mix of scripted,
    recent champions and a hall of fame (`RIVAL_MIX`). `test_race` runs one
    real race per driver, all worlds stepped together, rivals batched.
    `RaceStats` counts collisions caused (I hit the car ahead) vs suffered,
    walls, overtakes, times passed, draft time, final place. `race_score`:
    `RACE_WEIGHTS` (saved per run): place 3/2/1/0 + 0.5 laps - 2.0 damage
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
- Personalities: `STYLES` in `evolve.py` override `RACE_WEIGHTS`
  (permanent `overtake`, `passed`, `draft` terms, separate from the fading
  `bonus_*` ones). `train(start_from="RUN[:GEN]", style=, name=)` is a
  training camp: the new run breeds on from that run's generation, inherits
  its arch/tracks/races/race length, starts in racing school, and records
  `parent`, `style` and `name` in its config.
- `roster.py`: `champion(run, gen, label, rank)` builds a `NeuralDriver` for
  any ranked driver of a generation; `register_champions` puts them in the
  registry as `evo:<run>:<gen>`, plus the latest champion of every named run
  under its name. `compare.py` races runs' champions with rotating rolling
  starts and prints racecraft statistics.
- `game/screens.py` `LabScreen` (4 charts, generation picker, ghost pack,
  top-4 reverse-grid race, the champion's test races, champions race, you v
  champions) and `PackScreen`.

Results of the trial run are in Status above. Known weaknesses / next ideas:
1. Racing-school scores are noisy with 4 races per driver; `--races 3` or a
   bigger population trade time for steadier progress.
2. No ray-cast inputs (`Track.raycasts` exists); version 2 added only the
   cheap left/right room to the barrier. The user chose not to give drivers
   the track's identity (they should generalise, not memorise).
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
