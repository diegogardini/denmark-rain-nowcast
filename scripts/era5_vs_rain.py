#!/usr/bin/env python3
"""Winds at cloud height (ERA5) against the rain's own motion (report, Appendix B.3).

For every issue time, the rain's motion is taken from the Lucas-Kanade feature tracks (results/motion-tracks.jsonl)
and the wind from ERA5 at 850, 700, 500 and 300 hPa (data/era5, from fetch_era5.py), interpolated to the
track's position (bilinear, 0.25 degree grid) and to the issue time (linear between hours). "layer" is the mean
of the four levels, a simple stand-in for the mean wind of the cloud layer (Appendix B.3).

Compared, with the conventions of station_vs_rain.py: the wind's speed over the rain's, the turn from the rain's
direction to the wind's (positive = anticlockwise), and the size of the vector difference; per issue time for the
map as a whole (mean of the tracks against the mean wind at the same places), and per track. Also the whole-map
vector (results/motion-vectors.jsonl) against the layer wind, and the structure function of the ERA5 wind by
distance, to set beside those of the tracks and the ground stations.

  python scripts/era5_vs_rain.py        # results/era5-vs-rain.json
"""
import sys, json, math, glob
from pathlib import Path
import numpy as np
import h5py

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid

R = ROOT / "results"
LEVELS = ["850", "700", "500", "300", "layer"]
MIN_SPEED = 10.0          # km/h, as for the stations


def load_era5():
    ts, us, vs = [], [], []
    for f in sorted(glob.glob(str(ROOT / "data" / "era5" / "era5-*.nc"))):
        h = h5py.File(f)
        lat, lon = np.asarray(h["latitude"]), np.asarray(h["longitude"])
        lev = [str(int(x)) for x in np.asarray(h["pressure_level"])]
        order = [lev.index(l) for l in LEVELS[:-1]]
        ts.append(np.asarray(h["valid_time"]).astype(np.int64))
        us.append(np.asarray(h["u"])[:, order] * 3.6)            # km/h, toward east
        vs.append(np.asarray(h["v"])[:, order] * 3.6)            # km/h, toward north
    t = np.concatenate(ts); u = np.concatenate(us); v = np.concatenate(vs)
    s = np.argsort(t)
    u, v = u[s], v[s]
    u = np.concatenate([u, u.mean(1, keepdims=True)], 1)         # add the layer mean
    v = np.concatenate([v, v.mean(1, keepdims=True)], 1)
    if lat[0] > lat[-1]:
        lat, u, v = lat[::-1], u[..., ::-1, :], v[..., ::-1, :]
    return t[s], lat, lon, u, v


def at_time(T, U, V, t):
    """Wind fields [level, lat, lon] at time t (linear between hours), or None."""
    k = np.searchsorted(T, t)
    if k == 0 or k >= len(T):
        return None if k >= len(T) or T[0] != t else (U[0], V[0])
    w = (t - T[k - 1]) / (T[k] - T[k - 1])
    return U[k - 1] * (1 - w) + U[k] * w, V[k - 1] * (1 - w) + V[k] * w


def bilinear(F, lat, lon, la, lo):
    """F[..., lat, lon] at points (la, lo)."""
    i = np.clip(np.searchsorted(lat, la) - 1, 0, len(lat) - 2); j = np.clip(np.searchsorted(lon, lo) - 1, 0, len(lon) - 2)
    a = (la - lat[i]) / (lat[i + 1] - lat[i]); b = (lo - lon[j]) / (lon[j + 1] - lon[j])
    return (F[..., i, j] * (1 - a) * (1 - b) + F[..., i + 1, j] * a * (1 - b)
            + F[..., i, j + 1] * (1 - a) * b + F[..., i + 1, j + 1] * a * b)


def compare(ru, rv, wu, wv):
    """Speed ratio, turn (deg, positive = wind anticlockwise of the rain) and |difference|, where the rain moves."""
    rs = np.hypot(ru, rv); ok = rs >= MIN_SPEED
    ratio = np.hypot(wu, wv)[ok] / rs[ok]
    turn = np.degrees(np.arctan2(ru * wv - rv * wu, ru * wu + rv * wv))[ok]
    diff = np.hypot(wu - ru, wv - rv)[ok]
    return ratio, turn, diff


def summary(ratio, turn, diff):
    q = lambda x: dict(zip(("p25", "median", "p75"), map(float, np.percentile(x, [25, 50, 75]))))
    return dict(n=int(len(ratio)), speed_ratio=q(ratio), turn_deg=q(turn), turn_within_30=float(np.mean(np.abs(turn) <= 30)),
                diff_kmh=q(diff))


