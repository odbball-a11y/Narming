"""Liveries and championships: colours, points, the reverse grid, careers,
and the screens that play a season."""
import numpy as np
import pygame
import pytest

from ai import championship, livery, stable
from sim.race import Race
from sim.replay import Recording

from test_stable import press


def instant_racer(root, name, aggression=0.5, caution=0.3, traits=None):
    """A racer with a ready brain (copied from the graduate), no training."""
    racer = stable.create(root, name, aggression, caution, [{"name": "Scripted car", "kind": "scripted"}],
                          1, traits=traits)
    run = racer / "v1"
    run.mkdir()
    with np.load(stable.GRADUATE.with_suffix(".npz")) as data:
        np.savez_compressed(run / "gen_0001.npz", pop=data["pop"][:2], fitness=np.zeros(2))
    (run / "config.json").write_text("{}")
    return racer


# ------------------------------------------------------------------ liveries

def test_house_rivals_have_their_fixed_colours(dirs):
    rivals = {r["name"]: r for r in stable.house_rivals()}
    assert rivals["Dangerous Dave"]["livery"]["colour"] == "red"
    assert rivals["Careful Keith"]["livery"]["colour"] == "green"
    assert stable.house_driver("dangerous-dave").livery["colour"] == "red"


def test_new_racers_get_unique_colours_never_red_or_green(dirs):
    root = stable.STABLE_DIR
    seen = []
    for k in range(7):
        racer = instant_racer(root, f"Racer {k}")
        look = stable.livery_of(racer)
        assert look["colour"] not in livery.RESERVED
        assert look["colour"] not in [s["colour"] for s in seen]
        assert look["number"] not in [s["number"] for s in seen] + [5, 13]
        seen.append(look)
    assert {s["trim"] for s in seen} == set(livery.TRIMS)            # the trims vary too
    ninth = stable.livery_of(instant_racer(root, "Racer 8"))
    assert ninth["colour"] in livery.ORDER and ninth["number"] not in [s["number"] for s in seen]


def test_older_racers_without_a_livery_get_one_in_order(dirs):
    root = stable.STABLE_DIR
    old = instant_racer(root, "Old Timer")
    racer = stable.load(old)
    del racer["livery"]
    stable.save(old, racer)
    assert stable.livery_of(old)["colour"] in livery.ORDER
    assert stable.load(old)["livery"] == stable.livery_of(old)       # saved, so it never changes


def test_foal_has_a_family_look():
    sire = {"colour": "blue", "trim": "nose", "trim_colour": "white", "number": 10}
    dam = {"colour": "yellow", "trim": "wing", "trim_colour": "dark", "number": 11}
    foal = livery.inherit(sire, dam, [sire, dam])
    assert foal["colour"] not in ("blue", "yellow")                   # its own colour
    assert foal["trim_colour"] == "blue" and foal["trim"] == "wing"    # sire's colour, dam's trim
    assert foal["number"] not in (10, 11)


def test_bred_foal_gets_its_look_from_its_parents(dirs):
    root = stable.STABLE_DIR
    a, b = instant_racer(root, "Sire"), instant_racer(root, "Dam")
    for d in (a, b):
        stable.retire(d)
    foal = stable.mate(root, a, b, "Foal")
    look, sire = stable.load(foal)["livery"], stable.livery_of(a)
    assert look["trim_colour"] == sire["colour"] and look["trim"] == stable.livery_of(b)["trim"]


def test_cars_without_a_livery_never_take_a_liveried_cars_colour(dirs):
    dave = stable.house_driver("dangerous-dave")
    race = Race("oval", [(0, dave), (1, "scripted"), (2, "scripted"), (3, "scripted")], laps=1, rolling=True)
    looks = livery.resolve(race.drivers, race.slots)
    assert looks[0]["colour"] == "red"
    assert len({lk["colour"] for lk in looks}) == 4                   # no two cars alike
    assert "red" not in [lk["colour"] for lk in looks[1:]]


def test_replays_keep_liveries_and_each_cars_own_physics(dirs):
    keith, dave = stable.house_driver("careful-keith"), stable.house_driver("dangerous-dave")
    heavy = stable.house_driver("dangerous-dave")
    heavy.car_params = stable.cartraits.params_for(dict(stable.cartraits.default(), weight="heavy"))
    race = Race("oval", [(0, keith), (1, heavy), (2, "scripted")], laps=1, rolling=True).run(max_seconds=90)
    recording = Recording.from_race(race)
    assert [lk["colour"] for lk in recording.liveries[:2]] == ["green", "red"]
    assert recording.car_params[1]["mass"] > 1 and recording.car_params[2] is None
    replay = recording.make_race()
    assert replay.drivers[0].livery["colour"] == "green"
    assert replay.world.cars[1].params.mass == recording.car_params[1]["mass"]
    assert replay.run(max_seconds=90).final_hash == race.final_hash   # a trait car replays exactly now


