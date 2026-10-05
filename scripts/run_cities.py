#!/usr/bin/env python3
"""Rain at Danish cities: forecast against radar, in millimetres per hour.

For each issue time of the main benchmark, every model forecasts two hours ahead, and the rain
it predicts over each city (the mean of 3 x 3 grid cells, about 10 x 10 km) is added up over the
first and the second hour. The radar's own amount over the same area and hours is the truth.

  python scripts/run_cities.py            # writes results/cities.jsonl (+ .meta.json)
  NOWCAST_GRID=1km python scripts/run_cities.py --out results/cities-grid-1km.jsonl --procs 26
  python scripts/run_cities.py --out results/cities.jsonl --update gw4     # recompute one model's column in place
"""
import sys, json, time, argparse
import multiprocessing as mp
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import models
from nowcastlab.data import Archive, region_named
from nowcastlab import grid

CITIES = {"Copenhagen": (55.676, 12.568), "Aarhus": (56.157, 10.211), "Odense": (55.403, 10.402),
          "Aalborg": (57.048, 9.919), "Esbjerg": (55.476, 8.459)}
MODELS = ["persistence", "block", "gw4", "pysteps-lk"]      # --update can add "bw7" (block matching over 1 h)
ISSUES_FROM = ROOT / "results" / "benchmark-10min.jsonl"
OUT = ROOT / "results" / f"cities{grid.SUFFIX}.jsonl"
HIST = 7
_A = None
KEEP = None          # the cells kept by --region (True), or None for all
ONLY = MODELS        # the models to forecast (--update: just those)


CELLS = {k: grid.cell_of(*v) for k, v in CITIES.items()}
HALF = grid.FSS_WIN[3] // 2          # the city area: about 10 x 10 km on any grid (3 x 3 cells at 3.2 km)


def area_mean(g, rc):
    r, c = rc
    v = g[r - HALF:r + HALF + 1, c - HALF:c + HALF + 1]
    if KEEP is not None:
        v = np.where(KEEP[r - HALF:r + HALF + 1, c - HALF:c + HALF + 1], v, np.nan)
    return float(np.nanmean(v)) if np.isfinite(v).any() else float("nan")


def work(args):
    e, i = args
    A = _A
    per = A.step // 60
    steps = 120 // per
    frames = A.frames(i, HIST)
    make = {"persistence": lambda: models.make("persistence").forecast(frames, steps),
            "block": lambda: models.make("block").forecast(frames, steps),
            "gw4": lambda: models.make("global-windows").forecast_multi(frames, steps)["gw4"],
            "pysteps-lk": lambda: models.make("pysteps-lk").forecast(frames, steps),
            "bw7": lambda: models.make("block-windows").forecast_multi(frames, steps)["bw7"],   # block matching, 1 h
            "block-sub-all": lambda: models.make("block-sub-all").forecast(frames, steps)}       # sub-cell matching (#24)
    fc = {m: make[m]() for m in ONLY}
    truth = [A.rate[i + k] if i + k < len(A) and not A.missing[i + k] else None for k in range(1, steps + 1)]
    rows = []
    for city, rc in CELLS.items():
        for hour in (1, 2):
            ks = range((hour - 1) * 60 // per, hour * 60 // per)          # step indices within that hour
            if any(truth[k] is None for k in ks):
                continue
            obs = sum(area_mean(truth[k], rc) for k in ks) * per / 60      # mm in the hour
            if not np.isfinite(obs):
                continue
            row = dict(event=e, issue=int(A.time(i)), city=city, hour=hour, obs=obs)
            for m in ONLY:
                row[m] = sum(area_mean(fc[m][k], rc) for k in ks) * per / 60
            rows.append(row)
    return rows


def main():
    global _A, OUT, HIST, HALF, KEEP, ONLY
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--region", choices=["clean"], help="clean: leave out fixed radar echoes")
    ap.add_argument("--update", help="comma-separated models: recompute only their columns of the existing --out file")
    ap.add_argument("--half", type=int, default=HALF, help="the city area is (2 * half + 1) cells square")
    ap.add_argument("--hist", type=int, default=HIST,
                    help="scans of history to load; 4 gives the same forecasts (the models use at most 4) with fewer pair vectors to compute")
    a = ap.parse_args()
    OUT, HIST, HALF = Path(a.out), a.hist, a.half
    KEEP = region_named(a.region)
    if a.update:
        ONLY = a.update.split(",")
        old = {(r["issue"], r["city"], r["hour"]): r for r in map(json.loads, open(OUT))}
    _A = Archive(region=KEEP)
    pairs = sorted({(r["event"], r["issue"]) for r in map(json.loads, open(ISSUES_FROM)) if r["model"] == "persistence"})
    issues = [(e, (t - _A.t0) // _A.step) for e, t in pairs]
    issues = [(e, i) for e, i in issues if _A.frames(i, HIST) is not None]
    print(f"{len(issues)} issue times, cities {CELLS}", flush=True)
    t0, rows = time.time(), []
    with mp.get_context("fork").Pool(a.procs) as pool:
        for k, r in enumerate(pool.imap_unordered(work, issues, chunksize=4)):
            rows += r
            if k % 200 == 0:
                print(f"  {k}/{len(issues)} {time.time() - t0:.0f}s", flush=True)
    if a.update:                   # same rows, same radar amounts; only the named columns change
        new = {(r["issue"], r["city"], r["hour"]): r for r in rows}
        # the archive may have grown since the file was made, giving a few more hours a radar truth; keep the file's rows
        assert old.keys() <= new.keys(), f"rows missing from the rerun: {len(old.keys() - new.keys())}"
        for k, o in old.items():
            assert abs(o["obs"] - new[k]["obs"]) < 1e-9, o
            o.update({m: new[k][m] for m in ONLY})
        rows = list(old.values())
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    OUT.with_suffix(".meta.json").write_text(json.dumps(dict(cities=CITIES, cells=CELLS, models=MODELS, hist=HIST,
                                                            grid=grid.NAME, area_cells=2 * HALF + 1, region=a.region, issues_from=str(ISSUES_FROM.name))))
    print(len(rows), "rows ->", OUT)


if __name__ == "__main__":
    main()
