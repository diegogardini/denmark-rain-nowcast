"""Legacy-mode grids must match the plugin's GDAL grid for the same scan."""
import json, os
import numpy as np
import pytest
from nowcastlab import radar

RAW = "data/raw/20260923/dk.com.202609232200.500_max.h5"
REF = "data/legacy/plugin-cache/frames/dk.com.202609232200.500_max.h5.nowcast-grid.json"


@pytest.mark.skipif(not (os.path.exists(RAW) and os.path.exists(REF)), reason="sample data missing")
def test_legacy_mode_matches_gdal():
    ref = json.load(open(REF))
    r = np.array(ref["values"], np.float32).reshape(ref["rows"], ref["cols"])
    rate, geo = radar.read_rate(RAW)
    g = radar.to_grid(rate, geo, mode="legacy")
    assert abs(g.sum() / r.sum() - 1) < 0.01
    assert np.corrcoef(g.ravel(), r.ravel())[0, 1] > 0.995
    assert abs((g > 0.1).sum() / (r > 0.1).sum() - 1) < 0.02


@pytest.mark.skipif(not os.path.exists(RAW), reason="sample data missing")
def test_area_mode_never_exceeds_legacy():
    rate, geo = radar.read_rate(RAW)
    area, legacy = radar.to_grid(rate, geo, mode="area"), radar.to_grid(rate, geo, mode="legacy")
    ok = np.isfinite(area)
    assert (area[ok] <= legacy[ok] + 1e-6).all()


FULL = "data/raw/20260704/dk.com.202607040000.500_max.h5"
REDUCED = "data/raw/20260704/dk.com.202607040005.500_max.h5"


@pytest.mark.skipif(not (os.path.exists(FULL) and os.path.exists(REDUCED)), reason="sample data missing")
def test_nodata_is_not_dry():
    """The :05 composite covers far less than the :00 one; uncovered cells must be NaN, not 0 mm/h."""
    from nowcastlab.data import box_mask
    box = box_mask()
    full, reduced = (radar.to_grid(*radar.read_rate(p)) for p in (FULL, REDUCED))
    assert np.isfinite(full[box]).mean() > 0.95
    assert np.isfinite(reduced[box]).mean() < 0.8
    assert np.isnan(radar.read_rate(REDUCED)[0]).mean() > 0.7


@pytest.mark.skipif(not os.path.exists("data/index.npz"), reason="archive not built")
def test_archive_uses_full_scans_every_10_minutes():
    from nowcastlab.data import Archive
    a = Archive(days=["20260704"])
    assert a.step == 600 and len(a) == 144
    assert all(a.time(i) % 600 == 0 for i in range(len(a)))
    fr = a.frames(10, 3)
    assert all(np.isfinite(f).all() for f in fr)


@pytest.mark.skipif(not os.path.exists("data/index.npz"), reason="archive not built")
def test_common_region_gives_every_5_minute_scan_the_same_footprint():
    from nowcastlab.data import Archive, common_coverage
    a = Archive(days=["20260704"], stride=1, region=common_coverage())
    assert a.step == 300
    feet = [np.isfinite(a.rate[i]) for i in range(100, 104)]
    assert all((f == feet[0]).all() for f in feet)
