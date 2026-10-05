#!/usr/bin/env python3
"""What sets the speed of the whole-map vector? (report, Appendix B.4)

At every issue time of the main benchmark the whole-map vector is measured in several ways, and compared
with the motion of the rain's tracked features (results/motion-tracks.jsonl, from motion_coherence.py):

  smoothed   averaged from the per-block field as the block model uses it: neighbour smoothing, fill of
             empty blocks, and the shrink of blocks whose match confidence is below 0.3
  no-shrink  smoothed, without the shrink
  no-fill    smoothed, without filling empty blocks from their neighbours
  raw        none of the three: each block's own whole-cell match, weighted by its confidence (the model)
  raw-sub    raw, with each block's match refined to a fraction of a cell (a parabola through the
             mismatch at the best shift and its neighbours)
  raw-inner  raw, leaving out blocks within the search radius of missing radar data (coverage edges and
             gaps), where the fixed edge of the data favours no shift
  last-pair  raw, from the last scan pair only instead of the mean of the last three

Two tests:
  real       the last four scans, as forecast; speed ratio against the tracked motion. This mixes errors of the
             method with any bias of the tracks themselves.
  shifted    the last scan, moved by a known amount (the tracked motion, by bilinear sampling), and measured
             from that pair. Only the method's own error is left: no growth, decay or tracking error.

The ratio is the vector's component along the tracked direction divided by the tracked speed; the median over
issue times with at least 10 tracks is reported.

  python scripts/vector_speed.py [PROCS]      # results/vector-speed.json, vector-speed.jsonl
"""
import sys, json
import multiprocessing as mp
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_dilation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid, models, motion as M
from nowcastlab.data import Archive

R = ROOT / "results"
KMH = grid.KM * 6                         # cells per 10-minute step -> km/h
VARIANTS = ("smoothed", "no-shrink", "no-fill", "raw", "raw-sub", "raw-inner")
_A = None
_TR = None


def match(a, b, nodata, block=grid.BLOCK, radius=grid.RADIUS):
    """compute_block_motion without smoothing, also returning a sub-cell refinement and which blocks lie
    within the search radius of missing data."""
    f = M.compute_block_motion(a, b, block, radius, smooth=False)
    a, b = a.astype(np.float64), b.astype(np.float64)
    h, w = a.shape
    br, bc = f.conf.shape
    bp = np.pad(b, radius + 1, mode="edge")

    def block_ssd(r, c, dy, dx):
        r0, c0 = r * block, c * block
        aa = a[r0:r0 + block, c0:c0 + block]
        bb = bp[radius + 1 + dy + r0:radius + 1 + dy + r0 + aa.shape[0], radius + 1 + dx + c0:radius + 1 + dx + c0 + aa.shape[1]]
        return float(((aa - bb) ** 2).sum())

    sx, sy = f.dx.copy(), f.dy.copy()
    for r, c in zip(*np.nonzero(f.conf > 0)):
        dy, dx = int(f.dy[r, c]), int(f.dx[r, c])
        s0 = block_ssd(r, c, dy, dx)
        for axis in (0, 1):
            e = (0, 1) if axis else (1, 0)
            sm, sp = block_ssd(r, c, dy - e[0], dx - e[1]), block_ssd(r, c, dy + e[0], dx + e[1])
            den = sm - 2 * s0 + sp
            off = float(np.clip(0.5 * (sm - sp) / den, -0.5, 0.5)) if den > 0 else 0.0
            if axis:
                sx[r, c] += off
            else:
                sy[r, c] += off
    near = binary_dilation(nodata, iterations=radius) if nodata.any() else nodata
    p = np.zeros((br * block, bc * block), bool)
    p[:h, :w] = near
    edge = p.reshape(br, block, bc, block).any(axis=(1, 3))
    return f, sx, sy, edge


def weighted(dx, dy, conf, keep=None):
    m = conf > 0 if keep is None else (conf > 0) & keep
    if not m.any():
        return None
    return (float((dx[m] * conf[m]).sum() / conf[m].sum()), float((dy[m] * conf[m]).sum() / conf[m].sum()))


