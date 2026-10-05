#!/usr/bin/env python3
"""A fair comparison of the chance of rain (report, section 5.5).

The Brier score of section 5.2 treats a single forecast as a probability of 0 or 1 in each cell, while STEPS
gives a real probability, so STEPS wins partly by construction. Here every forecast also gets a neighbourhood
probability: the share of wet cells (for STEPS, the ensemble's chance of rain averaged) within a window of 3, 5
9, 15 or 25 cells around each cell (about 10 to 80 km), scored against that cell alone (results/probs.jsonl, from
run_eval.py --neighbourhood). Brier improvements are over persistence's own 0/1 forecast, so all are on one scale.

  python scripts/compare_probs.py        # results/probs.json
"""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
MODELS = ["persistence", "bw7", "gw4", "pysteps-lk", "pysteps-sprog", "pysteps-steps-mean", "pysteps-steps-default-mean"]
WINDOWS = ["", "_n3", "_n5", "_n9", "_n15", "_n25"]   # "" = the cell alone (0/1 for single forecasts)
LEADS = (30, 60, 120, 180)
N_BOOT, SEED = 2000, 5


def main():
    per = defaultdict(lambda: defaultdict(lambda: np.zeros(len(WINDOWS) + 1)))     # (model, lead) -> event -> [brier per window..., n]
    rel = defaultdict(lambda: np.zeros((3, 10)))                                     # (model, lead, kind) -> counts, psum, osum
    for l in open(R / "probs.jsonl"):
        r = json.loads(l)
        if r["model"] not in MODELS or r["lead"] not in LEADS:
            continue
        v = per[(r["model"], r["lead"])][r["event"]]
        for j, w in enumerate(WINDOWS):
            v[j] += r["brier" + w]
        v[-1] += r["n"]
        for kind in ("rel_n1", "rel_n3", "rel_n5", "rel_n9", "rel_n15", "rel_n25"):
            if kind in r:
                rel[(r["model"], r["lead"], kind)] += np.array(r[kind])
    events = sorted({e for k in per for e in per[k]})
    idx = {e: i for i, e in enumerate(events)}
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(events), size=(N_BOOT, len(events)))
    C = np.stack([np.bincount(d, minlength=len(events)) for d in draws]).astype(float)

    def mat(m, lead):
        a = np.zeros((len(events), len(WINDOWS) + 1))
        for e, v in per[(m, lead)].items():
            a[idx[e]] = v
        return a

    out = {"windows_km": {"": "cell", "_n3": 10, "_n5": 16, "_n9": 29, "_n15": 48, "_n25": 80}, "improvement": {}, "paired": {}, "reliability": {}}
    for lead in LEADS:
        P = mat("persistence", lead)
        bs_p = P[:, 0].sum() / P[:, -1].sum()
        for m in MODELS:
            A = mat(m, lead)
            for j, w in enumerate(WINDOWS):
                imp = bs_p - A[:, j].sum() / A[:, -1].sum()
                boot = (C @ P[:, 0]) / (C @ P[:, -1]) - (C @ A[:, j]) / (C @ A[:, -1])
                lo, hi = np.percentile(boot, [2.5, 97.5])
                out["improvement"][f"{m}{w}_at_{lead}"] = dict(d=float(imp), lo=float(lo), hi=float(hi))
    # head to head at the best window of each method, and STEPS as it was scored in section 5.2
    def best_window(m, lead=60):
        return max(WINDOWS, key=lambda w: out["improvement"][f"{m}{w}_at_{lead}"]["d"])
    best = {m: best_window(m) for m in MODELS}
    out["best_window"] = best
    comps = [("pysteps-steps-default-mean", "pysteps-lk"), ("pysteps-steps-default-mean", "bw7"), ("pysteps-steps-default-mean", "gw4"),
             ("pysteps-steps-mean", "pysteps-lk"), ("pysteps-lk", "bw7"), ("bw7", "gw4")]
    for lead in LEADS:
        for a, b in comps:
            wa, wb = best[a], best[b]
            A, B = mat(a, lead), mat(b, lead)
            ja, jb = WINDOWS.index(wa), WINDOWS.index(wb)
            d0 = B[:, jb].sum() / B[:, -1].sum() - A[:, ja].sum() / A[:, -1].sum()
            boot = (C @ B[:, jb]) / (C @ B[:, -1]) - (C @ A[:, ja]) / (C @ A[:, -1])
            lo, hi = np.percentile(boot, [2.5, 97.5])
            out["paired"][f"{a}{wa}_vs_{b}{wb}_at_{lead}"] = dict(d=float(d0), lo=float(lo), hi=float(hi))
    for (m, lead, kind), v in rel.items():
        out["reliability"][f"{m}_{kind}_at_{lead}"] = dict(n=v[0].tolist(), p=(v[1] / np.maximum(v[0], 1)).tolist(),
                                                         o=(v[2] / np.maximum(v[0], 1)).tolist())
    km = out["windows_km"]
    imp = out["improvement"]
    pair = lambda a, b, L: out["paired"][f"{a}{best[a]}_vs_{b}{best[b]}_at_{L}"]
    out["summary"] = dict(
        best_km={m: km[w] for m, w in best.items()},
        cell={f"{m}_{L}": imp[f"{m}_at_{L}"]["d"] for m in MODELS for L in (60, 180)},
        best={f"{m}_{L}": imp[f"{m}{best[m]}_at_{L}"]["d"] for m in MODELS for L in (60, 180)},
        steps_vs_lk_cell_60=imp["pysteps-steps-default-mean_at_60"]["d"] - imp["pysteps-lk_at_60"]["d"],
        steps_vs_lk_60=pair("pysteps-steps-default-mean", "pysteps-lk", 60), steps_vs_lk_180=pair("pysteps-steps-default-mean", "pysteps-lk", 180),
        steps_vs_bw7_60=pair("pysteps-steps-default-mean", "bw7", 60), steps_vs_bw7_180=pair("pysteps-steps-default-mean", "bw7", 180))
    (R / "probs.json").write_text(json.dumps(out, indent=1))
    for lead in (60, 180):
        print(f"+{lead}")
        for m in MODELS[1:]:
            print(f"  {m:28s}", "  ".join(f"{w or 'cell':5s} {out['improvement'][f'{m}{w}_at_{lead}']['d']:+.4f}" for w in WINDOWS))
    print("best windows", best)
    for k, v in out["paired"].items():
        print(f"  {k}: {v['d']:+.4f} [{v['lo']:+.4f}, {v['hi']:+.4f}]")


if __name__ == "__main__":
    main()
