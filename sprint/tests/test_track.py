import math

import numpy as np
import pytest

from sim.track import Track, wrap_angle

HUD_H = 11.0


@pytest.fixture(scope="module", params=Track.available())
def track(request):
    return Track.load(request.param)


def test_track_fits_the_screen_below_the_hud(track):
    x0, y0, x1, y1 = track.report()["bounds"]
    assert x0 >= 1.0 and x1 <= 159.0
    assert y0 >= HUD_H + 1.0 and y1 <= 89.0


def test_barriers_are_well_formed(track):
    report = track.report()
    # Barrier offset must be smaller than the corner radius everywhere,
    # otherwise the inside wall would fold over itself.
    assert report["max_limit_over_radius"] < 0.95
    # Different pieces of road never share a verge.
    assert report["min_gap_between_sections"] > 0.5


def test_uniform_sampling(track):
    seg = np.hypot(*(np.roll(track.center, -1, axis=0) - track.center).T)
    assert seg.max() / seg.min() < 1.05
    assert track.length == pytest.approx(seg.sum(), rel=1e-3)


def test_locate_on_and_off_the_centreline(track):
    for s in np.linspace(0, track.length, 37, endpoint=False):
        i = track.index_at(s)
        for lateral in (0.0, 2.0, -3.0):
            x = track.center[i, 0] + track.normal[i, 0] * lateral
            y = track.center[i, 1] + track.normal[i, 1] * lateral
            idx, prog, lat = track.locate(x, y)
            assert lat == pytest.approx(lateral, abs=0.15)
            diff = (prog - i * track.ds + track.length / 2) % track.length - track.length / 2
            assert abs(diff) < 0.6
            # The hinted (walking) search agrees with the global search.
            assert abs(track.nearest_index(x, y, hint=(i - 9) % track.n) - idx) <= 1


def test_progress_increases_round_the_lap(track):
    last = -1.0
    for i in range(0, track.n, 5):
        _, s, _ = track.locate(*track.center[i])
        assert s > last
        last = s


def test_heading_error_sign(track):
    s = 20.0
    h = track.heading_at(s)
    assert track.heading_error(h, s) == pytest.approx(0.0)
    assert track.heading_error(h + 0.3, s) == pytest.approx(0.3)    # pointing right
    assert track.heading_error(h - 0.3, s) == pytest.approx(-0.3)
    assert abs(wrap_angle(3 * math.pi)) == pytest.approx(math.pi)


def test_curvature_matches_turning(track):
    # Total turning over a closed lap is one full revolution.
    total = float(np.sum(track.curvature) * track.ds)
    assert abs(total) == pytest.approx(2 * math.pi, rel=0.02)
    # curvature_ahead looks the right distance down the road.
    assert track.curvature_ahead(10.0, 30.0) == track.curvature_at(40.0)


def test_raycasts_measure_distance_to_the_boundaries(track):
    i = track.index_at(5.0)                  # on the start straight
    x, y = track.center[i]
    h = track.heading[i]
    right, left = track.raycasts(x, y, [h + math.pi / 2, h - math.pi / 2])
    assert right == pytest.approx(track.limit[i], abs=0.3)
    assert left == pytest.approx(track.limit[i], abs=0.3)
    edge = track.raycast(x, y, h + math.pi / 2, boundary="tarmac")
    assert edge == pytest.approx(track.half_width[i], abs=0.3)
    ahead = track.raycast(x, y, h, max_dist=500.0)
    assert track.limit[i] < ahead < 500.0
    assert track.raycast(x, y, h, max_dist=3.0) == 3.0     # capped when nothing is hit


def test_checkpoints_and_grid(track):
    assert len(track.checkpoints) >= 8
    assert track.checkpoint_indices[0] == 0
    assert track.checkpoint_indices == sorted(track.checkpoint_indices)
    assert len(track.grid) == 4
    for x, y, heading in track.grid:
        idx, s, lat = track.locate(x, y)
        assert s > track.length / 2                    # behind the line
        assert abs(lat) < track.half_width[idx] - 1.5  # on the tarmac
        assert abs(track.heading_error(heading, s)) < 0.2
    # Grid slots do not overlap.
    for a in range(4):
        for b in range(a + 1, 4):
            assert math.dist(track.grid[a][:2], track.grid[b][:2]) > 3.6


def test_racing_line_defaults_to_centreline(track):
    assert np.allclose(track.racing_line, track.center)
    assert track.racing_line_point(12.0) == track.point_at(12.0)
