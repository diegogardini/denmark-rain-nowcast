#!/usr/bin/env python3
"""Summary of the local chance of rain (report, Appendix C; from results/local-probs.npz).

Every choice is made on one half of the season and scored on the other (April to June against July to
September, and the other way round), so each rain episode is scored once, by settings chosen without it:

  pers               persistence, 0 or 1 (the reference)
  gw                 the whole-map vector, 0 or 1 in each cell
  gw_fixed           read over the one round window that is best at +60 min (as in Appendix C)
  gw_grow            read over the round window that is best at each lead time
  gw_grow_stretch    the same, also allowing windows stretched along the motion
  gwlag_grow_stretch the same, with the forecasts of the last 30 minutes as extra members
  steps              STEPS at its defaults, the share of members with rain in the cell
  steps_grow         STEPS read over the round window that is best at each lead time

and each of them calibrated: the chance in each of 20 bins replaced by how often it rained in that bin on the
other half. Scores: Brier improvement over persistence, and its difference from STEPS with a 95% interval from
resampling rain episodes.

  python scripts/local_probs_summary.py      # results/local-probs.json
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
NB, N_BOOT, SEED = 20, 2000, 8
LEADS = list(range(10, 130, 10))


def main():
    d = np.load(R / "local-probs.npz")
    D, combos = d["data"], [tuple(c.split("|")) for c in d["combos"]]       # D[event, thr, combo, step, 2 + 2*NB]
    combos = [(n, float(s), float(r)) for n, s, r in combos]
    month = np.array([int(np.datetime64(int(t), "s").astype(object).month) for t in d["event_start"]])
    halves = [month <= 6, month > 6]
    ix = {c: j for j, c in enumerate(combos)}
    centres = (np.arange(NB) + 0.5) / NB

    def brier(sel, t, c, k, calib=None):
        """Per-event Brier sums for one combo and step; calibrated with a per-bin mapping if given."""
        x = D[sel, t, c, k]
        if calib is None:
            return x[:, 0]
        n, o = x[:, 2:2 + NB], x[:, 2 + NB:]
        return (n * calib ** 2 - 2 * calib * o + o).sum(1)

    def calibration(sel, t, c, k):
        x = D[sel, t, c, k].sum(0)
        n, o = x[2:2 + NB], x[2 + NB:]
        return np.where(n >= 50, o / np.maximum(n, 1), centres)

    def choose(sel, t, names, k, ratios=(1.0,)):
        cands = [ix[c] for c in combos if c[0] in names and c[2] in ratios]
        return min(cands, key=lambda c: D[sel, t, c, k, 0].sum())

    variants = {"pers": None, "gw": None, "gw_fixed": None, "gw_grow": None, "gw_grow_stretch": None,
                "gwlag_grow_stretch": None, "steps": None, "steps_grow": None}
    out = {"leads": LEADS, "thresholds": [float(x) for x in d["thresholds"]], "issues": int(d["issues"]), "by_threshold": {}}
    rng = np.random.default_rng(SEED)
    E = D.shape[0]
    W = np.stack([np.bincount(rng.integers(0, E, E), minlength=E) for _ in range(N_BOOT)])
    for t, thr in enumerate(d["thresholds"]):
        S = {}                                            # (variant, calibrated) -> [event, step] Brier sums, out of sample
        n = np.zeros((E, len(LEADS)))
        picks = {}
        for v in variants:
            for cal in (False, True):
                S[(v, cal)] = np.zeros((E, len(LEADS)))
        for f, (train, test) in enumerate([(halves[0], halves[1]), (halves[1], halves[0])]):
            fixed = choose(train, t, ("gw",), 5)          # the round window best at +60 min
            for k in range(len(LEADS)):
                ck = {"pers": ix[("pers", 0.0, 1.0)], "gw": ix[("gw", 0.0, 1.0)], "gw_fixed": fixed,
                      "gw_grow": choose(train, t, ("gw",), k), "gw_grow_stretch": choose(train, t, ("gw",), k, (1.0, 0.5)),
                      "gwlag_grow_stretch": choose(train, t, ("gwlag",), k, (1.0, 0.5)),
                      "steps": ix[("steps", 0.0, 1.0)], "steps_grow": choose(train, t, ("steps",), k)}
                for v, c in ck.items():
                    picks.setdefault(v, {}).setdefault(f"fold{f}", []).append("|".join(map(str, combos[c])))
                    S[(v, False)][test, k] = brier(test, t, c, k)
                    S[(v, True)][test, k] = brier(test, t, c, k, calibration(train, t, c, k))
                n[test, k] = D[test, t, ix[("pers", 0.0, 1.0)], k, 1]
        res = {"picks": picks, "improvement": {}, "vs_steps": {}}
        P = S[("pers", False)]
        for (v, cal), s in S.items():
            name = v + ("_cal" if cal else "")
            res["improvement"][name] = [float((P[:, k].sum() - s[:, k].sum()) / n[:, k].sum()) for k in range(len(LEADS))]
        ref = S[("steps_grow", True)]                     # STEPS at its best window, calibrated: the strongest reference
        for (v, cal), s in S.items():
            name = v + ("_cal" if cal else "")
            diffs = []
            for k in range(len(LEADS)):
                d0 = (ref[:, k].sum() - s[:, k].sum()) / n[:, k].sum()
                boot = (W @ ref[:, k] - W @ s[:, k]) / (W @ n[:, k])
                lo, hi = np.percentile(boot, [2.5, 97.5])
                diffs.append(dict(d=float(d0), lo=float(lo), hi=float(hi)))
            res["vs_steps"][name] = diffs
        out["by_threshold"][f"{thr:g}"] = res
        print(f"\nthreshold {thr:g} mm/h: Brier improvement over persistence (out of sample)")
        print(f"{'':24s}" + "".join(f"{L:>8d}" for L in LEADS))
        for name, vals in res["improvement"].items():
            print(f"{name:24s}" + "".join(f"{x:8.4f}" for x in vals))
        print("  difference from calibrated STEPS at its best window (+60, +120):")
        for name, vals in res["vs_steps"].items():
            print(f"  {name:24s} " + "  ".join(f"{vals[k]['d']:+.4f} [{vals[k]['lo']:+.4f}, {vals[k]['hi']:+.4f}]" for k in (5, 11)))
    (R / "local-probs.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
