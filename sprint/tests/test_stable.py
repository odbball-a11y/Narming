"""The racing stable: racers, personalities, training partners, upskilling,
careers, house rivals and the workshop, plus their screens."""
import shutil

import numpy as np
import pygame
import pytest

from ai import evolve, stable
from sim.driver import driver_types
from sim.race import FINISHED, Race


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """A private stable, workshop and house-rivals folder; the shipped
    graduate and rivals are copied in."""
    rivals = tmp_path / "rivals"
    shutil.copytree(stable.RIVALS_DIR, rivals)
    monkeypatch.setattr(stable, "RIVALS_DIR", rivals)
    monkeypatch.setattr(stable, "STABLE_DIR", tmp_path / "stable")
    monkeypatch.setattr(stable, "WORKSHOP_DIR", tmp_path / "workshop")
    return tmp_path


def quick_train(racer_dir, generations=None):
    """Train with a tiny population so tests stay fast."""
    if generations:
        racer = stable.load(racer_dir)
        racer["versions"][-1]["generations"] = generations
        stable.save(racer_dir, racer)
    stable.train(racer_dir, population=4)


def test_shipped_graduate_and_house_rivals():
    grad = stable.graduate()
    assert set(grad["tracks"]) == {"oval", "speedway", "esses", "technical", "grandprix"}
    with np.load(stable.GRADUATE.with_suffix(".npz")) as data:
        assert data["pop"].shape[1] == evolve.n_weights(grad["arch"])
    names = {r["name"] for r in stable.house_rivals()}
    assert {"Dangerous Dave", "Careful Keith"} <= names
    dave = stable.house_driver("dangerous-dave")
    assert dave.label == "Dangerous Dave"


def test_sliders_span_balanced_to_dave_and_keith():
    assert stable.sliders_to_weights(0, 0)["damage"] == 2.0
    dave = stable.sliders_to_weights(1, 0)
    keith = stable.sliders_to_weights(0, 1)
    for key in ("damage", "fault", "overtake", "draft", "place"):
        assert dave[key] == evolve.style_weights("aggressive")[key]
        assert keith[key] == evolve.style_weights("cautious")[key]
    middle = stable.sliders_to_weights(0.5, 0.5)
    assert 0 < middle["overtake"] < dave["overtake"]
    assert middle["damage"] > 0


def test_create_train_upskill_and_partners(dirs):
    root = stable.STABLE_DIR
    first = stable.create(root, "Speedy Sue", 0.8, 0.2, [{"name": "Scripted car", "kind": "scripted"}], 2)
    assert first.name == "speedy-sue" and stable.brain_file(first) is None
    assert stable.needs_training(first)
    # Before anything is trained, the only partners are scripted cars and itself.
    assert [p["kind"] for p in stable.partner_options(root)] == ["scripted", "self"]
    quick_train(first)
    assert stable.progress(first) == {"version": 1, "done": 2, "target": 2}
    config = evolve.load_config(first / "v1")
    assert config["race_weights"] == stable.sliders_to_weights(0.8, 0.2)
    assert config["parent"]["file"].endswith("graduate.npz") and config["phase2_start"] == 1
    # A trained racer becomes a training partner for the next one ...
    options = stable.partner_options(root)
    assert any(p["name"] == "Speedy Sue" for p in options)
    assert not any(p["key"].startswith("house:") for p in options)     # house rivals are race-only
    assert any(p["key"].startswith("house:") for p in stable.partner_options(root, include_house=True))
    second = stable.create(root, "Speedy Sue", 0.1, 0.9, [o for o in options if o["kind"] == "file"], 1)
    assert second.name == "speedy-sue-2"
    quick_train(second)
    scenarios = evolve.load_history(second / "v1")[0]["scenarios"]
    assert all(r == "p:0" for s in scenarios for r in s["rivals"])
    # Upskilling carries on from the current brain with a new personality.
    stable.upskill(first, 0.2, 0.9, [{"name": "Itself", "kind": "self"}], 1)
    assert stable.load(first)["caution"] == 0.9 and stable.progress(first)["version"] == 2
    quick_train(first)
    assert evolve.load_config(first / "v2")["parent"]["file"].endswith("v1/gen_0002.npz")
    assert [h["version"] for h in stable.history(first)] == [1, 1, 2]
    assert stable.brain_file(first).parent.name == "v2"
    with pytest.raises(ValueError):
        stable.create(root, "   ", 0, 0, [], 1)


