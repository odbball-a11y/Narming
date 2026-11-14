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
python train.py --run long --from graduate --car random --generations 1000   # from the shipped graduate
python train.py --run vb --racer "Vortex Brick" --tracks speedway --races 3 --minutes 60   # an existing racer, one car, one track, an hour
python train.py --list                            # racers and house rivals you can name (--racer / --car NAME)
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

## The stable (built: steps 1-5, championship done; 6-8 cars still to do)

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
  (50: ten five-race championships, user request; was 20); `retire` also works early. `can_race`/`can_train` need "racing",
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
The card picks the race track (Left/Right on RACE).

House rivals recreated (user approved) in the workshop from the five-track
graduate, standard car: Dangerous Dave (aggression 1, caution 0) 40 gens v
scripted + himself; Careful Keith (0, 1) 40 gens v scripted + himself + new
Dave; then Dave +20 gens v scripted + himself + Keith; both published.
Head to head, 4 rotating-start races per track with 2 scripted cars: Dave
17/20 wins (avg place 1.0-1.25, 1.5-2.5 passes, rough on Technical and
Grand Prix ~33% damage); Keith 3/20 (place 2.5-3.25, never passes, ~0
collisions caused). Keith's caution-1.0 scoring makes holding position
always beat passing; a caution ~0.7 with some aggression would likely give
a careful racer that still overtakes.

- Liveries (`ai/livery.py`, data only): `{"colour", "trim" (stripe | twin |
  nose | wing | band), "trim_colour", "number"}` in `racer["livery"]` (house
  cards too). Assigned by the game at creation (`assign`: the first palette
  colour nobody has, never red/green, which are Dave and Keith's, with
  varying trims and numbers from 10); `livery_of` fills it in lazily for
  older racers; `inherit` gives a foal its own free colour, its sire's colour
  as trim colour and its dam's trim style. `resolve(drivers, slots)` gives
  every car of a race a look: a driver's `.livery`, or its slot colour
  unless a liveried car has it. `render.make_car_sprite(colour, ppu, trim,
  trim_colour)` and `RaceRenderer.sprite_for`; HUD, results and the
  championship screens use them. Replays store liveries and each car's own
  `car_params` (a replay of a trait car now reproduces; it did not before).
- Championship (`ai/championship.py`): saved as `stable/championship.json`
  (finished seasons in `stable/seasons/`). `start(root, [racer dirs])` (see the
  six-car note below; then house rivals, then scripted cars with fixed liveries,
  tracks `TRACK_ORDER`); `standings` (points, wins, places; `moved`),
  `grid` (race 1 seeded draw, then reverse standings, leader last),
  `build_race`, `finish_race` (points `POINTS` 10-7-5-3-2-1 + 1 fastest lap
  among finishers; DNF 0; calls `stable.record_race(defer_retire=True)` so
  careers count once per race and a racer at its limit finishes the season;
  the last race runs `complete`: titles, retirements, deaths, archive).
  Screens: `ChampionshipSetupScreen`, `ChampionshipHub` (watch or simulate
  the next race, abandon with a second press), `StandingsScreen` (result and
  table after every race, champion banner at the end). `RaceScreen(on_over,
  on_continue)` is the watched championship race (no restart; quitting a race
  discards it). The racer card's RACE became ENTER CHAMPIONSHIP (workshop
  keeps a test race). User choices: watch-or-sim per race, reverse grid,
  game-assigned colours then inheritance; my defaults: 10-7-5-3 + fastest
  lap, damage resets, one or two of your racers.

