#!/usr/bin/env python3
"""Convert data/grids/*.npz to memory-mappable data/days/*.npy and (re)build data/index.npz.

Incremental: days already converted are skipped. Run after scripts/backfill.py.
Each day is a full 288-frame array on a regular 5-minute axis, NaN where a scan is missing
and, inside a scan, NaN where the radar had no data. The index holds each frame's wet
fraction over the covered part of the evaluation box (NaN for a missing scan).
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nowcastlab.data import DAY_DIR, INDEX, ROOT, PER_DAY, STEP, day_of, box_mask
from nowcastlab.radar import ROWS, COLS

DAY_DIR.mkdir(parents=True, exist_ok=True)
mask = box_mask()
idx = dict(np.load(INDEX)) if INDEX.exists() else {}
for f in sorted((ROOT / "grids").glob("2*.npz")):
    stem = f.stem
    out = DAY_DIR / f"{stem}.npy"
    if out.exists() and stem in idx:
        continue
    z = np.load(f)
    slot = np.round((z["times"] - day_of(stem)) / STEP).astype(int)
    keep = (slot >= 0) & (slot < PER_DAY)
    day = np.full((PER_DAY, ROWS, COLS), np.nan, np.float32)
    day[slot[keep]] = z["rate"][keep]
    np.save(out.with_suffix(".tmp.npy"), day)
    out.with_suffix(".tmp.npy").rename(out)
    box = day[:, mask]
    covered = np.isfinite(box).sum(axis=1)
    wet = ((box >= 0.1).sum(axis=1) / np.maximum(covered, 1)).astype(np.float32)
    wet[covered == 0] = np.nan
    idx[stem] = wet
    print(stem, int((~np.isnan(wet)).sum()), "frames", flush=True)
np.savez(INDEX, **idx)
print("index:", len(idx), "days")
