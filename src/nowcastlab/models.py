"""Nowcast models behind one interface.

    model.forecast(frames, steps) -> array [steps, H, W] of rain rate (mm/h)

`frames` is a list of past grids, oldest first, equally spaced (STEP_MIN
minutes). The last frame is "now". A model may use as many past frames as it
likes; the plugin's models use only the last two. Motion is in grid cells per
frame step, so nothing but STEPS needs to know the step length.
"""
from __future__ import annotations

import numpy as np
from . import motion as M
from . import grid

STEP_MIN = 10       # minutes between frames; the harness sets it from the archive


class Persistence:
    name = "persistence"

    def forecast(self, frames, steps):
        return np.repeat(frames[-1][None].astype(np.float32), steps, axis=0)


def _walk(frame, steps, vec_at, zero_outside=False):
    """Semi-Lagrangian backward tracing, as extrapolateSequence: each output
    cell walks back along the motion field one step per lead step and reads
    the last observed frame once (no repeated resampling, so no blurring).
    `vec_at(x, y)` returns the per-cell displacement (dx, dy) at positions."""
    h, w = frame.shape
    # Positions are carried between steps as float32 (as the JS Float32Array
    # does) but sampled at the unrounded value, so results match bit for bit
    # in practice.
    yy, xx = (a.astype(np.float32) for a in np.mgrid[0:h, 0:w])
    out = np.empty((steps, h, w), np.float32)
    f = frame.astype(np.float64)
    for s in range(steps):
        dx, dy = vec_at(xx.astype(np.float64), yy.astype(np.float64))
        nx = xx.astype(np.float64) - dx
        ny = yy.astype(np.float64) - dy
        xx, yy = nx.astype(np.float32), ny.astype(np.float32)
        val = M.sample_bilinear(f, nx, ny)
        if zero_outside:      # no rain enters from beyond the map edge (pysteps does the same)
            val = val * ((nx >= 0) & (nx <= w - 1) & (ny >= 0) & (ny <= h - 1))
        out[s] = np.maximum(0.0, val)
    return out


class BlockMatch:
    """The plugin's model: per-block motion field (smoothed, extended over dry
    ground), each block moved at its own confidence-weighted vector."""
    name = "block"
    subcell = False                       # refine each block's match to a fraction of a cell (report, Appendix B.4)

    def __init__(self, block=grid.BLOCK, radius=grid.RADIUS):     # 8 and 6 cells on the 3.2 km grid
        self.block, self.radius = block, radius

    def field(self, frames):
        f = M.compute_block_motion(frames[-2], frames[-1], self.block, self.radius, subcell=self.subcell)
        return M.fill_motion_field(f)

    def forecast(self, frames, steps):
        return self.move(frames, self.field(frames), steps)

    def move(self, frames, f, steps):
        """Move the latest scan along a per-block field."""
        wdx = f.dx * M.motion_weight(f.conf)
        wdy = f.dy * M.motion_weight(f.conf)
        moving = f.conf > 0
        b = self.block
        br, bc = f.conf.shape

        def vec_at(x, y):
            ci = np.clip(np.floor(np.clip(np.floor(x + 0.5), 0, frames[-1].shape[1] - 1) / b).astype(int), 0, bc - 1)
            ri = np.clip(np.floor(np.clip(np.floor(y + 0.5), 0, frames[-1].shape[0] - 1) / b).astype(int), 0, br - 1)
            mv = moving[ri, ci]
            return np.where(mv, wdx[ri, ci], 0.0), np.where(mv, wdy[ri, ci], 0.0)

        return _walk(frames[-1], steps, vec_at)


class BlockWindows(BlockMatch):
    """Block matching over several scan pairs (report, Appendix B.1): each pair is matched on its own, each block's
    vector is averaged over the pairs of the window, weighted by match confidence (its confidence is the mean
    over the pairs, so a block matched in only one pair counts for less), and only then are the neighbour
    borrowing and the fill applied. "bwN" uses the last N scans; bw2 is block matching itself."""
    name = "block-windows"
    multi = True
    windows = (2, 4, 7, 13)               # scans; at 10 min, 4 = 30 minutes, 7 = one hour

    def forecast_multi(self, frames, steps):
        raw = [M.compute_block_motion(frames[k], frames[k + 1], self.block, self.radius, smooth=False)
               for k in range(len(frames) - 1)]
        out = {}
        for n in self.windows:
            if n - 1 > len(raw):
                continue
            fs = raw[len(raw) - (n - 1):]
            conf = np.stack([f.conf for f in fs])
            sw = conf.sum(0)
            with np.errstate(invalid="ignore", divide="ignore"):
                dx = np.where(sw > 0, sum(f.dx * f.conf for f in fs) / sw, 0.0)
                dy = np.where(sw > 0, sum(f.dy * f.conf for f in fs) / sw, 0.0)
            f = M.BlockField(dx, dy, conf.mean(0), self.block)
            out[f"bw{n}"] = self.move(frames, M.fill_motion_field(M.smooth_block_motion(f, 2)), steps)
        return out


