import json
import os

import numpy as np
import pygame
import pytest

from ai import academy, assess, curriculum


def fake_car(root, cid, a, b, runs=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{cid}.json").write_text(json.dumps({"id": cid, "name": cid.title(), "kind": "house",
                                                  "runs": {"A": runs or a, "B": runs or b}}))


def solo_runs(pace, walls):
    return [["solo", t, {"pace": pace, "lap_cv": 0.01, "offtrack": 0.0, "walls": walls, "damage": 0.0, "minutes": 1.0}]
            for t in assess.TRACKS]


def test_measures_are_real_quantities_and_a_car_that_never_tries_is_not_praised():
    runs = [["overtake", "oval", {"passes": 0, "clean_passes": 0, "fault": 0, "reached": 0, "minutes": 1.0}]]
    m = assess.measures(runs)
    assert m["forced_passes"] is None and m["overtake_caused"] is None          # not measured, not a strength
    runs = [["overtake", "oval", {"passes": 2, "clean_passes": 1, "fault": 1, "reached": 2, "minutes": 1.0}]]
    m = assess.measures(runs)
    assert m["forced_passes"] == 0.5 and m["overtake_caused"] == 0.5


def test_field_scoring_needs_reliability_and_a_clear_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(assess, "OUT", tmp_path)
    paces = [0.90, 0.93, 0.96, 0.99, 1.02, 1.05]
    for k, p in enumerate(paces):                        # pace: the same in both runs (reliable)
        a, b = solo_runs(p, walls=k % 2), solo_runs(p + 0.001, walls=(k + 1) % 2)   # walls: A and B disagree
        fake_car(tmp_path, f"car{k}", a, b)
    f = assess.field()
    assert f["measures"]["pace"]["reliable"] and not f["measures"]["walls_per_min"]["reliable"]
    fastest = {r["key"]: r for r in f["report"]["car0"]["rows"]}
    slowest = {r["key"]: r for r in f["report"]["car5"]["rows"]}
    assert fastest["pace"]["tag"] == "strength" and fastest["pace"]["percentile"] == 1.0
    assert slowest["pace"]["tag"] == "weakness" and slowest["pace"]["percentile"] == 0.0
    assert fastest["walls_per_min"]["tag"] is None                                 # unreliable: never a verdict
    text = assess.report_text("car0")
    assert "Strengths:" in text and "lap pace" in text


def test_the_battery_runs_on_real_physics_and_the_screen_shows_it(tmp_path, monkeypatch):
    from ai import migrate
    migrate.ensure()
    monkeypatch.setattr(assess, "OUT", tmp_path)
    monkeypatch.setattr(academy, "ACADEMY_DIR", tmp_path / "academy")
    monkeypatch.setattr(curriculum, "ALL_TRACKS", ["oval"])
    monkeypatch.setattr(assess, "BATTERY", [("solo", "pace", assess._solo, ["oval", "national"]),
                                            ("overtake", "overtaking", assess._overtake, ["oval"]),
                                            ("race", "racing", assess._race, ["oval"])])
    monkeypatch.setattr(assess, "TRACKS", ["oval"])
    out = assess.assess("Careful Keith", workers=1, log=lambda m: None)
    assert set(out["measures"]) == {"A", "B"} and out["measures"]["A"]["pace"] > 0
    races = [r for r in out["runs"]["A"] if r[0] == "race"]
    assert races and races[0][2]["field"] == 6
    assess.field()
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from game.app import App
    from game.audio import Audio
    from game.scouting_screen import ScoutingScreen
    pygame.display.init()
    pygame.font.init()
    app = App(pygame.display.set_mode((960, 540)), Audio())
    view = ScoutingScreen(app, "careful-keith", "Careful Keith")
    app.show(view)
    app.draw()
    assert view.report and view.report["rows"]
    if os.environ.get("SHOT"):
        pygame.image.save(app.screen, os.environ["SHOT"])
