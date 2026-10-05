#!/usr/bin/env python3
"""The fixed-echo check (report, Appendix A.3): the benchmark, the cities and the whole-map vector, with and without the
fixed-echo mask (results/fixed-echo-mask.npy, from scripts/fixed_echo_mask.py).

  python scripts/compare_mask.py            # results/fixed-echo-check.json, and a table on stdout

Runs compared (all on the same issue times):
  benchmark-10min.jsonl  against benchmark-clean.jsonl         (run_eval.py --region clean)
  cities-5x5.jsonl       against cities-5x5-clean.jsonl        (run_cities.py --half 2 [--region clean]); the
                         usual 3 x 3 city area lies entirely inside the mask at Copenhagen, so a 5 x 5 area is used
  motion-vectors.jsonl   against motion-vectors-clean.jsonl    (motion_stats.py PROCS [clean])
Gains are over persistence in the same run, so leaving cells out of the scoring is not itself credited.
"""
import sys, json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from scipy.ndimage import binary_dilation
from compare_grids import gain, pooled_gain, compare
from nowcastlab.data import box_mask
import run_cities

R = ROOT / "results"
MODELS = [("block", "Block matching"), ("gw4", "Whole-map vector, 30 min"), ("gw7", "Whole-map vector, 1 h"),
          ("pysteps-lk", "pysteps LK"), ("pysteps-lk7", "pysteps LK, 1 h"), ("pysteps-sprog", "pysteps S-PROG"),
          ("pysteps-steps-mean", "pysteps STEPS mean")]
LEADS = (30, 60, 120, 180)
CITY_MODELS = ("persistence", "block", "gw4", "pysteps-lk")


def load(name):
    return [json.loads(l) for l in open(R / name)]


def cities(name):
    rows = [r for r in load(name) if r["hour"] == 1]
    out = {}
    for c in sorted({r["city"] for r in rows}) + ["all"]:
        rs = [r for r in rows if c == "all" or r["city"] == c]
        o = np.array([r["obs"] for r in rs])
        d = {"n": len(rs)}
        for m in CITY_MODELS:
            f = np.array([r[m] for r in rs])
            hit, union = ((o >= 0.5) & (f >= 0.5)).sum(), ((o >= 0.5) | (f >= 0.5)).sum()
            d[m] = dict(ratio=float(f.sum() / o.sum()), csi=float(hit / union))
        out[c] = d
    return out


def speed_ratio(name):
    tr = {}
    for t in map(json.loads, open(R / "motion-tracks.jsonl")):
        if len(t["u"]) >= 10:
            tr[t["issue"]] = (float(np.mean(t["u"])), float(np.mean(t["v"])))
    v = {x["issue"]: x["model"] for x in map(json.loads, open(R / name)) if x["issue"] in tr and x["smoothed"]}
    return {i: math.hypot(*v[i]) / math.hypot(*tr[i]) for i in v}, v


def main():
    out = {"mask": json.loads((R / "fixed-echo-mask.json").read_text())}
    out["mask"]["masked_in_box_share"] = out["mask"]["masked_in_box"] / out["mask"]["box_cells"]
    a, b = load("benchmark-10min.jsonl"), load("benchmark-clean.jsonl")
    out["benchmark"] = {}
    for m, _ in MODELS:
        for lead in LEADS:
            ga, gb = gain(a, m, lead), gain(b, m, lead)
            if not ga or not gb:
                continue
            d, lo, hi, w = compare(ga, gb)
            out["benchmark"].setdefault(m, {})[str(lead)] = dict(before=pooled_gain(ga, sorted(ga)), after=pooled_gain(gb, sorted(gb)),
                                                   diff=d, lo=lo, hi=hi, blocks_better=w)
    out["cities_before"], out["cities_after"] = cities("cities-5x5.jsonl"), cities("cities-5x5-clean.jsonl")
    out["cities_3x3_after"] = cities("cities-clean.jsonl")
    ra, va = speed_ratio("motion-vectors.jsonl")
    rb, vb = speed_ratio("motion-vectors-clean.jsonl")
    common = sorted(set(ra) & set(rb))
    moved = [math.hypot(va[i][0] - vb[i][0], va[i][1] - vb[i][1]) for i in common]
    out["speed"] = dict(n=len(common), ratio_before=float(np.median([ra[i] for i in common])),
                        ratio_after=float(np.median([rb[i] for i in common])),
                        vector_change_median=float(np.median(moved)), vector_change_p90=float(np.percentile(moved, 90)))
    # the weaker echo around the Copenhagen core, and how far the mask would spread at lower thresholds
    fd = np.nan_to_num(np.load(R / "climatology.npz")["wet_freq_dry_map"])
    mask, box = np.load(R / "fixed-echo-mask.npy"), box_mask()
    r, c = run_cities.CELLS["Copenhagen"]
    kept = fd[r - 2:r + 3, c - 2:c + 3][~mask[r - 2:r + 3, c - 2:c + 3]]
    out["copenhagen_ring"] = dict(cells=int(kept.size), median=float(np.median(kept)), max=float(kept.max()),
                                  box_median=float(np.median(fd[box])), box_p99=float(np.percentile(fd[box], 99)))
    out["sweep"] = {}
    for t in (0.01, 0.005, 0.003, 0.002):
        m = binary_dilation(fd > t, structure=np.ones((3, 3), bool))
        out["sweep"][f"t{round(t * 1000)}"] = dict(                # t10: 1%, t5: 0.5%, ...box_share=float((m & box).sum() / box.sum()),
                                    copenhagen_5x5_masked=int(m[r - 2:r + 3, c - 2:c + 3].sum()))
    (R / "fixed-echo-check.json").write_text(json.dumps(out, indent=1))

    p = print
    p("# Fixed-echo check\n")
    p("FSS gain over persistence (about 30 km, 0.5 mm/h), without and with the mask:\n")
    p("| Model | Lead | Without | With | Difference [95% CI] | Blocks better |")
    p("|---|---|---|---|---|---|")
    for m, lab in MODELS:
        for lead in LEADS:
            x = out["benchmark"].get(m, {}).get(str(lead))
            if x:
                p(f"| {lab} | +{lead} | {x['before']:+.3f} | {x['after']:+.3f} | {x['diff']:+.4f} [{x['lo']:+.4f}, {x['hi']:+.4f}] | {100 * x['blocks_better']:.0f}% |")
    p("\nCities, next hour, 5 x 5 cells: rain ratio and CSI at 0.5 mm, without -> with the mask:\n")
    p("| City | " + " | ".join(CITY_MODELS) + " |")
    p("|---|" + "---|" * len(CITY_MODELS))
    for c in out["cities_before"]:
        x, y = out["cities_before"][c], out["cities_after"][c]
        p(f"| {c} | " + " | ".join(f"{x[m]['ratio']:.2f} -> {y[m]['ratio']:.2f}, {x[m]['csi']:.2f} -> {y[m]['csi']:.2f}" for m in CITY_MODELS) + " |")
    s = out["speed"]
    p(f"\nWhole-map vector speed / tracked speed (median): {s['ratio_before']:.3f} -> {s['ratio_after']:.3f}; "
      f"the vector moves by {s['vector_change_median']:.2f} km/h (median), {s['vector_change_p90']:.2f} km/h (90th percentile)")


if __name__ == "__main__":
    main()
