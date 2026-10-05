#!/usr/bin/env python3
"""Over what distance does the rain move the same way? (report, Appendix B.3)

At every issue time of the main benchmark, individual rain features are tracked across the last four
scans (30 minutes) with pysteps' Lucas-Kanade method, returning its raw feature tracks before any
interpolation (at most one per 4 x 4 cells, about 13 km; no neighbour-based outlier filter, so nothing
makes nearby tracks agree). For every pair of tracks inside the scoring box, the squared difference of
their motion is added to a histogram by distance: the structure function D(r) = mean |v(x) - v(x + r)|^2.

D at the shortest distances is mostly measurement noise; its rise with distance is real variation in the
motion, and the distance where it levels off is how far the motion stays the same. (Small matched blocks
were tried first and rejected: on this grid their whole-cell matches scatter by tens of km/h, which is the
noise the block method's neighbour smoothing exists to hide.)

  python scripts/motion_coherence.py [--procs 10]          # results/motion-coherence.json, motion-tracks.jsonl
"""
import sys, json, argparse, datetime as dt
import multiprocessing as mp
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid
from nowcastlab.data import Archive, box_mask

DECL = 4                                 # at most one track per 4 x 4 cells
FD = dict(min_distance=3, quality_level=0.001)
BIN_KM, MAX_KM = 10.0, 400.0
NB = int(np.ceil(MAX_KM / BIN_KM))
SEASONS = {"Apr-May": (4, 5), "Jun-Jul": (6, 7), "Aug-Sep": (8, 9)}
_A = None
_BOX = None                              # the scoring box


def tracks(frames):
    """Feature tracks: positions (km, east and south) and motion (km/h, east and north)."""
    from pysteps.motion.lucaskanade import dense_lucaskanade
    from pysteps.utils import transformation
    rdb, _ = transformation.dB_transform(np.stack(frames).astype(np.float64), threshold=0.1, zerovalue=-15.0)
    try:
        xy, uv = dense_lucaskanade(rdb, dense=False, decl_scale=DECL, k_outlier=None, fd_kwargs=FD)
    except Exception:
        return None
    if len(xy) == 0:
        return None
    kmh = grid.KM * 60 / (_A.step / 60)
    col, row = xy[:, 0], xy[:, 1]
    inside = _BOX[np.clip(row.astype(int), 0, grid.ROWS - 1), np.clip(col.astype(int), 0, grid.COLS - 1)]
    return col[inside] * grid.KM, row[inside] * grid.KM, np.stack([uv[inside, 0] * kmh, -uv[inside, 1] * kmh], -1)


def work(i):
    frames = _A.frames(i, 4)
    if frames is None:
        return None
    t = tracks(frames)
    if t is None or len(t[0]) < 2:
        return None
    x, y, vv = t
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    dv2 = ((vv[:, None, :] - vv[None, :, :]) ** 2).sum(-1)
    iu = np.triu_indices(len(x), 1)
    d, dv2 = d[iu], dv2[iu]
    keep = d < MAX_KM
    idx = (d[keep] / BIN_KM).astype(int)
    s = np.bincount(idx, dv2[keep], NB)[:NB]
    n = np.bincount(idx, minlength=NB).astype(float)[:NB]
    month = dt.datetime.fromtimestamp(_A.time(i), dt.UTC).month
    spread = float(((vv - vv.mean(0)) ** 2).sum(-1).mean())     # variance of motion across tracks, this time
    track = dict(issue=int(_A.time(i)), x=np.round(x, 1).tolist(), y=np.round(y, 1).tolist(),
                 u=np.round(vv[:, 0], 2).tolist(), v=np.round(vv[:, 1], 2).tolist())
    return month, s, n, len(x), spread, track


def main():
    global _A, _BOX
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=10)
    a = ap.parse_args()
    _A = Archive()
    _BOX = box_mask()
    issues = sorted({(r["issue"] - _A.t0) // _A.step for r in map(json.loads, open(ROOT / "results" / "benchmark-10min.jsonl"))
                     if r["model"] == "persistence"})
    with mp.get_context("fork").Pool(a.procs) as pool:
        res = [r for r in pool.map(work, issues, chunksize=8) if r]
    out = dict(grid=grid.NAME, method="pysteps Lucas-Kanade feature tracks", decl_cells=DECL, bin_km=BIN_KM,
               issues=len(res), tracks_per_issue=float(np.mean([r[3] for r in res])),
               spread_kmh2=float(np.mean([r[4] for r in res])))

    def curve(sel):
        s = sum(r[1] for r in sel); n = sum(r[2] for r in sel)
        return dict(r_km=[(k + 0.5) * BIN_KM for k in range(NB)], D=[float(x) for x in np.where(n > 0, s / np.maximum(n, 1), np.nan)],
                    pairs=[int(x) for x in n], spread_kmh2=float(np.mean([r[4] for r in sel])))
    out["all"] = curve(res)
    out["seasons"] = {k: curve([r for r in res if r[0] in m]) for k, m in SEASONS.items()}
    with open(ROOT / "results" / f"motion-tracks{grid.SUFFIX}.jsonl", "w") as f:     # every track, for comparing with station winds
        for r in res:
            f.write(json.dumps(r[5]) + "\n")
    path = ROOT / "results" / f"motion-coherence{grid.SUFFIX}.json"
    path.write_text(json.dumps(out))
    D = np.array(out["all"]["D"])
    print(f"{len(res)} issues, {out['tracks_per_issue']:.0f} tracks each")
    for k in range(0, NB, 2):
        print(f"  {out['all']['r_km'][k]:5.0f} km: rms difference {np.sqrt(D[k]):5.1f} km/h  ({out['all']['pairs'][k]} pairs)")
    print("->", path)


if __name__ == "__main__":
    main()
