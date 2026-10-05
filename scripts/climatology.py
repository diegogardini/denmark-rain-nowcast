#!/usr/bin/env python3
"""Rain climatology of the archive, cell by cell, over all full-range scans (April to September 2026).

For every grid cell: how often it has at least 0.5 mm/h (wet frequency), the mean rain rate, and how often
it is wet while almost the whole map is dry (less than 0.5% of the scoring area wet). Real rain is rarely
alone on a dry map; a cell that is often wet then is a candidate for a fixed echo (clutter from buildings,
masts, wind turbines or the sea surface) rather than rain.

  python scripts/climatology.py [--procs 26]        # results/climatology.npz (+ .json summary)
"""
import sys, json, argparse
import multiprocessing as mp
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid
from nowcastlab.data import Archive, box_mask

_A = None
THR = 0.5
DRY_MAP = 0.005


def work(day):
    """Sums over one day's full-range scans."""
    A = _A
    n = np.zeros((grid.ROWS, grid.COLS)); wet = np.zeros_like(n); rate = np.zeros_like(n)
    n_dry = 0; wet_dry = np.zeros_like(n)
    for k in range(A.per_day):
        i = day * A.per_day + k
        if i >= len(A) or A.missing[i]:
            continue
        f = A.rate[i]
        ok = np.isfinite(f)
        g = np.where(ok, f, 0.0)
        n += ok; wet += (g >= THR) & ok; rate += g
        if np.nan_to_num(A.wet[i]) < DRY_MAP:
            n_dry += 1; wet_dry += (g >= THR) & ok
    return n, wet, rate, n_dry, wet_dry


def main():
    global _A
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--last", default="20260923", help="last day included (the benchmark period ends 2026-09-23)")
    a = ap.parse_args()
    stems = sorted(p.stem for p in (ROOT / "data" / "days").glob("2*.npy") if p.stem <= a.last)
    _A = Archive(days=stems)
    days = range(len(_A) // _A.per_day)
    with mp.get_context("fork").Pool(a.procs) as pool:
        parts = pool.map(work, days)
    n = sum(p[0] for p in parts); wet = sum(p[1] for p in parts); rate = sum(p[2] for p in parts)
    n_dry = sum(p[3] for p in parts); wet_dry = sum(p[4] for p in parts)
    freq = np.where(n > 0, wet / np.maximum(n, 1), np.nan)
    mean = np.where(n > 0, rate / np.maximum(n, 1), np.nan)
    freq_dry = wet_dry / max(n_dry, 1)
    np.savez_compressed(ROOT / "results" / "climatology.npz", wet_freq=freq.astype(np.float32), mean_rate=mean.astype(np.float32),
                        wet_freq_dry_map=freq_dry.astype(np.float32), scans=n.astype(np.int32))
    box = box_mask()
    summary = dict(scans=int(n.max()), dry_map_scans=int(n_dry), thr=THR, dry_map=DRY_MAP,
                   box_wet_freq_median=float(np.nanmedian(freq[box])), box_wet_freq_dry_map_p99=float(np.nanpercentile(freq_dry[box], 99)))
    (ROOT / "results" / "climatology.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
