# AI Sprint Racing

A top-down, single-screen arcade racer in the spirit of the 1980s sprint
games: small cars, the whole circuit in view, quick laps, sliding. All art is
drawn in code and the track layouts are original.

**Status: Stage 1, milestone 1 (prototype).** One car on the Speedway track
with keyboard control, the full physics model, lap timing, a headless runner
and tests. Menus, the second track, four-car races, sound and replays come in
milestone 2. Stage 2 (a later project) adds AI drivers.

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
py -m game                      # drive the red car on Speedway
py -m game --driver scripted    # watch the computer drive instead
py headless.py --cars 4         # race with no window, prints lap times and steps/s
py -m pytest                    # run the tests
py render_frames.py --out shots # save PNG frames without opening a window
```

(On macOS / Linux use `python` instead of `py`.)

## Controls

| Key | Action |
|---|---|
| Up | throttle |
| Down | brake; when nearly stopped, reverse |
| Left / Right | steer |
| R | back to the grid |
| F1 | debug overlay (speed, slip, surface, next checkpoint) |
| F5 | reload `sim/tuning.py` and restart (tune without quitting) |
| F11 | fullscreen |
| Esc | quit |

Bindings for players 1-4 are in `config/controls.json` (arrows, WASD, IJKL,
numpad). Only player 1 is used in the prototype.

## Tuning the feel

Every tunable number is in `sim/tuning.py`, each with a note on what it does.
Edit, save, press F5 in the game. The ones that change the feel most:

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
sim/      simulation only, never imports pygame (tests enforce it)
  tuning.py   every tunable value
  track.py    spline track, boundaries, checkpoints, grid, AI queries
  car.py      arcade physics (velocity separate from heading, limited grip)
  world.py    fixed 120 Hz step, collisions, lap counting, standings
  driver.py   Controls, Driver interface, driver registry
  scripted.py look-ahead racing-line driver
game/     pygame front end
  input.py    key bindings, keyboard Driver with steering smoothing
  render.py   camera, procedural track / car / HUD drawing
  app.py      fixed-timestep loop with interpolated rendering
tracks/   one JSON file per track
config/   controls.json
tests/    pytest suite
headless.py, render_frames.py   command-line tools
```

See `CLAUDE.md` for the architecture, conventions and the Stage 2 plan.
