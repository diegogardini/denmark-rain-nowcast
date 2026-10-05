#!/usr/bin/env python3
"""Does a long history lag where the flow turns? (report, Appendix B.1)

Every issue time of the history run (results/benchmark-10min-window.jsonl) is rated by how fast the flow is
changing, three ways:

  radar  how much the whole-map vector (results/motion-vectors.jsonl, 30 min of history) changes over the next
         hour: the size of the difference between the vector at the issue time and one hour later, km/h
  era5   the same for the ERA5 700 hPa wind averaged over the scoring box (data/era5, hourly), km/h; independent
         of the radar
  vort   the ERA5 700 hPa relative vorticity, box mean of its absolute value, 1e-5 per second: strong where the
         flow curves around a low or shears across a front

For each rating the issue times are split into thirds (steady, middle, turning) and the history run is re-scored
within each third: FSS gain over persistence per method, and paired differences between histories with 95%
intervals from resampling rain episodes (the same episodes for both thirds, so the change between steady and
turning flow gets an interval too). No new forecasts.

  python scripts/turning_flow.py          # results/turning-flow.json
"""
import sys, json, glob
from pathlib import Path
from collections import defaultdict
import numpy as np
import h5py

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
N_BOOT, SEED = 2000, 22
LEADS = (30, 60, 120, 180)
BOX = dict(lat=(54.3, 58.0), lon=(8.0, 15.3))                  # the scoring box, as in era5_vs_rain.py
PAIRS = [("gw2", "gw4"), ("gw7", "gw4"), ("gw13", "gw4"), ("gwx3", "gw13"),
         ("bw2", "bw7"), ("bw13", "bw7"), ("pysteps-lk13", "pysteps-lk")]
MODELS = sorted({m for p in PAIRS for m in p} | {"bw4", "gw3", "gw5", "gw10", "gwx6", "pysteps-lk7"})


def era5():
    """Hourly box-mean 700 hPa wind (km/h east, north) and box-mean |vorticity| (1e-5 / s), by unix time."""
    out = {}
    for f in sorted(glob.glob(str(ROOT / "data" / "era5" / "era5-*.nc"))):
        h = h5py.File(f)
        lat, lon = np.asarray(h["latitude"]), np.asarray(h["longitude"])
        k = [str(int(x)) for x in np.asarray(h["pressure_level"])].index("700")
        u, v = np.asarray(h["u"])[:, k] * 3.6, np.asarray(h["v"])[:, k] * 3.6      # km/h; [time, lat, lon]
        if lat[0] > lat[-1]:
            lat, u, v = lat[::-1], u[:, ::-1], v[:, ::-1]
        dy = np.radians(lat[1] - lat[0]) * 6371.0                                  # km
        dx = np.radians(lon[1] - lon[0]) * 6371.0 * np.cos(np.radians(lat))[:, None]
        zeta = np.gradient(v, axis=2) / dx - np.gradient(u, axis=1) / dy           # 1/h
        zeta *= 1e5 / 3600                                                          # 1e-5 / s
        box = ((lat >= BOX["lat"][0]) & (lat <= BOX["lat"][1]))[:, None] & ((lon >= BOX["lon"][0]) & (lon <= BOX["lon"][1]))[None, :]
        for i, t in enumerate(np.asarray(h["valid_time"]).astype(np.int64)):
            out[int(t)] = (float(u[i][box].mean()), float(v[i][box].mean()), float(np.abs(zeta[i][box]).mean()))
    return out


def ratings(issues):
    vec = {r["issue"]: r["model"] for r in map(json.loads, open(R / "motion-vectors.jsonl")) if r["model"]}
    E = era5()

    def at(t):
        """ERA5 values at time t, linear between the hours, or None."""
        h0 = t - t % 3600
        if h0 not in E or h0 + 3600 not in E:
            return None
        w = (t - h0) / 3600
        return [x * (1 - w) + y * w for x, y in zip(E[h0], E[h0 + 3600])]

    out = {"radar": {}, "era5": {}, "vort": {}}
    for t in issues:
        if t in vec and t + 3600 in vec:
            a, b = vec[t], vec[t + 3600]
            out["radar"][t] = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        a, b = at(t), at(t + 3600)
        if a and b:
            out["era5"][t] = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            out["vort"][t] = a[2]
    return out


