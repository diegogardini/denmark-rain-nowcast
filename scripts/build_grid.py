#!/usr/bin/env python3
"""Build the archive on a finer grid directly from the raw DMI files.

  NOWCAST_GRID=2km python scripts/build_grid.py [--procs 26]
  NOWCAST_GRID=1km python scripts/build_grid.py

Writes data/days-<grid>/YYYYMMDD.npy and data/index-<grid>.npz. Unlike the 3.2 km archive
(scripts/backfill.py --regrid, then scripts/build_index.py), only the full-range scans are kept,
144 a day, 10 minutes apart: the doppler scans in between cover too little of the map for this
benchmark (report, section 2.1), and dropping them halves the size (about 9 GB at 2 km, 37 GB at 1 km).
Missing scans are NaN, and so are cells without radar data, as on the 3.2 km grid. Safe to re-run:
days already built are skipped.
"""
import sys, argparse, datetime as dt
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid, radar
from nowcastlab.data import DAY_DIR, INDEX, ROOT as DATA, box_mask

FRAMES = 144                 # full-range scans per day, at minutes divisible by 10


def build_day(stem):
    out = DAY_DIR / f"{stem}.npy"
    if out.exists():
        return stem, None
    day = np.full((FRAMES, grid.ROWS, grid.COLS), np.nan, np.float32)
    for p in sorted((DATA / "raw" / stem).glob("*.h5")):
        t = dt.datetime.strptime(p.name.split(".")[2], "%Y%m%d%H%M")
        if t.minute % 10:
            continue                                   # a doppler scan
        k = (t.hour * 60 + t.minute) // 10
        rate, geo = radar.read_rate(p)
        day[k] = radar.to_grid(rate, geo, mode="area")
    tmp = out.with_suffix(".tmp.npy")
    np.save(tmp, day)
    tmp.rename(out)
    box = day[:, box_mask()]
    covered = np.isfinite(box).sum(axis=1)
    wet = ((box >= 0.1).sum(axis=1) / np.maximum(covered, 1)).astype(np.float32)
    wet[covered == 0] = np.nan
    return stem, wet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=26)
    a = ap.parse_args()
    if grid.NAME == "3.2km":
        sys.exit("set NOWCAST_GRID=2km or 1km; the 3.2 km archive is built by backfill.py --regrid and build_index.py")
    DAY_DIR.mkdir(parents=True, exist_ok=True)
    stems = sorted(p.name for p in (DATA / "raw").iterdir() if p.is_dir())
    idx = dict(np.load(INDEX)) if INDEX.exists() else {}
    print(f"grid {grid.NAME}: {grid.COLS} x {grid.ROWS} cells of {grid.KM:.2f} km, {len(stems)} days -> {DAY_DIR}", flush=True)
    with ProcessPoolExecutor(a.procs) as ex:
        for stem, wet in ex.map(build_day, stems):
            if wet is not None:
                idx[stem] = wet
            print(stem, "built" if wet is not None else "skipped", flush=True)
    missing = [s for s in stems if s not in idx]          # days built by an earlier run: index them
    for s in missing:
        day = np.load(DAY_DIR / f"{s}.npy", mmap_mode="r")
        box = np.asarray(day)[:, box_mask()]
        covered = np.isfinite(box).sum(axis=1)
        w = ((box >= 0.1).sum(axis=1) / np.maximum(covered, 1)).astype(np.float32)
        w[covered == 0] = np.nan
        idx[s] = w
    np.savez(INDEX, **idx)
    print("index:", len(idx), "days ->", INDEX)


if __name__ == "__main__":
    main()
