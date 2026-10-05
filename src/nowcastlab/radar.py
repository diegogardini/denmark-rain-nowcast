"""DMI radar composite (ODIM HDF5) -> rain-rate grids.

Mirrors legacy/js/helpers/dmi-radar-to-png (GDAL) so old and new grids are
comparable: raw uint8 -> dBZ (gain/offset) -> mm/h by the Marshall-Palmer pair
recorded in the file -> floor at 0.05 mm/h -> area average onto a WGS84 grid.

"No data" is not "dry". DMI's composite alternates two products: scans at
minutes divisible by 10 cover about 54% of the raster, the scans in between
(:05, :15, ...) only about 21%, with the rest flagged nodata (255). Nodata is
kept as NaN here, and grid cells without coverage are NaN, so a reduced scan
can never read as an absence of rain.
"""
from __future__ import annotations

import numpy as np
import h5py
from pyproj import Transformer
from scipy.ndimage import uniform_filter

# The map domain and the analysis grid (224 x 160 cells of about 3.2 km by default; see grid.py).
from .grid import BOUNDS, COLS, ROWS
RATE_FLOOR = 0.05
MIN_COVER = 0.5      # a grid cell needs this fraction of covered native pixels, else NaN


def _attr(group, key, default):
    if key not in group.attrs:
        return default
    v = group.attrs[key]
    v = np.asarray(v).ravel()[0]
    return v.decode() if isinstance(v, bytes) else v


def read_rate(path):
    """Returns (rate mm/h float32 array on the native grid, NaN where nodata; geo dict)."""
    with h5py.File(path, "r") as f:
        raw = f["dataset1/data1/data"][...]
        what = f["dataset1/data1/what"] if "dataset1/data1/what" in f else f["what"]
        gain = float(_attr(what, "gain", 0.5))
        offset = float(_attr(what, "offset", -32.0))
        nodata = int(_attr(what, "nodata", 255))
        zr_a = float(_attr(f["how"], "zr-a", 200.0)) if "how" in f else 200.0
        zr_b = float(_attr(f["how"], "zr-b", 1.6)) if "how" in f else 1.6
        w = f["where"]
        geo = dict(
            projdef=str(_attr(w, "projdef", "")),
            xscale=float(_attr(w, "xscale", 500)),
            yscale=float(_attr(w, "yscale", 500)),
            ul_lon=float(_attr(w, "UL_lon", 0)),
            ul_lat=float(_attr(w, "UL_lat", 0)),
        )
    dbz = raw.astype(np.float32) * gain + offset
    with np.errstate(over="ignore", invalid="ignore"):
        rate = (np.power(10.0, dbz / 10.0) / zr_a) ** (1.0 / zr_b)
    rate[~np.isfinite(rate)] = 0.0
    rate[rate < RATE_FLOOR] = 0.0
    rate[raw == nodata] = np.nan
    return rate.astype(np.float32), geo


def to_grid(rate, geo, bounds=BOUNDS, cols=COLS, rows=ROWS, mode="area"):
    """Resample the native grid onto a regular lon/lat grid (row 0 = north).

    mode="area":   mean rain rate over the covered pixels of the cell (dry pixels
                   count as 0); NaN where less than MIN_COVER of it is covered.
    mode="legacy": mean over the *raining* pixels only. This is what the
                   plugin's GDAL pipeline did (`-r average` skips the nodata
                   value 0), so a cell with one drizzle pixel reads as that
                   pixel's full rate. Kept for parity with the legacy grids
                   and verification data; it inflates the wet area. Nodata
                   reads as dry, as it did in GDAL.
    """
    tr = Transformer.from_crs("EPSG:4326", geo["projdef"], always_xy=True)
    x0, y0 = tr.transform(geo["ul_lon"], geo["ul_lat"])  # upper-left corner of the raster
    lon = bounds["west"] + (np.arange(cols) + 0.5) * (bounds["east"] - bounds["west"]) / cols
    lat = bounds["north"] - (np.arange(rows) + 0.5) * (bounds["north"] - bounds["south"]) / rows
    LON, LAT = np.meshgrid(lon, lat)
    X, Y = tr.transform(LON, LAT)
    # cell footprint in native pixels (~3.2 km / 0.5 km)
    cell_x = (bounds["east"] - bounds["west"]) / cols * 111.32 * np.cos(np.radians(56.0)) * 1000
    cell_y = (bounds["north"] - bounds["south"]) / rows * 111.32 * 1000
    k = max(1, int(np.ceil(min(cell_x / geo["xscale"], cell_y / geo["yscale"]))))
    covered = np.isfinite(rate)
    rate = np.where(covered, rate, 0.0).astype(np.float32)
    smooth = uniform_filter(rate, size=k, mode="constant", cval=0.0)
    if mode == "legacy":
        wet = uniform_filter((rate > 0).astype(np.float32), size=k, mode="constant", cval=0.0)
        smooth = np.where(wet > 0, smooth / np.maximum(wet, 1e-9), 0.0).astype(np.float32)
    elif mode == "area":
        cover = uniform_filter(covered.astype(np.float32), size=k, mode="constant", cval=0.0)
        smooth = np.where(cover >= MIN_COVER, smooth / np.maximum(cover, 1e-9), np.nan).astype(np.float32)
    else:
        raise ValueError(mode)
    ci = np.floor((X - x0) / geo["xscale"]).astype(int)
    ri = np.floor((y0 - Y) / geo["yscale"]).astype(int)
    inside = (ci >= 0) & (ci < rate.shape[1]) & (ri >= 0) & (ri < rate.shape[0])
    out = np.full((rows, cols), 0.0 if mode == "legacy" else np.nan, np.float32)
    out[inside] = smooth[ri[inside], ci[inside]]
    return out


def load_grid(path, **kw):
    rate, geo = read_rate(path)
    return to_grid(rate, geo, **kw)
