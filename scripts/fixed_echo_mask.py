#!/usr/bin/env python3
"""The fixed-echo mask (report, Appendix A.3): grid cells the radar reports as wet far more often than real rain allows.

A cell is a fixed echo when it is wet (0.5 mm/h or more) in more than THRESHOLD of the scans in which almost
the whole map is dry (results/climatology.npz, from scripts/climatology.py); the mask also takes the ring of
cells around each such cell, so the edges of an echo go too. The mask uses the radar data only, never forecast
scores. Masked cells are treated as having no radar data: left out of every input and of the scoring.

  python scripts/fixed_echo_mask.py          # results/fixed-echo-mask.npy (+ .json)
"""
import sys, json
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_dilation, label

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import grid
from nowcastlab.data import box_mask

THRESHOLD = 0.01          # wet in more than 1% of almost-dry scans; 99% of the scoring area stays below about 0.13%


def main():
    c = np.load(ROOT / "results" / "climatology.npz")
    fd = np.nan_to_num(c["wet_freq_dry_map"])
    core = fd > THRESHOLD
    mask = binary_dilation(core, structure=np.ones((3, 3), bool))
    np.save(ROOT / "results" / "fixed-echo-mask.npy", mask)
    lab, n = label(core, structure=np.ones((3, 3), bool))
    LON, LAT = grid.lonlat()
    box = box_mask()
    spots = []
    for k in range(1, n + 1):
        m = lab == k
        i = np.argmax(np.where(m, fd, -1))
        r, cc = np.unravel_index(i, fd.shape)
        spots.append(dict(lat=round(float(LAT[r, cc]), 3), lon=round(float(LON[r, cc]), 3), cells=int(m.sum()),
                          peak=round(float(fd[r, cc]), 4), in_box=bool(box[r, cc])))
    spots.sort(key=lambda s: -s["peak"])
    out = dict(threshold=THRESHOLD, core_cells=int(core.sum()), masked_cells=int(mask.sum()),
               masked_in_box=int((mask & box).sum()), box_cells=int(box.sum()),
               box_p99=float(np.percentile(fd[box], 99)), spots=spots)
    (ROOT / "results" / "fixed-echo-mask.json").write_text(json.dumps(out, indent=1))
    print(f"{out['core_cells']} fixed-echo cells, {out['masked_cells']} masked with their neighbours "
          f"({out['masked_in_box']} of {out['box_cells']} scoring cells, {100 * out['masked_in_box'] / out['box_cells']:.2f}%)")
    for s in spots:
        print(f"  {s['lat']:.2f}N {s['lon']:.2f}E  {s['cells']} cells, wet on {100 * s['peak']:.1f}% of almost-dry scans{'' if s['in_box'] else '  (outside the scoring area)'}")


if __name__ == "__main__":
    main()
