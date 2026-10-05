"""The Python models must reproduce the plugin's JS models on real scan pairs.

Fixture: tests/fixtures/js_parity.json.gz, made by scripts/make_parity_fixture.cjs
(gzip it afterwards). Four 5-minute scan pairs; per-block and global forecasts
at several leads, plus the block motion field.
"""
import gzip, json
from pathlib import Path
import numpy as np
import pytest
from nowcastlab import motion, models

FIX = Path(__file__).parent / "fixtures" / "js_parity.json.gz"
cases = json.load(gzip.open(FIX)) if FIX.exists() else []


def grids(c):
    shp = (c["rows"], c["cols"])
    return np.array(c["a"], np.float32).reshape(shp), np.array(c["b"], np.float32).reshape(shp)


@pytest.mark.parametrize("i", range(len(cases)))
def test_block_motion_matches_js(i):
    a, b = grids(cases[i])
    f = motion.compute_block_motion(a, b, 8, 6)
    ref = np.array(cases[i]["motion"]).reshape(f.conf.shape + (3,))
    assert np.abs(f.dx - ref[..., 0]).max() < 1e-9
    assert np.abs(f.dy - ref[..., 1]).max() < 1e-9
    assert np.abs(f.conf - ref[..., 2]).max() < 1e-6


@pytest.mark.parametrize("name", ["block", "global"])
@pytest.mark.parametrize("i", range(len(cases)))
def test_forecast_matches_js(i, name):
    a, b = grids(cases[i])
    out = models.make(name).forecast([a, b], 24)
    for k, ref in cases[i]["leads"].items():
        r = np.array(ref[name], np.float32).reshape(b.shape)
        got = out[int(k) - 1]
        assert np.abs(got - r).max() < 1e-3, f"pair {i} {name} lead {k}: {np.abs(got - r).max()}"
        assert abs(got.sum() / max(r.sum(), 1e-9) - 1) < 1e-4


SEQ = Path(__file__).parent / "fixtures" / "js_parity_seq.json.gz"
seq_cases = json.load(gzip.open(SEQ)) if SEQ.exists() else []


@pytest.mark.parametrize("i", range(len(seq_cases)))
def test_whole_map_vector_matches_widget_js(i):
    """The widget's whole-map vector over four scans (JS) and the report's 30-minute whole-map vector
    (global-windows, gw4) agree."""
    c = seq_cases[i]
    shp = (c["rows"], c["cols"])
    frames = [np.array(f, np.float32).reshape(shp) for f in c["frames"]]
    out = models.make("global-windows").forecast_multi(frames, 24)["gw4"]
    for k, ref in c["leads"].items():
        r = np.array(ref, np.float32).reshape(shp)
        assert np.abs(out[int(k) - 1] - r).max() < 1e-3, f"seq {i} lead {k}"


def test_subcell_matching_recovers_a_fractional_shift():
    """A smooth rain field moved by (1.4, -0.7) cells: whole-cell matches can only be whole numbers; the
    sub-cell refinement halves the error per block, and its median is close to the true shift."""
    from nowcastlab import motion as M
    yy, xx = np.mgrid[0:96, 0:96].astype(float)
    a = sum(np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * 6.0 ** 2)) * 5
            for x0, y0 in [(20, 30), (50, 45), (70, 20), (35, 70), (75, 75)])
    b = M.sample_bilinear(a, xx - 1.4, yy + 0.7)
    whole = M.compute_block_motion(a, b, 16, 4, smooth=False)
    sub = M.compute_block_motion(a, b, 16, 4, smooth=False, subcell=True)
    m = sub.conf > 0.2
    assert m.sum() >= 6
    err = lambda f: np.hypot(f.dx[m] - 1.4, f.dy[m] + 0.7).mean()
    assert err(sub) < 0.6 * err(whole)
    assert abs(np.median(sub.dx[m]) - 1.4) < 0.1 and abs(np.median(sub.dy[m]) + 0.7) < 0.1


def test_subcell_all_sees_a_shift_below_half_a_cell():
    """Moved by 0.4 cells, every whole-cell match is no shift (no confidence); subcell="all" recovers it."""
    from nowcastlab import motion as M
    yy, xx = np.mgrid[0:96, 0:96].astype(float)
    a = sum(np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * 6.0 ** 2)) * 5
            for x0, y0 in [(20, 30), (50, 45), (70, 20), (35, 70), (75, 75)])
    b = M.sample_bilinear(a, xx - 0.4, yy)
    whole = M.compute_block_motion(a, b, 16, 4, smooth=False)
    sub = M.compute_block_motion(a, b, 16, 4, smooth=False, subcell="all")
    m = sub.conf > 0.2
    assert (whole.conf > 0).sum() <= 6          # a few edge blocks aside, whole-cell matching sees no motion
    assert m.sum() >= 6 and abs(np.median(sub.dx[m]) - 0.4) < 0.1 and abs(np.median(sub.dy[m])) < 0.1


def test_block_windows_of_one_pair_is_block_matching():
    """bw2 (the latest pair only) must be exactly the block model."""
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:80, 0:112].astype(float)
    frames = []
    for k in range(4):
        f = sum(np.exp(-((xx - x0 - 1.3 * k) ** 2 + (yy - y0 - 0.6 * k) ** 2) / (2 * 5.0 ** 2)) * 4
                for x0, y0 in rng.uniform(10, 70, size=(8, 2)))
        frames.append(f.astype(np.float32))
    bw = models.make("block-windows", block=8, radius=6).forecast_multi(frames, 3)
    assert set(bw) == {"bw2", "bw4"}
    assert np.array_equal(bw["bw2"], models.make("block", block=8, radius=6).forecast(frames, 3))