def test_career_racing_and_registry(dirs):
    racer_dir = stable.create(stable.STABLE_DIR, "Racer X", 0.5, 0.5,
                              [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(racer_dir)
    keys = stable.register(stable.STABLE_DIR)
    assert "racer:racer-x" in keys and "house:dangerous-dave" in keys
    assert dict(driver_types())["racer:racer-x"] == "Racer X"
    driver = stable.champion(racer_dir)
    race = Race("speedway", [(0, driver), (1, stable.house_driver("careful-keith"))], laps=1, rolling=True)
    race.run(max_seconds=120)
    assert race.phase == FINISHED
    row = next(r for r in race.results() if r["car"] == 0)
    stable.record_result(racer_dir, row["place"], row["best_lap"], "speedway")
    stable.record_result(racer_dir, 1, 12.0, "speedway")
    career = stable.load(racer_dir)["career"]
    assert career["races"] == 2 and career["wins"] >= 1 and career["best_laps"]["speedway"] <= 12.0


def test_workshop_publishes_house_rivals(dirs):
    racer_dir = stable.create(stable.WORKSHOP_DIR, "The Professor", 0.4, 0.6,
                              [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(racer_dir)
    stable.publish(racer_dir)
    rival = next(r for r in stable.house_rivals() if r["id"] == "the-professor")
    assert rival["name"] == "The Professor" and rival["caution"] == 0.6 and rival["exam"]
    assert stable.house_driver("the-professor").label == "The Professor"


# ----------------------------------------------------------------- screens

@pytest.fixture
def app(dirs, monkeypatch):
    from game.app import App
    from game.audio import Audio
    pygame.display.init()
    pygame.font.init()
    a = App(pygame.display.set_mode((640, 360)), Audio())
    started = []

    def fake_start(racer_dir):                     # train in-process, tiny, instead of a subprocess
        started.append(racer_dir)
        quick_train(racer_dir, generations=1)

    monkeypatch.setattr(a, "start_training", fake_start)
    a.started = started
    return a


def press(app, *keys):
    for key in keys:
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))
        app.draw()


def type_text(app, text):
    for ch in text:
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))
    app.draw()


def test_create_a_racer_through_the_screens_then_race_it(app):
    from game.screens import MainMenu, RaceScreen
    from game.stable_screens import CreateScreen, RacerScreen, StableScreen
    app.show(MainMenu(app))
    press(app, pygame.K_DOWN, pygame.K_RETURN)
    assert isinstance(app.current, StableScreen)
    press(app, pygame.K_RETURN)                                  # + CREATE A RACER
    create = app.current
    assert isinstance(create, CreateScreen)
    assert [p["kind"] for p in create.partners] == ["scripted"]  # only scripted cars to start with
    press(app, *[pygame.K_DOWN] * create.rows().index("start"), pygame.K_RETURN)   # START, but no name
    assert "name" in create.message
    create.row = 0
    type_text(app, "Zippy Zoe!")
    press(app, pygame.K_BACKSPACE)
    assert create.name == "Zippy Zoe"
    press(app, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_RIGHT)    # aggression 0.3 -> 0.5
    press(app, pygame.K_DOWN, pygame.K_LEFT)                     # caution 0.3 -> 0.2
    assert (create.aggression, create.caution) == (0.5, 0.2)
    create.row = create.rows().index("start")
    press(app, pygame.K_RETURN)
    card = app.current
    assert isinstance(card, RacerScreen) and app.started
    racer = stable.load(card.racer_dir)
    assert racer["name"] == "Zippy Zoe" and racer["aggression"] == 0.5
    card.reload()
    app.draw()
    assert card.rows()[0] == "championship"
    press(app, pygame.K_RETURN)                                  # ENTER CHAMPIONSHIP
    from game.stable_screens import ChampionshipHub, ChampionshipSetupScreen, StandingsScreen
    setup = app.current
    assert isinstance(setup, ChampionshipSetupScreen) and setup.chosen == [card.racer_dir]
    setup.row = setup.rows().index("start")
    press(app, pygame.K_RETURN)
    assert isinstance(app.current, ChampionshipHub)
    press(app, pygame.K_RETURN)                                  # WATCH THE RACE
    view = app.current
    assert isinstance(view, RaceScreen) and view.race.rolling and view.on_continue
    assert {d.label for d in view.race.drivers} == {"Zippy Zoe", "Careful Keith", "Dangerous Dave", "Scripted 1"}
    while not view.over:
        view.tick()
    assert stable.load(card.racer_dir)["career"]["races"] == 1   # career recorded
    press(app, pygame.K_RETURN)                                  # CONTINUE
    assert isinstance(app.current, StandingsScreen)
    press(app, pygame.K_RETURN)                                  # on to the hub
    assert isinstance(app.current, ChampionshipHub)
    press(app, pygame.K_DOWN, pygame.K_RETURN)                   # SIMULATE THE RACE
    assert isinstance(app.current, StandingsScreen)
    assert stable.load(card.racer_dir)["career"]["races"] == 2
    app.show(RacerScreen(app, card.racer_dir))
    app.draw()
    press(app, pygame.K_DOWN, pygame.K_RETURN)                   # UPSKILL
    assert isinstance(app.current, CreateScreen) and app.current.racer_dir == card.racer_dir
    assert any(p["kind"] == "self" for p in app.current.partners)
    press(app, pygame.K_ESCAPE, pygame.K_ESCAPE)
    assert isinstance(app.current, StableScreen) and len(app.current.racers) == 1