def pair(a, b, nodata):
    """The pair's vector under every variant, in cells per step (x east, y south)."""
    f, sx, sy, edge = match(a, b, nodata)
    smooth = M.smooth_block_motion(f, 2)
    return {"smoothed": M.global_vector(M.fill_motion_field(smooth)),
            "no-shrink": weighted(*(lambda g: (g.dx, g.dy, g.conf))(M.fill_motion_field(smooth))),
            "no-fill": M.global_vector(smooth),
            "raw": weighted(f.dx, f.dy, f.conf),
            "raw-sub": weighted(sx, sy, f.conf),
            "raw-inner": weighted(f.dx, f.dy, f.conf, ~edge)}


def mean(vs):
    vs = [v for v in vs if v is not None]
    return (float(np.mean([v[0] for v in vs])), float(np.mean([v[1] for v in vs]))) if vs else None


def kmh(v):
    return None if v is None else (v[0] * KMH, -v[1] * KMH)          # east and north, km/h


def work(i):
    fr = _A.frames(i, 4)
    t = _TR.get(int(_A.time(i)))
    if fr is None or t is None:
        return None
    nodata = [~np.isfinite(_A.rate[i - k]) for k in (3, 2, 1, 0)]
    pairs = [pair(fr[k], fr[k + 1], nodata[k] | nodata[k + 1]) for k in range(3)]
    real = {v: kmh(mean([p[v] for p in pairs])) for v in VARIANTS}
    real["last-pair"] = kmh(pairs[-1]["raw"])
    # the known shift: the tracked motion in cells per step, x east and y south
    d = (t[0] / KMH, -t[1] / KMH)
    a = fr[-1]
    rows, cols = np.mgrid[0:a.shape[0], 0:a.shape[1]].astype(float)
    b = M.sample_bilinear(a, cols - d[0], rows - d[1])
    shifted = {v: kmh(x) for v, x in pair(a, b, nodata[-1]).items()}
    return dict(issue=int(_A.time(i)), tracked=t, real=real, shifted=shifted)


def along(v, t):
    return None if v is None else (v[0] * t[0] + v[1] * t[1]) / (t[0] ** 2 + t[1] ** 2)


def main():
    global _A, _TR
    _TR = {}
    for tr in map(json.loads, open(R / "motion-tracks.jsonl")):
        if len(tr["u"]) >= 10:
            _TR[tr["issue"]] = (float(np.mean(tr["u"])), float(np.mean(tr["v"])))
    _A = Archive()
    issues = sorted({(r["issue"] - _A.t0) // _A.step for r in map(json.loads, open(R / "benchmark-10min.jsonl"))
                     if r["model"] == "persistence"})
    # check: "raw" is exactly the model's own vector, and "smoothed" that of global-windows-smoothed
    i = next(i for i in issues if _A.frames(i, 4) is not None and int(_A.time(i)) in _TR)
    own = kmh(models.GlobalWindows._mean(models.GlobalWindows().pair_vectors(_A.frames(i, 4))))
    sm = models.GlobalWindowsSmoothed()
    own_s = kmh(sm._mean(sm.pair_vectors(_A.frames(i, 4))))
    w = work(i)["real"]
    assert np.allclose(own, w["raw"]) and np.allclose(own_s, w["smoothed"]), (own, w["raw"], own_s, w["smoothed"])
    with mp.get_context("fork").Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 10) as pool:
        rows = [r for r in pool.map(work, issues, chunksize=4) if r]
    with open(R / "vector-speed.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = dict(n=len(rows), tracked_median_kmh=float(np.median([np.hypot(*r["tracked"]) for r in rows])))
    for test in ("real", "shifted"):
        out[test] = {}
        for v in rows[0][test]:
            a = np.array([x for r in rows if (x := along(r[test][v], r["tracked"])) is not None])
            out[test][v] = dict(median=float(np.median(a)), p25=float(np.percentile(a, 25)), p75=float(np.percentile(a, 75)), n=len(a))
    # the shifted test by speed: is the shortfall a fixed amount (whole-cell matching) or a fixed share?
    sp = np.array([np.hypot(*r["tracked"]) for r in rows])
    out["shifted_by_speed"] = {}
    for lo, hi in ((0, 25), (25, 40), (40, 55), (55, 200)):
        sel = [r for r, s in zip(rows, sp) if lo <= s < hi]
        out["shifted_by_speed"][f"{lo}-{hi}"] = {v: float(np.median([x for r in sel if (x := along(r["shifted"][v], r["tracked"])) is not None]))
                                                 for v in ("smoothed", "raw", "raw-sub")} | {"n": len(sel)}
    (R / "vector-speed.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
