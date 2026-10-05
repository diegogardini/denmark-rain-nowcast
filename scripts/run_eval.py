#!/usr/bin/env python3
"""python scripts/run_eval.py [--days 20260825,...] [--every 3] [--models a,b] [--out results/x.jsonl]"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nowcastlab import evaluate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days"); ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--models", default="persistence,block,global,block-smooth")
    ap.add_argument("--procs", type=int, default=10)
    ap.add_argument("--leads", default="30,60,90,120,180,240,360"); ap.add_argument("--hist", type=int, default=2)
    ap.add_argument("--events", default="fine", choices=["fine", "coarse"])
    ap.add_argument("--stride", type=int, default=2, help="2: 10-minute axis of full scans; 1: every 5-minute scan")
    ap.add_argument("--region", choices=["common", "clean"],
                    help="common: cells covered by both kinds of scan; clean: leave out fixed radar echoes")
    ap.add_argument("--issues-from", help="reuse the issue times of this results file")
    ap.add_argument("--out", default="results/hindcast.jsonl")
    ap.add_argument("--neighbourhood", action="store_true", help="also score neighbourhood probabilities and reliability")
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    rows, meta = evaluate.run(a.models.split(","), days=a.days.split(",") if a.days else None,
                              every=a.every, procs=a.procs, out=a.out, event_mode=a.events, leads=tuple(int(x) for x in a.leads.split(',')), hist=a.hist, stride=a.stride, region=a.region, issues_from=a.issues_from,
                              neighbourhood=a.neighbourhood,
                              log=lambda m: print(m, flush=True))
    Path(a.out).with_suffix(".meta.json").write_text(json.dumps(meta))
    print(len(rows), "scored forecasts ->", a.out)


if __name__ == "__main__":
    main()
