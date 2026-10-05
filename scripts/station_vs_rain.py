#!/usr/bin/env python3
"""Surface wind at DMI stations against the rain's own motion around them (report, Appendix B.3).

For every station and issue time, the rain's motion near the station is the mean of the Lucas-Kanade
feature tracks within 25 km (results/motion-tracks.jsonl); the station's 10-minute mean wind comes from
results/station-wind.json. Also the structure function of the station winds by distance, to set beside
that of the rain's motion (results/motion-coherence.json).

  python scripts/station_vs_rain.py            # results/station-vs-rain.json
"""
import sys, json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid

R = ROOT / "results"
NEAR_KM = 25.0


def main():
    sw = json.loads((R / "station-wind.json").read_text())
    st = sw["stations"]
    ids = sorted(st)
    lon = np.array([st[i][0] for i in ids]); lat = np.array([st[i][1] for i in ids])
    # station positions in the same km frame as the tracks (east of the west edge, south of the north edge)
    sx = (lon - grid.BOUNDS["west"]) / (grid.BOUNDS["east"] - grid.BOUNDS["west"]) * grid.COLS * grid.KM
    sy = (grid.BOUNDS["north"] - lat) / (grid.BOUNDS["north"] - grid.BOUNDS["south"]) * grid.ROWS * grid.KM
    ratio, turn, pairs = [], [], 0
    for line in open(R / "motion-tracks.jsonl"):
        t = json.loads(line)
        obs = sw["obs"].get(str(t["issue"]))
        if not obs or not t["x"]:
            continue
        x, y, u, v = map(np.array, (t["x"], t["y"], t["u"], t["v"]))
        for k, sid in enumerate(ids):
            if sid not in obs:
                continue
            near = np.hypot(x - sx[k], y - sy[k]) <= NEAR_KM
            if near.sum() < 3:
                continue
            ru, rv = u[near].mean(), v[near].mean()                   # rain motion, km/h east and north
            spd, frm = obs[sid][0] * 3.6, math.radians(obs[sid][1])
            wu, wv = -spd * math.sin(frm), -spd * math.cos(frm)       # wind blowing toward
            rs = math.hypot(ru, rv)
            if rs < 10 or spd < 1:
                continue
            ratio.append(spd / rs)
            # angle from the rain's direction to the wind's; positive = wind turned anticlockwise (backed)
            turn.append(math.degrees(math.atan2(ru * wv - rv * wu, ru * wu + rv * wv)))
            pairs += 1
    ratio, turn = np.array(ratio), np.array(turn)
    out = dict(pairs=pairs, near_km=NEAR_KM,
               speed_ratio=dict(zip(("p25", "median", "p75"), map(float, np.percentile(ratio, [25, 50, 75])))),
               turn_deg=dict(zip(("p25", "median", "p75"), map(float, np.percentile(turn, [25, 50, 75])))),
               turn_within_30=float(np.mean(np.abs(turn) <= 30)))
    # station wind structure function by distance
    la, lo = np.radians(lat), np.radians(lon)
    D = 2 * 6371 * np.arcsin(np.sqrt(np.sin((la[:, None] - la[None, :]) / 2) ** 2
                                     + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin((lo[:, None] - lo[None, :]) / 2) ** 2))
    B = 20.0; nb = 20; s = np.zeros(nb); n = np.zeros(nb); speeds = []
    for o in sw["obs"].values():
        idx = [ids.index(i) for i in o]
        if len(idx) < 2:
            continue
        sp = np.array([o[ids[i]][0] for i in idx]) * 3.6; d = np.radians([o[ids[i]][1] for i in idx])
        u, v = -sp * np.sin(d), -sp * np.cos(d); speeds += list(sp)
        dd = D[np.ix_(idx, idx)]; dv2 = (u[:, None] - u[None, :]) ** 2 + (v[:, None] - v[None, :]) ** 2
        iu = np.triu_indices(len(idx), 1); k = (dd[iu] / B).astype(int); m = k < nb
        np.add.at(s, k[m], dv2[iu][m]); np.add.at(n, k[m], 1)
    out["station_speed_median_kmh"] = float(np.median(speeds))
    out["station_structure"] = dict(r_km=[(k + 0.5) * B for k in range(nb)], rms_kmh=[float(math.sqrt(a / b)) if b else None for a, b in zip(s, n)],
                                    pairs=[int(x) for x in n])
    (R / "station-vs-rain.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "station_structure"}, indent=1))


if __name__ == "__main__":
    main()