# -------------------------------------------------------------- championship

def test_a_season_has_five_races_the_right_points_and_a_reverse_grid(dirs):
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    ch = championship.start(root, [zoe])
    assert [e["name"] for e in ch["entrants"]][:3] == ["Zoe", "Careful Keith", "Dangerous Dave"]
    assert ch["entrants"][3]["kind"] == "scripted" and ch["entrants"][3]["livery"]["colour"] not in ("red", "green")
    assert ch["tracks"] == ["oval", "speedway", "esses", "technical", "grandprix"]
    with pytest.raises(ValueError):
        championship.start(root, [zoe])                                # one at a time
    first_grid = championship.grid(ch, 0)
    assert sorted(first_grid) == [0, 1, 2, 3] and first_grid == championship.grid(ch, 0)   # drawn, but fixed
    for k in range(5):
        nxt = championship.next_race(ch)
        assert nxt["number"] == k + 1 and nxt["track"] == championship.TRACK_ORDER[k]
        if k:                                                          # the leader starts last
            table = championship.standings(ch)
            assert nxt["grid"][-1] == table[0]["entrant"] and nxt["grid"][0] == table[-1]["entrant"]
        race = championship.build_race(root, ch)
        assert race.rolling and race.laps == race.track.default_laps
        assert [d.label for d in race.drivers] == [ch["entrants"][e]["name"] for e in nxt["grid"]]
        race.run(max_seconds=400)
        record = championship.finish_race(root, ch, race)
        for res in record["results"]:
            base = championship.POINTS[res["place"] - 1] if res["finished"] else 0
            assert res["points"] == base + (1 if res["fastest"] else 0)
        assert sum(r["fastest"] for r in record["results"]) <= 1
    assert championship.active(root) is None and ch["done"]            # filed away
    assert (championship.seasons_dir(root) / "season_001.json").exists()
    table = championship.standings(ch)
    assert [r["position"] for r in table] == [1, 2, 3, 4]
    assert table[0]["points"] >= table[1]["points"] >= table[2]["points"] >= table[3]["points"]
    assert ch["champion"] == table[0]["entrant"] and "champion" in ch["news"][0]
    assert stable.load(zoe)["career"]["races"] == 5                    # careers counted, once per race
    assert stable.clock(root) == 5


def test_did_not_finish_scores_nothing_and_fastest_lap_needs_a_finish(dirs):
    root = stable.STABLE_DIR
    ch = championship.start(root, [instant_racer(root, "Zoe")])
    race = championship.build_race(root, ch)
    race.run(max_seconds=400)

    class Fake:
        track = race.track
        world = race.world
        drivers = race.drivers

        def results(self):
            rows = race.results()
            rows[-1] = dict(rows[-1], finished=False, time=None, best_lap=min(r["best_lap"] for r in rows) - 1)
            return rows

    record = championship.finish_race(root, ch, Fake())
    dnf = next(r for r in record["results"] if not r["finished"])
    assert dnf["points"] == 0 and not dnf["fastest"]


def test_standings_tie_break_and_places_gained(dirs):
    ch = {"entrants": [{"name": n} for n in "ABCD"], "tracks": ["oval"] * 3, "races": []}

    def race(order, points):
        ch["races"].append({"results": [{"entrant": e, "place": i + 1, "finished": True, "points": p}
                                        for i, (e, p) in enumerate(zip(order, points))]})

    race([0, 1, 2, 3], [10, 7, 5, 3])
    race([1, 0, 3, 2], [10, 7, 5, 3])
    table = championship.standings(ch)
    assert [r["entrant"] for r in table][:2] == [0, 1]                 # 17 each: A and B, A first: more podiums...
    race([2, 1, 0, 3], [10, 7, 5, 3])
    table = championship.standings(ch)
    assert table[0]["entrant"] == 1 and table[0]["moved"] == 1 and table[1]["entrant"] == 0 \
        and table[1]["moved"] == -1


def test_career_limit_mid_season_waits_for_the_end(dirs, monkeypatch):
    monkeypatch.setattr(stable, "CAREER_RACES", 3)
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    ch = championship.start(root, [zoe])
    for k in range(5):
        race = championship.build_race(root, ch)
        race.run(max_seconds=400)
        championship.finish_race(root, ch, race)
        if k < 4:
            assert stable.status(zoe) == "racing"                      # still racing after reaching the limit
    assert stable.status(zoe) == "stud"
    assert any("retires" in n for n in ch["news"])


