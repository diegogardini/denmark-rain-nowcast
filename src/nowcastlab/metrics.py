"""Scores for one forecast against the radar that followed it."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

from .grid import FSS_WIN, odd_cells

NB_WIN = {3: FSS_WIN[3], 5: odd_cells(16.0), 9: FSS_WIN[9], 15: odd_cells(48.0), 25: odd_cells(80.0)}   # ~10 to ~80 km; keys in 3.2 km cells
REL_BINS = 10


def _fractions(pred, truth, thr, win):
    """Wet-area fractions in win x win neighbourhoods of forecast and radar."""
    p = uniform_filter((pred >= thr).astype(np.float64), win, mode="constant")
    t = uniform_filter((truth >= thr).astype(np.float64), win, mode="constant")
    return p, t


def _fss(pred, truth, thr, win):
    """Fractions skill score: compares wet-area fractions in win x win
    neighbourhoods, so a shower displaced by a few cells is not a total miss.
    Returns (sum squared error, sum reference) so scores can be pooled."""
    p, t = _fractions(pred, truth, thr, win)
    return float(((p - t) ** 2).sum()), float((p ** 2).sum() + (t ** 2).sum())


def _neighbourhood(pb, mask, win):
    """The mean of a probability field over win x win cells, counting only cells with radar data."""
    m = mask.astype(np.float64)
    num = uniform_filter(np.where(mask, pb, 0.0), win, mode="constant")
    den = uniform_filter(m, win, mode="constant")
    return np.where(den > 0, num / np.maximum(den, 1e-12), 0.0)


def _reliability(pb, obs):
    """Per probability bin: number of cells, forecast probability summed, observed events summed."""
    b = np.minimum((pb * REL_BINS).astype(int), REL_BINS - 1)
    return ([int(x) for x in np.bincount(b, minlength=REL_BINS)],
            [float(x) for x in np.bincount(b, weights=pb, minlength=REL_BINS)],
            [float(x) for x in np.bincount(b, weights=obs, minlength=REL_BINS)])


def score(pred, truth, mask, prob=None, thr_p=0.5, bands=None, neighbourhood=False):
    """All numbers needed for pooled skill, restricted to `mask`. Counts, not
    ratios, so cases can be summed before dividing. `bands` ({name: boolean mask},
    e.g. distance from the nearest radar) adds the ~30 km FSS sums over each band."""
    out = {"sum_f": float(pred[mask].sum()), "sum_t": float(truth[mask].sum())}
    p, t = pred[mask].astype(np.float64), truth[mask].astype(np.float64)
    out["sse"] = float(((p - t) ** 2).sum())
    out["n"] = int(mask.sum())
    if p.std() > 0 and t.std() > 0:
        out["corr"] = float(np.corrcoef(p, t)[0, 1])
    else:
        out["corr"] = None
    for thr in (0.1, 0.5, 1.0):
        P, T = p >= thr, t >= thr
        out[f"hit{thr}"] = int((P & T).sum())
        out[f"miss{thr}"] = int((~P & T).sum())
        out[f"fa{thr}"] = int((P & ~T).sum())
    # Brier score for the event "rain >= thr_p": a deterministic forecast is a 0/1 probability,
    # an ensemble supplies its own exceedance probability.
    pb = (pred >= thr_p).astype(np.float64) if prob is None else np.asarray(prob, np.float64)
    obs = (truth[mask] >= thr_p).astype(np.float64)
    out["brier"] = float(((pb[mask] - obs) ** 2).sum())
    if neighbourhood:
        # neighbourhood probabilities (report, Appendix C): the chance of rain in a cell is the share of wet cells (or of wet
        # ensemble members, averaged) within a window around it, scored against that cell alone
        for k, win in NB_WIN.items():
            pn = _neighbourhood(pb, mask, win)[mask]
            out[f"brier_n{k}"] = float(((pn - obs) ** 2).sum())
            out[f"rel_n{k}"] = _reliability(pn, obs)          # every window, so each method's best can be shown (#23)
        out["rel_n1"] = _reliability(pb[mask], obs)
    pm = np.where(mask, pred, 0.0)
    tm = np.where(mask, truth, 0.0)
    for key in (3, 9):           # ~10 km and ~30 km neighbourhoods (FSS_WIN cells on this grid)
        for thr in (0.5,):
            e, r = _fss(pm, tm, thr, FSS_WIN[key])
            out[f"fss{key}_{thr}_e"], out[f"fss{key}_{thr}_r"] = e, r
    if bands:
        p, t = _fractions(pm, tm, 0.5, FSS_WIN[9])
        err, ref = (p - t) ** 2, p ** 2 + t ** 2
        for name, bm in bands.items():
            b = bm & mask
            out[f"fss9_{name}_e"], out[f"fss9_{name}_r"] = float(err[b].sum()), float(ref[b].sum())
    return out
