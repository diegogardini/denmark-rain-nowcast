#!/usr/bin/env python3
"""The cell-size study: the same benchmark on the 3.2, 2 and 1 km grids (scripts/run_grid_study.sh).

  python scripts/compare_grids.py > results/REPORT-grids.md

Every grid scores the same issue times, so grids are compared pairwise, resampling event blocks.
Scores are relative to persistence on the same grid, so a finer grid is not credited for merely
resolving the truth more finely.
"""
import sys, json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import report
from nowcastlab.grid import GRIDS as GRID_CELLS

R = ROOT / "results"
GRIDS = ["3.2km", "2km", "1km"]
MODELS = [("block", "Block matching"), ("gw2", "Whole-map vector, last pair"), ("gw4", "Whole-map vector, 30 min"),
          ("gw7", "Whole-map vector, 1 h"), ("pysteps-lk", "pysteps Lucas-Kanade")]
LEADS = (30, 60, 120, 180)
BANDS = [("near", "under 60 km"), ("mid", "60-120 km"), ("far", "over 120 km")]


def load(g):
    return [r for r in map(json.loads, open(R / f"grid-{g}.jsonl"))]


def sums(rows, model, lead, key="fss9_0.5"):
    per = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if r["model"] == model and r["lead"] == lead and f"{key}_e" in r:
            per[r["event"]][0] += r[f"{key}_e"]; per[r["event"]][1] += r[f"{key}_r"]
    return per


def gain(rows, model, lead, key="fss9_0.5"):
    """{event: (e_model, r_model, e_persistence, r_persistence)}."""
    m, p = sums(rows, model, lead, key), sums(rows, "persistence", lead, key)
    return {e: (*m[e], *p[e]) for e in m if e in p}


def pooled_gain(g, events):
    f = lambda i, j: 1 - sum(g[e][i] for e in events) / sum(g[e][j] for e in events)
    return f(0, 1) - f(2, 3)


def compare(ga, gb, n_boot=2000, seed=5):
    """Gain on grid b minus gain on grid a, with a 95% interval, and share of blocks where b is better."""
    ev = np.array(sorted(set(ga) & set(gb)))
    d0 = pooled_gain(gb, ev) - pooled_gain(ga, ev)
    rng = np.random.default_rng(seed)
    ds = []
    for _ in range(n_boot):
        pick = rng.choice(ev, len(ev), replace=True)
        ds.append(pooled_gain(gb, pick) - pooled_gain(ga, pick))
    one = lambda g, e: (1 - g[e][0] / g[e][1]) - (1 - g[e][2] / g[e][3]) if g[e][1] and g[e][3] else np.nan
    wins = [one(gb, e) > one(ga, e) for e in ev if np.isfinite(one(ga, e)) and np.isfinite(one(gb, e))]
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return d0, lo, hi, float(np.mean(wins))


def main():
    rows = {g: load(g) for g in GRIDS if (R / f"grid-{g}.jsonl").exists()}
    grids = list(rows)
    p = print
    p("# Cell-size study\n")
    meta = {g: json.loads((R / f"grid-{g}.meta.json").read_text()) for g in grids}
    p("| Grid | Cells | km per cell | Block (cells) | Search radius (cells) | FSS window (cells) |")
    p("|---|---|---|---|---|---|")
    for g in grids:
        m = meta[g]
        cols, rows_ = GRID_CELLS[g]
        p(f"| {g} | {cols} x {rows_} | {m.get('km_per_cell', 3.2):.2f} | {m.get('block')} | {m.get('radius')} | {m.get('fss_win', {}).get('9')} |")
    p("\nScores are the FSS gain over persistence on the same grid (about 30 km neighbourhood, 0.5 mm/h).\n")
    for lead in LEADS:
        p(f"\n## +{lead} min\n")
        p("| Model | " + " | ".join(grids) + " | " + " | ".join(f"{g} minus 3.2km [95% CI], blocks better" for g in grids[1:]) + " |")
        p("|---|" + "---|" * (2 * len(grids) - 1))
        for m, lab in MODELS:
            gs = {g: gain(rows[g], m, lead) for g in grids}
            if not all(gs.values()):
                continue
            cells = [f"{pooled_gain(gs[g], sorted(gs[g])):+.3f}" for g in grids]
            for g in grids[1:]:
                d, lo, hi, w = compare(gs["3.2km"], gs[g])
                cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}], {w * 100:.0f}%")
            p(f"| {lab} | " + " | ".join(cells) + " |")
    p("\n## By distance from the nearest radar, +60 min\n")
    p("| Model | Distance | " + " | ".join(grids) + " |")
    p("|---|---|" + "---|" * len(grids))
    for m, lab in MODELS:
        for band, blab in BANDS:
            gs = {g: gain(rows[g], m, 60, f"fss9_{band}") for g in grids}
            if not all(gs.values()):
                continue
            p(f"| {lab} | {blab} | " + " | ".join(f"{pooled_gain(gs[g], sorted(gs[g])):+.3f}" for g in grids) + " |")
    p("\n## Rain at cities, next hour: CSI at 0.5 mm\n")
    p("| Model | " + " | ".join(grids) + " |")
    p("|---|" + "---|" * len(grids))
    city = {g: [r for r in map(json.loads, open(R / f"cities-grid-{g}.jsonl")) if r["hour"] == 1]
            for g in grids if (R / f"cities-grid-{g}.jsonl").exists()}
    for m, lab in [("persistence", "Persistence"), ("block", "Block matching"), ("gw4", "Whole-map vector, 30 min"), ("pysteps-lk", "pysteps Lucas-Kanade")]:
        cells = []
        for g in grids:
            if g not in city:
                cells.append("-"); continue
            o = np.array([r["obs"] for r in city[g]]) >= 0.5; f = np.array([r[m] for r in city[g]]) >= 0.5
            cells.append(f"{(o & f).sum() / ((o | f).sum()):.2f}")
        p(f"| {lab} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
