#!/usr/bin/env python3
"""Two robustness checks on existing results (report, section 6).

1. Resampling units (#10). The 95% intervals resample event blocks, but blocks cut from one long rainy spell
   are related. The same intervals are recomputed resampling whole calendar days (UTC), and whole rainy spells
   (event blocks less than 3 hours apart merged).
2. Held-out months (#11). Every setting chosen on the data is chosen again on April to June only (the best
   FSS gain over persistence at +60 minutes, about 30 km) and scored on July to September, and the other way
   round. The regret is how much the held-out half loses against the setting that would have been best on it.
   The methods, each at its setting chosen on the other half, are then compared on the held-out half alone.

  python scripts/robustness.py          # results/robustness.json, and tables on stdout
"""
import sys, json, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"
N_BOOT, SEED = 2000, 11
SPELL_GAP = 3 * 3600


def load(stem):
    rows = [json.loads(l) for l in open(R / f"{stem}.jsonl")]
    meta = json.loads((R / f"{stem}.meta.json").read_text())
    return rows, meta["events"]


def sums(rows, models, leads):
    """{(model, lead): {event: [mismatch, reference]}} for FSS over about 30 km."""
    out = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for r in rows:
        if r["model"] in models and r["lead"] in leads and "fss9_0.5_e" in r:
            a = out[(r["model"], r["lead"])][r["event"]]
            a[0] += r["fss9_0.5_e"]; a[1] += r["fss9_0.5_r"]
    return out


def units_of(events, kind):
    """Map event index -> resampling unit."""
    if kind == "block":
        return {i: i for i in range(len(events))}
    if kind == "day":
        return {i: dt.datetime.fromtimestamp(s, dt.UTC).strftime("%Y-%m-%d") for i, (s, e) in enumerate(events)}
    order = sorted(range(len(events)), key=lambda i: events[i][0])
    unit, spell, last_end = {}, -1, None
    for i in order:
        s, e = events[i]
        if last_end is None or s - last_end > SPELL_GAP:
            spell += 1
        unit[i] = spell
        last_end = e if last_end is None else max(last_end, e)
    return unit


def gain(S, m, lead, ev, base="persistence"):
    f = lambda k: 1 - sum(S[(k, lead)][e][0] for e in ev) / sum(S[(k, lead)][e][1] for e in ev)
    return f(m) - f(base)


class Boot:
    """Pooled FSS differences with an interval from resampling units (clusters of events)."""

    def __init__(self, S, events_used, unit):
        self.S = S
        self.ids = sorted({unit[e] for e in events_used}, key=str)
        self.col = {u: j for j, u in enumerate(self.ids)}
        self.unit = unit
        rng = np.random.default_rng(SEED)
        n = len(self.ids)
        draws = rng.integers(0, n, size=(N_BOOT, n))
        self.C = np.zeros((N_BOOT, n))
        for b in range(N_BOOT):
            self.C[b] = np.bincount(draws[b], minlength=n)

    def vec(self, m, lead):
        v = np.zeros((len(self.ids), 2))
        for e, (x, y) in self.S[(m, lead)].items():
            if e in self.unit and self.unit[e] in self.col:
                v[self.col[self.unit[e]]] += (x, y)
        return v

    def diff(self, a, b, lead):
        """FSS(a) - FSS(b) pooled, the 95% interval, its width."""
        A, B = self.vec(a, lead), self.vec(b, lead)
        d0 = (1 - A[:, 0].sum() / A[:, 1].sum()) - (1 - B[:, 0].sum() / B[:, 1].sum())
        ds = (1 - self.C @ A[:, 0] / (self.C @ A[:, 1])) - (1 - self.C @ B[:, 0] / (self.C @ B[:, 1]))
        lo, hi = np.percentile(ds, [2.5, 97.5])
        return dict(d=float(d0), lo=float(lo), hi=float(hi), width=float(hi - lo))


# ------------------------------------------------------------------ 1. resampling units
def intervals():
    rows, events = load("benchmark-10min")
    models = ["persistence", "bw7", "gw4", "pysteps-lk", "pysteps-steps-mean"]
    S = sums(rows, set(models), {60, 180})
    used = {e for k in S for e in S[k]}
    out = {"units": {}, "gain": {}, "paired": {}}
    comps = [("pysteps-lk", "bw7"), ("pysteps-lk", "gw4"), ("bw7", "gw4")]
    for kind in ("block", "day", "spell"):
        unit = units_of(events, kind)
        B = Boot(S, used, unit)
        out["units"][kind] = len(B.ids)
        for lead in (60, 180):
            for m in models[1:]:
                out["gain"].setdefault(f"{m}_at_{lead}", {})[kind] = B.diff(m, "persistence", lead)
            for a, b in comps:
                out["paired"].setdefault(f"{a}_vs_{b}_at_{lead}", {})[kind] = B.diff(a, b, lead)
    return out


# ------------------------------------------------------------------ 2. held-out months
DECISIONS = [
    ("block matching: history", "benchmark-10min-window", ["bw2", "bw4", "bw7", "bw13"], "bw7"),
    ("whole-map vector: history", "benchmark-10min-window", ["gw2", "gw3", "gw4", "gw5", "gw7", "gw10", "gw13", "gwx3", "gwx6"], "gw4"),
    ("pysteps Lucas-Kanade: history", "benchmark-10min-window", ["pysteps-lk", "pysteps-lk7", "pysteps-lk13"], "pysteps-lk"),
    ("whole-map vector: own matches or smoothed field", "benchmark-10min", ["gw4", "gw4f"], "gw4"),
    ("block matching: block size", "blocksize-3.2km", ["block-13km", "block", "block-51km", "block-102km", "block-smooth-13km",
                                                        "block-smooth-26km", "block-smooth-51km", "block-smooth-102km"], "block"),
]
HALVES = {"Apr-Jun": ("04", "05", "06"), "Jul-Sep": ("07", "08", "09")}