def test_titles_are_counted(dirs):
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe", traits={"top_speed": 5, "accel": 4, "handling": 2, "braking": 1,
                                             "weight": "light"})
    ch = championship.start(root, [zoe])
    ch["tracks"] = ["oval"]                                            # a one-race season, to be quick
    championship._write(championship.path(root), ch)
    race = championship.build_race(root, ch)
    race.run(max_seconds=200)
    championship.finish_race(root, ch, race)
    champion = ch["entrants"][ch["champion"]]
    assert (stable.load(zoe)["career"].get("titles", 0) == 1) == (champion["id"] == "zoe")


# ------------------------------------------------------------------ screens

def test_play_a_season_through_the_screens(app):
    from game.screens import RaceScreen
    from game.stable_screens import (ChampionshipHub, ChampionshipSetupScreen, StableScreen,
                                     StandingsScreen)
    root = stable.STABLE_DIR
    racers = [instant_racer(root, name) for name in ("Ann", "Ben", "Cal")]
    app.show(StableScreen(app))
    app.current.row = app.current.rows().index("championship")
    press(app, pygame.K_RETURN)
    setup = app.current
    assert isinstance(setup, ChampionshipSetupScreen)
    press(app, pygame.K_RETURN)                                        # tick Ann
    press(app, pygame.K_DOWN, pygame.K_RETURN)                         # and Ben
    press(app, pygame.K_DOWN, pygame.K_RETURN)                         # a third is refused
    assert len(setup.chosen) == 2 and "At most" in setup.message
    assert [f["kind"] for f in setup.field()] == ["yours", "yours", "house rival", "house rival"]
    setup.row = setup.rows().index("start")
    press(app, pygame.K_RETURN)
    hub = app.current
    assert isinstance(hub, ChampionshipHub) and hub.next["number"] == 1
    # Quit a watched race half way: nothing is recorded and the race is still to come.
    press(app, pygame.K_RETURN)
    view = app.current
    assert isinstance(view, RaceScreen) and view.pause_items == ["RESUME", "QUIT RACE"]
    for _ in range(200):
        app.update(1 / 60)
    press(app, pygame.K_ESCAPE, pygame.K_DOWN, pygame.K_RETURN)        # QUIT RACE
    hub = app.current
    assert isinstance(hub, ChampionshipHub) and len(hub.ch["races"]) == 0
    assert championship.active(root)["races"] == []
    # Simulate the whole season from the hub.
    for k in range(5):
        hub = app.current
        assert isinstance(hub, ChampionshipHub) and hub.next["number"] == k + 1
        hub.row = hub.ROWS.index("sim")
        press(app, pygame.K_RETURN)
        standing = app.current
        assert isinstance(standing, StandingsScreen) and standing.k == k
        app.draw()
        press(app, pygame.K_RETURN)
    assert isinstance(app.current, StableScreen)                       # the season is over
    assert championship.active(root) is None
    ann, ben, cal = racers
    assert stable.load(ann)["career"]["races"] == 5 and stable.load(ben)["career"]["races"] == 5
    assert stable.load(cal)["career"]["races"] == 0                    # not entered
    assert stable.clock(root) == 5


def test_abandoning_needs_a_second_press_and_the_season_resumes(app):
    from game.stable_screens import ChampionshipHub, StableScreen
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    championship.start(root, [zoe])
    app.show(ChampionshipHub(app))
    app.current.row = app.current.ROWS.index("abandon")
    press(app, pygame.K_RETURN)
    assert championship.active(root) is not None and app.current.confirm
    press(app, pygame.K_ESCAPE)                                        # leaving keeps the season
    assert isinstance(app.current, StableScreen) and championship.active(root)
    app.show(ChampionshipHub(app))                                     # resumed
    app.current.row = app.current.ROWS.index("abandon")
    press(app, pygame.K_RETURN, pygame.K_RETURN)
    assert championship.active(root) is None and isinstance(app.current, StableScreen)


def test_stable_screens_show_liveries_and_titles(app):
    from game.stable_screens import RacerScreen, StableScreen
    root = stable.STABLE_DIR
    zoe = instant_racer(root, "Zoe")
    racer = stable.load(zoe)
    racer["career"]["titles"] = 2
    stable.save(zoe, racer)
    for screen in (StableScreen(app), RacerScreen(app, zoe)):
        app.show(screen)
        app.draw()
    assert RacerScreen(app, zoe).rows()[0] == "championship"
