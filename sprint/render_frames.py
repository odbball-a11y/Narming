"""Render frames of the game to PNG with no window (SDL dummy video driver).

    python render_frames.py --out shots --driver scripted --seconds 2 6 12

Used to check by eye that the track, cars and HUD are drawn correctly on
machines with no display.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.app import PrototypeApp  # noqa: E402
from sim import tuning  # noqa: E402
from sim.track import Track  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="shots")
    ap.add_argument("--track", default="speedway", choices=Track.available())
    ap.add_argument("--driver", default="scripted")
    ap.add_argument("--size", type=int, nargs=2, default=(1280, 720))
    ap.add_argument("--seconds", type=float, nargs="+", default=[0.0, 3.0, 8.0])
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    pygame.init()
    screen = pygame.display.set_mode(tuple(args.size))
    app = PrototypeApp(screen, args.track, args.driver)
    app.debug = args.debug
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for seconds in sorted(args.seconds):
        while app.session.world.time < seconds:
            app.session.tick()
        app.draw()
        path = out / f"{args.track}_{seconds:05.1f}s.png"
        pygame.image.save(screen, str(path))
        print("wrote", path)
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
