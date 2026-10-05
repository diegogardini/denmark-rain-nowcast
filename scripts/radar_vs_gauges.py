#!/usr/bin/env python3
"""Radar against rain gauges (report, Appendix A.4).

For every DMI rain gauge and every hour of the archive, the gauge's rain in the hour (results/gauges.json, from
fetch_gauges.py) is set against the radar's: the mean rain rate in the station's 3.2 km grid cell over the six
full-range scans of that hour (10 to 60 minutes before the time stamp, and the time stamp itself), in mm. Hours
with a missing scan or no radar data at the station are left out. Also the same over the 3 x 3 cells around it.

Gauges whose season total is less than half the median of their three nearest gauges' are left out as faulty
(a check that does not use the radar). Reported: the ratio of total amounts (radar over gauge), the hour-by-hour correlation, detection of rainy hours
(at least 0.5 mm) with the gauge as the truth, by distance from the nearest radar, per station, and the hours in
which the radar shows rain over a gauge that stays dry (fixed echoes, Appendix A.3).

  python scripts/radar_vs_gauges.py      # results/radar-vs-gauges.json
"""
import sys, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid
from nowcastlab.data import Archive

R = ROOT / "results"
WET = 0.5            # mm in the hour


def scores(g, r):
    g, r = np.asarray(g), np.asarray(r)
    G, Rw = g >= WET, r >= WET
    hit, miss, fa = int((G & Rw).sum()), int((G & ~Rw).sum()), int((~G & Rw).sum())
    return dict(hours=int(len(g)), gauge_mm=float(g.sum()), radar_mm=float(r.sum()),
                ratio=float(r.sum() / g.sum()) if g.sum() > 0 else None,
                corr=float(np.corrcoef(g, r)[0, 1]) if len(g) > 2 and g.std() > 0 and r.std() > 0 else None,
                wet_gauge=int(G.sum()), pod=hit / max(hit + miss, 1), far=fa / max(hit + fa, 1), csi=hit / max(hit + miss + fa, 1),
                radar_wet_gauge_dry=int((Rw & (g == 0)).sum()))


