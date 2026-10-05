#!/usr/bin/env python3
"""Timing at one spot as a chance (report, Appendix C): "rain starts within ...", "dry within ...", "rain in the next ...".

The widget says things like "rain in ~25 min" or "dry within 40 min" from one forecast. Here those statements are
given a chance and scored in every cell of the scoring area, at every issue time of the main benchmark, for
horizons of 30, 60 and 120 minutes and rain of at least 0.1 or 0.5 mm/h:

  start    dry now, rain at some 10-minute step within the horizon (cells dry now)
  stop     raining now, and dry for good by the horizon: no rain at any step from the horizon to +2 hours, as the
           widget's "dry within 40 min" means (cells wet now)
  any      rain at some step within the horizon (all cells)

from these forecasts:

  pers      persistence: the latest scan, unchanged (start and stop never happen)
  gw        the whole-map vector (30 min of history), 0 or 1
  gw_max    the chance at each step read over a window that widens with lead time (step 1: sigma about a
            kilometre per three minutes ahead), and the largest of them over the horizon
  gw_shift  a coherent shift ensemble: 40 copies of the same forecast, each displaced by a random offset that
            grows with lead time at the same rate and keeps its direction, so each member's timing is coherent
  steps     pysteps STEPS at its defaults (24 members, motion perturbed): the share of members for which it happens

Kept per rain episode: the Brier score's sum and count and a reliability table, for calibration on the other half
of the season (local_timing_summary.py).

  python scripts/local_timing.py [PROCS]      # results/local-timing.npz
"""
import sys, json, time
import multiprocessing as mp
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import models
from nowcastlab.data import Archive, box_mask

R = ROOT / "results"
STEPS, THRS, NB, M = 12, (0.1, 0.5), 20, 40
HORIZONS = (3, 6, 12)                                    # steps of 10 minutes: 30, 60, 120 min
EVENTS = ("start", "stop", "any")
VARIANTS = ("pers", "gw", "gw_max", "gw_shift", "steps")
SIG = np.arange(1, STEPS + 1) * 10 / 3 / 3.2              # step 1's rule: sigma (cells) = lead (min) / 3 km per 3.2 km cell
_A = _MASK = None


def score(p, y):
    """Brier sum, count and reliability table (count, rain) of chances p for outcomes y (0/1)."""
    b = np.minimum((p * NB).astype(int), NB - 1)
    return np.r_[((p - y) ** 2).sum(), len(y), np.bincount(b, minlength=NB), np.bincount(b, weights=y, minlength=NB)]


def window(f, cover, s):
    num = gaussian_filter(f * cover, s, mode="constant")
    den = gaussian_filter(cover.astype(float), s, mode="constant")
    return np.clip(np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0), 0, 1)


def work(args):
    e, i = args
    if i + STEPS >= len(_A) or _A.missing[i + 1:i + STEPS + 1].any():
        return e, None
    frames = _A.frames(i, 4)
    if frames is None:
        return e, None
    fc = models.make("global-windows").forecast_multi(frames, STEPS)["gw4"]
    ens = models.make("pysteps-steps-default").forecast_ensemble(frames, STEPS, seed=int(i))
    now, truth = _A.rate[i], np.stack([_A.rate[i + k] for k in range(1, STEPS + 1)])
    m = _MASK & np.isfinite(now) & np.isfinite(truth).all(0)
    cover = np.isfinite(now)
    z = np.random.default_rng(int(i)).standard_normal((M, 2))
    yy, xx = np.mgrid[0:now.shape[0], 0:now.shape[1]].astype(float)
    out = np.zeros((len(THRS), len(EVENTS), len(HORIZONS), len(VARIANTS), 2 + 2 * NB))
    for t, thr in enumerate(THRS):
        wet_now = np.nan_to_num(now) >= thr
        obs = np.nan_to_num(truth) >= thr                                    # [step, y, x]
        f = fc >= thr
        pk = np.stack([window(f[k].astype(float), cover, SIG[k]) for k in range(STEPS)])
        shift = np.stack([np.stack([map_coordinates(f[k].astype(float), [yy + z[j, 1] * SIG[k], xx + z[j, 0] * SIG[k]], order=0, mode="constant")
                                    for k in range(STEPS)]) for j in range(M)]) > 0.5      # [member, step, y, x]
        en = ens >= thr                                                      # [member, step, y, x]
        for h, n in enumerate(HORIZONS):
            ev = {"any": obs[:n].any(0), "start": obs[:n].any(0), "stop": ~obs[n - 1:].any(0)}
            where = {"any": m, "start": m & ~wet_now, "stop": m & wet_now}
            prob = {"pers": {"any": wet_now.astype(float), "start": np.zeros(now.shape), "stop": np.zeros(now.shape)},
                    "gw": {"any": f[:n].any(0).astype(float), "start": f[:n].any(0).astype(float), "stop": (~f[n - 1:].any(0)).astype(float)},
                    "gw_max": {"any": pk[:n].max(0), "start": pk[:n].max(0), "stop": 1 - pk[n - 1:].max(0)},
                    "gw_shift": {"any": shift[:, :n].any(1).mean(0), "start": shift[:, :n].any(1).mean(0), "stop": (~shift[:, n - 1:].any(1)).mean(0)},
                    "steps": {"any": en[:, :n].any(1).mean(0), "start": en[:, :n].any(1).mean(0), "stop": (~en[:, n - 1:].any(1)).mean(0)}}
            for q, evn in enumerate(EVENTS):
                w = where[evn]
                y = ev[evn][w].astype(float)
                for v, var in enumerate(VARIANTS):
                    out[t, q, h, v] = score(prob[var][evn][w], y)
    return e, out


def main():
    global _A, _MASK
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    _A, _MASK = Archive(), box_mask()
    src = R / "benchmark-10min.jsonl"
    pairs = sorted({(r["event"], r["issue"]) for r in map(json.loads, open(src)) if r["model"] == "persistence"})
    issues = [(e, (t - _A.t0) // _A.step) for e, t in pairs]
    if len(sys.argv) > 2:
        issues = issues[:int(sys.argv[2])]
    events = sorted({e for e, _ in pairs})
    meta = json.loads(src.with_suffix(".meta.json").read_text())
    shape = (len(THRS), len(EVENTS), len(HORIZONS), len(VARIANTS), 2 + 2 * NB)
    tot = {e: np.zeros(shape) for e in events}
    t0, done = time.time(), 0
    with mp.get_context("fork").Pool(procs) as pool:
        for e, out in pool.imap_unordered(work, issues, chunksize=2):
            if out is not None:
                tot[e] += out; done += 1
            if done and done % 100 == 0:
                print(f"  {done}/{len(issues)} issues, {time.time() - t0:.0f}s", flush=True)
    np.savez_compressed(R / "local-timing.npz", events=np.array(events), event_start=np.array([meta["events"][e][0] for e in events]),
                        thresholds=np.array(THRS), event_types=np.array(EVENTS), horizons_min=np.array(HORIZONS) * 10,
                        variants=np.array(VARIANTS), data=np.stack([tot[e] for e in events]), issues=done)
    print(f"{done} issue times -> results/local-timing.npz, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
