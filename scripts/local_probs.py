#!/usr/bin/env python3
"""A local chance of rain from the whole-map vector (report, Appendix C).

For every issue time of the main benchmark and every 10-minute step to +2 hours, the chance of rain in each cell
of the scoring area (rain >= 0.1 or >= 0.5 mm/h), from:

  pers     persistence, 0 or 1
  gw       the whole-map vector (30 min of history), 0 or 1, then read over a window
  gwlag    the same, plus the forecasts issued 10, 20 and 30 minutes earlier as extra members (a time-lagged
           ensemble), then read over a window
  steps    pysteps STEPS at its defaults (24 members, motion perturbed): the share of members with rain, then
           read over a (round) window

The windows are Gaussian kernels: round, or stretched along the measured motion (at one spot an error in speed
shifts *when* rain arrives, which matters more than a small error in direction). Every kernel is scored, so the
best one per lead time can be chosen on one half of the season and tested on the other (local_probs_summary.py).

Kept per rain episode, kernel and lead: the Brier score's sum and count, and a reliability table (20 bins of the
forecast chance: number of cells, number with rain), from which a calibrated score can be computed exactly.

  python scripts/local_probs.py [PROCS]       # results/local-probs.npz
"""
import sys, json, time
import multiprocessing as mp
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import models
from nowcastlab.data import Archive, box_mask

R = ROOT / "results"
STEPS, LAGS, THRS, NB = 12, (1, 2, 3), (0.1, 0.5), 20
SIG = (0, 0.75, 1.5, 2.5, 4, 6, 9, 13)                   # sigma along the motion, in cells (3.2 km); 0 = the cell alone
RATIO = (1.0, 0.5)                                        # sigma across / along: 1 = round, 0.5 = stretched along the motion
STEPS_SIG = (0, 0.75, 1.5, 2.5, 4)


def kernels_for(sig, ratio):
    return [(s, r) for s in sig for r in (ratio if s else (1.0,))]


COMBOS = ([("pers", 0, 1.0)] + [("gw", s, r) for s, r in kernels_for(SIG, RATIO)] +
          [("gwlag", s, r) for s, r in kernels_for(SIG, RATIO)] + [("steps", s, 1.0) for s in STEPS_SIG])
_A = _MASK = None


def kernel(s, r, angle):
    """A normalised Gaussian kernel, sigma s along the direction `angle` (radians, in grid x/y) and r*s across."""
    h = int(np.ceil(3 * s))
    y, x = np.mgrid[-h:h + 1, -h:h + 1].astype(float)
    a = x * np.cos(angle) + y * np.sin(angle)
    c = -x * np.sin(angle) + y * np.cos(angle)
    k = np.exp(-0.5 * ((a / s) ** 2 + (c / (r * s)) ** 2))
    return k / k.sum()


def smooth(p, cover, s, r, angle):
    """Window average of p over the cells with radar coverage (so the map edge does not dilute it)."""
    if not s:
        return p
    k = kernel(s, r, angle)
    num = fftconvolve(p * cover, k, mode="same")
    den = fftconvolve(cover.astype(float), k, mode="same")
    return np.clip(np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0.0), 0, 1)


def gw_forecast(i, steps):
    fr = _A.frames(i, 4)
    if fr is None:
        return None, None
    m = models.make("global-windows")
    v = m._mean(m.pair_vectors(fr)[-3:])
    return m.forecast_multi(fr, steps)["gw4"], v


def work(args):
    e, i = args
    out = np.zeros((len(THRS), len(COMBOS), STEPS, 2 + 2 * NB))
    fc, v = gw_forecast(i, STEPS)
    if fc is None:
        return e, None
    lag = {j: gw_forecast(i - j, STEPS + j)[0] for j in LAGS}
    frames = _A.frames(i, 4)
    ens = models.make("pysteps-steps-default").forecast_ensemble(frames, STEPS, seed=int(i))      # [member, step, y, x]
    cover = np.isfinite(_A.rate[i])
    angle = float(np.arctan2(v[1], v[0])) if np.hypot(*v) > 0.2 else 0.0
    ratio_ok = np.hypot(*v) > 0.2                         # no direction to stretch along when the rain hardly moves
    for k in range(STEPS):
        j = i + k + 1
        if j >= len(_A) or _A.missing[j]:
            continue
        truth = _A.rate[j]
        m = _MASK & np.isfinite(truth)
        for t, thr in enumerate(THRS):
            y = (truth[m] >= thr).astype(float)
            base = {"pers": (frames[-1] >= thr).astype(float), "gw": (fc[k] >= thr).astype(float),
                    "steps": (ens[:, k] >= thr).mean(0)}
            members = [base["gw"]] + [(lag[jj][k + jj] >= thr).astype(float) for jj in LAGS if lag[jj] is not None]
            base["gwlag"] = np.mean(members, axis=0)
            for c, (name, s, r) in enumerate(COMBOS):
                if r != 1.0 and not ratio_ok:
                    out[t, c, k, 0] = np.nan                  # marked: falls back to the round kernel below
                    continue
                p = smooth(base[name], cover, s, r, angle)[m]
                b = np.minimum((p * NB).astype(int), NB - 1)
                out[t, c, k, 0] = ((p - y) ** 2).sum()
                out[t, c, k, 1] = len(y)
                out[t, c, k, 2:2 + NB] = np.bincount(b, minlength=NB)
                out[t, c, k, 2 + NB:] = np.bincount(b, weights=y, minlength=NB)
            for c, (name, s, r) in enumerate(COMBOS):      # stretched kernels without a direction: use the round one
                if np.isnan(out[t, c, k, 0]):
                    out[t, c, k] = out[t, COMBOS.index((name, s, 1.0)), k]
    return e, out


def main():
    global _A, _MASK
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    _A, _MASK = Archive(), box_mask()
    src = R / "benchmark-10min.jsonl"
    pairs = sorted({(r["event"], r["issue"]) for r in map(json.loads, open(src)) if r["model"] == "persistence"})
    issues = [(e, (t - _A.t0) // _A.step) for e, t in pairs]
    if len(sys.argv) > 2:                                 # a quick check on the first N issue times
        issues = issues[:int(sys.argv[2])]
    events = sorted({e for e, _ in pairs})
    meta = json.loads(src.with_suffix(".meta.json").read_text())
    tot = {e: np.zeros((len(THRS), len(COMBOS), STEPS, 2 + 2 * NB)) for e in events}
    t0, done = time.time(), 0
    with mp.get_context("fork").Pool(procs) as pool:
        for e, out in pool.imap_unordered(work, issues, chunksize=2):
            if out is not None:
                tot[e] += out
                done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(issues)} issues, {time.time() - t0:.0f}s", flush=True)
    np.savez_compressed(R / "local-probs.npz", events=np.array(events), event_start=np.array([meta["events"][e][0] for e in events]),
                        thresholds=np.array(THRS), combos=np.array([f"{n}|{s}|{r}" for n, s, r in COMBOS]),
                        data=np.stack([tot[e] for e in events]), issues=done)
    print(f"{done} issue times -> results/local-probs.npz, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
