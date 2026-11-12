# AI Sprint Racing

A top-down, single-screen arcade racer in the spirit of the 1980s sprint
games: small cars, the whole circuit in view, quick laps, sliding. All art is
drawn in code and the track layouts are original.

**Status:** the playable game (two tracks, four cars, menus, sound, replays)
plus damage, drafting, and AI drivers that learn by evolution, generation by
generation, which you can watch improve.

## Install

Needs Python 3.10 or newer (developed on 3.13 with pygame-ce 2.5.8, NumPy
2.5.3, pytest 9.2.0).

Windows (PowerShell or cmd), from this `sprint` folder:

```
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
```

macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

## Run

Always from the `sprint` folder:

```
py -m game                          # the game
py -m game --track technical        # jump straight to race setup on a track
py -m game --no-sound --fullscreen
py headless.py --track technical --cars 4      # race with no window: lap times, steps/s
py headless.py --record replays/a.replay.gz    # save a race's controls
py headless.py --replay replays/a.replay.gz    # play back and verify it is identical
py train.py                         # breed AI drivers (see "AI drivers" below)
py -m pytest                        # run the tests
py render_frames.py --out shots     # save a PNG of every screen without opening a window
```

(On macOS / Linux use `python` instead of `py`.)

## Playing

Main menu: **Race**, **Stable**, **AI Lab**, **Controls**, **Replays**, **Quit**. Menus use the arrow
keys, Enter and Esc.

**Race setup:** pick one of the five tracks, the number of laps,
the start (rolling, the default: single file and already at speed, car 1
leading; or a standing grid), and who drives each of the four cars: `None`, any of the four keyboard sets,
any connected gamepad, `Scripted` (the computer), or a trained AI champion
(`Evo gen N`, once you have trained some). Any driver type can go in any slot. The default is you on the arrow keys against three scripted cars.

Default keys (edit `config/controls.json` to change them; key names are
pygame key names):

| Player | Left | Right | Throttle | Brake / reverse |
|---|---|---|---|---|
| Arrows | Left | Right | Up | Down |
| WASD | A | D | W | S |
| IJKL | J | L | I | K |
| Numpad | 4 | 6 | 8 | 5 |

Gamepad: left stick steers, right trigger or A accelerates, left trigger or B
brakes. Plug it in before starting the game.

During a race:

| Key | Action |
|---|---|
| P or Esc | pause (resume, restart, quit to menu) |
| F1 | debug overlay (speed, slip, surface, next checkpoint) |
| F5 | reload `sim/tuning.py` and restart the race |
| F11 | fullscreen |
| F (replays only) | hold to fast-forward |

Holding brake when stopped reverses. A lap only counts if you pass every
checkpoint in order, so cutting across the grass or going backwards does not
count. Once the winner finishes the others have 30 seconds to finish.

The results screen lets you race again, watch the replay, or save it to
`replays/`; saved replays appear under **Replays** in the main menu.

Many keyboards cannot report more than a few keys held at once, so four
players on one keyboard may see dropped inputs. That is hardware, not the game.

## Tracks

| Track | Character | Width | Scripted lap |
|---|---|---|---|
| Oval | two long straights, two wide fast turns; pack racing and slipstream passes | widest | about 11.5 s |
| Speedway | fast, long straights, sweeping bends | wide | about 14 s |
| Esses | four flowing left-right sweeps, no hard braking | average | about 17 s |
| Technical | hairpin, chicane, narrow climb | narrow in places | about 22 s |
| Grand Prix | long straight, three hairpins, chicane, long sweep | narrow | about 24 s |

The AI racers in the stable only know Speedway so far.

## Damage and drafting

**Damage.** Hard hits on the barrier or another car damage the car, shown by
the DMG bar in its HUD panel and by smoke. Damage is permanent for the race
and only costs speed: a wrecked car loses 30% of its top speed and 35% of its
acceleration, but steers as before.

**Drafting.** Sit behind a fast car, in line with it and within about six car
lengths, and you get a tow: up to 15% more top speed and 40% more acceleration. Blue-white streaks
stream from the lead car to yours and DRAFT shows in your HUD panel.

Both are tunable in `sim/tuning.py` (the Damage and Drafting sections).

## Your stable

Main menu, **Stable**. Build a stable of named AI racers and race them against
the house rivals, Dangerous Dave and Careful Keith.

- **Create a racer**: type a name, set its **aggression** and **caution**
  (0 to 1), tick its **training partners**, choose how many **generations**
  to train, then **Start training**. Training runs in the background (about
  half a minute per generation) while you use the rest of the game. New
  racers start from a racing-school graduate that can already lap Speedway.
  - Aggression: training rewards places, passes and slipstreaming, and
    damage is cheap (Dangerous Dave is 1.0).
  - Caution: training makes damage and collisions it causes very costly
    (Careful Keith is 1.0).
  - Training partners: at first only scripted cars. Every racer you train
    becomes a possible partner for the next, and an upskill can train
    against the racer itself. House rivals are never training partners:
    they are what your racers are built to beat.