def test_workshop_screen_can_train_against_and_publish_house_rivals(app):
    from game.stable_screens import CreateScreen, RacerScreen, StableScreen
    app.workshop = True
    app.show(StableScreen(app))
    press(app, pygame.K_RETURN)
    create = app.current
    assert any(p["key"] == "house:dangerous-dave" for p in create.partners)
    type_text(app, "Brick Wall")
    create.row = create.rows().index("start")
    press(app, pygame.K_RETURN)
    card = app.current
    assert isinstance(card, RacerScreen)
    assert str(stable.WORKSHOP_DIR) in str(card.racer_dir)
    card.row = card.rows().index("publish")
    press(app, pygame.K_RETURN)
    assert "house rival" in card.message
    assert any(r["name"] == "Brick Wall" for r in stable.house_rivals())


def test_training_runs_in_a_separate_process_and_can_be_stopped(dirs):
    from game.app import App
    from game.audio import Audio
    pygame.display.init()
    a = App(pygame.display.set_mode((320, 180)), Audio())
    racer_dir = stable.create(stable.STABLE_DIR, "Bg", 0.3, 0.3, [{"name": "Scripted car", "kind": "scripted"}], 1)
    a.start_training(racer_dir)
    assert a.training_dir() == str(racer_dir)
    with pytest.raises(RuntimeError):
        a.start_training(racer_dir)
    a.stop_training()
    assert a.training_dir() is None and (racer_dir / "train.log").exists()


# ------------------------------------------------------------------ breeding

def two_trained(root):
    p = [{"name": "Scripted car", "kind": "scripted"}]
    a = stable.create(root, "Bold Betty", 0.9, 0.1, p, 1)
    b = stable.create(root, "Steady Sam", 0.1, 0.9, p, 1)
    quick_train(a)
    quick_train(b)
    stable.retire(a)          # only racers at stud can breed
    stable.retire(b)
    return a, b


def small_breed(foal_dir):
    return stable.breed(foal_dir, litter=4, shortlist=2, camp_generations=1, camp_population=4)


def test_crossover_copies_whole_neurons_from_either_parent():
    from ai.brain import random_weights, unpack
    arch = stable.graduate()["arch"]
    rng = np.random.default_rng(0)
    a, b = random_weights(rng, 2, arch)
    child = stable.crossover(a, b, arch, rng)
    for (wa, ba), (wb, bb), (wc, bc) in zip(unpack(a, arch), unpack(b, arch), unpack(child, arch)):
        from_a = [np.allclose(wc[j], wa[j], atol=0.15) and abs(bc[j] - ba[j]) < 0.15 for j in range(len(bc))]
        from_b = [np.allclose(wc[j], wb[j], atol=0.15) and abs(bc[j] - bb[j]) < 0.15 for j in range(len(bc))]
        assert all(x or y for x, y in zip(from_a, from_b))        # every neuron is one parent's
        assert any(from_a) and any(from_b)                       # and both parents contribute