class GlobalVector(BlockMatch):
    """Same measurement, but one shared vector for the whole map."""
    name = "global"

    def forecast(self, frames, steps):
        v = M.global_vector(self.field(frames)) or (0.0, 0.0)
        return _walk(frames[-1], steps, lambda x, y: (v[0], v[1]))


class GlobalVectorAvg(BlockMatch):
    """Control: the global vector averaged over the last three frame pairs (4 frames),
    to give our model the same history the pysteps models get."""
    name = "global4"

    def forecast(self, frames, steps):
        vs = []
        n = len(frames)
        for k in range(max(0, n - 4), n - 1):
            v = M.global_vector(M.fill_motion_field(M.compute_block_motion(frames[k], frames[k + 1], self.block, self.radius)))
            if v is not None:
                vs.append(v)
        v = (float(np.mean([a for a, _ in vs])), float(np.mean([b for _, b in vs]))) if vs else (0.0, 0.0)
        return _walk(frames[-1], steps, lambda x, y: (v[0], v[1]))


class GlobalWindows(BlockMatch):
    """Many motion-window lengths from one set of pair measurements.

    The global vector of every consecutive frame pair is measured once, then
    combined in different ways: the plain mean over the last n-1 pairs ("gwN"),
    or an exponentially recency-weighted mean over all pairs with a half-life of
    h pairs ("gwxH"). Used to find how much history helps.
    """
    name = "global-windows"
    multi = True
    windows = (2, 3, 4, 5, 7, 10, 13)        # scans; at 10 min, 7 = one hour, 13 = two
    half_lives = (3, 6)
    zero_outside = False
    suffix = ""

    def pair_vectors(self, frames):
        """The whole-map vector of each pair: every block's own whole-cell match, weighted by its match
        confidence. Not the smoothed and filled per-block field: averaged into one vector, that pulls it
        toward the mean of neighbouring blocks' differing vectors, which is shorter (report, Appendix B.4)."""
        out = []
        for k in range(len(frames) - 1):
            f = M.compute_block_motion(frames[k], frames[k + 1], self.block, self.radius, smooth=False, subcell=self.subcell)
            m = f.conf > 0
            out.append((float((f.dx[m] * f.conf[m]).sum() / f.conf[m].sum()),
                        float((f.dy[m] * f.conf[m]).sum() / f.conf[m].sum())) if m.any() else None)
        return out                              # oldest pair first, None where nothing was measurable

    @staticmethod
    def _mean(vs, w=None):
        pairs = [(v, (1.0 if w is None else w[i])) for i, v in enumerate(vs) if v is not None]
        if not pairs:
            return (0.0, 0.0)
        tw = sum(x for _, x in pairs)
        return (sum(v[0] * x for v, x in pairs) / tw, sum(v[1] * x for v, x in pairs) / tw)

    def forecast_multi(self, frames, steps):
        vs = self.pair_vectors(frames)
        out = {}
        for n in self.windows:
            if n - 1 > len(vs):
                continue
            v = self._mean(vs[len(vs) - (n - 1):])
            out[f"gw{n}{self.suffix}"] = _walk(frames[-1], steps, lambda x, y, v=v: (v[0], v[1]), self.zero_outside)
        for h in self.half_lives:
            w = [0.5 ** ((len(vs) - 1 - i) / h) for i in range(len(vs))]
            v = self._mean(vs, w)
            out[f"gwx{h}{self.suffix}"] = _walk(frames[-1], steps, lambda x, y, v=v: (v[0], v[1]), self.zero_outside)
        return out


class BlockSub(BlockMatch):
    """Block matching with each block's match refined to a fraction of a cell (report, Appendix B.4)."""
    name = "block-sub"
    subcell = True


class GlobalWindowsSub(GlobalWindows):
    """The whole-map vector from sub-cell block matches ("gwNsub")."""
    name = "global-windows-sub"
    windows = (2, 4, 7)
    half_lives = ()
    suffix = "sub"
    subcell = True


