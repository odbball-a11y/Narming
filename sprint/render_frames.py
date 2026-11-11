"""Render every screen of the game to PNG with no window (SDL dummy driver).

    python render_frames.py --out shots
    python render_frames.py --out shots --track technical --size 1920 1080

Drives the real App with synthetic key presses, so what is saved is what the
game draws.  Used to check screens by eye on machines with no display.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.app import App  # noqa: E402
from game.audio import Audio  # noqa: E402
from ai import roster  # noqa: E402
from game.screens import (ControlsScreen, LabScreen, MainMenu, PackScreen, RaceScreen,  # noqa: E402
                          SetupScreen)
from sim import tuning  # noqa: E402
from sim.race import Race  # noqa: E402
from sim.replay import Recording  # noqa: E402
from sim.track import Track  # noqa: E402


def key(app, code) -> None:
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="shots")
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--size", type=int, nargs=2, default=(1280, 720))
    ap.add_argument("--seconds", type=float, nargs="+", default=[4.0, 12.0],
                    help="race times to capture")
    args = ap.parse_args()

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode(tuple(args.size))
    app = App(screen, Audio())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def shot(name: str) -> None:
        app.draw()
        path = out / f"{name}.png"
        pygame.image.save(screen, str(path))
        print("wrote", path)

    app.show(MainMenu(app))
    shot("1_menu")
    app.setup["track"] = args.track
    app.show(SetupScreen(app))
    shot("2_setup")
    app.show(ControlsScreen(app))
    shot("3_controls")

    race = Race(args.track, [(s, "scripted") for s in range(4)], laps=2)
    view = RaceScreen(app, race)
    app.show(view)
    for _ in range(int(1.5 * tuning.TICK_RATE)):
        view.tick()
    shot(f"4_{args.track}_countdown")
    for seconds in sorted(args.seconds):
        while race.world.time < seconds and not view.over:
            view.tick()
        view.debug = True
        shot(f"5_{args.track}_{seconds:04.1f}s")
        view.debug = False
    key(app, pygame.K_p)
    shot(f"6_{args.track}_paused")
    key(app, pygame.K_p)
    while not view.over:
        view.tick()
    shot(f"7_{args.track}_results")
    replay = Recording.from_race(race)
    app.show(RaceScreen(app, replay.make_race(), recording=replay))
    while not app.current.over:
        app.current.tick()
    shot(f"8_{args.track}_replay_results")

    # AI lab: charts, a generation as a ghost pack, and the racing views.
    app.show(LabScreen(app))
    shot("9_lab")
    run = roster.latest_run()
    if run:
        pack = PackScreen(app, run)
        app.show(pack)
        for gen in roster.spread(pack.gens, 3):
            pack.load(gen)
            for _ in range(int(6.0 * tuning.TICK_RATE)):
                pack.pack.step()
            shot(f"10_{args.track}_pack_gen{gen:04d}")
        for name, action in (("top4", lambda lab: lab.top4_race()),
                             ("test_race", lambda lab: lab.test_race()),
                             ("champions", lambda lab: lab.champions_race(with_human=False))):
            lab = LabScreen(app)
            app.show(lab)
            action(lab)
            view = app.current
            if view is lab:
                continue
            while view.race.world.time < 9.0 and not view.over:
                view.tick()
            shot(f"11_{args.track}_{name}")
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
