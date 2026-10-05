"""Hindcast harness: every model, every issue time, every lead, scored against
the radar frame that actually followed, grouped by rain event."""
from __future__ import annotations

import json, time
import multiprocessing as mp
import numpy as np

from . import models, metrics, grid
from pathlib import Path
from .data import Archive, box_mask, region_named

LEADS_MIN = (30, 60, 90, 120, 180, 240, 360)
_A = None
_MASK = None
_BANDS = None         # {name: cells at that distance from the nearest radar}, see grid.BANDS
_NEIGHBOURHOOD = False  # also score neighbourhood probabilities and reliability (report, Appendix C)


def wet_fraction(archive, mask=None, thr=0.1):
    """Per-frame wet fraction of the default Denmark box (precomputed in the index)."""
    return np.nan_to_num(archive.wet, nan=0.0)


def find_events(archive, mask=None, mode="fine", min_wet=0.02, min_len_h=1.0, min_peak=0.05):
    """Rain events as [(start_idx, end_idx)].

    mode="coarse": rainy frames (>= min_wet of the box wet) merged across dry gaps
                   shorter than 3 h. Long: 13 to 96 h in the first 30 days.
    mode="fine":   merged across gaps shorter than 1 h, and any episode longer than
                   12 h is cut into consecutive 12 h blocks. Blocks of one long
                   episode are still correlated with each other, so the intervals
                   are somewhat optimistic, but there are several times more units.
    """
    gap_h, max_len_h = {"coarse": (3, None), "fine": (1, 12)}[mode]
    wf = wet_fraction(archive)
    rainy = np.flatnonzero((wf >= min_wet) & ~archive.missing)
    if not len(rainy):
        return []
    STEP = archive.step
    gap = gap_h * 3600 // STEP
    eps, s = [], rainy[0]
    p = s
    for i in rainy[1:]:
        if i - p > gap:
            eps.append((s, p)); s = i
        p = i
    eps.append((s, p))
    events = []
    for a, b in eps:
        if max_len_h and (b - a) * STEP > max_len_h * 3600:
            step = max_len_h * 3600 // STEP
            events += [(x, min(x + step - 1, b)) for x in range(a, b + 1, step)]
        else:
            events.append((a, b))
    return [(a, b) for a, b in events if (b - a) * STEP >= min_len_h * 3600 and wf[a:b + 1].max() >= min_peak]


def issue_indices(archive, events, every=3, min_wet_issue=0.01, mask=None, hist=2):
    wf = wet_fraction(archive)
    out = []
    for e, (a, b) in enumerate(events):
        for i in range(a, b + 1):
            if (i - a) % every == 0 and wf[i] >= min_wet_issue and archive.frames(i, hist) is not None:
                out.append((e, i))
    return out


def _work(args):
    e, i, names, leads, hist = args
    frames = _A.frames(i, hist)
    per = _A.step // 60                          # minutes per frame step
    steps = max(leads) // per
    rows = []
    for name in names:
        m = models.make(name)
        if getattr(m, "ensemble", False):
            ens = m.forecast_ensemble(frames, steps, seed=int(i))
            variants = {name + "-mean": (ens.mean(0), (ens >= 0.5).mean(0)), name + "-member": (ens[0], None)}
        elif getattr(m, "multi", False):
            variants = {k: (v, None) for k, v in m.forecast_multi(frames, steps).items()}
        else:
            variants = {name: (m.forecast(frames, steps), None)}
        fb = bool(getattr(m, "fallback", False))
        for vname, (fc, prob) in variants.items():
            for L in leads:
                j, k = i + L // per, L // per - 1
                if j >= len(_A) or _A.missing[j]:
                    continue
                truth = _A.rate[j]
                mask = _MASK & np.isfinite(truth)        # score only where the radar saw
                s = metrics.score(fc[k], truth, mask, prob=None if prob is None else prob[k], bands=_BANDS,
                                  neighbourhood=_NEIGHBOURHOOD)
                s.update(event=e, issue=int(_A.time(i)), model=vname, lead=L, fallback=fb)
                rows.append(s)
    return rows


def run(names, leads=LEADS_MIN, days=None, every=3, procs=10, out=None, log=print, event_mode="fine", hist=2, stride=2,
        region=None, issues_from=None, neighbourhood=False):
    """region: "common" restricts frames and scoring to cells covered by both kinds of DMI scan; "clean"
    leaves out the cells with a fixed radar echo (results/fixed-echo-mask.npy).
    issues_from: a results .jsonl whose (event, issue time) pairs are reused, so runs on
    different time axes score exactly the same forecasts moments."""
    global _A, _MASK, _BANDS, _NEIGHBOURHOOD
    _NEIGHBOURHOOD = neighbourhood
    arch = _A = Archive(days=days, stride=stride, region=region_named(region))
    per = arch.step // 60
    if any(L % per for L in leads):
        raise ValueError(f"leads must be multiples of the {per}-minute frame step")
    models.STEP_MIN = per
    mask = _MASK = box_mask()
    dist = grid.radar_distance()
    _BANDS = {name: (dist >= lo) & (dist < hi) for name, (lo, hi) in grid.BANDS.items()}
    if issues_from:
        src = json.loads(open(Path(issues_from).with_suffix(".meta.json")).read())
        events = [((a - arch.t0) // arch.step, (b - arch.t0) // arch.step) for a, b in src["events"]]
        pairs = {(r["event"], r["issue"]) for r in map(json.loads, open(issues_from))}
        issues = sorted((e, (t - arch.t0) // arch.step) for e, t in pairs)
        issues = [(e, i) for e, i in issues if arch.frames(i, hist) is not None]
        log(f"reusing {len(pairs)} issue times from {issues_from}; {len(issues)} have {hist} scans of history")
    else:
        events = find_events(arch, mask, mode=event_mode)
        issues = issue_indices(arch, events, every, mask=mask, hist=hist)
    log(f"{len(arch)} frames every {per} min, {int(arch.missing.sum())} missing, {len(events)} events, {len(issues)} issue times")
    t0 = time.time()
    rows = []
    # fork: workers share the (large) archive copy-on-write instead of each loading it
    with mp.get_context("fork").Pool(procs) as pool:
        for k, r in enumerate(pool.imap_unordered(_work, [(e, i, names, leads, hist) for e, i in issues], chunksize=4)):
            rows += r
            if k % 50 == 0:
                log(f"  {k}/{len(issues)} issues, {time.time() - t0:.0f}s")
    if out:
        with open(out, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    meta = dict(event_mode=event_mode, step_min=per, hist=hist, every=every, region=region, issues_from=issues_from,
                grid=grid.NAME, km_per_cell=grid.KM, block=grid.BLOCK, radius=grid.RADIUS, fss_win=grid.FSS_WIN, events=[(int(arch.time(a)), int(arch.time(b))) for a, b in events])
    return rows, meta