def main():
    gz = json.loads((R / "gauges.json").read_text())
    ids = sorted(gz["stations"])
    cells = {s: grid.cell_of(gz["stations"][s][1], gz["stations"][s][0]) for s in ids}
    ids = [s for s in ids if 1 <= cells[s][0] < grid.ROWS - 1 and 1 <= cells[s][1] < grid.COLS - 1]
    dist = grid.radar_distance()
    mask = np.load(R / "fixed-echo-mask.npy")
    A = Archive()
    pairs = {s: [[], [], []] for s in ids}          # gauge mm, radar mm (cell), radar mm (3 x 3)
    for key, o in gz["obs"].items():
        t = int(key)
        j = (t - A.t0) // A.step
        idx = [j - k for k in range(6)]
        if idx[-1] < 0 or j >= len(A) or any(A.missing[i] for i in idx):
            continue
        frames = [A.rate[i] for i in idx]
        for s in ids:
            if s not in o:
                continue
            r0, c0 = cells[s]
            cell = [f[r0, c0] for f in frames]
            box = [np.nanmean(f[r0 - 1:r0 + 2, c0 - 1:c0 + 2]) if np.isfinite(f[r0 - 1:r0 + 2, c0 - 1:c0 + 2]).any() else np.nan for f in frames]
            if not (np.all(np.isfinite(cell)) and np.all(np.isfinite(box))):
                continue
            pairs[s][0].append(o[s]); pairs[s][1].append(float(np.mean(cell))); pairs[s][2].append(float(np.mean(box)))
    out = {"stations": {}, "all": {}, "bands": {}}
    for s in ids:
        if len(pairs[s][0]) < 100:
            continue
        r0, c0 = cells[s]
        out["stations"][s] = dict(lon=gz["stations"][s][0], lat=gz["stations"][s][1], radar_km=float(dist[r0, c0]),
                                  fixed_echo=bool(mask[r0 - 1:r0 + 2, c0 - 1:c0 + 2].any()),
                                  cell=scores(pairs[s][0], pairs[s][1]), box=scores(pairs[s][0], pairs[s][2]))
    # quality control without the radar: a gauge far below its neighbours is faulty (stuck, blocked, misreported)
    ok = list(out["stations"])
    lat = {s: out["stations"][s]["lat"] for s in ok}; lon = {s: out["stations"][s]["lon"] for s in ok}
    km = lambda a, b: np.hypot((lat[a] - lat[b]) * 111.2, (lon[a] - lon[b]) * 111.2 * np.cos(np.radians(56)))
    for s in ok:
        near = sorted((t for t in ok if t != s), key=lambda t: km(s, t))[:3]
        ref = float(np.median([out["stations"][t]["cell"]["gauge_mm"] for t in near]))
        out["stations"][s]["neighbour_mm"] = ref
        out["stations"][s]["faulty"] = bool(out["stations"][s]["cell"]["gauge_mm"] < 0.5 * ref)
    out["faulty"] = [s for s in ok if out["stations"][s]["faulty"]]
    out["gauges_total"] = len(ok)
    use = [s for s in ok if not out["stations"][s]["faulty"]]
    # by nearest radar
    out["by_radar"] = {}
    for name, (rla, rlo) in grid.RADARS.items():
        ss = [s for s in use if min(grid.RADARS, key=lambda n: np.hypot(grid.RADARS[n][0] - lat[s], (grid.RADARS[n][1] - lon[s]) * 0.56)) == name]
        if ss:
            out["by_radar"][name] = dict(stations=len(ss), **scores(np.concatenate([pairs[t][0] for t in ss]), np.concatenate([pairs[t][1] for t in ss])))
    cat = lambda k, ss: np.concatenate([pairs[s][k] for s in ss])
    for area, k in (("cell", 1), ("box", 2)):
        out["all"][area] = scores(cat(0, use), cat(k, use))
        clean = [s for s in use if not out["stations"][s]["fixed_echo"]]
        out["all"][area + "_without_fixed_echoes"] = scores(cat(0, clean), cat(k, clean))
    for band, (lo, hi) in grid.BANDS.items():
        ss = [s for s in use if lo <= out["stations"][s]["radar_km"] < hi]
        if ss:
            out["bands"][band] = dict(stations=len(ss), **scores(cat(0, ss), cat(1, ss)))
    (R / "radar-vs-gauges.json").write_text(json.dumps(out, indent=1))
    a = out["all"]["cell"]
    print(f"{len(use)} gauges, {a['hours']} station-hours: radar/gauge {a['ratio']:.2f}, corr {a['corr']:.2f}, "
          f"POD {a['pod']:.2f} FAR {a['far']:.2f} CSI {a['csi']:.2f}")
    for k in ("cell_without_fixed_echoes", "box", "box_without_fixed_echoes"):
        b = out["all"][k]
        print(f"  {k}: ratio {b['ratio']:.2f} corr {b['corr']:.2f} CSI {b['csi']:.2f}")
    for band, b in out["bands"].items():
        print(f"  {band}: {b['stations']} gauges, ratio {b['ratio']:.2f}, corr {b['corr']:.2f}, CSI {b['csi']:.2f}")
    print("  left out as faulty:", out["faulty"])
    for name, b in out["by_radar"].items():
        print(f"  nearest radar {name}: {b['stations']} gauges, ratio {b['ratio']:.2f}, corr {b['corr']:.2f}, CSI {b['csi']:.2f}")
    for s in use:
        x = out["stations"][s]
        if x["fixed_echo"]:
            print(f"  near a fixed echo: {s} {x['lat']:.2f}N {x['lon']:.2f}E ratio {x['cell']['ratio']:.2f}, radar wet over a dry gauge {x['cell']['radar_wet_gauge_dry']} h")


if __name__ == "__main__":
    main()