- Training focus (user request: "choose all tracks or a particular track for
  the same amount of generations; a single track should make you a
  specialist"): each racer version has `focus` (a track key or None).
  `stable.train` trains on `[focus]` or all five tracks with
  `races_per_track = graduate races x 5 / tracks trained` (equal effort), and
  always `exam_tracks` = all five, so a specialist is measured everywhere
  (`evolve.train(exam_tracks=)`). `specialty` / `specialty_text`: a specialist
  at a track when more than half of the racer's generations were on it.
  Create and Upskill screens have a TRAINING ON row; the card shows it.
  Every championship race is `championship.RACE_LAPS` = 10 laps (user request; was 5).

Specialist experiment (15 generations each, same personality and car, one
racer on all tracks, one on the Oval only, `stable.train` from the
graduate): Oval lap 10.74 -> 10.70 (general) v 10.79 -> 10.38 (specialist,
3% quicker on its track); elsewhere the specialist got worse as it forgot
(Esses 14.29 -> 15.35 s, Technical 21.45 -> 22.23, Grand Prix 22.93 ->
24.48 with 51% damage) while the all-rounder improved slightly everywhere.
So focus works as intended: a clear but modest gain on the chosen track, at
a real cost elsewhere. One seed only.

Careers count every race a racer starts, finished or not (a DNF is no win or
podium): `record_result(..., finished=)`.

- Ratings (`ai/rating.py`; user asked for an Elo-style rating for every car
  including scripted, rated by every race with no placement test, then said
  "use trueskill"): TrueSkill via a bundled copy of the `trueskill` 0.4.5
  package in `ai/vendor/trueskill/` (BSD; `six` removed; the pip package no
  longer builds on current Python/setuptools; not for commercial use per its
  licence note). `ENV = TrueSkill(draw_probability=0.10)`; displayed rating =
  1000 + 40 (mu - 25), +/- = 40 sigma. `update(root, entrants, results,
  track)` rates a championship race (finishers ranked by place, non-finishers
  tied for last) for the overall and the track rating; `loosen` raises sigma
  when a racer is upskilled; `summary`, `rating_of`, `table`. Stored in
  `stable/ratings.json` keyed `racer:<id>` / `house:<id>` / `scripted:<id>`.
  `finish_race` puts `rating` / `track_rating` / `sigma` on each result.
  Scripted entrants have fixed identities (their number sets a skill slot and
  `car_params`). Screens: ratings in the championship tables, `RatingsScreen`
  (scrolls), racer card, Hall of Fame (peak), certificate.

- Championship stars and training budget: a racer's titles show as gold
  stars (`draw_stars`) on the ratings screen, house panel, card and champion
  banner (`rating.add_title` / `titles_for_key` / `championship.titles_of`;
  house and scripted cars keep titles in `ratings.json`). Each racer has a
  lifetime budget of `stable.TRAINING_BUDGET` = 50 training generations
  (`training_planned` / `training_left`; None in the workshop). `create`
  and `upskill` refuse more than is left, the Create/Upskill screens offer
  `generation_choices(left)` (10..50, or what remains), foals count
  `CAMP_GENERATIONS`, and the card hides UPSKILL when fully trained.

- Track records and Hall of Fame (`ai/records.py`, `stable/records.json`):
  `finish_race` records the race's fastest lap as a track record when it
  beats the old one (`track_record` on that result). `StandingsScreen` shows
  "FASTEST LAP name time" (and NEW TRACK RECORD, or the current record).
  `HallScreen` (always in the stable menu) has track records, past
  champions (`championship.past_champions`) and the legends (dead racers).

- Practice races can use retired racers and legends too (`register` tags them "(retired)" / "(legend)"); championships never do.
- Plain races count for nothing: only championship races (`RaceScreen`
  with `on_over`) touch careers, the stable clock, ratings, titles or track
  records; a race from the main menu or the workshop is practice.
  `TrainingScreen` (card row TRAINING HISTORY) lists every round of training
  with its sliders, partners, focus and the test result at its end.

- Entering: up to `MAX_OWN` = 3 of your racers (a race holds four cars), and
  the field always gets the highest-rated house rival (`house_field` sorts
  rivals by rating), then the next, then scripted cars.

- Dynasty (`dynasty.py`, output `dynasty/` git-ignored and `dynasty_report/`):
  a self-running stable that races whole championships, trains between
  championships (specialist 20 gens / all-rounder 10), breeds retired studs and
  writes `REPORT.md` / `journal.md`; resumable (`python dynasty.py --hours 8`).
  `ai/snapshot.py` saves and loads a whole stable as `saves/NAME.zip` (old
  generations cut to four drivers; the stable it replaces is kept aside). The 8 h
  run is in `saves/dynasty-final.zip`; findings in `dynasty_report/ANALYSIS.md`.

- Corner inputs (input version 4, `brain._INPUTS_V4`): `Track.ideal()` solves a
  minimum-curvature line once per track (bounded least squares on a coarse grid);
  drivers see the ideal line's lateral offset now / 12 / 30 units ahead, a speed
  margin (speed against what the next corners allow, including planned braking),
  the safe speed and distance of the limiting corner, and grip use. `lines.py`
  measures lap time and slide share. `stable.SOLO_SHARE` = 0.5 (the Lab default
  `evolve.SOLO_SHARE` stays 0.2).
  Experiment (30 generations from the graduate, one seed, standard car): slide
  share of a lap (sideways speed above 3 u/s) was 25.7% before, 30.6% with the new
  inputs at solo share 0.5 and 27.1% at 0.2; laps were a little quicker at 0.2
  (Speedway 12.46 -> 12.20 v 12.58). The scripted driver never slides and is
  ~17% slower, so in this physics sliding is not penalised: the grip model removes
  sideways speed for free, and evolution uses that. Fixing it needs a slide cost
  in the physics (tyre scrub) or in the score.

- Physics options (`tuning.CarParams.scrub`, `brake_circle`, `throttle_circle`,
  all 0 = the original physics, and left out of `physics_fingerprint` while off,
  so old replays still match): scrub = forward deceleration proportional to the
  sideways speed grip could not remove (a clean line never pays it); the circle
  replaces the linear throttle/brake grip losses with sqrt(1 - used^2).
  `lines_physics.py` runs the old graduate and the scripted driver under variants
  (no retraining). Result: scrub is the lever; 8 makes the old graduate slide
  6.5% of a lap instead of 25.7%, 18% -> 1% damage, only 2.8% slower; 16 is ~7%
  slower (barely quicker than scripted); the friction circle alone changes little
  without retraining. Scripted laps never change.

- Two-grip physics (`CarParams.front_limit`, `yaw_lag`, `balance`,
  `brake_transfer`; 0 = off): the front has its own grip limit (steering demand
  above it is cut: understeer; braking eats it through the friction circle), the
  rear is `grip` (throttle eats it: power oversteer; braking unloads it), and the
  yaw rate follows steering with a lag that grows while the rear slides.
  `car.yaw_rate`, `front_use`, `rear_slip`; inputs version 5 (yaw rate, front
  grip use, rear slip, balance). Balance is a bred trait (`cartraits.balance_of`,
  -2 very stable .. +2 very loose; no star cost; `inherit` takes it from a parent
  with a 25% chance of a step), shown in `describe` and on the certificate.
  Training test (30 gens from the graduate, inputs v4, solo share 0.5): current
  physics was at pace 0.92 by gen 3; with front_limit 1.0 + yaw_lag 0.08 it took
  ~30 gens to reach 0.92 (started 1.045), and races were cautious for a while.
- Weight transfer (`weight_transfer`, `lateral_transfer`, `load_sensitivity`,
  `suspension_lag`; needs the two-grip model; 0 = off): smoothed forward and
  sideways acceleration move load (`car.front_load`, `rear_load`) between the
  ends, grip goes as load^0.9, cornering at the limit costs `lateral_transfer`;
  replaces `brake_transfer`. Inputs version 6 (front load, rear load).

- Full physics on by default (physics 3): scrub 8, friction circle 0.8/0.6,
  front grip 1.2 x rear (so full throttle can power-oversteer; with 1.0 the car only
  ever understeered), yaw lag 0.08 s, weight transfer 0.2, lateral transfer 0.1.
  `CLASSIC_PHYSICS` turns it all off. Track records are tagged by physics.
  Graduate retrained ("graduate6", 200 gens from the old graduate, `car="random"`
  incl. balance): driving school finished by gen 18; racing school at first hung
  back (place ~3.9 of 4 from last, 0.2 passes), so from gen 69 the run was scored
  with `sliders_to_weights(0.8, 0.1)` (damage 1.18, permanent overtake 0.28),
  after which passes rose to ~2 per exam race. Head to head, 8 races per track, 3
  laps, under the new physics: gen 175 avg place 1.70 / 18 wins of 40, gen 200
  2.10 / 14, gen 150 2.60 / 8, old graduate 3.60 / 0. Gen 175 is
  `house/graduate.npz` now. Contact is rough on Technical and Grand Prix (44-60%
  damage in all-AI races). `evolve.train(start_file=..., driving_school=True)`
  now really starts in driving school (it used to force racing school).

- Six-car championships (`championship.FIELD` = 6, `MAX_OWN` = 5: up to five
  of yours, the best-rated house rival always races, then the other rival, then
  scripted cars). Rolling single-file starts handle any number of cars.
  The race HUD is now a timing screen (`RaceRenderer.draw_hud`): rows in race
  order (1st-3rd left, 4th-6th right), each with colour, name (cyan while in a
  tow), lap, current lap time (or finishing time), last, best (pink = the race's
  fastest) and a damage bar; `PLACES` goes to 8th. The results overlay, the
  championship table and the standings screen tighten their rows for six.
  AI training races are still four cars (three rivals); not yet trained in
  six-car fields.

- Track notes (user choices: per corner, speed + line + throttle, inherited,
  house rivals get notes that keep evolving). `Track.corners()` finds apexes as
  peaks of the smoothed ideal-line curvature at least 25 units apart and shares
  the lap between them (Oval 4, Speedway 5, Technical 7, Esses 9, Grand Prix 9).
  A driver's vector = network weights + notes for every track
  (`arch["notes"]` = [[track, corners, fingerprint], ...]; `with_notes`,
  `genome_size`, `fit_genomes` pads older vectors with zero notes). Notes never
  touch the network: `observe` reads `car.notes` (set by `NeuralDriver.reset`,
  `PackRun`, `test_race`) and scales the corner's safe speed (+-25%), shifts its
  ideal line (+-half the half-width) and, after the apex, moves the speed-margin
  input (when to get on the power). Zero notes drive exactly as before (tested).
  `evolve.train(notes=True)`; `breed(frozen=)` keeps notes of tracks not being
  trained (and, with `notes_only`, the whole network) unchanged. Stable training
  and foal camps use notes; `crossover` takes each corner's notes from one
  parent. `stable.house_notes(id, gens)` / `python -m ai.stable house-notes
  "Careful Keith" --generations 20` is a notes-only camp (run
  `training/house-<id>-notes`, continues each call) written back into the rival.
  Screens: TRAINING HISTORY shows track knowledge (generations per track) and a
  map per track with corners coloured by the speed note.
  Experiment (Speedway only, 30 gens from the graduate, same seed): head to head
  over 16 five-lap races, with notes gen 30 / gen 25 averaged place 2.75 / 1.75
  against 3.25 / 2.25 without, best laps 13.46 / 12.90 v 13.56 / 13.21; the
  notes were still small (+-0.1) after 30 gens. One seed.

- Telemetry (user: "track the traces of all drivers ... builds a history of
  what is fastest"; own laps count; screen + ghost; it enhances the notes,
  compared to the ideal line, informing braking points). `sim/telemetry.py`
  `LapRecorder` (in every `Race`, and `PackRun(record=True)`) keeps each car's
  flying laps (lap 2 on) resampled every 2 units: t, x, y, heading, lateral,
  speed, throttle, brake, steering, slip; `pose_at` for ghosts. `ai/telemetry.py`
  keeps the 5 fastest laps per track plus the fastest of every car type in
  `telemetry/<track>.json` (git-ignored, tagged with the physics fingerprint;
  `entry`, `submit`, `submit_race`, `best`). A car type is its physics
  (`car_type(params)`: top speed, accel, grip, brakes, mass, balance; user: "we
  don't want cars learning from slow traces"): `best(track, params)` and
  `reference(track, params)` use the best lap of that type, else the nearest
  type within `NEAR` (0.12, about three stars at the same weight), else none. Practice races (humans included), every
  championship race and every training exam (the champion's solo and race
  laps) submit. `corner_report` gives per corner the lap's apex speed v the
  ideal line's safe speed, its apex line v the ideal, where it lifted/braked
  and where it got back on the power; `reference(track, params)` turns that into
  reference notes (same three fields), and every AI sees its own notes plus the
  reference (`car.reference`, set beside `car.notes`; `brain.USE_REFERENCE`).
  Tests keep their own telemetry (conftest). TELEMETRY screen (main menu):
  fastest laps, the lap's line with lift/brake and power-on points, speed trace
  v the record and the ideal line's safe speed with a pedal strip, and a
  corner table. Practice races with a human show a ghost of the best lap for
  that car's type (G toggles).
- Front grip 1.2 -> 1.1 (user: cars lost the back end through the Esses; physics
  4 for track records, telemetry restarts with the new fingerprint). Esses, house
  rivals unretrained, 5-lap solo, lap / share of the lap with the rear past 50%
  slip: Keith 16.30 -> 15.89 s, 5.5 -> 4.3%; Dave 15.71 -> 15.18, 9.2 -> 5.7%;
  Zappy Zoe 15.39 -> 15.65, 3.0 -> 3.7%; Bold Zoe 15.18 -> 15.42, 8.5 -> 7.9%
  (rear past 90% 1.0 -> 0.2%). Graduate7 trained its first 25 gens at 1.2.
- Grip 34 -> 36 (+6%; scripted slots 32.5 -> 34.5 and 36 -> 38; records physics
  5). With front grip 1.1, house rivals unretrained, best lap old -> new grip:
  Esses Keith 15.84 -> 15.66, Dave 15.14 -> 14.87, Zappy 15.37 -> 15.11, Bold
  15.56 (15% damage) -> 14.38 (none); Technical 0.3-0.7 s quicker each; rear
  slide share about the same.
- Breeding by time trial (user: "maybe the trial is not a race but more time
  trials ... we pick the best one"). `breed` makes `LITTER` (50) foals with
  `crossover(method)`; `CROSSOVER` = "mixed" alternates "blend" (weighted average
  of the parents, w 0.35-0.65, then mutation) and "dominant" (90% of neurons from
  one parent). Round 1 is `time_trial`: every foal and both parents lap every
  track alone for `TRIAL_LAPS` scripted laps in the foal's car; score = median
  flying-lap pace + damage/2 + lap spread. The fastest `SHORTLIST` (5) get one
  race check per track (dropped if damage > 0.5) and `FINALISTS` (3) go to camps
  as before. Certificate: `method`, per candidate `made_by`, `trial_pace`,
  `race_check`, and `trial` {parents_pace, foal_pace, vs_parents, litter_best}
  ("at birth X% quicker than its parents"). Crossover test (litters of 40, three
  house-rival pairs, time trials): neuron splice median foal 12-29% slower than
  its parents, 0-1 of 40 beat both; blend median 1-6% quicker, 11-40 of 40 beat
  both; dominant gave the single fastest foal in two of three pairs.
- Track school (main menu TRACK SCHOOL; user: "watch a car training for speed on
  a track ... see the lap times improve"). `ai/trackschool.py`: `options(root)`
  (graduate, house rivals, every trained stable racer), `start(option, track)`
  makes a practice copy in `trackschool/<driver>-<track>/` (git-ignored; the real
  racer and its budget are never touched), `train` = `evolve.train` on that one
  track, solo only (`phase2_from` never), notes on, population 60, ~2-3 s per
  generation; run by the game as `python -m ai.trackschool DIR` (`App.start_trackschool`).
  It stops itself (`Stopped`) when the screen has not touched `alive` for
  `HEARTBEAT` (60 s), so a crashed game does not leave it training for ever.
  `game/trackschool_screen.py`: pick driver and track; then stints of
  `STINT_LAPS` (3) laps, the first from a rolling start, each by the best of
  the newest finished generation; live delta to the session-best lap (by
  distance), last lap, session best, best ever for this car type
  (`telemetry.best`), a stint scoreboard and the per-generation test-lap chart.
  Trial (Zappy Zoe, Esses): stints went from 15.3 s to ~13.5 s within ~100 gens.
  Sessions are kept: `start` carries on an earlier session for the same driver
  and track (`existing`, `folder`; `fresh=True` wipes it). For a house rival,
  `save_to_house(dir, gen=None)` makes the generation with the fastest clean
  test lap (`best_generation`, damage <= 5%) the house car: old files kept in
  `house/rivals/old/`, card gets `track_school` entries and new `arch`, its
  rating is loosened. Screen: CONTINUE / START AGAIN / MAKE THIS THE HOUSE CAR
  rows, H (twice) while watching; CLI `python -m ai.trackschool save DIR [--gen N]`.
  Note the copy only trained on one track (other tracks' notes frozen, network
  shared), so it may be weaker elsewhere.
  Any car can do this (user: "any car can be saved as the championship driver,
  with a * that points out this additional training"): `can_save` (house rivals
  and stable racers; not the graduate), `save` dispatches; `save_to_racer` adds a
  version (`generations` 0, so the training budget is untouched; `track_school`
  in the version and `racer["track_school"]`; refused while the racer has
  unfinished training or no longer races). `stable.shown_name(data)` adds " *"
  to anything with `track_school` (championship entrants, driver labels, the
  stable list, house panel, card title); `track_school_text` is the card note.
  `App.stop_training` now stops the job's whole process group (worker processes
  were left running before; `taskkill /T` on Windows).
- Smoothness: `PackRun` measures input jumps between decisions and the share
  of decisions sliding; the solo score pays `SMOOTH_WEIGHT` (0.1) x (jitter +
  slide); exams report `solo_jitter` / `solo_slide`; `stable.smoothness(exam)`
  is shown on the racer card.

Still to build: six-car training races (slower training), wet/dry weather (not
wanted for now), PPO as a rival method.

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
AI training. The renderer draws tow ripples (`draw_tows`: curved waves rolling
back from the car giving a tow to the car taking it, `TOW_*`; user choice, replacing
the haze below, which is now off: `HAZE_ON`), smoke, the HUD damage bar, a heat-haze wake
behind every car above `HAZE_FROM` (55%) of its top speed (the track behind it
is redrawn in shifted patches plus faint ripples drifting back; it stretches to
reach a car taking a tow; replaced the tow streaks, user choice) and, on every
`("car", a, b, impact)` event (`on_tick(world, events)`), sparks at the contact
point scaled by the impact, a short flash, and bits of debris after big hits
(`DEBRIS_LIFE` 4 s). Constants at the top of `game/render.py`.

## AI drivers (`ai/`)

`ai/` imports `sim/` and NumPy only; `game/` imports `ai/`. Method:
neuroevolution in two phases (the user chose generations over PPO, and asked
for "learn to drive first, then learn to race").

- `brain.py`: `observe(world, i)` gives 46 inputs (`INPUT_NAMES`; version 4 adds the ideal line and corner speed, below): speeds,
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