def main():
    T, lat, lon, U, V = load_era5()
    west, north = grid.BOUNDS["west"], grid.BOUNDS["north"]
    kx = (grid.BOUNDS["east"] - west) / (grid.COLS * grid.KM)      # degrees per km, east
    ky = (north - grid.BOUNDS["south"]) / (grid.ROWS * grid.KM)     # degrees per km, south
    per_issue = {l: [[], [], [], []] for l in LEVELS}              # rain u, rain v, wind u, wind v
    per_track = {l: [[], [], [], []] for l in LEVELS}
    layer_at = {}
    for line in open(R / "motion-tracks.jsonl"):
        t = json.loads(line)
        if len(t["u"]) < 10:
            continue
        f = at_time(T, U, V, t["issue"])
        if f is None:
            continue
        x, y, u, v = map(np.array, (t["x"], t["y"], t["u"], t["v"]))
        la, lo = north - y * ky, west + x * kx
        wu, wv = bilinear(f[0], lat, lon, la, lo), bilinear(f[1], lat, lon, la, lo)    # [level, track]
        for k, l in enumerate(LEVELS):
            for acc, vals in ((per_track[l], (u, v, wu[k], wv[k])), (per_issue[l], (u.mean(), v.mean(), wu[k].mean(), wv[k].mean()))):
                for a, b in zip(acc, vals):
                    a.append(b)
        layer_at[t["issue"]] = (float(wu[-1].mean()), float(wv[-1].mean()))
    out = {"levels": LEVELS, "map": {}, "track": {}}
    for l in LEVELS:
        out["map"][l] = summary(*compare(*map(np.array, per_issue[l])))
        out["track"][l] = summary(*compare(*(np.concatenate([np.atleast_1d(x) for x in a]) for a in per_track[l])))
    # the whole-map vector against the layer wind at the same issue times
    vec = {r["issue"]: r["model"] for r in map(json.loads, open(R / "motion-vectors.jsonl")) if r["model"]}
    common = [i for i in vec if i in layer_at]
    out["whole_map_vector"] = summary(*compare(np.array([vec[i][0] for i in common]), np.array([vec[i][1] for i in common]),
                                               np.array([layer_at[i][0] for i in common]), np.array([layer_at[i][1] for i in common])))
    # structure function of the ERA5 wind (700 hPa and layer) inside the scoring box, at the issue times
    box = (lat[:, None] >= 54.3) & (lat[:, None] <= 58.0) & (lon[None, :] >= 8.0) & (lon[None, :] <= 15.3)
    LA, LO = np.meshgrid(lat, lon, indexing="ij"); la, lo = np.radians(LA[box]), np.radians(LO[box])
    D = 2 * 6371 * np.arcsin(np.sqrt(np.sin((la[:, None] - la[None, :]) / 2) ** 2
                                     + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin((lo[:, None] - lo[None, :]) / 2) ** 2))
    iu = np.triu_indices(len(la), 1); B, nb = 20.0, 20
    kbin = (D[iu] / B).astype(int); keep = kbin < nb
    sf = {}
    for k, l in ((1, "700"), (4, "layer")):
        s = np.zeros(nb); n = np.zeros(nb)
        for i in layer_at:
            f = at_time(T, U, V, i)
            wu, wv = f[0][k][box], f[1][k][box]
            dv2 = (wu[:, None] - wu[None, :]) ** 2 + (wv[:, None] - wv[None, :]) ** 2
            np.add.at(s, kbin[keep], dv2[iu][keep]); np.add.at(n, kbin[keep], 1)
        sf[l] = dict(r_km=[(k_ + 0.5) * B for k_ in range(nb)], rms_kmh=[float(math.sqrt(a / b)) if b else None for a, b in zip(s, n)])
    out["structure"] = sf
    out["issues"] = len(layer_at)
    (R / "era5-vs-rain.json").write_text(json.dumps(out, indent=1))
    for l in LEVELS:
        m, t_ = out["map"][l], out["track"][l]
        print(f"{l:>6}: map ratio {m['speed_ratio']['median']:.2f} turn {m['turn_deg']['median']:+.0f} diff {m['diff_kmh']['median']:.0f} km/h"
              f" | track ratio {t_['speed_ratio']['median']:.2f} turn {t_['turn_deg']['median']:+.0f} within30 {t_['turn_within_30']:.0%}"
              f" diff {t_['diff_kmh']['median']:.0f}")
    w = out["whole_map_vector"]
    print(f"whole-map vector vs layer wind: ratio {w['speed_ratio']['median']:.2f} turn {w['turn_deg']['median']:+.0f} diff {w['diff_kmh']['median']:.0f}")
    for l, v in sf.items():
        print(l, "rms by distance", [round(x) if x else None for x in v["rms_kmh"][:14]])


if __name__ == "__main__":
    main()
