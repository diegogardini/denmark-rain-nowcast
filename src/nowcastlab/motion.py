"""Motion estimation: a faithful port of legacy/js/Interpolation.js.

Everything is in grid-cell units per frame step. Block arrays are shaped
[block_rows, block_cols]. Ported first for exact parity with the plugin, then
varied by the models in models.py.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class BlockField:
    dx: np.ndarray
    dy: np.ndarray
    conf: np.ndarray
    block: int

    def copy(self):
        return BlockField(self.dx.copy(), self.dy.copy(), self.conf.copy(), self.block)


def sample_bilinear(grid, colf, rowf):
    """Bilinear sample with edge clamping (as sampleBilinear in Interpolation.js)."""
    h, w = grid.shape
    c = np.clip(colf, 0, w - 1)
    r = np.clip(rowf, 0, h - 1)
    c0 = np.floor(c).astype(int)
    r0 = np.floor(r).astype(int)
    c1 = np.minimum(c0 + 1, w - 1)
    r1 = np.minimum(r0 + 1, h - 1)
    tc = c - c0
    tr = r - r0
    top = grid[r0, c0] + (grid[r0, c1] - grid[r0, c0]) * tc
    bot = grid[r1, c0] + (grid[r1, c1] - grid[r1, c0]) * tc
    return top + (bot - top) * tr


def compute_block_motion(a, b, block=8, radius=4, smooth=True, subcell=False):
    """Block matching from frame a to frame b, then neighbour smoothing (smooth=False returns each
    block's own match, for measuring how motion varies between blocks without the smoothing
    making neighbours agree). subcell=True refines each moved block's whole-cell match to a fraction of a
    cell: a parabola through the mismatch at the best shift and its two neighbours, in each direction
    (at most half a cell; not at the edge of the search window). subcell="all" also refines blocks whose
    best whole-cell match is no shift, with the parabola's predicted drop in mismatch as their match.

    Confidence = relative SSD improvement of the best offset over staying put
    (see the long comment in Interpolation.js matchBlock for why nothing else).
    """
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    h, w = a.shape
    br, bc = -(-h // block), -(-w // block)
    ph, pw = br * block, bc * block
    offs = [(dy, dx) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]

    def block_sum(x):
        p = np.zeros((ph, pw))
        p[:h, :w] = x
        return p.reshape(br, block, bc, block).sum(axis=(1, 3))

    ssd = np.empty((len(offs), br, bc))
    # b shifted by (dy, dx) with edge values repeated: the same as indexing b with clipped rows and
    # columns, but padding once and slicing is much faster on large grids
    bp = np.pad(b, radius, mode="edge")
    for i, (dy, dx) in enumerate(offs):
        shifted = bp[radius + dy:radius + dy + h, radius + dx:radius + dx + w]
        ssd[i] = block_sum((a - shifted) ** 2)
    base_i = offs.index((0, 0))
    base = ssd[base_i]
    n = block_sum(np.ones((h, w)))
    mean = block_sum(a) / np.maximum(n, 1)

    best_i = np.argmin(ssd, axis=0)          # first minimum, same order as the JS loops
    best = np.take_along_axis(ssd, best_i[None], 0)[0]
    moved = best < base                       # JS only replaces on a strict improvement
    dy_tab = np.array([o[0] for o in offs], float)
    dx_tab = np.array([o[1] for o in offs], float)
    dy = np.where(moved, dy_tab[best_i], 0.0)
    dx = np.where(moved, dx_tab[best_i], 0.0)
    if subcell:
        n = 2 * radius + 1
        cube = ssd.reshape(n, n, br, bc)                  # [dy + radius, dx + radius, block row, block col]
        iy, ix = best_i // n, best_i % n
        rr, cc = np.indices((br, bc))
        # "all" also refines blocks whose best whole-cell match is no shift: the parabola's own minimum
        # gives them a match (and a confidence) where the whole-cell search found none
        cand = moved | ((subcell == "all") & (base > 0))
        drop = np.zeros((br, bc))
        for axis, (d, i) in enumerate(((dy, iy), (dx, ix))):
            inner = cand & (i > 0) & (i < n - 1)
            lo, hi = np.clip(i - 1, 0, n - 1), np.clip(i + 1, 0, n - 1)
            if axis == 0:
                sm, s0, sp = cube[lo, ix, rr, cc], cube[iy, ix, rr, cc], cube[hi, ix, rr, cc]
            else:
                sm, s0, sp = cube[iy, lo, rr, cc], cube[iy, ix, rr, cc], cube[iy, hi, rr, cc]
            den = sm - 2 * s0 + sp
            ok = inner & (den > 0)
            with np.errstate(divide="ignore", invalid="ignore"):
                off = np.where(ok, np.clip(0.5 * (sm - sp) / den, -0.5, 0.5), 0.0)
                drop += np.where(ok, np.maximum(0.0, (sm - sp) * off / 2 - den * off ** 2 / 2), 0.0)
            d += off
        if subcell == "all":
            still = ~moved & cand & (drop > 0)
            best = np.where(still, base - np.minimum(drop, base), best)
            moved = moved | still
    best_ssd = np.where(moved, best, base)
    with np.errstate(divide="ignore", invalid="ignore"):
        conf = np.where(base > 0, (base - best_ssd) / base, 0.0)
    conf = np.clip(conf, 0, 1)
    dry = mean < 0.05
    dx[dry] = dy[dry] = conf[dry] = 0.0
    field = BlockField(dx, dy, conf, block)
    return smooth_block_motion(field, 2) if smooth else field


def smooth_block_motion(f, radius, trust=0.5):
    """Low-confidence blocks borrow from confident neighbours (smoothBlockMotion)."""
    br, bc = f.conf.shape
    out = f.copy()
    for r in range(br):
        for c in range(bc):
            if f.conf[r, c] >= trust:
                continue
            sx = sy = sw = mx = 0.0
            for rr in range(max(0, r - radius), min(br, r + radius + 1)):
                for cc in range(max(0, c - radius), min(bc, c + radius + 1)):
                    if (rr, cc) == (r, c) or f.conf[rr, cc] <= 0:
                        continue
                    k = f.conf[rr, cc]
                    sx += f.dx[rr, cc] * k
                    sy += f.dy[rr, cc] * k
                    sw += k
                    mx = max(mx, k)
            if sw > 0:
                inherited = min(0.6, mx * 0.8)
                out.dx[r, c] = sx / sw
                out.dy[r, c] = sy / sw
                out.conf[r, c] = max(f.conf[r, c], inherited)
    return out


def fill_motion_field(f):
    """Extend motion over empty blocks so rain keeps moving over dry ground (fillMotionField)."""
    br, bc = f.conf.shape
    cur = f.copy()
    for _ in range(br + bc):
        nxt = cur.copy()
        changed = False
        for r in range(br):
            for c in range(bc):
                if cur.conf[r, c] > 0:
                    continue
                sx = sy = sw = best = 0.0
                for rr in range(max(0, r - 1), min(br, r + 2)):
                    for cc in range(max(0, c - 1), min(bc, c + 2)):
                        if (rr, cc) == (r, c) or cur.conf[rr, cc] <= 0:
                            continue
                        k = cur.conf[rr, cc]
                        sx += cur.dx[rr, cc] * k
                        sy += cur.dy[rr, cc] * k
                        sw += k
                        best = max(best, k)
                if sw > 0:
                    nxt.dx[r, c] = sx / sw
                    nxt.dy[r, c] = sy / sw
                    nxt.conf[r, c] = min(0.6, best * 0.95)
                    changed = True
        cur = nxt
        if not changed:
            break
    return cur


def motion_weight(conf):
    return np.clip(conf / 0.3, 0.0, 1.0)


def global_vector(f):
    """Confidence-weighted mean displacement over all blocks (None if none measured)."""
    m = f.conf > 0
    sw = f.conf[m].sum()
    if sw <= 0:
        return None
    w = motion_weight(f.conf[m])
    return (float((f.dx[m] * w * f.conf[m]).sum() / sw), float((f.dy[m] * w * f.conf[m]).sum() / sw))