def month_split(events):
    m = {i: dt.datetime.fromtimestamp(s, dt.UTC).strftime("%m") for i, (s, e) in enumerate(events)}
    return {h: {i for i, mo in m.items() if mo in ms} for h, ms in HALVES.items()}


def held_out():
    out = {"decisions": [], "final": {}}
    cache = {}
    for label, stem, cands, used_in_report in DECISIONS:
        if stem not in cache:
            cache[stem] = load(stem)
        rows, events = cache[stem]
        S = sums(rows, set(cands) | {"persistence"}, {60, 180})
        halves = month_split(events)
        full = {c: gain(S, c, 60, {e for e in S[(c, 60)]}) for c in cands}
        dec = dict(label=label, report=used_in_report, full=full, folds={})
        for train, test in (("Apr-Jun", "Jul-Sep"), ("Jul-Sep", "Apr-Jun")):
            tr = {c: gain(S, c, 60, halves[train] & set(S[(c, 60)])) for c in cands}
            te = {c: gain(S, c, 60, halves[test] & set(S[(c, 60)])) for c in cands}
            pick = max(tr, key=tr.get)
            best = max(te, key=te.get)
            dec["folds"][f"{train}_to_{test}"] = dict(pick=pick, best=best, pick_test=te[pick], best_test=te[best],
                                                   report_test=te[used_in_report], regret=te[best] - te[pick],
                                                   train=tr, test=te)
        out["decisions"].append(dec)
    # the methods at the settings chosen on the other half, compared on the held-out half alone
    rows, events = cache["benchmark-10min-window"]
    halves = month_split(events)
    fam = {"block matching": ["bw2", "bw4", "bw7", "bw13"],
           "whole-map vector": ["gw2", "gw3", "gw4", "gw5", "gw7", "gw10", "gw13", "gwx3", "gwx6"],
           "pysteps Lucas-Kanade": ["pysteps-lk", "pysteps-lk7", "pysteps-lk13"]}
    allm = {m for v in fam.values() for m in v} | {"persistence"}
    S = sums(rows, allm, {60, 180})
    for train, test in (("Apr-Jun", "Jul-Sep"), ("Jul-Sep", "Apr-Jun")):
        chosen = {f: max(ms, key=lambda c: gain(S, c, 60, halves[train] & set(S[(c, 60)]))) for f, ms in fam.items()}
        test_ev = halves[test] & {e for k in S for e in S[k]}
        B = Boot(S, test_ev, {e: e for e in test_ev})
        res = dict(chosen=chosen, events=len(test_ev), gain={}, paired={})
        for lead in (60, 180):
            for f, m in chosen.items():
                res["gain"][f"{f}_at_{lead}"] = B.diff(m, "persistence", lead)
            for a, b in (("pysteps Lucas-Kanade", "block matching"), ("pysteps Lucas-Kanade", "whole-map vector"),
                         ("block matching", "whole-map vector")):
                res["paired"][f"{a} vs {b}_at_{lead}"] = B.diff(chosen[a], chosen[b], lead)
        out["final"][f"{train}_to_{test}"] = res
    return out


def main():
    res = {"intervals": intervals(), "held_out": held_out()}
    I, H = res["intervals"], res["held_out"]
    wider = [x[k]["width"] / x["block"]["width"] - 1 for x in list(I["gain"].values()) + list(I["paired"].values()) for k in ("day", "spell")]
    regrets = [f["regret"] for d in H["decisions"] if "size" not in d["label"] for f in d["folds"].values()]
    res["summary"] = dict(widest=float(max(wider)), median_wider_spell=float(np.median(
        [x["spell"]["width"] / x["block"]["width"] - 1 for x in list(I["gain"].values()) + list(I["paired"].values())])),
        max_regret_history=float(max(regrets)),
        blocksize_regret=float(max(f["regret"] for d in H["decisions"] if "size" in d["label"] for f in d["folds"].values())))
    (R / "robustness.json").write_text(json.dumps(res, indent=1))
    I = res["intervals"]
    print("units:", I["units"])
    for k, v in list(I["gain"].items()) + list(I["paired"].items()):
        print(f"{k:32s} " + "  ".join(f"{u}: {x['d']:+.3f} [{x['lo']:+.3f}, {x['hi']:+.3f}] w{x['width']:.3f}" for u, x in v.items()))
    for d in res["held_out"]["decisions"]:
        print("\n" + d["label"], "| report uses", d["report"])
        for f, x in d["folds"].items():
            print(f"  {f}: pick {x['pick']} -> {x['pick_test']:+.3f} on held-out; best there {x['best']} {x['best_test']:+.3f}; "
                  f"regret {x['regret']:.4f}; report's setting {x['report_test']:+.3f}")
    for f, x in res["held_out"]["final"].items():
        print("\nfinal", f, x["chosen"], x["events"], "events")
        for k, v in x["paired"].items():
            print(f"  {k}: {v['d']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]")


if __name__ == "__main__":
    main()
