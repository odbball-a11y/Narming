# AI Sprint Racing

A top-down, single-screen arcade racer in the spirit of the 1980s sprint
games: small cars, the whole circuit in view, quick laps, sliding. All art is
drawn in code and the track layouts are original.

**Status: Stage 1 complete.** Two tracks, up to four cars (human, gamepad or
scripted in any slot), menus, countdown, HUD, results, pause, synthesised
sound, and exact replays. Stage 2 (a later project) adds AI drivers.

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
py -m pytest                        # run the tests
py render_frames.py --out shots     # save a PNG of every screen without opening a window
```

(On macOS / Linux use `python` instead of `py`.)

## Playing

Main menu: **Race**, **Controls**, **Replays**, **Quit**. Menus use the arrow
keys, Enter and Esc.

**Race setup:** pick the track (Speedway or Technical), the number of laps,
and who drives each of the four cars: `None`, any of the four keyboard sets,
any connected gamepad, or `Scripted` (the computer). Any driver type can go
in any slot. The default is you on the arrow keys against three scripted cars.

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
  render.py   camera, procedural track / car / HUD drawing
  input.py    key bindings, keyboard and gamepad Drivers
  audio.py    synthesised sound, silent fallback
tracks/   one JSON file per track
config/   controls.json
tests/    pytest suite
headless.py, render_frames.py   command-line tools
```

See `CLAUDE.md` for the architecture, conventions and the Stage 2 plan.
