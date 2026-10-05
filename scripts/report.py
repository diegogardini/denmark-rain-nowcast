#!/usr/bin/env python3
"""python scripts/report.py results/hindcast.jsonl > results/REPORT.md"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nowcastlab import report
rows = report.load(sys.argv[1])
print(report.markdown(report.summarize(rows)))
