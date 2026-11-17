import json
import os

import pygame
import pytest

from ai import championship, halloffame, stable


def fake_history(root, seasons=3, cars=30):
    """Seasons of six-car championships drawn from a pool of `cars` scripted
    entrants, written the way championship.py saves them."""
    import random
    rng = random.Random(4)
    pool = [{"kind": "scripted", "id": f"s{k}", "name": f"Car {k}", "livery": None} for k in range(cars)]
    (root / "seasons").mkdir(parents=True)
    for season in range(1, seasons + 1):
        for part in range(cars // 6):
            entrants = pool[part * 6:(part + 1) * 6]
            races = []
            for track in championship.TRACK_ORDER:
                order = list(range(6))
                rng.shuffle(order)
                races.append({"track": track, "order": order, "results": [
                    {"entrant": e, "place": p + 1, "finished": p < 5, "best_lap": 12.0 + rng.random(), "fastest": False,
                     "points": championship.POINTS[p] if p < 5 else 0} for p, e in enumerate(order)]})
            ch = {"season": season * 10 + part, "entrants": entrants, "tracks": list(championship.TRACK_ORDER),
                  "races": races, "done": True}
            (root / "seasons" / f"season_{season * 10 + part}.json").write_text(json.dumps(ch))
    return pool


def test_stats_count_every_race_by_track_and_head_to_head(tmp_path):
    fake_history(tmp_path)
    cars = halloffame.stats(tmp_path)
    assert len(cars) == 30
    for c in cars.values():
        assert c["races"] == 15 and sum(t["races"] for t in c["tracks"].values()) == 15
        assert c["wins"] == sum(t["wins"] for t in c["tracks"].values())
        assert all(sum(v) == 15 for v in c["h2h"].values()) and len(c["h2h"]) == 5
        assert len(c["seasons"]) == 3
    assert sum(c["titles"] for c in cars.values()) == len(halloffame.champions(tmp_path)) == 15
    rows = halloffame.table(cars, "wins")
    assert [c["wins"] for _, c in rows] == sorted((c["wins"] for c in cars.values()), reverse=True)
    pct = halloffame.table(cars, "win %")
    assert halloffame.rate(pct[0][1]) == max(halloffame.rate(c) for c in cars.values())
    assert halloffame.table(cars, "wins", "your racers") == []
    few = dict(next(iter(cars.values())), races=2)
    assert halloffame.rate(few) is None                       # too few races for a rate


def test_the_hall_scrolls_switches_tabs_and_opens_a_cars_record(tmp_path, monkeypatch):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from game.app import App
    from game.audio import Audio
    from game.stable_screens import CarRecordScreen, HallScreen
    fake_history(tmp_path)
    pygame.display.init()
    pygame.font.init()
    app = App(pygame.display.set_mode((960, 540)), Audio())
    monkeypatch.setattr(stable, "STABLE_DIR", tmp_path)
    hall = HallScreen(app)
    app.show(hall)
    key = lambda k: hall.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k))
    for tab in range(4):
        app.draw()
        key(pygame.K_RIGHT)
    assert hall.tab == 0
    for _ in range(20):
        key(pygame.K_DOWN)
    app.draw()
    assert hall.row == 20 and hall.top > 0                    # scrolled past the first screenful
    key(pygame.K_PAGEDOWN)
    assert hall.row == 29
    key(pygame.K_s)
    key(pygame.K_f)
    assert (hall.sort, hall.show) == ("win %", "your racers")
    key(pygame.K_f)
    key(pygame.K_f)
    key(pygame.K_f)
    key(pygame.K_f)
    key(pygame.K_RIGHT)
    key(pygame.K_w)
    app.draw()
    key(pygame.K_RETURN)
    record = app.current
    assert isinstance(record, CarRecordScreen) and record.car["races"] == 15
    app.draw()
    if os.environ.get("SHOT"):
        pygame.image.save(app.screen, os.environ["SHOT"] + "_record.png")
    record.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert isinstance(app.current, HallScreen) and app.current.tab == 1
    if os.environ.get("SHOT"):
        for tab in range(3):
            app.current.tab = tab
            app.draw()
            pygame.image.save(app.screen, os.environ["SHOT"] + f"_tab{tab}.png")