def test_mate_breed_and_certificate(dirs):
    root = stable.STABLE_DIR
    betty, sam = two_trained(root)
    with pytest.raises(ValueError):
        stable.mate(root, betty, betty, "Clone")
    foal = stable.mate(root, betty, sam, "Little Lucky", "learner")
    racer = stable.load(foal)
    assert racer["parents"] == ["bold-betty", "steady-sam"]
    assert 0.2 <= racer["aggression"] <= 0.8 and 0.2 <= racer["caution"] <= 0.8   # near the middle
    assert stable.is_breeding(foal) and stable.brain_file(foal) is None
    assert not stable.needs_training(foal)
    cert = small_breed(foal)
    assert not stable.is_breeding(foal) and stable.brain_file(foal) is not None
    assert not (foal / "litter").exists() and (foal / "foal.npz").exists()
    assert cert["litter"] == 4 and len(cert["candidates"]) == 2
    assert sum(c["chosen"] for c in cert["candidates"]) == 1
    assert cert["sire"]["name"] == "Bold Betty" and cert["dam"]["name"] == "Steady Sam"
    assert cert["criterion"] == "learner" and cert["target_pace"] > 0
    assert all("pace" in c for c in cert["candidates"])
    assert cert["expectations"] and all(isinstance(n, str) for n in cert["expectations"])
    assert stable.load(foal)["certificate"] == cert
    # The foal races, and can itself be upskilled and bred.
    assert stable.champion(foal).label == "Little Lucky"
    stable.upskill(foal, 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(foal)
    stable.retire(foal)
    grandchild = stable.mate(root, foal, betty, "Lucky Too")
    cert2 = small_breed(grandchild)
    assert cert2["grandparents"]["Little Lucky"] == ["Bold Betty", "Steady Sam"]
    assert any("relatives" in n for n in cert2["expectations"]) is False   # Betty is a founder: no shared parent


def test_same_parents_and_name_breed_the_same_foal(dirs):
    root = stable.STABLE_DIR
    betty, sam = two_trained(root)
    first = stable.mate(root, betty, sam, "Twin")
    c1 = small_breed(first)
    shutil.rmtree(first)
    for parent in (betty, sam):                    # undo the first litter's breeding count
        r = stable.load(parent)
        r["breedings"] = 0
        stable.save(parent, r)
    second = stable.mate(root, betty, sam, "Twin")
    c2 = small_breed(second)
    assert [c["foal"] for c in c1["candidates"]] == [c["foal"] for c in c2["candidates"]]
    assert c1["winner"]["foal"] == c2["winner"]["foal"]


def test_breed_through_the_screens(app, monkeypatch):
    from game.stable_screens import BreedScreen, CertificateScreen, RacerScreen, StableScreen
    root = stable.STABLE_DIR
    app.show(StableScreen(app))
    app.current.row = app.current.rows().index("breed")
    press(app, pygame.K_RETURN)
    assert isinstance(app.current, StableScreen)                 # not enough trained racers yet
    two_trained(root)
    bred = []
    monkeypatch.setattr(app, "start_breeding", lambda d: (bred.append(d), small_breed(d)))
    app.show(StableScreen(app))
    app.current.row = app.current.rows().index("breed")
    press(app, pygame.K_RETURN)
    screen = app.current
    assert isinstance(screen, BreedScreen)
    assert {stable.load(p)["name"] for p in screen.parents} == {"Bold Betty", "Steady Sam"}
    press(app, pygame.K_RIGHT)                                   # sire cycles but never equals the dam
    assert screen.sire != screen.dam
    screen.row = screen.ROWS.index("start")
    press(app, pygame.K_RETURN)
    assert "Name" in screen.message
    screen.row = screen.ROWS.index("name")
    type_text(app, "Little Lucky")
    screen.row = screen.ROWS.index("criterion")
    press(app, pygame.K_RIGHT)
    assert screen.criterion == "learner"
    screen.row = screen.ROWS.index("start")
    press(app, pygame.K_RETURN)
    card = app.current
    assert isinstance(card, RacerScreen) and bred
    card.reload()
    assert card.rows()[0] == "certificate"
    press(app, pygame.K_RETURN)
    assert isinstance(app.current, CertificateScreen)
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.current, RacerScreen)


def test_interrupted_breeding_can_be_resumed_from_the_card(app):
    from game.stable_screens import RacerScreen, status_text
    betty, sam = two_trained(stable.STABLE_DIR)
    foal = stable.mate(stable.STABLE_DIR, betty, sam, "Paused Pip")
    card = RacerScreen(app, foal)
    app.show(card)
    app.draw()
    assert card.rows() == ["resume_breeding", "back"]
    assert "PAUSED" in status_text(app, foal)[0]


# ------------------------------------------------------------------- careers