class BlockSubAll(BlockMatch):
    """block-sub, also refining blocks whose best whole-cell match is no shift (report, Appendix B.4)."""
    name = "block-sub-all"
    subcell = "all"


class GlobalWindowsSubAll(GlobalWindowsSub):
    """global-windows-sub, also refining blocks whose best whole-cell match is no shift ("gwNsuba")."""
    name = "global-windows-sub-all"
    suffix = "suba"
    subcell = "all"


class GlobalWindowsSmoothed(GlobalWindows):
    """The whole-map vector averaged from the smoothed and filled per-block field, as the block model uses it
    ("gwNf"): a comparison for the report's Appendix B.4."""
    name = "global-windows-smoothed"
    windows = (2, 4, 7)
    half_lives = ()
    suffix = "f"

    def pair_vectors(self, frames):
        return [M.global_vector(M.fill_motion_field(M.compute_block_motion(frames[k], frames[k + 1], self.block, self.radius)))
                for k in range(len(frames) - 1)]


class GlobalScaled(GlobalWindows):
    """The 30-minute whole-map vector, and the same vector sped up by 5, 10 and 15% (gw4s105, ...): a test of
    whether its speed is biased low (report, Appendix B.4)."""
    name = "global-scaled"
    factors = (1.0, 1.05, 1.1, 1.15)

    def forecast_multi(self, frames, steps):
        vs = self.pair_vectors(frames)
        v = self._mean(vs[-3:])
        return {f"gw4s{int(round(k * 100))}": _walk(frames[-1], steps, lambda x, y, k=k: (v[0] * k, v[1] * k)) for k in self.factors}


class GlobalWindowsZero(GlobalWindows):
    """Same as GlobalWindows, but rain never enters from beyond the map edge (the edge value is not
    repeated). A check on whether edge replication inflates the rain total."""
    name = "global-windows-zero"
    windows = (2, 13)
    half_lives = ()
    zero_outside = True
    suffix = "z"


class SmoothedBlock(BlockMatch):
    """Block field interpolated bilinearly between block centres, so the motion changes smoothly
    across block edges instead of jumping there (the blended field of the report's Appendix B.3)."""
    name = "block-smooth"

    def forecast(self, frames, steps):
        return self.move(frames, self.field(frames), steps)

    def move(self, frames, f, steps):
        """Move the latest scan along a per-block field."""
        wdx = f.dx * M.motion_weight(f.conf) * (f.conf > 0)
        wdy = f.dy * M.motion_weight(f.conf) * (f.conf > 0)
        b = self.block
        br, bc = f.conf.shape

        def vec_at(x, y):
            fx = np.clip(x / b - 0.5, 0, bc - 1)
            fy = np.clip(y / b - 0.5, 0, br - 1)
            return M.sample_bilinear(wdx, fx, fy), M.sample_bilinear(wdy, fx, fy)

        return _walk(frames[-1], steps, vec_at)


class _Pysteps:
    """State-of-the-art baselines from the open-source pysteps library
    (Pulkkinen et al., 2019, GMD). They use the last `history` frames (4 = 20 min)
    where the plugin-derived models use two, which is how they are normally run."""
    history = 4
    ensemble = False

    def __init__(self):
        self.fallback = False

    def _prep(self, frames):
        from pysteps.utils import transformation
        if len(frames) < self.history:
            raise ValueError(f"{self.name} needs {self.history} frames, got {len(frames)}")
        fr = np.stack(frames[-self.history:]).astype(np.float64)
        rdb, meta = transformation.dB_transform(fr, threshold=0.1, zerovalue=-15.0)
        return fr, rdb, meta

    def _flow(self, rdb):
        from pysteps import motion
        return motion.get_method("LK")(rdb)

    @staticmethod
    def _back(field_db, meta):
        out = 10.0 ** (np.asarray(field_db, np.float64) / 10.0)
        out[~np.isfinite(out)] = 0.0
        out[out < 0.1] = 0.0
        return out.astype(np.float32)


def _quiet():
    import contextlib, io
    return contextlib.redirect_stdout(io.StringIO())


