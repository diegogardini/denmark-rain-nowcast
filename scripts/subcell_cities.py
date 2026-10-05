#!/usr/bin/env python3
"""Sub-cell block matching at the cities (report, Appendix B.4).

Block matching with each block's match refined to a fraction of a cell (block-sub-all) against plain whole-cell
block matching (block), both on the latest pair of scans, at the five cities of section 5.6
(results/cities.jsonl, column added by run_cities.py --update block-sub-all). For the next hour and the hour
after: rainy hours caught, false alarms, CSI and the rain total, with the CSI difference's 95% interval from
resampling rain episodes, as in section 5.6.

  python scripts/subcell_cities.py       # results/subcell-cities.json
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
THR, N_BOOT, SEED = 0.5, 2000, 24
A, B = "block-sub-all", "block"


def counts(rows, m):
    o = np.array([r["obs"] for r in rows]); f = np.array([r[m] for r in rows])
    O, F = o >= THR, f >= THR
    return np.array([(O & F).sum(), (O & ~F).sum(), (~O & F).sum(), f.sum(), o.sum()], float)


def main():
    rows = [json.loads(l) for l in open(R / "cities.jsonl")]
    out = {}
    for hour in (1, 2):
        hr = [r for r in rows if r["hour"] == hour and A in r]
        ev = sorted({r["event"] for r in hr})
        by = {e: [r for r in hr if r["event"] == e] for e in ev}
        C = {m: np.array([counts(by[e], m) for e in ev]) for m in (A, B)}
        csi = lambda c: c[0] / (c[0] + c[1] + c[2])
        res = {}
        for m in (A, B):
            c = C[m].sum(0)
            res[m] = dict(caught=c[0] / (c[0] + c[1]), false_alarms=c[2] / (c[0] + c[2]), csi=csi(c), rain_ratio=c[3] / c[4])
        rng = np.random.default_rng(SEED)
        d = []
        for _ in range(N_BOOT):
            w = np.bincount(rng.integers(0, len(ev), len(ev)), minlength=len(ev))
            d.append(csi(w @ C[A]) - csi(w @ C[B]))
        lo, hi = np.percentile(d, [2.5, 97.5])
        res["csi_diff"] = dict(d=res[A]["csi"] - res[B]["csi"], lo=float(lo), hi=float(hi))
        out[f"hour{hour}"] = {k: ({kk: float(vv) for kk, vv in v.items()}) for k, v in res.items()}
        print(f"hour {hour}: " + "; ".join(f"{m}: caught {res[m]['caught']:.3f} FA {res[m]['false_alarms']:.3f} CSI {res[m]['csi']:.3f} ratio {res[m]['rain_ratio']:.2f}"
                                           for m in (A, B)) + f"; CSI diff {res['csi_diff']['d']:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    (R / "subcell-cities.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
