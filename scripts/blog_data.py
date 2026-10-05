#!/usr/bin/env python3
"""Data drawn live by the blog page (docs/BLOG.template.html): coastlines, one real radar rain field, and the
block and whole-map motion of one real scan pair. Written to results/blog-data.json, embedded by build_blog.py.

  python scripts/blog_data.py
"""
import sys, json, datetime as dt
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from nowcastlab import models, motion
from nowcastlab.data import Archive
from nowcastlab.radar import BOUNDS
from mapstyle import _COAST, BINS
from run_cities import CITIES


def index_at(arch, *when):
    return int((dt.datetime(*when, tzinfo=dt.UTC).timestamp() - arch.t0) // arch.step)


arch = Archive(stride=1)
# the hero: a light shower day (15 September 2026, 15:00 UTC), so Denmark's coast stays visible under the rain,
# with the whole-map motion of its last half hour
i = index_at(arch, 2026, 9, 15, 15, 0)
rain = np.nan_to_num(arch.rate[i])
levels = np.digitize(rain, BINS)                                   # 0 dry, 1 light, 2 moderate, 3 heavy
vec = np.mean(models.GlobalWindows().pair_vectors([np.nan_to_num(arch.rate[j]) for j in range(i - 3, i + 1)]), axis=0)
# the arrows: the example scan pair of the report's motion figure (4 September 2026, 10:40 UTC)
k = index_at(arch, 2026, 9, 4, 10, 40)
a, b = (np.nan_to_num(arch.rate[j]) for j in (k - 1, k))
f = motion.fill_motion_field(motion.compute_block_motion(a, b, 8, 6))
w = motion.motion_weight(f.conf)
gx, gy = models.GlobalWindows().pair_vectors([a, b])[0]
blocks = []
for r in range(f.conf.shape[0]):
    for c in range(f.conf.shape[1]):
        if f.conf[r, c] > 0.3 and b[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8].mean() > 0.3:
            blocks.append([c * 8 + 3.5, r * 8 + 3.5, round(float(f.dx[r, c] * w[r, c]), 2), round(float(f.dy[r, c] * w[r, c]), 2)])

rings = _COAST["denmark"] + [r for n in _COAST["neighbours"] for r in n["rings"]]
coast = [[[round(p[0], 3), round(p[1], 3)] for p in ring[::2] + ring[-1:]] for ring in rings]
out = dict(ext=[BOUNDS["west"], BOUNDS["east"], BOUNDS["south"], BOUNDS["north"]], coast=coast,
           rain="".join(map(str, levels.ravel())), vec=[round(float(v), 3) for v in vec],
           blocks=blocks, gvec=[round(float(gx), 3), round(float(gy), 3)],
           cities=[[n, lon, lat] for n, (lat, lon) in CITIES.items()])
(ROOT / "results" / "blog-data.json").write_text(json.dumps(out, separators=(",", ":")))
print(len(blocks), "blocks; vec", out["vec"], "gvec", out["gvec"], "wet", (levels > 0).mean().round(3),
      (ROOT / "results" / "blog-data.json").stat().st_size // 1024, "KB")
