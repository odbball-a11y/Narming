"""Track notes: per-corner notes that evolve with a brain and adjust what it sees."""
import json
import shutil

import numpy as np

from ai import brain, evolve, stable
from sim.track import Track


def graduate_vectors(count=2):
    with np.load(stable.GRADUATE.with_suffix(".npz")) as data:
        return data["pop"][:count].astype(np.float64)


def test_every_track_has_corners_covering_the_lap():
    for key in Track.available():
        corners = Track.load(key).corners()
        assert 2 <= corners["count"] <= 12
        assert set(corners["of"]) == set(range(corners["count"]))         # every sample belongs to a corner
        assert any(corners["exit"]) and not all(corners["exit"])


def test_zero_notes_drive_exactly_as_no_notes_and_real_notes_change_driving():
    arch = brain.with_notes(stable.graduate()["arch"])
    plain = graduate_vectors(1)
    noted = brain.fit_genomes(plain, arch)
    assert noted.shape[1] == brain.genome_size(arch) > brain.n_weights(arch)
    a = evolve.test_solo(noted, arch, "oval", seconds=8)
    b = evolve.test_solo(plain, stable.graduate()["arch"], "oval", seconds=8)
    assert a["laps"] == b["laps"]
    track = Track.load("oval")
    changed = noted.copy()
    k = brain.n_weights(arch) + sum(c * brain.NOTE_FIELDS for key, c, _ in arch["notes"] if key < "oval")
    changed[0, k:k + track.corners()["count"] * 3] = 0.9
    assert brain.notes_for(changed[0], arch, track)[0, 0] == 0.9
    c = evolve.test_solo(changed, arch, "oval", seconds=8)
    assert c["laps"] != a["laps"]


def test_notes_of_other_tracks_stay_frozen_while_training_one():
    arch = brain.with_notes(stable.graduate()["arch"])
    pop = brain.fit_genomes(graduate_vectors(4), arch)
    mask = brain.notes_mask(arch, ["oval"])
    children = evolve.breed(pop, np.random.default_rng(1), 20, 2, mask)
    assert np.allclose(children[:, mask], 0.0)                              # untouched
    oval = ~mask.copy()
    oval[:brain.n_weights(arch)] = False
    assert np.abs(children[:, oval]).sum() > 0                              # the trained track's notes move


def test_foals_get_each_corners_notes_from_one_parent():
    arch = brain.with_notes(stable.graduate()["arch"])
    a, b = brain.fit_genomes(graduate_vectors(2), arch)
    k = brain.n_weights(arch)
    a[k:], b[k:] = 0.5, -0.5
    child = stable.crossover(a, b, arch, np.random.default_rng(2))
    notes = child[k:].reshape(-1, brain.NOTE_FIELDS)
    for row in notes:
        assert np.allclose(row, 0.5, atol=0.1) or np.allclose(row, -0.5, atol=0.1)


def test_a_house_rival_learns_notes_without_changing_how_it_drives(tmp_path, monkeypatch):
    rivals = tmp_path / "rivals"
    shutil.copytree(stable.RIVALS_DIR, rivals)
    monkeypatch.setattr(stable, "RIVALS_DIR", rivals)
    monkeypatch.setattr(evolve, "RUNS_DIR", tmp_path / "runs")
    with np.load(rivals / "careful-keith.npz") as data:
        before = data["pop"][0].astype(np.float64)
    had = json.loads((rivals / "careful-keith.json").read_text()).get("notes_generations", 0)
    card = stable.house_notes("careful-keith", 1, tracks=["oval"], population=6)
    with np.load(rivals / "careful-keith.npz") as data:
        after = data["pop"][0].astype(np.float64)
    arch = card["arch"]
    assert arch["notes"] and card["notes_generations"] == had + 1
    k = brain.n_weights(arch)
    assert np.allclose(after[:k], before[:k], atol=1e-6)                    # the same driver
    assert len(after) == brain.genome_size(arch)
    assert json.loads((rivals / "careful-keith.json").read_text())["arch"]["notes"]
    driver = stable.house_driver("careful-keith")
    assert driver.arch.get("notes")