class PystepsLK(_Pysteps):
    """Lucas-Kanade optical flow (dense, sub-pixel), semi-Lagrangian extrapolation of the latest frame."""
    name = "pysteps-lk"

    def forecast(self, frames, steps):
        fr, rdb, meta = self._prep(frames)
        from pysteps import nowcasts
        try:
            with _quiet():
                v = self._flow(rdb)
                out = nowcasts.get_method("extrapolation")(fr[-1], v, steps)
            self.fallback = False
            return np.nan_to_num(out, nan=0.0).astype(np.float32)
        except Exception:
            self.fallback = True
            return Persistence().forecast(frames, steps)


class PystepsLK2(PystepsLK):
    """Control: the same Lucas-Kanade model, given only the last two frames like our models."""
    name = "pysteps-lk2"
    history = 2


class PystepsLK7(PystepsLK):
    name = "pysteps-lk7"
    history = 7


class PystepsLK8(PystepsLK):
    name = "pysteps-lk8"
    history = 8


class PystepsLK13(PystepsLK):
    name = "pysteps-lk13"
    history = 13


class PystepsSPROG(_Pysteps):
    """S-PROG: extrapolation plus an AR(2) model per spatial scale, so small scales decay faster with lead time."""
    name = "pysteps-sprog"

    def forecast(self, frames, steps):
        fr, rdb, meta = self._prep(frames)
        from pysteps import nowcasts
        try:
            with _quiet():
                v = self._flow(rdb)
                out = nowcasts.get_method("sprog")(rdb[-3:], v, steps, n_cascade_levels=6, precip_thr=meta["threshold"])
            self.fallback = False
            return self._back(out, meta)
        except Exception:
            self.fallback = True
            return Persistence().forecast(frames, steps)


class PystepsSTEPS(_Pysteps):
    """STEPS: S-PROG plus scale-dependent stochastic noise, an ensemble of equally likely futures."""
    name = "pysteps-steps"
    ensemble = True
    members = 8
    vel_pert = None                     # pysteps' default is "bps" (see pysteps-steps-bps and pysteps-steps-default)

    def __init__(self, members=None):
        super().__init__()
        if members is not None:
            self.members = members

    def forecast_ensemble(self, frames, steps, seed=0):
        fr, rdb, meta = self._prep(frames)
        from pysteps import nowcasts
        try:
            with _quiet():
                v = self._flow(rdb)
                out = nowcasts.get_method("steps")(
                    rdb[-3:], v, steps, n_ens_members=self.members, n_cascade_levels=6, precip_thr=meta["threshold"],
                    kmperpixel=grid.KM, timestep=STEP_MIN, noise_method="nonparametric", vel_pert_method=self.vel_pert,
                    mask_method="incremental", seed=seed, num_workers=1)
            self.fallback = False
            return self._back(out, meta)
        except Exception:
            self.fallback = True
            p = Persistence().forecast(frames, steps)
            return np.repeat(p[None], self.members, axis=0)


class PystepsSTEPSBps(PystepsSTEPS):
    """STEPS with pysteps' default motion perturbation ("bps"), still 8 members."""
    name = "pysteps-steps-bps"
    vel_pert = "bps"


class PystepsSTEPSDefault(PystepsSTEPS):
    """STEPS at pysteps' defaults: 24 members and the "bps" motion perturbation."""
    name = "pysteps-steps-default"
    members = 24
    vel_pert = "bps"


REGISTRY = {m.name: m for m in (Persistence, BlockMatch, GlobalVector, GlobalVectorAvg, SmoothedBlock, PystepsLK, PystepsLK2, PystepsLK7, PystepsLK8, PystepsLK13, PystepsSPROG, PystepsSTEPS, GlobalWindows, GlobalWindowsZero, GlobalScaled, GlobalWindowsSmoothed, BlockSub, GlobalWindowsSub, BlockSubAll, GlobalWindowsSubAll, BlockWindows, PystepsSTEPSBps, PystepsSTEPSDefault)}


def _sized(base, km):
    """A block model with blocks of about `km` on the current grid (block-size study, Appendix B.3)."""
    cells = grid.cells(km)
    return type(f"{base.__name__}{int(km)}", (base,), dict(name=f"{base.name}-{int(km)}km", __init__=lambda self, block=cells, radius=grid.RADIUS: base.__init__(self, block, radius)))


# block-13km, block-51km, block-102km (4, 16, 32 cells at 3.2 km; block itself is 26 km, 8 cells) and blended variants
for _km in (13, 26, 51, 102):
    for _base in (BlockMatch, SmoothedBlock):
        _m = _sized(_base, _km)
        REGISTRY[_m.name] = _m


def make(name, **kw):
    return REGISTRY[name](**kw)