- **The racer's card** shows its personality, what it trained against, its
  measured racecraft (best lap alone, and a test race from last against three
  scripted cars: place, passes, collisions caused, damage, time in a tow),
  charts over every generation, and its career (races, wins, podiums, best
  race laps).
- **Race the house rivals**: your racer against the house rivals with a
  rolling start; the starting order rotates each race. Finished races count
  towards its career.
- **Upskill**: more training for an existing racer, with a new personality
  or new partners, carrying on from its current brain.
- Training stops if you quit the game; **Resume training** on the card
  carries on from where it stopped. Only one racer trains at a time.

Your racers are saved in the `stable` folder.

### Breeding

**Breed two racers** (on the stable screen, once two racers are at stud):
pick a sire and a dam, name the foal, and choose how the best foal is picked:

- **Fastest lap** after its mini-camp, or
- **Quickest learner**: fewest training generations to match its parents'
  pace.

The game then breeds a litter of 20 foals in the background (about a minute
on a 4-core PC). Each foal is made of whole neurons from one parent or the
other, plus a few small mutations; its personality is its parents' average,
give or take. Round 1 tries every foal alone and in one race; the best 5 go
on to round 2, three generations of training each with their own
personality. The winner is your foal.

Its **breeding certificate** (on its card) shows the pedigree (parents and
grandparents), its temperament, the shortlisted foals side by side with the
one picked, and what to expect from it, as predictions from its family.

### Careers

- A racer has a **racing career of 20 races**. After the 20th it retires to
  stud. **Retire to stud** on its card ends the career early.
- Only racers **at stud** can be bred from, and studs no longer race or train.
- A stud dies after **5 litters**, or of old age after **40 stable races**
  (run by any of your racers) at stud, whichever comes first.
- The dead go to the **Hall of Fame** (on the stable screen) with their
  record and number of foals. Their brains stay available as training
  partners.
- None of this applies in the workshop.

The numbers are `CAREER_RACES`, `STUD_BREEDINGS` and `STUD_LIFETIME` in
`ai/stable.py`.

Coming next: championships across several tracks, weather and car traits.

### Making house rivals (Workshop)

`py -m game --workshop` opens the same screens as a workshop. Racers made
there can also train against the existing house rivals, and **Publish as house
rival** copies one into `house/rivals`, which ships with the game.

## AI drivers

The AI learns by evolution, in two phases. A generation is 80 drivers, each a
small neural network. Every driver is tested, the best survive, and the next
generation is bred from mutated copies of the good ones.

- **Driving school (phase 1).** The whole generation drives the track at once
  as ghosts that pass through each other. Score: distance covered, less
  damage. It ends by itself once the champion laps both tracks cleanly.
- **Racing school (phase 2).** Every driver runs four real races per
  generation (two per track), with collisions, damage and drafting, from a
  single-file rolling start in every position. All drivers in a generation face the same races,
  so the comparison is fair. Rivals are scripted cars for the first 10
  generations, then a mix of scripted cars, the AI's own recent champions and
  a hall of fame of older ones, so it has to race opponents that fight back.
  Score: finishing place above all (3, 2, 1, 0 points for 1st to 4th), then
  distance, less damage taken and collisions it caused.
  Optionally (on by default) there are small bonuses early on for overtaking,
  not being overtaken and time in the draft; they fade out over 60
  generations.

The drivers see: their speed and slide, position and angle on the track,
the bends ahead and how long the straight ahead is, their damage, the tow
they get and the tow they give, the two cars ahead, the car behind, and cars
alongside on either side. They also have a small memory they carry from one
moment to the next.

### Training

In a terminal in the `sprint` folder (with the virtual environment on):

```
py train.py                                   # 50 more generations of run "default"
py train.py --generations 200
py train.py --run big --hidden 32 32 --memory 8      # a separate run with a bigger brain
py train.py --run plain --no-race-bonuses            # a separate run scored on results only
py train.py --run long --race-laps 3                 # a separate run with longer training races
py train.py --run speedway --tracks speedway --races 4 --race-laps 3   # one track only
```

Each generation prints one line. Ctrl+C is safe; running the same command
again carries on from where it stopped. The network size, memory and scoring
are fixed when a run is created, so to compare settings give the new run its
own `--run` name. Driving-school generations take a few seconds, racing-school
ones about 25 seconds on 4 cores.

### Racing personalities: training camps

A training camp takes the drivers of an existing run and trains them on in
racing school with a different idea of what a good race is:

```
py train.py --run dave --from speedway --style aggressive --name "Dangerous Dave"
py train.py --run keith --from speedway --style cautious --name "Careful Keith"
```

