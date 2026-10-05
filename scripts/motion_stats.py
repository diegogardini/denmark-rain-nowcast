#!/usr/bin/env python3
"""How rain moves over Denmark: the whole-map motion vector (30 min of history) at every issue time of
the main benchmark, and how much it has changed one and three hours later.

  python scripts/motion_stats.py [PROCS] [clean]    # results/motion-stats.json, motion-vectors.jsonl ("-clean" without fixed echoes)
"""
import sys, json, math
import multiprocessing as mp
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import models, grid, motion as M
from nowcastlab.data import Archive, region_named

_A = None
KMH = grid.KM * 6          # cells per 10-minute step -> km/h


def vector(i, smoothed=False):
    """The whole-map vector over the last 30 minutes, km/h east and north. smoothed=True averages the smoothed
    and filled per-block field instead of each block's own match (report, Appendix B.4)."""
    fr = _A.frames(i, 4)
    if fr is None:
        return None
    m = models.GlobalWindowsSmoothed() if smoothed else models.GlobalWindows()
    v = m._mean(m.pair_vectors(fr))
    return (v[0] * KMH, -v[1] * KMH)      # east and north components, km/h


def work(i):
    return i, vector(i), vector(i + 6), vector(i + 18), vector(i, smoothed=True)


def main():
    global _A
    clean = len(sys.argv) > 2 and sys.argv[2] == "clean"
    _A = Archive(region=region_named("clean") if clean else None)
    tag = "-clean" if clean else ""
    issues = sorted({(r["issue"] - _A.t0) // _A.step for r in map(json.loads, open(ROOT / "results" / "benchmark-10min.jsonl"))
                     if r["model"] == "persistence"})
    with mp.get_context("fork").Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 10) as pool:
        rows = pool.map(work, issues, chunksize=8)
    now = [(u, v) for _, a, _, _, _ in rows if a for u, v in [a]]
    speed = np.array([math.hypot(u, v) for u, v in now])
    toward = np.array([(math.degrees(math.atan2(u, v)) + 360) % 360 for u, v in now])   # direction moved toward, from north
    ch1 = np.array([math.hypot(b[0] - a[0], b[1] - a[1]) for _, a, b, _, _ in rows if a and b])
    ch3 = np.array([math.hypot(c[0] - a[0], c[1] - a[1]) for _, a, _, c, _ in rows if a and c])
    sectors = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    share = {s: float(np.mean(((toward + 22.5) // 45 % 8) == k)) for k, s in enumerate(sectors)}
    out = dict(n=len(now), speed_kmh=dict(zip(("p25", "median", "p75", "p90"), map(float, np.percentile(speed, [25, 50, 75, 90])))),
               toward_share=share,
               change_1h_kmh=dict(zip(("p25", "median", "p75"), map(float, np.percentile(ch1, [25, 50, 75])))),
               change_3h_kmh=dict(zip(("p25", "median", "p75"), map(float, np.percentile(ch3, [25, 50, 75])))))
    (ROOT / "results" / f"motion-stats{tag}.json").write_text(json.dumps(out, indent=1))
    with open(ROOT / "results" / f"motion-vectors{tag}.jsonl", "w") as f:          # per issue time, for the speed-bias check
        for i, a, _, _, u in rows:
            if a:
                f.write(json.dumps(dict(issue=int(_A.time(i)), model=a, smoothed=u)) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