def main():
    S = defaultdict(lambda: [0.0, 0.0])          # (model, lead, issue) -> FSS error, reference
    event = {}
    for line in open(R / "benchmark-10min-window.jsonl"):
        r = json.loads(line)
        if r["lead"] in LEADS and (r["model"] in MODELS or r["model"] == "persistence"):
            s = S[(r["model"], r["lead"], r["issue"])]
            s[0] += r["fss9_0.5_e"]; s[1] += r["fss9_0.5_r"]
            event[r["issue"]] = r["event"]
    issues = sorted(event)
    rate = ratings(issues)
    episodes = sorted(set(event.values()))
    col = {e: j for j, e in enumerate(episodes)}
    rng = np.random.default_rng(SEED)
    C = np.stack([np.bincount(rng.integers(0, len(episodes), len(episodes)), minlength=len(episodes)) for _ in range(N_BOOT)])

    def sums(model, lead, sel):
        """Per-episode FSS error and reference over the selected issue times."""
        a = np.zeros((len(episodes), 2))
        for t in sel:
            if (model, lead, t) in S:
                a[col[event[t]]] += S[(model, lead, t)]
        return a

    def fss(a, w=None):
        e, r = (a[:, 0], a[:, 1]) if w is None else (w @ a[:, 0], w @ a[:, 1])
        return 1 - e.sum() / r.sum() if w is None else 1 - e / r

    out = {"what": __doc__.split("\n\n")[0], "n_boot": N_BOOT, "ratings": {}}
    for name, rt in rate.items():
        ts = sorted(rt, key=rt.get)
        cuts = [float(np.percentile(list(rt.values()), q)) for q in (100 / 3, 200 / 3)]
        groups = {"steady": [t for t in ts if rt[t] <= cuts[0]], "middle": [t for t in ts if cuts[0] < rt[t] <= cuts[1]],
                  "turning": [t for t in ts if rt[t] > cuts[1]]}
        res = {"cuts": cuts, "median": {g: float(np.median([rt[t] for t in v])) for g, v in groups.items()},
               "issues": {g: len(v) for g, v in groups.items()},
               "episodes": {g: len({event[t] for t in v}) for g, v in groups.items()}, "gain": {}, "paired": {}}
        for lead in LEADS:
            P = {g: sums("persistence", lead, v) for g, v in groups.items()}
            for m in MODELS:
                for g, v in groups.items():
                    a = sums(m, lead, v)
                    res["gain"][f"{m}_{g}_at_{lead}"] = fss(a) - fss(P[g])
            for a_, b_ in PAIRS:
                d, boot = {}, {}
                for g in ("steady", "turning"):
                    A, B = sums(a_, lead, groups[g]), sums(b_, lead, groups[g])
                    d[g] = fss(A) - fss(B)
                    boot[g] = fss(A, C) - fss(B, C)
                    lo, hi = np.nanpercentile(boot[g], [2.5, 97.5])
                    res["paired"][f"{a_}_vs_{b_}_{g}_at_{lead}"] = dict(d=d[g], lo=float(lo), hi=float(hi))
                dd = boot["turning"] - boot["steady"]
                lo, hi = np.nanpercentile(dd, [2.5, 97.5])
                res["paired"][f"{a_}_vs_{b_}_change_at_{lead}"] = dict(d=d["turning"] - d["steady"], lo=float(lo), hi=float(hi))
        out["ratings"][name] = res
    # how the three ratings relate
    common = sorted(set(rate["radar"]) & set(rate["era5"]))
    rk = lambda x: np.argsort(np.argsort(x))
    out["rank_corr"] = {"radar_era5": float(np.corrcoef(rk([rate["radar"][t] for t in common]), rk([rate["era5"][t] for t in common]))[0, 1]),
                        "era5_vort": float(np.corrcoef(rk([rate["era5"][t] for t in common]), rk([rate["vort"][t] for t in common]))[0, 1])}
    (R / "turning-flow.json").write_text(json.dumps(out, indent=1))
    for name, res in out["ratings"].items():
        print(f"\n{name}: thirds at {res['cuts'][0]:.1f} / {res['cuts'][1]:.1f}; medians " +
              ", ".join(f"{g} {v:.1f}" for g, v in res["median"].items()) + f"; issues {res['issues']}, episodes {res['episodes']}")
        for lead in (60, 180):
            for a_, b_ in PAIRS:
                s, t, c = (res["paired"][f"{a_}_vs_{b_}_{g}_at_{lead}"] for g in ("steady", "turning", "change"))
                print(f"  +{lead} {a_:>13} - {b_:<11} steady {s['d']:+.3f} [{s['lo']:+.3f},{s['hi']:+.3f}]  "
                      f"turning {t['d']:+.3f} [{t['lo']:+.3f},{t['hi']:+.3f}]  change {c['d']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}]")
    print("\nrank correlations:", out["rank_corr"])


if __name__ == "__main__":
    main()
