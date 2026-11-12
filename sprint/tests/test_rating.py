"""TrueSkill ratings for every car in the championships."""
import numpy as np
import pygame
import pytest

from ai import championship, rating, stable

from test_championship import instant_racer
from test_stable import press

FIELD = [{"kind": "racer", "id": "zoe", "name": "Zoe"}, {"kind": "house", "id": "dave", "name": "Dave"},
         {"kind": "scripted", "id": "scripted1", "name": "Scripted 1"},
         {"kind": "scripted", "id": "scripted2", "name": "Scripted 2"}]


def race(order, finished=(True, True, True, True)):
    """Result rows: entrant i finishes in place order[i]."""
    return [{"entrant": i, "place": p, "finished": f} for i, (p, f) in enumerate(zip(order, finished))]


def test_trueskill_is_bundled_and_everyone_starts_the_same(tmp_path):
    assert rating.rating_of(tmp_path, FIELD[0]) == rating.START == 1000
    changes = rating.update(tmp_path, FIELD, race([1, 2, 3, 4]), "oval")
    assert all(c["before"] == 1000 for c in changes.values())


def test_winners_gain_losers_lose_and_uncertainty_shrinks(tmp_path):
    for _ in range(4):
        changes = rating.update(tmp_path, FIELD, race([1, 2, 3, 4]), "oval")
    after = [changes[i]["after"] for i in range(4)]
    assert after == sorted(after, reverse=True) and after[0] > 1100 and after[3] < 900
    table = rating.table(tmp_path)
    assert [r["name"] for r in table] == ["Zoe", "Dave", "Scripted 1", "Scripted 2"]
    assert all(r["races"] == 4 and r["sigma"] < rating.SCALE * rating.ENV.sigma for r in table)
    assert rating.summary(tmp_path, "racer:zoe")["races"] == 4
    assert rating.summary(tmp_path, "racer:nobody") is None


def test_beating_stronger_cars_gains_more_than_beating_weaker_ones(tmp_path):
    for _ in range(5):
        rating.update(tmp_path, FIELD, race([1, 2, 3, 4]), "oval")           # Zoe is now the standard to beat
    before = {i: rating.rating_of(tmp_path, FIELD[i]) for i in range(4)}
    upset = rating.update(tmp_path, FIELD, race([4, 3, 2, 1]), "oval")      # the order is turned upside down
    assert upset[3]["after"] - before[3] > 0 > upset[0]["after"] - before[0]
    assert upset[3]["after"] - before[3] > 40                                # a big upset moves things


def test_cars_that_do_not_finish_share_last_place(tmp_path):
    changes = rating.update(tmp_path, FIELD, race([1, 2, 3, 4], (True, True, False, False)), "oval")
    gain = {i: changes[i]["after"] - changes[i]["before"] for i in range(4)}
    assert gain[0] > gain[1] > 0 > gain[2] and gain[3] < 0
    assert gain[2] == pytest.approx(gain[3], abs=2.0)                       # a tie for last: nearly equal


def test_track_ratings_are_kept_apart(tmp_path):
    for _ in range(3):
        rating.update(tmp_path, FIELD, race([1, 2, 3, 4]), "oval")
    for _ in range(3):
        rating.update(tmp_path, FIELD, race([4, 3, 2, 1]), "esses")
    zoe = rating.summary(tmp_path, "racer:zoe")
    assert zoe["tracks"]["oval"] > 1000 > zoe["tracks"]["esses"]            # a specialist shows up
    assert rating.rating_of(tmp_path, FIELD[0], "oval") == zoe["tracks"]["oval"]
    assert rating.rating_of(tmp_path, FIELD[0], "grandprix") == 1000


def test_upskilling_loosens_the_rating(tmp_path, dirs):
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    entrants = [{"kind": "racer", "id": "zoe", "name": "Zoe"}] + FIELD[1:]
    for _ in range(6):
        rating.update(root, entrants, race([1, 2, 3, 4]), "oval")
    sure = rating.summary(root, "racer:zoe")["sigma"]
    stable.upskill(zoe, 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    assert rating.summary(root, "racer:zoe")["sigma"] > sure + 50           # less sure of it now


def test_every_championship_race_rates_everyone_scripted_cars_included(dirs):
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    ch = championship.start(root, [zoe])
    race_ = championship.build_race(root, ch)
    race_.run(max_seconds=400)
    record = championship.finish_race(root, ch, race_)
    assert all(len(r["rating"]) == 2 and r["sigma"] > 0 for r in record["results"])
    table = {r["name"]: r for r in rating.table(root)}
    assert set(table) == {"Zoe", "Careful Keith", "Dangerous Dave", "Scripted 1"}      # scripted car included
    assert all(r["races"] == 1 for r in table.values())
    winner = next(r for r in record["results"] if r["place"] == 1)
    assert winner["rating"][1] > winner["rating"][0]
    # Rated by racing alone: the four ratings stay centred on the standard.
    assert sum(r["rating"] for r in table.values()) / 4 == pytest.approx(1000, abs=1)


def test_scripted_cars_are_the_same_car_every_race(dirs):
    root = stable.STABLE_DIR
    ch = championship.start(root, [instant_racer(root, "Zoe")])
    first = championship.build_race(root, ch)
    scripted = next(d for d in first.drivers if d.label == "Scripted 1")
    assert scripted.livery == ch["entrants"][3]["livery"]
    skill, params = scripted.skill, scripted.car_params
    ch["races"].append({"track": "oval", "order": [3, 2, 1, 0], "results": []})     # the grid changes
    second = championship.build_race(root, ch)
    again = next(d for d in second.drivers if d.label == "Scripted 1")
    assert again.skill == skill and again.car_params == params
    assert second.slots.index(first.drivers.index(scripted)) is not None


def test_ratings_screen(app):
    from game.stable_screens import RatingsScreen, StableScreen
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    app.show(RatingsScreen(app))
    app.draw()
    assert app.current.rows == []                                           # nothing rated yet
    ch = championship.start(root, [zoe])
    race_ = championship.build_race(root, ch)
    race_.run(max_seconds=400)
    championship.finish_race(root, ch, race_)
    app.show(StableScreen(app))
    app.current.row = app.current.rows().index("ratings")
    press(app, pygame.K_RETURN)
    screen = app.current
    assert isinstance(screen, RatingsScreen) and len(screen.rows) == 4
    press(app, pygame.K_DOWN, pygame.K_UP)
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.current, StableScreen)
