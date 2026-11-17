import json

import league


def test_promotion_and_relegation_swap_the_top_and_bottom_two():
    divs = [["a", "b", "c", "d", "e", "f"], ["g", "h", "i", "j", "k", "l"]]
    points = {k: 10 - n for n, k in enumerate("abcdefghijkl")}       # a best ... l worst within each division
    new, tables = league.promote_relegate(divs, points, {}, {})
    assert tables[0] == divs[0] and tables[1] == divs[1]
    assert set(new[0]) == {"a", "b", "c", "d", "g", "h"}               # e, f down; g, h up
    assert set(new[1]) == {"e", "f", "i", "j", "k", "l"}


def test_divisions_are_kept_between_seasons_and_new_cars_start_at_the_bottom():
    state = {"drivers": {k: {"mu": 25.0 + n} for n, k in enumerate("abcdefgh")},
             "divisions": [["a", "b", "c", "d", "e", "f"]]}
    divs = league.divisions_of(state, list("abcdefgh"))
    assert divs == [["a", "b", "c", "d", "e", "f", "g", "h"]]          # a tiny last division is merged
    first = league.divisions_of({"drivers": state["drivers"]}, list("abcdefghijkl")[:8])
    assert first[0][0] == "h"                                          # first time: by rating


def test_a_league_runs_seasons_and_marks_provisional_ratings(tmp_path, monkeypatch):
    def fake_race(job):                                               # the car listed first in "abc..." order wins
        track, keys, laps, seed = job
        order = sorted(keys)
        return track, [(k, order.index(k) + 1, True, 12.0) for k in keys]
    monkeypatch.setattr(league, "run_race", fake_race)
    entries = {k: {"name": k.upper(), "status": "x"} for k in "abcdefghijkl"}
    state = league.run_league(entries, rounds=3, laps=1, workers=1, save=tmp_path / "l.json", log=lambda m: None)
    assert state["round"] == 3 and len(state["seasons"]) == 3 and len(state["divisions"]) == 2
    assert {"a", "b"} <= set(state["divisions"][0])                    # the best stay at the top
    text = league.table(state)
    assert "Division 1" in text and "provisional" in text
    again = league.run_league(entries, rounds=4, laps=1, workers=1, save=tmp_path / "l.json", log=lambda m: None)
    assert again["round"] == 4                                        # resumes and adds a season
