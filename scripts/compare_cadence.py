#!/usr/bin/env python3
"""Does the 5- or 10-minute cadence matter, once the coverage artefact is removed?

Both runs use only the cells that both kinds of DMI scan cover (data/common_coverage.npy)
and the same issue times, so every difference is the cadence alone.

  python scripts/compare_cadence.py > results/REPORT-cadence.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import report

R = ROOT / "results"
T10, T5 = R / "check-cadence-10min.jsonl", R / "check-cadence-5min.jsonl"

# (label, model on the 10-minute axis, model on the 5-minute axis), matched by minutes of history
PAIRS = [
    ("Block matching, last pair of scans", "block", "block"),
    ("Global vector, 10 min of history", "gw2", "gw3"),
    ("Global vector, 30 min of history", "gw4", "gw7"),
    ("Global vector, 60 min of history", "gw7", "gw13"),
    ("pysteps LK, 30 min of history", "pysteps-lk", "pysteps-lk7"),
    ("pysteps LK, 60 min of history", "pysteps-lk7", "pysteps-lk13"),
]
ONLY5 = [("Global vector, 5 min of history (one pair)", "gw2"), ("pysteps LK, 15 min of history (4 scans)", "pysteps-lk")]


def gain(S, m, lead):
    e = S[(m, lead)]
    lo, hi = e["dFSS9_ci"]
    return f"{e['dFSS9']:+.3f} [{lo:+.3f}, {hi:+.3f}]"


def main():
    S10, S5 = report.summarize_file(T10), report.summarize_file(T5)
    rows10, rows5 = report.load(T10), report.load(T5)
    both = [dict(r, model="10:" + r["model"]) for r in rows10] + [dict(r, model="5:" + r["model"]) for r in rows5]
    p = print
    p("# Cadence check: 5-minute against 10-minute scans on a fixed footprint\n")
    e10, e5 = S10[("persistence", 60)], S5[("persistence", 60)]
    p("Frames and scoring are restricted to the cells both kinds of DMI scan cover "
      f"(`data/common_coverage.npy`: 37% of the grid, 56% of the scoring box). Both runs score the same issue times "
      f"({e10['cases']} on the 10-minute axis, {e5['cases']} on the 5-minute axis, which needs a full hour of history; "
      f"{e10['events']} and {e5['events']} blocks). Persistence forecasts the same frames in both runs; the paired "
      "column compares the two cadences on the issue times they share.\n")
    for lead in (30, 60, 120, 180):
        p(f"\n## +{lead} min\n")
        p(f"Persistence FSS: {S10[('persistence', lead)]['FSS9']:.3f} (10-min run), {S5[('persistence', lead)]['FSS9']:.3f} (5-min run).\n")
        p("| Model | 10-minute scans | 5-minute scans | 5-min minus 10-min, paired [95% CI] | Blocks where 5-min is better | Rain ratio 10 / 5 |")
        p("|---|---|---|---|---|---|")
        for label, m10, m5 in PAIRS:
            d, (lo, hi), w = report.paired_fss(both, "5:" + m5, "10:" + m10, lead)
            p(f"| {label} | {gain(S10, m10, lead)} | {gain(S5, m5, lead)} | {d:+.3f} [{lo:+.3f}, {hi:+.3f}] | {w:.0%} | "
              f"{S10[(m10, lead)]['ratio']:.2f} / {S5[(m5, lead)]['ratio']:.2f} |")
        for label, m5 in ONLY5:
            p(f"| {label} | - | {gain(S5, m5, lead)} | | | - / {S5[(m5, lead)]['ratio']:.2f} |")
    p("\n## Key comparisons within each cadence, +60 min\n")
    p("| Comparison | 10-minute scans | 5-minute scans |")
    p("|---|---|---|")
    for label, (a10, b10), (a5, b5) in [
        ("Global vector (60 min) minus block", ("gw7", "block"), ("gw13", "block")),
        ("pysteps LK (30 min) minus global vector (30 min)", ("pysteps-lk", "gw4"), ("pysteps-lk7", "gw7")),
        ("Global vector, 60 min minus 10 min of history", ("gw7", "gw2"), ("gw13", "gw3")),
    ]:
        cells = []
        for rows, a, b in ((rows10, a10, b10), (rows5, a5, b5)):
            d, (lo, hi), w = report.paired_fss(rows, a, b, 60)
            cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}], first better in {w:.0%}")
        p(f"| {label} | {cells[0]} | {cells[1]} |")


if __name__ == "__main__":
    main()
