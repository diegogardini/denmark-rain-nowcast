#!/usr/bin/env python3
"""Numbers for the three follow-up checks in the report, from existing results (light; no forecasting).

1. The rain deficit at the cities (section 5.6, Appendix A.3): the ratio city by city, and the fixed echo at Copenhagen
   (results/climatology.npz, from scripts/climatology.py).
2. Is the whole-map vector too slow (Appendix B.4)? Its speed against the rain's tracked speed
   (results/motion-vectors.jsonl, results/motion-tracks.jsonl).
3. Why the finer grid helps most far from the radars (Appendix B.2): what the distance bands contain.

  python scripts/explain_checks.py          # results/explain-checks.json
"""
import sys, json, math
from pathlib import Path
import numpy as np
from matplotlib.path import Path as MPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from nowcastlab import grid
from nowcastlab.data import box_mask
import run_cities

R = ROOT / "results"


def main():
    out = {}
    # 1. cities
    rows = [r for r in map(json.loads, open(R / "cities.jsonl")) if r["hour"] == 1]
    ratio = lambda rs, m: sum(r[m] for r in rs) / sum(r["obs"] for r in rs)
    out["city_ratio"] = {c: {m: ratio([r for r in rows if r["city"] == c], m) for m in ("persistence", "block", "gw4", "pysteps-lk")}
                         for c in run_cities.CITIES}
    rest = [r for r in rows if r["city"] != "Copenhagen"]
    out["ratio_without_copenhagen"] = {m: ratio(rest, m) for m in ("persistence", "block", "gw4", "pysteps-lk")}
    c = np.load(R / "climatology.npz")
    f, m, fd = c["wet_freq"], c["mean_rate"], c["wet_freq_dry_map"]
    box = box_mask()
    r0, c0 = grid.cell_of(*run_cities.CITIES["Copenhagen"])
    ring = np.ones((21, 21), bool); ring[7:14, 7:14] = False
    out["copenhagen"] = dict(mean_rate=float(m[r0 - 1:r0 + 2, c0 - 1:c0 + 2].mean()),
                             mean_rate_around=float(np.nanmean(m[r0 - 10:r0 + 11, c0 - 10:c0 + 11][ring])),
                             wet_on_dry_map_max=float(fd[r0 - 1:r0 + 2, c0 - 1:c0 + 2].max()),
                             box_wet_on_dry_map_p99=float(np.nanpercentile(fd[box], 99)))
    # 2. speed of the whole-map vector
    tr = {}
    for line in open(R / "motion-tracks.jsonl"):
        t = json.loads(line)
        if len(t["u"]) >= 10:
            tr[t["issue"]] = (float(np.mean(t["u"])), float(np.mean(t["v"])))
    pairs = [(tr[v["issue"]], v["model"], v["smoothed"]) for v in map(json.loads, open(R / "motion-vectors.jsonl"))
             if v["issue"] in tr and v["smoothed"]]
    lk = np.array([math.hypot(*a) for a, _, _ in pairs]); gm = np.array([math.hypot(*b) for _, b, _ in pairs])
    gu = np.array([math.hypot(*u) for _, _, u in pairs])
    out["speed"] = dict(n=len(pairs), tracked_median=float(np.median(lk)), vector_median=float(np.median(gm)),
                        ratio_median=float(np.median(gm / lk)), ratio_smoothed=float(np.median(gu / lk)),
                        by_speed={f"{lo}-{hi}": float(np.median(gm[(lk >= lo) & (lk < hi)] / lk[(lk >= lo) & (lk < hi)]))
                                  for lo, hi in ((0, 25), (25, 40), (40, 55), (55, 200))})
    # 3. the distance bands
    coast = json.loads((ROOT / "scripts" / "coast.json").read_text())
    LON, LAT = grid.lonlat(); pts = np.c_[LON.ravel(), LAT.ravel()]
    land = np.zeros(LON.size, bool)
    for ring_ in coast["denmark"] + [x for n in coast["neighbours"] for x in n["rings"]]:
        land |= MPath(np.asarray(ring_)).contains_points(pts)
    land = land.reshape(LON.shape)
    dist = grid.radar_distance()
    tracks = {k: 0 for k in grid.BANDS}
    for line in open(R / "motion-tracks.jsonl"):
        t = json.loads(line)
        for x, y in zip(t["x"], t["y"]):
            d = dist[min(int(y / grid.KM), grid.ROWS - 1), min(int(x / grid.KM), grid.COLS - 1)]
            for k, (lo, hi) in grid.BANDS.items():
                if lo <= d < hi:
                    tracks[k] += 1
    out["bands"] = {}
    for k, (lo, hi) in grid.BANDS.items():
        b = box & (dist >= lo) & (dist < hi) & np.isfinite(f)
        out["bands"][k] = dict(sea=float((~land[b]).mean()), wet_freq=float(np.nanmean(f[b])),
                               rain_when_wet=float(np.nanmean(m[b]) / np.nanmean(f[b])),
                               fixed_echo_cells=int((fd[b] > 0.01).sum()), tracks_per_1000_cells=1000 * tracks[k] / b.sum() / 1649)
    (R / "explain-checks.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