def test_career_ends_at_stud_after_the_race_limit(dirs, monkeypatch):
    monkeypatch.setattr(stable, "CAREER_RACES", 3)
    root = stable.STABLE_DIR
    racer = stable.create(root, "Short Career", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(racer)
    assert stable.can_race(racer) and not stable.can_breed(racer)
    news = []
    for k in range(3):
        news += stable.record_result(racer, 2, 12.5, "speedway")
    assert stable.status(racer) == "stud" and "retires to stud" in news[-1]
    assert stable.clock(root) == 3
    assert not stable.can_race(racer) and not stable.can_train(racer) and stable.can_breed(racer)
    assert stable.record_result(racer, 1, 11.0, "speedway") == []     # studs no longer race
    assert stable.load(racer)["career"]["races"] == 3
    with pytest.raises(ValueError):
        stable.upskill(racer, 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    assert "racer:short-career" not in stable.register(root)          # not offered for races


def test_studs_die_after_their_litters_or_of_old_age(dirs, monkeypatch):
    monkeypatch.setattr(stable, "STUD_BREEDINGS", 1)
    root = stable.STABLE_DIR
    betty, sam = two_trained(root)
    with pytest.raises(ValueError):
        stable.mate(root, stable.create(root, "Racing", 0.5, 0.5, [], 1), betty, "No")
    foal = stable.mate(root, betty, sam, "Last Foal")
    assert stable.load(betty)["breedings"] == 1
    small_breed(foal)
    assert stable.status(betty) == "dead" and stable.status(sam) == "dead"
    assert stable.load(betty)["death_cause"] == "after 1 litter"
    assert [d.name for d in stable.hall_of_fame(root)] == ["bold-betty", "steady-sam"]
    assert betty not in stable.list_racers(root)
    assert stable.offspring(root, "bold-betty") == ["Last Foal"]
    assert any(p["name"] == "Bold Betty" for p in stable.partner_options(root))   # legends still spar
    # Old age: a stud with no litters dies after STUD_LIFETIME stable races.
    monkeypatch.setattr(stable, "STUD_LIFETIME", 2)
    old = stable.create(root, "Old Timer", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(old)
    stable.retire(old)
    assert stable.stud_life_left(old) == 2
    stable.record_result(foal, 1, 12.0, "speedway")
    assert stable.status(old) == "stud"
    news = stable.record_result(foal, 1, 12.0, "speedway")
    assert stable.status(old) == "dead" and any("Old Timer" in n for n in news)
    assert "old age" in stable.load(old)["death_cause"]


def test_workshop_racers_have_no_career_limits(dirs, monkeypatch):
    monkeypatch.setattr(stable, "CAREER_RACES", 1)
    root = stable.WORKSHOP_DIR
    a = stable.create(root, "W One", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    b = stable.create(root, "W Two", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(a)
    quick_train(b)
    for _ in range(3):
        stable.record_result(a, 1, 12.0, "speedway")
    assert stable.status(a) == "racing" and stable.can_race(a) and stable.can_breed(a)
    foal = stable.mate(root, a, b, "W Foal")
    assert stable.load(a).get("breedings", 0) == 0 and foal.exists()


def test_career_screens(app, monkeypatch):
    from game.stable_screens import HallScreen, RacerScreen, StableScreen, status_text
    monkeypatch.setattr(stable, "STUD_BREEDINGS", 1)
    root = stable.STABLE_DIR
    racer = stable.create(root, "Retiree", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(racer)
    card = RacerScreen(app, racer)
    app.show(card)
    app.draw()
    assert "RACING" in status_text(app, racer)[0]
    assert "retire" in card.rows() and "championship" in card.rows()
    card.row = card.rows().index("retire")
    press(app, pygame.K_RETURN)
    assert stable.status(racer) == "stud" and "retires" in card.message
    assert card.rows() == ["training", "back"] and "AT STUD" in status_text(app, racer)[0]
    other = stable.create(root, "Mate", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(other)
    stable.retire(other)
    small_breed(stable.mate(root, racer, other, "Heir"))
    app.show(StableScreen(app))
    app.draw()
    assert "hall" in app.current.rows()
    app.current.row = app.current.rows().index("hall")
    press(app, pygame.K_RETURN)
    hall = app.current
    assert isinstance(hall, HallScreen) and len(hall.legends) == 2
    press(app, pygame.K_RETURN)
    assert isinstance(app.current, RacerScreen) and "HALL OF FAME" in status_text(app, racer)[0]
    press(app, pygame.K_ESCAPE)
    assert isinstance(app.current, HallScreen)


def test_race_news_appears_on_the_results_screen(app, monkeypatch):
    from game.stable_screens import RacerScreen
    monkeypatch.setattr(stable, "CAREER_RACES", 1)
    racer = stable.create(stable.STABLE_DIR, "One Race", 0.5, 0.5, [{"name": "Scripted car", "kind": "scripted"}], 1)
    quick_train(racer)
    card = RacerScreen(app, racer)
    app.show(card)
    card.race()
    view = app.current
    view.on_over = stable.record_race                      # a plain race counts for nothing; this one is scored
    while not view.over:
        view.tick()
    assert "retires to stud" in view.message
    assert stable.status(racer) == "stud"
