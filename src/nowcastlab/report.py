"""Turn a hindcast .jsonl into tables. Confidence intervals resample whole
rain EVENTS (not issue times), because forecasts issued minutes apart share the
same weather; the effective sample size is the number of events."""
from __future__ import annotations

import json
from collections import defaultdict
import numpy as np

SUMS = ["sum_f", "sum_t", "hit0.1", "miss0.1", "fa0.1", "hit0.5", "miss0.5", "fa0.5", "hit1.0", "miss1.0", "fa1.0",
        "fss9_0.5_e", "fss9_0.5_r", "fss3_0.5_e", "fss3_0.5_r", "brier", "n", "n_cases"]


def load(path):
    return [json.loads(l) for l in open(path)]


def pooled(rows_by_event, events):
    tot = defaultdict(float)
    for e in events:
        for k, v in rows_by_event[e].items():
            tot[k] += v
    return tot


def csi(t, thr):
    d = t[f"hit{thr}"] + t[f"miss{thr}"] + t[f"fa{thr}"]
    return t[f"hit{thr}"] / d if d else float("nan")


def fss(t, win):
    r = t[f"fss{win}_0.5_r"]
    return 1 - t[f"fss{win}_0.5_e"] / r if r else float("nan")


METRICS = {
    "ratio": lambda t: t["sum_f"] / t["sum_t"] if t["sum_t"] else float("nan"),
    "CSI0.1": lambda t: csi(t, 0.1),
    "CSI0.5": lambda t: csi(t, 0.5),
    "CSI1.0": lambda t: csi(t, 1.0),
    "FSS3": lambda t: fss(t, 3),
    "FSS9": lambda t: fss(t, 9),
    "BS": lambda t: t["brier"] / t["n"] if t["n"] else float("nan"),
}


def summarize(rows, n_boot=2000, seed=0, baseline="persistence", min_cases=1):
    """{(model, lead): {...}} with event-bootstrap CIs and paired deltas vs baseline."""
    rng = np.random.default_rng(seed)
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))     # (model,lead) -> event -> sums
    fb = defaultdict(lambda: [0, 0])
    logr = defaultdict(list)
    corr = defaultdict(list)
    for r in rows:
        key = (r["model"], r["lead"])
        d = per[key][r["event"]]
        for k in SUMS[:-1]:
            d[k] += r.get(k, 0)
        d["n_cases"] += 1
        fb[key][0] += bool(r.get("fallback")); fb[key][1] += 1
        if r["sum_f"] > 0 and r["sum_t"] > 0:
            logr[key].append(np.log(r["sum_f"] / r["sum_t"]))
        if r["corr"] is not None:
            corr[key].append(r["corr"])
    out = {}
    for key, ev in per.items():
        events = sorted(ev)
        base = per.get((baseline, key[1]))
        entry = {"events": len(events), "cases": int(sum(ev[e]["n_cases"] for e in events)),
                 "sd_log_ratio": float(np.std(logr[key])) if len(logr[key]) > 1 else float("nan"),
                 "corr": float(np.mean(corr[key])) if corr[key] else float("nan"),
                 "fallback": fb[key][0] / fb[key][1]}
        t = pooled(ev, events)
        for m, f in METRICS.items():
            entry[m] = f(t)
        if base and key[0] != baseline:
            common = [e for e in events if e in base]
            for m in ("FSS9", "CSI0.5", "CSI0.1", "BS"):
                f = METRICS[m]
                diffs = []
                for _ in range(n_boot):
                    pick = rng.choice(common, len(common), replace=True)
                    diffs.append(f(pooled(ev, pick)) - f(pooled(base, pick)))
                entry[f"d{m}"] = f(pooled(ev, common)) - f(pooled(base, common))
                entry[f"d{m}_ci"] = (float(np.nanpercentile(diffs, 2.5)), float(np.nanpercentile(diffs, 97.5)))
        out[key] = entry
    return out


def markdown(summary, models=None):
    models = models or sorted({k[0] for k in summary})
    leads = sorted({k[1] for k in summary})
    lines = []
    for lead in leads:
        lines.append(f"\n**+{lead} min**\n")
        lines.append("| model | events | cases | rain ratio | scatter | corr | CSI0.1 | CSI0.5 | FSS(30km) | dFSS vs persistence [95% CI] | Brier@0.5 | dBrier [95% CI] |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for m in models:
            e = summary.get((m, lead))
            if not e:
                continue
            d = ""
            if "dFSS9" in e:
                lo, hi = e["dFSS9_ci"]
                d = f"{e['dFSS9']:+.3f} [{lo:+.3f}, {hi:+.3f}]"
            db = ""
            if "dBS" in e:
                lo, hi = e["dBS_ci"]
                db = f"{e['dBS']:+.4f} [{lo:+.4f}, {hi:+.4f}]"
            lines.append(f"| {m} | {e['events']} | {e['cases']} | {e['ratio']:.2f} | {e['sd_log_ratio']:.2f} | {e['corr']:.2f} | "
                         f"{e['CSI0.1']:.2f} | {e['CSI0.5']:.2f} | {e['FSS9']:.2f} | {d} | {e['BS']:.4f} | {db} |")
    return "\n".join(lines)


# ---- caching and paired comparisons -------------------------------------------------

def summarize_file(path, **kw):
    """summarize() of a results file, cached next to it (the bootstrap is slow)."""
    import json as _json
    from pathlib import Path as _P
    src, cache = _P(path), _P(path).with_suffix(".summary.json")
    if cache.exists() and cache.stat().st_mtime >= src.stat().st_mtime:
        raw = _json.loads(cache.read_text())
        out = {}
        for k, v in raw.items():
            m, lead = k.rsplit("|", 1)
            out[(m, int(lead))] = {a: (tuple(b) if isinstance(b, list) else b) for a, b in v.items()}
        return out
    S = summarize(load(path), **kw)
    cache.write_text(_json.dumps({f"{m}|{l}": v for (m, l), v in S.items()}, default=float))
    return S


def unit_sums(rows, model, lead):
    """{unit: {fss numerator, fss denominator}} for one model and lead."""
    per = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["model"] == model and r["lead"] == lead:
            d = per[r["event"]]
            d["e"] += r["fss9_0.5_e"]
            d["r"] += r["fss9_0.5_r"]
    return per


def paired_fss(rows, a, b, lead, n_boot=2000, seed=1, relative=False):
    """FSS(a) - FSS(b) pooled (or FSS(a) / FSS(b) - 1 with relative=True), with a 95% interval
    from resampling event units, and the share of units where a beats b."""
    rng = np.random.default_rng(seed)
    A, B = unit_sums(rows, a, lead), unit_sums(rows, b, lead)
    units = np.array(sorted(set(A) & set(B)))
    f = lambda X, u: 1 - sum(X[i]["e"] for i in u) / sum(X[i]["r"] for i in u)
    g = (lambda u: f(A, u) / f(B, u) - 1) if relative else (lambda u: f(A, u) - f(B, u))
    d0 = g(units)
    ds = [g(p) for p in (rng.choice(units, len(units), replace=True) for _ in range(n_boot))]
    wins = [(1 - A[u]["e"] / A[u]["r"]) > (1 - B[u]["e"] / B[u]["r"]) for u in units if A[u]["r"] > 0 and B[u]["r"] > 0]
    return d0, tuple(np.percentile(ds, [2.5, 97.5])), float(np.mean(wins))
