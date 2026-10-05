#!/usr/bin/env python3
"""Summary of timing at one spot (report, Appendix C; from results/local-timing.npz).

Calibration is fitted on one half of the season and applied to the other (April to June against July to
September, and the other way round), so every rain episode is scored out of sample. Scores: the Brier
improvement over persistence for each statement, horizon and threshold, and the difference from calibrated STEPS
with a 95% interval from resampling rain episodes (positive: better than STEPS).

  python scripts/local_timing_summary.py      # results/local-timing.json
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
NB, N_BOOT, SEED = 20, 2000, 9


def main():
    d = np.load(R / "local-timing.npz")
    D = d["data"]                                           # [event, thr, type, horizon, variant, 2 + 2*NB]
    V, T, Hs, thr = list(d["variants"]), list(d["event_types"]), list(d["horizons_min"]), list(d["thresholds"])
    month = np.array([int(np.datetime64(int(t), "s").astype(object).month) for t in d["event_start"]])
    halves = [month <= 6, month > 6]
    centres = (np.arange(NB) + 0.5) / NB
    E = D.shape[0]
    rng = np.random.default_rng(SEED)
    Wb = np.stack([np.bincount(rng.integers(0, E, E), minlength=E) for _ in range(N_BOOT)])
    out = {"horizons_min": [int(h) for h in Hs], "thresholds": [float(x) for x in thr], "issues": int(d["issues"]), "results": {}}
    for ti, th in enumerate(thr):
        for qi, ev in enumerate(T):
            for hi, hz in enumerate(Hs):
                x = D[:, ti, qi, hi]                      # [event, variant, 2 + 2*NB]
                S = {}
                for vi, v in enumerate(V):
                    raw, cal = np.zeros(E), np.zeros(E)
                    for train, test in ((halves[0], halves[1]), (halves[1], halves[0])):
                        tr = x[train, vi].sum(0)
                        c = np.where(tr[2:2 + NB] >= 50, tr[2 + NB:] / np.maximum(tr[2:2 + NB], 1), centres)
                        n, o = x[test, vi, 2:2 + NB], x[test, vi, 2 + NB:]
                        raw[test] = x[test, vi, 0]
                        cal[test] = (n * c ** 2 - 2 * c * o + o).sum(1)
                    S[v], S[v + "_cal"] = raw, cal
                n = x[:, 0, 1]
                P = S["pers"]
                key = f"{th:g}|{ev}|{int(hz)}"
                res = {"cells": float(n.sum()), "base_rate": float(x[:, 0, 2 + NB:].sum() / max(n.sum(), 1)), "improvement": {}, "vs_steps_cal": {}}
                for v, s in S.items():
                    res["improvement"][v] = float((P.sum() - s.sum()) / n.sum())
                    d0 = (S["steps_cal"].sum() - s.sum()) / n.sum()
                    boot = (Wb @ S["steps_cal"] - Wb @ s) / np.maximum(Wb @ n, 1)
                    lo, hi = np.percentile(boot, [2.5, 97.5])
                    res["vs_steps_cal"][v] = dict(d=float(d0), lo=float(lo), hi=float(hi))
                out["results"][key] = res
    (R / "local-timing.json").write_text(json.dumps(out, indent=1))
    show = ["gw", "gw_cal", "gw_max_cal", "gw_shift", "gw_shift_cal", "steps", "steps_cal"]
    for th in thr:
        print(f"\nthreshold {th:g} mm/h: Brier improvement over persistence, out of sample; [diff from calibrated STEPS, 95% interval]")
        for ev in T:
            for hz in Hs:
                r = out["results"][f"{th:g}|{ev}|{int(hz)}"]
                line = f"  {ev:5s} {int(hz):3d} min (base {r['base_rate']:.2f}): " + "  ".join(f"{v} {r['improvement'][v]:.4f}" for v in show)
                print(line)
                for v in ("gw_shift_cal", "gw_max_cal"):
                    q = r["vs_steps_cal"][v]
                    print(f"      {v} - steps_cal: {q['d']:+.4f} [{q['lo']:+.4f}, {q['hi']:+.4f}]")


if __name__ == "__main__":
    main()