- **aggressive**: places count for more, every pass earns a bonus and every
  time it is passed costs, slipstreaming is rewarded, damage is cheap.
- **cautious**: damage and collisions it causes are very expensive.

The camp copies its settings (track, race length, network) from the `--from`
run and starts racing straight away. Named racers appear by name in race
setup and in the AI Lab (R switches runs). To see how differently they race:

```
py compare.py dave keith                 # 8 races, rolling start, order rotating
py compare.py dave keith --races 16 --laps 5
```

It prints wins, average place, passes, collisions caused and suffered,
barrier hits, damage, time in the draft and best lap for each driver.

### Watching

While training runs, open a **second** terminal, start the game
(`py -m game`) and choose **AI Lab**. It updates as each generation finishes.

Charts (the yellow line marks where racing school began):
- **Best lap alone**: the champion's time-trial lap on each track.
- **Race from last on grid**: the champion's finishing place, passes made and
  collisions it caused in a 3-lap race against three scripted cars, starting
  last.
- **Damage and drafting**: damage at the end of that race, and the share of
  it spent in someone's slipstream.
- **Score of the generation**: best and average. The score is calculated
  differently in racing school, so the line jumps where it starts.

Menu (pick a generation with **GEN**, Left/Right, PgUp/PgDn, End = latest):
- **Ghost pack**: the whole generation driving at once, as in driving school.
  It moves on to the next generation by itself (A toggles that, T changes
  track, hold F to fast-forward).
- **Top 4 race**: the generation's four best drivers race each other, with
  the best starting last.
- **Test race**: watch one of the races the generation was scored on
  (Left/Right picks which), with its champion in the seat it was tested in.
- **Champions race**: an early, a middle and the latest champion against a
  scripted car.
- **You v champions**: you against two champions and a scripted car.

R switches between training runs, so you can compare a big-brain run with a
standard one.

Trained runs are saved in `training/<run>/`. Runs from the previous version
of the trainer are moved to `<run>-v1` (not deleted) the first time you train
with the same name. If you change the physics values in `sim/tuning.py`,
drivers trained before the change may drive worse.

## Tuning the feel

Every tunable number is in `sim/tuning.py`, each with a note on what it does.
Edit, save, press F5 during a race. The ones that change the feel most:

| Value | Now | Try | Effect |
|---|---|---|---|
| `grip` | 34 | 26 to 45 | lower = slides everywhere; higher = on rails |
| `steer_rate_high` | 1.5 | 1.2 to 2.0 | turn rate at top speed; higher = bigger slides at speed |
| `steer_rate_low` | 3.0 | 2.4 to 3.8 | turn rate at low speed; higher = sharper in tight corners |
| `throttle_grip_loss` | 0.18 | 0 to 0.4 | how much flooring it loosens the tail |
| `accel` / `top_speed` | 20 / 32 | 16-26 / 28-38 | punch and pace |
| `brake_decel` | 42 | 30 to 60 | how late you can brake |
| `KEY_STEER_RATE` | 5 | 3 to 10 | how fast a held key reaches full lock |
| `KEY_STEER_RETURN_RATE` | 8 | 4 to 14 | how fast steering centres on release |
| `GRASS_DRAG` / `GRASS_GRIP` | 1.5 / 0.4 | | how punishing the verge is |
| `WALL_RESTITUTION` / `WALL_FRICTION` | 0.35 / 0.45 | | bounce and speed lost on the barrier |

## Layout

```
ai/       learned drivers (NumPy only, no pygame)
  stable.py   racers: create, train, upskill, careers, house rivals, publish
  brain.py    what a driver sees, the neural network, NeuralDriver
  evolve.py   tests, breeding, the training loop, saved runs
  roster.py   puts trained champions in the driver registry
sim/      simulation only, never imports pygame (tests enforce it)
  tuning.py   every tunable value
  track.py    spline track, boundaries, checkpoints, grid, AI queries
  car.py      arcade physics (velocity separate from heading, limited grip)
  world.py    fixed 120 Hz step, collisions, lap counting, standings
  race.py     countdown, finish, results
  replay.py   record per-tick controls, play them back exactly
  driver.py   Controls, Driver interface, driver registry
  scripted.py look-ahead racing-line driver
game/     pygame front end
  app.py      window, main loop, screen switching
  screens.py  menus, race screen (fixed-timestep loop, interpolated drawing)
  stable_screens.py  stable, create-a-racer and racer-card screens
  render.py   camera, procedural track / car / HUD drawing
  input.py    key bindings, keyboard and gamepad Drivers
  audio.py    synthesised sound, silent fallback
tracks/   one JSON file per track
house/    shipped AI: the graduate starting brain and the house rivals
config/   controls.json
tests/    pytest suite
headless.py, train.py, compare.py, render_frames.py   command-line tools
```

See `CLAUDE.md` for the architecture, conventions and the Stage 2 plan.
