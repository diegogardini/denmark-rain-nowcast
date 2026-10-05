"""The radar archive as one regular time axis, loaded lazily.

By default the axis is 10 minutes and uses only the full-coverage scans (minutes
divisible by 10). DMI's scans in between cover far less of the map (see radar.py);
mixing the two makes every other scan look dry over the far range. stride=1 gives
the raw 5-minute axis with both kinds of scan.

Converted days live in data/days/YYYYMMDD.npy (288 x 160 x 224 float32, NaN for a
missing scan) and are memory-mapped, so a 6-month archive costs almost no RAM and
worker processes share the OS page cache. data/index.npz holds the per-frame
wet fraction of the evaluation box, so events can be found without touching the
frames. Build both with scripts/build_index.py.
"""
from __future__ import annotations

from pathlib import Path
import datetime as dt
import numpy as np

from .grid import COLS, ROWS, SUFFIX, lonlat

ROOT = Path(__file__).resolve().parents[2] / "data"
DAY_DIR = ROOT / f"days{SUFFIX}"            # one directory per grid (grid.py); days/ is the 3.2 km grid
INDEX = ROOT / f"index{SUFFIX}.npz"
STEP = 300             # spacing of the stored day files, not of the archive axis
PER_DAY = 288
DAY_SEC = 86400


def box_mask(west=8.0, east=15.3, south=54.3, north=58.0):
    """Boolean [ROWS, COLS] mask of the Denmark evaluation box (8-15.3E, 54.3-58N)."""
    LON, LAT = lonlat()
    return (LON >= west) & (LON < east) & (LAT >= south) & (LAT < north)


def day_of(stem):
    d = dt.datetime.strptime(stem, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


class _Rate:
    """Array-like over all frames: rate[i] -> [ROWS, COLS] float32 (all NaN = missing
    scan; NaN cells = no radar coverage)."""

    def __init__(self, archive):
        self.a = archive
        self.shape = (len(archive), ROWS, COLS)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return np.stack([self[j] for j in range(*i.indices(len(self.a)))])
        a = self.a
        if i < 0:
            i += len(a)
        d, k = divmod(i, a.per_day)
        k = k * a.stride // a.file_stride
        m = a.maps.get(d)
        if m is None:
            return np.full((ROWS, COLS), np.nan, np.float32)
        f = np.asarray(m[k])
        if a.region is not None:
            f = np.where(a.region, f, np.nan).astype(np.float32)
        return f


COMMON = ROOT / f"common_coverage{SUFFIX}.npy"
FIXED_ECHO = ROOT.parent / "results" / "fixed-echo-mask.npy"


def fixed_echo_mask():
    """Cells with a fixed radar echo (clutter), from scripts/fixed_echo_mask.py; True where masked. 3.2 km grid only."""
    m = np.load(FIXED_ECHO)
    if m.shape != (ROWS, COLS):
        raise ValueError(f"the fixed-echo mask is for the 3.2 km grid, not {ROWS} x {COLS}")
    return m


def region_named(name):
    """The regions an archive can be restricted to: common (both scan types cover it), clean (no fixed echoes)."""
    if name is None:
        return None
    if name == "common":
        return common_coverage()
    if name == "clean":
        return ~fixed_echo_mask()
    raise ValueError(name)


def common_coverage(day_dir=DAY_DIR, sample_days=("20260405", "20260615", "20260820", "20260920")):
    """Cells covered by BOTH kinds of DMI scan (full at :00/:10, reduced at :05/:15, ...):
    finite in at least 99% of the non-missing frames of a few sample days. Cached in data/."""
    if COMMON.exists():
        return np.load(COMMON)
    fin, n = 0, 0
    for s in sample_days:
        day = np.load(Path(day_dir) / f"{s}.npy", mmap_mode="r")
        for k in range(PER_DAY):
            f = np.asarray(day[k])
            if np.isfinite(f).any():
                fin = fin + np.isfinite(f); n += 1
    mask = fin / n >= 0.99
    np.save(COMMON, mask)
    return mask


class Archive:
    def __init__(self, days=None, day_dir=DAY_DIR, index=INDEX, stride=2, region=None):
        """stride=2: 10-minute axis of full-coverage scans (default). stride=1: every scan.
        region: optional boolean [ROWS, COLS]; cells outside it read as no coverage (NaN)
        in every frame, e.g. common_coverage() for a 5-minute axis with a fixed footprint."""
        stems = sorted(p.stem for p in Path(day_dir).glob("2*.npy"))
        if days:
            stems = [s for s in stems if s in set(days)]
        first = day_of(stems[0])
        self.t0 = first
        self.stride = stride
        self.region = region
        self.step = STEP * stride                  # seconds between frames on this axis
        self.per_day = PER_DAY // stride
        n_days = (day_of(stems[-1]) - first) // DAY_SEC + 1
        self.maps = {(day_of(s) - first) // DAY_SEC: np.load(Path(day_dir) / f"{s}.npy", mmap_mode="r") for s in stems}
        # A day file holds every scan (288) or, for the finer grids, only the full-range ones (144).
        self.file_stride = PER_DAY // next(iter(self.maps.values())).shape[0]
        if stride % self.file_stride:
            raise ValueError(f"these day files hold every {self.file_stride * 5} min; stride {stride} is not available")
        self.n = n_days * self.per_day
        idx = np.load(index)
        self.wet = np.full(self.n, np.nan, np.float32)
        for s in stems:
            d = (day_of(s) - first) // DAY_SEC
            self.wet[d * self.per_day:(d + 1) * self.per_day] = idx[s][::stride // self.file_stride]
        self.missing = np.isnan(self.wet)
        self.rate = _Rate(self)

    def __len__(self):
        return self.n

    def time(self, i):
        return self.t0 + i * self.step

    def frames(self, i, n=2):
        """The n frames ending at index i (oldest first), or None if any is missing.
        Cells without radar coverage are returned as 0 (models need finite input);
        scoring uses rate[] and skips them."""
        if i - n + 1 < 0 or self.missing[i - n + 1:i + 1].any():
            return None
        return [np.nan_to_num(self.rate[j], nan=0.0) for j in range(i - n + 1, i + 1)]
