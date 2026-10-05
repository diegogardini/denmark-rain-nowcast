#!/usr/bin/env python3
"""Build docs/REPORT.md from docs/REPORT.template.md and the benchmark result files.

Every number in the report comes from the result files, so text and data cannot drift.
Placeholders (in double braces); KIND may carry a source, KIND@SRC, else main then window:

  {{d:MODEL:LEAD}}     FSS gain over persistence, signed        {{ci:MODEL:LEAD}}  its 95% interval
  {{f:MODEL:LEAD}}     FSS                                      {{r:MODEL:LEAD}}   rain ratio (forecast / observed)
  {{b:MODEL:LEAD}}     Brier improvement over persistence       {{c:MODEL:LEAD}}   CSI at 0.5 mm/h
  {{pd:A:B:LEAD}}      paired FSS difference A - B with interval  {{pw:A:B:LEAD}} share of blocks where A beats B
  {{over:MODEL:LEAD}}  share of event blocks whose rain total is above the observed one
  {{q:MODEL:LEAD:P}}   percentile P of the per-block rain ratio
  {{n:NAME}}           counts (units, issues, days, scans, fullrange, doppler, missing, rows)
  {{table:NAME}}       a generated table (headline, leads, windows, longleads, months, paired, ratioq, cadence)

Sources: main   results/benchmark-10min.jsonl        (full-range scans, 10-minute axis; headline)
         window results/benchmark-10min-window.jsonl (history up to 2 h, leads to 6 h)
         c10, c5 results/check-cadence-{10,5}min.jsonl (fixed common footprint, same issue times)
"""
import re, sys, json, datetime as dt
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import report

R = ROOT / "results"
FILES = {"main": R / "benchmark-10min.jsonl", "window": R / "benchmark-10min-window.jsonl",
         "c10": R / "check-cadence-10min.jsonl", "c5": R / "check-cadence-5min.jsonl",
         "speed": R / "speed-scaling.jsonl", "steps": R / "steps-defaults.jsonl"}
S = {k: report.summarize_file(p) for k, p in FILES.items()}
_rows = {}
CASES = json.loads((R / "cases.json").read_text()) if (R / "cases.json").exists() else {}
meta = json.loads(FILES["main"].with_suffix(".meta.json").read_text())


def rows(src="main"):
    if src not in _rows:
        _rows[src] = report.load(FILES[src])
    return _rows[src]


def extra_rows(stem):
    """Rows of any results file, loaded once."""
    if stem not in _rows:
        _rows[stem] = report.load(R / f"{stem}.jsonl")
    return _rows[stem]


NAMES = {"persistence": "Persistence (nothing moves)", "block": "Block matching, last pair (10 min)",
         "bw2": "Block matching, last pair (10 min)", "bw4": "Block matching, 4 scans (30 min)",
         "bw7": "Block matching, 7 scans (1 h)", "bw13": "Block matching, 13 scans (2 h)",
         "gw2": "Whole-map vector, last pair (10 min)", "gw3": "Whole-map vector, 3 scans (20 min)",
         "gw4": "Whole-map vector, 4 scans (30 min)", "gw5": "Whole-map vector, 5 scans (40 min)",
         "gw7": "Whole-map vector, 7 scans (1 h)", "gw10": "Whole-map vector, 10 scans (1.5 h)",
         "gw13": "Whole-map vector, 13 scans (2 h)",
         "gwx3": "Whole-map vector, 13 scans, recent pairs weighted (half-life 3)",
         "gwx6": "Whole-map vector, 13 scans, recent pairs weighted (half-life 6)",
         "pysteps-lk": "pysteps Lucas-Kanade, 4 scans (30 min)", "pysteps-lk7": "pysteps Lucas-Kanade, 7 scans (1 h)",
         "pysteps-lk13": "pysteps Lucas-Kanade, 13 scans (2 h)", "pysteps-sprog": "pysteps S-PROG, 4 scans",
         "pysteps-steps-mean": "pysteps STEPS, ensemble mean and probabilities, 4 scans",
         "pysteps-steps-member": "pysteps STEPS, a single member, 4 scans"}
HIST = {"persistence": "1", "block": "2", "bw7": "7", "gw2": "2", "gw4": "4", "gw7": "7", "pysteps-lk": "4", "pysteps-lk7": "7",
        "pysteps-sprog": "4", "pysteps-steps-mean": "4"}


# section 5 shows each method at its best history (Appendix B.1): block matching over 1 hour, the whole-map vector and
# pysteps over 30 minutes; S-PROG and STEPS at pysteps' default
BEST = ["persistence", "bw7", "gw4", "pysteps-lk", "pysteps-sprog", "pysteps-steps-mean"]
# section 5 names: the history is stated once, above the tables
SHORT = {"persistence": "Persistence (nothing moves)", "bw7": "Block matching", "gw4": "Whole-map vector",
         "pysteps-lk": "pysteps Lucas-Kanade", "pysteps-sprog": "pysteps S-PROG", "pysteps-steps-mean": "pysteps STEPS, ensemble mean"}
def group_of(m, prev):
    """The model type for the first row of a run of the same type, blank below it (the page merges the cells)."""
    return "" if prev is not None and GROUP.get(prev) == GROUP[m] else GROUP[m]


GROUP = {"persistence": "Reference", "bw7": "Simple motion", "gw4": "Simple motion",
         "pysteps-lk": "State of the art", "pysteps-sprog": "State of the art", "pysteps-steps-mean": "State of the art"}


def entry(model, lead, src=None):
    for k in ([src] if src else ["main", "window"]):
        if (model, int(lead)) in S[k]:
            return S[k][(model, int(lead))]
    raise KeyError(f"no result for {model} at +{lead} min in {src or 'main/window'}")


def sg(x, d=3):
    return f"{x:+.{d}f}"


def interval(e, key):
    lo, hi = e[key]
    return f"[{lo:+.3f}, {hi:+.3f}]"


_paired = {}


def paired(a, b, lead, src="main", relative=False):
    k = (a, b, int(lead), src, relative)
    if k not in _paired:
        _paired[k] = report.paired_fss(rows(src), a, b, int(lead), relative=relative)
    return _paired[k]


def unit_ratios(model, lead, src="main"):
    ev = {}
    for r in rows(src):
        if r["model"] == model and r["lead"] == int(lead):
            d = ev.setdefault(r["event"], [0.0, 0.0]); d[0] += r["sum_f"]; d[1] += r["sum_t"]
    return np.array([a / b for a, b in ev.values() if b > 0])


def month_of(e):
    return dt.datetime.fromtimestamp(meta["events"][e][0], dt.UTC).strftime("%Y-%m")


def counts(name):
    if name == "units":
        return str(len(meta["events"]))
    if name == "issues":
        return f"{S['main'][('persistence', 30)]['cases']:,}"
    if name == "cadence_issues":
        return f"{S['c5'][('persistence', 60)]['cases']:,}"
    return {"days": "176", "scans": "50,688", "fullrange": "25,300", "doppler": "25,319", "missing": "69",
            "rows": f"{len(rows()):,}"}[name]


def scalar(kind, args):
    kind, _, src = kind.partition("@")
    src = src or None
    if kind == "d":
        return sg(entry(*args, src=src)["dFSS9"])
    if kind == "pc":                 # {{pc:A:B:LEAD}}: how much more accurately A places rain than B, % of B's FSS
        fa, fb = entry(args[0], args[2], src)["FSS9"], entry(args[1], args[2], src)["FSS9"]
        return f"{(fa / fb - 1) * 100:.0f}%"
    if kind == "pci":                # {{pci:A:B:LEAD}}: 95% interval of pc, resampling rain episodes
        lo, hi = paired(args[0], args[1], args[2], relative=True)[1]
        return f"{lo * 100:.0f}% to {hi * 100:.0f}%"
    if kind == "ci":
        return interval(entry(*args, src=src), "dFSS9_ci")
    if kind == "f":
        return f"{entry(*args, src=src)['FSS9']:.2f}"
    if kind == "r":
        return f"{entry(*args, src=src)['ratio']:.2f}"
    if kind == "b":
        return sg(-entry(*args, src=src)["dBS"], 4)
    if kind == "c":
        return f"{entry(*args, src=src)['CSI0.5']:.2f}"
    if kind == "pd":
        d, ci, w = paired(*args, src=src or "main")
        return f"{sg(d)} [{ci[0]:+.3f}, {ci[1]:+.3f}]"
    if kind == "pw":
        return f"{paired(*args, src=src or 'main')[2] * 100:.0f}%"
    if kind == "over":
        return f"{(unit_ratios(*args, src=src or 'main') > 1).mean() * 100:.0f}%"
    if kind == "q":
        return f"{np.percentile(unit_ratios(args[0], args[1], src=src or 'main'), float(args[2])):.2f}"
    if kind == "n":
        return counts(args[0])
    if kind == "city":
        return city_n(args[0])
    if kind == "ms":                 # {{ms:WHAT}}: motion statistics (results/motion-stats.json)
        ms = json.loads((R / "motion-stats.json").read_text())
        what = args[0]
        if what == "speed":
            return f"{ms['speed_kmh']['median']:.0f}"
        if what == "speedq":
            return f"{ms['speed_kmh']['p25']:.0f} to {ms['speed_kmh']['p75']:.0f}"
        if what == "eastward":
            return f"{(ms['toward_share']['east'] + ms['toward_share']['north-east']) * 100:.0f}%"
        if what == "westward":
            return f"{sum(ms['toward_share'][k] for k in ('west', 'south-west', 'north-west')) * 100:.0f}%"
        if what in ("trackp99", "trackabove", "trackbelow"):     # local speeds of the Lucas-Kanade feature tracks (no search limit)
            sp = np.concatenate([np.hypot(t["u"], t["v"]) for t in map(json.loads, open(R / "motion-tracks.jsonl")) if len(t["u"]) >= 10])
            return f"{np.percentile(sp, 99):.0f}" if what == "trackp99" else f"{(sp > 115).mean() * 100:.1f}%" if what == "trackabove" else f"{(sp <= 115).mean() * 100:.1f}%"
        if what in ("change1", "change3"):
            return f"{ms['change_1h_kmh' if what == 'change1' else 'change_3h_kmh']['median']:.0f}"
        raise KeyError(what)
    if kind == "gc":                 # {{gc:MODEL:GRID}}: city CSI for the next hour on a grid
        rows = [r for r in report.load(R / f"cities-grid-{args[1]}.jsonl") if r["hour"] == 1]
        c = city_scores(rows, args[0])
        return f"{c['hit'] / (c['hit'] + c['miss'] + c['fa']):.2f}"
    if kind == "pr":                 # {{pr:FILES:A:B:LEAD}}: paired FSS A - B with interval; FILES are results
        # stems joined by "+" (e.g. vector-raw+benchmark-10min), each run on the same issue times
        a_, b_, lead = args[1], args[2], int(args[3])
        rs = [r for stem in args[0].split("+") for r in extra_rows(stem) if r["model"] in (a_, b_)]
        d, ci, w = report.paired_fss(rs, a_, b_, lead)
        return f"{sg(d)} [{ci[0]:+.3f}, {ci[1]:+.3f}]"
    if kind == "rr":                 # {{rr:FILE:MODEL:LEAD}}: pooled rain ratio (forecast over observed) from any results file
        rs = [r for r in extra_rows(args[0]) if r["model"] == args[1] and r["lead"] == int(args[2])]
        return f"{sum(r['sum_f'] for r in rs) / sum(r['sum_t'] for r in rs):.2f}"
    if kind == "pw2":                # {{pw2:FILES:A:B:LEAD}}: share of event blocks where A beats B, from any results files
        rs = [r for stem in args[0].split("+") for r in extra_rows(stem) if r["model"] in (args[1], args[2])]
        return f"{report.paired_fss(rs, args[1], args[2], int(args[3]))[2] * 100:.0f}%"
    if kind == "lt":                 # {{lt:THR:EVENT:HORIZON:VARIANT:imp|vs|pct}}: timing at one spot (results/local-timing.json)
        r = json.loads((R / "local-timing.json").read_text())["results"][f"{args[0]}|{args[1]}|{args[2]}"]
        if args[4] == "imp":
            return f"{r['improvement'][args[3]]:.3f}"
        if args[4] == "pct":
            return f"{r['improvement'][args[3]] / r['improvement']['steps_cal'] * 100:.0f}%"
        x = r["vs_steps_cal"][args[3]]
        return f"{x['d']:+.4f} [{x['lo']:+.4f}, {x['hi']:+.4f}]"
    if kind == "lp":                 # {{lp:THR:VARIANT:LEAD:imp|vs|vsci}}: local chance of rain (results/local-probs.json)
        J = json.loads((R / "local-probs.json").read_text())
        B, k = J["by_threshold"][args[0]], J["leads"].index(int(args[2]))
        if args[3] == "imp":
            return f"{B['improvement'][args[1]][k]:.3f}"
        x = B["vs_steps"][args[1]][k]
        return f"{x['d']:+.3f}" if args[3] == "vs" else f"{x['d']:+.4f} [{x['lo']:+.4f}, {x['hi']:+.4f}]"
    if kind == "tfa":                # {{tfa:RATING:A:B:GROUP:LEAD}}: size of the FSS difference between A and B in one third
        g = json.loads((R / "turning-flow.json").read_text())["ratings"][args[0]]["gain"]
        return f"{abs(g[f'{args[1]}_{args[3]}_at_{args[4]}'] - g[f'{args[2]}_{args[3]}_at_{args[4]}']):.3f}"
    if kind == "tfg":                # {{tfg:RATING:A:B:GROUP:LEAD}}: FSS gain of A minus that of B in one third (turning-flow.json)
        g = json.loads((R / "turning-flow.json").read_text())["ratings"][args[0]]["gain"]
        return sg(g[f"{args[1]}_{args[3]}_at_{args[4]}"] - g[f"{args[2]}_{args[3]}_at_{args[4]}"])
    if kind == "tfp":                # {{tfp:RATING:KEY}}: a paired difference from results/turning-flow.json, with interval
        x = json.loads((R / "turning-flow.json").read_text())["ratings"][args[0]]["paired"][args[1]]
        return f"{sg(x['d'])} [{x['lo']:+.3f}, {x['hi']:+.3f}]"
    if kind in ("ex", "fe", "vs", "rb", "pb", "e5", "rg", "tf", "sb"):   # {{ex:dotted.path:FMT}} from results/explain-checks.json, {{fe:...}} from
        # results/fixed-echo-check.json, {{vs:...}} from results/vector-speed.json, {{rb:...}} from results/robustness.json;
        # FMT pct/pct1/pct2, 0f, 2f, 3f
        v = json.loads((R / {"ex": "explain-checks.json", "fe": "fixed-echo-check.json", "vs": "vector-speed.json",
                             "rb": "robustness.json", "pb": "probs.json", "e5": "era5-vs-rain.json",
                             "rg": "radar-vs-gauges.json", "tf": "turning-flow.json", "sb": "subcell-cities.json"}[kind]).read_text())
        for k in args[0].split("."):
            v = v[int(k)] if isinstance(v, list) else v[k]
        fmt = args[1] if len(args) > 1 else "2f"
        if fmt == ",":                                             # thousands separators
            return f"{v:,}"
        if fmt.startswith("pct"):                                  # pct, pct1, pct2: percent with 0, 1, 2 decimals
            return f"{v * 100:.{int(fmt[3:] or 0)}f}%"
        return format(v, "." + fmt)
    if kind == "sc":                 # {{sc:MODEL:LEAD}}: speed-scaled vector minus the unscaled one, with interval
        d, ci, w = report.paired_fss(globals()["rows"]("speed"), args[0], "gw4s100", int(args[1]))
        return f"{sg(d)} [{ci[0]:+.3f}, {ci[1]:+.3f}]"
    if kind == "coh":                # {{coh:KM}}: rms difference of rain motion between tracks KM apart (km/h)
        c = json.loads((R / "motion-coherence.json").read_text())["all"]
        k = min(range(len(c["r_km"])), key=lambda j: abs(c["r_km"][j] - float(args[0])))
        return f"{c['D'][k] ** 0.5:.0f}"
    if kind == "stc":                # {{stc:KM}}: the same for station winds
        c = json.loads((R / "station-vs-rain.json").read_text())["station_structure"]
        k = min(range(len(c["r_km"])), key=lambda j: abs(c["r_km"][j] - float(args[0])))
        return f"{c['rms_kmh'][k]:.0f}"
    if kind == "sv":                 # {{sv:WHAT}}: station wind against the rain's motion
        v = json.loads((R / "station-vs-rain.json").read_text())
        return {"ratio": lambda: f"{v['speed_ratio']['median'] * 100:.0f}%", "turn": lambda: f"{v['turn_deg']['median']:.0f}",
                "turnq": lambda: f"{v['turn_deg']['p25']:.0f} to {v['turn_deg']['p75']:.0f}",
                "within30": lambda: f"{v['turn_within_30'] * 100:.0f}%", "speed": lambda: f"{v['station_speed_median_kmh']:.0f}",
                "pairs": lambda: f"{v['pairs']:,}"}[args[0]]()
    if kind == "bsg":                # {{bsg:MODEL:LEAD:GRID}} block-size run: gain over persistence
        return sg(bs_gain(args[0], args[1], args[2]))
    if kind == "bsd":                # {{bsd:MODEL:LEAD:GRID}} minus the 26 km blocks, with interval
        d, lo, hi, _ = bs_cmp(args[0], args[1], args[2])
        return f"{sg(d)} [{lo:+.3f}, {hi:+.3f}]"
    if kind == "gg":                 # {{gg:MODEL:LEAD:NB:GRID}}: FSS gain over persistence on a grid (NB 30, 10 or a band)
        gs = grid_gain(args[0], args[1], grid_key(args[2]), args[3])
        return sg(CG.pooled_gain(gs, sorted(gs)))
    if kind == "gd":                 # {{gd:MODEL:LEAD:NB:GRID}}: that grid minus 3.2 km, with its interval
        d, lo, hi, _ = grid_cmp(args[0], args[1], grid_key(args[2]), args[3])
        return f"{sg(d)} [{lo:+.3f}, {hi:+.3f}]"
    if kind == "gw":                 # {{gw:MODEL:LEAD:NB:GRID}}: share of blocks where that grid is better
        return f"{grid_cmp(args[0], args[1], grid_key(args[2]), args[3])[3] * 100:.0f}%"
    if kind in ("cpod", "cfar", "ccsi", "cratio", "cerr"):          # {{cpod:MODEL:HOUR}} etc., pooled over the cities
        rows = [r for r in city_rows() if r["hour"] == int(args[1])]
        c = city_scores(rows, args[0])
        return {"cpod": lambda: f"{c['hit'] / (c['hit'] + c['miss']) * 100:.0f}%",
                "cfar": lambda: f"{c['fa'] / (c['hit'] + c['fa']) * 100:.0f}%",
                "ccsi": lambda: f"{c['hit'] / (c['hit'] + c['miss'] + c['fa']):.2f}",
                "cratio": lambda: f"{c['sf'] / c['so']:.2f}",
                "cerr": lambda: f"{c['ae'] / c['n']:.2f}"}[kind]()
    if kind == "case":
        c = CASES[args[0]]
        what = args[1]
        if what == "time":
            return c["time"]
        if what == "obs":
            o = c["motion"]["observed"]
            return f"{o['kmh']:.0f} km/h toward the {o['toward']}"
        if what == "err":
            return f"{c['motion'][args[2]]['err_kmh']:.0f}"
        if what == "vec":
            m = c["motion"][args[2]]
            return f"{m['kmh']:.0f} km/h toward the {m['toward']}"
        if what == "fss":
            return f"{c['scores'][args[2] + ':' + args[3]]['fss']:.2f}"
        if what == "ratio":
            return f"{c['scores'][args[2] + ':' + args[3]]['ratio']:.2f}"
        raise KeyError(what)
    raise KeyError(kind)


# ---------------------------------------------------------------- tables
def t_headline_compact(lead=60):
    """Section 5.2: placement as % better than "nothing moves" (FSS ratio), with its interval, and the rain ratio."""
    models = BEST
    out = ["| Model type | Method | Rain placed better than \"nothing moves\" [95% interval] | Rain ratio |", "|---|---|---|---|"]
    for i, m in enumerate(models):
        e = entry(m, lead, "main")
        if m == "persistence":
            cell = "(reference)"
        else:
            d, (lo, hi), _ = paired(m, "persistence", lead, relative=True)
            cell = f"+{d * 100:.0f}% [{lo * 100:.0f}% to {hi * 100:.0f}%]"
        out.append(f"| {group_of(m, models[i - 1] if i else None)} | {SHORT[m]} | {cell} | {e['ratio']:.2f} |")
    return "\n".join(out)


def t_headline(lead=60):
    models = BEST
    out = ["| Model type | Method | FSS | FSS gain over persistence [95% CI] | CSI 0.5 | Rain ratio | Brier improvement |", "|---|---|---|---|---|---|---|"]
    for i, m in enumerate(models):
        e = entry(m, lead, "main")
        gain = f"{sg(e['dFSS9'])} {interval(e, 'dFSS9_ci')}" if "dFSS9" in e else "(reference)"
        b = sg(-e["dBS"], 4) if "dBS" in e else "(reference)"
        out.append(f"| {group_of(m, models[i - 1] if i else None)} | {SHORT[m]} | {e['FSS9']:.2f} | {gain} | {e['CSI0.5']:.2f} | {e['ratio']:.2f} | {b} |")
    return "\n".join(out)


def t_leads():
    """Gain across lead times for the best configurations, to 3 hours (all methods were run that far)."""
    leads = (30, 60, 90, 120, 180)
    out = ["| Model type | Method | " + " | ".join(f"+{l} min" for l in leads) + " |", "|---|---|" + "---|" * len(leads)]
    out.append("| Reference | *Persistence FSS* | " + " | ".join(f"{entry('persistence', l, 'main')['FSS9']:.2f}" for l in leads) + " |")
    for i, m in enumerate(BEST[1:]):
        cells = [sg(entry(m, l, "main")["dFSS9"]) for l in leads]
        out.append(f"| {group_of(m, BEST[i])} | {SHORT[m]} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def t_windows():
    leads = (30, 60, 120, 180, 240, 360)
    models = ["bw2", "bw4", "bw7", "bw13", "gw2", "gw3", "gw4", "gw5", "gw7", "gw10", "gw13", "gwx3", "gwx6",
              "pysteps-lk", "pysteps-lk7", "pysteps-lk13"]
    W = S["window"]
    out = ["| Method | " + " | ".join(f"+{l} min" for l in leads) + " | Rain ratio at +60 |", "|---|" + "---|" * (len(leads) + 1)]
    out.append("| *Persistence FSS (reference)* | " + " | ".join(f"{W[('persistence', l)]['FSS9']:.2f}" for l in leads) + " | 1.00 |")
    for m in models:
        out.append(f"| {NAMES[m]} | " + " | ".join(sg(W[(m, l)]["dFSS9"]) for l in leads) + f" | {W[(m, 60)]['ratio']:.2f} |")
    return "\n".join(out)


def t_longleads():
    leads = (240, 360)
    models = ["gw2", "gw4", "gw7", "pysteps-lk", "pysteps-lk7"]
    W = S["window"]
    out = ["| Method | +240 min (4 h) | +360 min (6 h) |", "|---|---|---|"]
    out.append(f"| *Persistence FSS (reference)* | {W[('persistence', 240)]['FSS9']:.2f} | {W[('persistence', 360)]['FSS9']:.2f} |")
    for m in models:
        out.append(f"| {NAMES[m]} | " + " | ".join(f"{sg(W[(m, l)]['dFSS9'])} {interval(W[(m, l)], 'dFSS9_ci')}" for l in leads) + " |")
    return "\n".join(out)


def t_months(lead=60):
    agg = {}
    for r in rows():
        if r["lead"] == lead:
            k = (month_of(r["event"]), r["model"])
            a = agg.setdefault(k, [0.0, 0.0]); a[0] += r["fss9_0.5_e"]; a[1] += r["fss9_0.5_r"]
    units = {}
    for e in range(len(meta["events"])):
        units[month_of(e)] = units.get(month_of(e), 0) + 1
    f = lambda a: 1 - a[0] / a[1]
    models = ["bw7", "gw4", "pysteps-lk", "pysteps-steps-mean"]
    short = {"bw7": "Block matching", "gw4": "Whole-map vector",
             "pysteps-lk": "pysteps Lucas-Kanade", "pysteps-steps-mean": "pysteps STEPS mean"}
    names = {"04": "April", "05": "May", "06": "June", "07": "July", "08": "August", "09": "September"}
    out = ["| Month | Rain episodes | Persistence FSS | " + " | ".join(short[m] for m in models) + " |", "|---|---|---|" + "---|" * len(models)]
    for mo in sorted({k[0] for k in agg}):
        p = f(agg[(mo, "persistence")])
        out.append(f"| {names[mo[5:]]} | {units[mo]} | {p:.2f} | " + " | ".join(sg(f(agg[(mo, m)]) - p) for m in models) + " |")
    return "\n".join(out)


def t_paired():
    """Methods head to head on the same event blocks (A - B pooled, and the share of blocks A wins)."""
    pairs = [("pysteps-lk", "gw4", "pysteps Lucas-Kanade", "Whole-map vector"),
             ("pysteps-lk", "bw7", "pysteps Lucas-Kanade", "Block matching"),
             ("bw7", "gw4", "Block matching", "Whole-map vector")]
    out = ["| A | B | A − B, +60 min [95% CI] | Episodes where A is better, +60 | A − B, +180 min [95% CI] | Episodes where A is better, +180 |",
           "|---|---|---|---|---|---|"]
    for a, b, la, lb in pairs:
        cells = []
        for lead in (60, 180):
            d, ci, w = paired(a, b, lead, "main")
            cells += [f"{sg(d)} [{ci[0]:+.3f}, {ci[1]:+.3f}]", f"{w * 100:.0f}%"]
        out.append(f"| {la} | {lb} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def t_ratioq(lead=60):
    models = ["persistence", "bw7", "gw4", "pysteps-lk", "pysteps-steps-mean"]
    out = [f"| Model type | Method | 10th | 25th | median | 75th | 90th | Episodes above 1.0 |", "|---|---|---|---|---|---|---|---|"]
    for i, m in enumerate(models):
        v = unit_ratios(m, lead)
        q = np.percentile(v, [10, 25, 50, 75, 90])
        out.append(f"| {group_of(m, models[i - 1] if i else None)} | {SHORT[m]} | " + " | ".join(f"{x:.2f}" for x in q) + f" | {(v > 1).mean() * 100:.0f}% |")
    return "\n".join(out)


def t_cadence():
    pairs = [("Block matching, last pair of scans", "block", "block"), ("Block matching, 30 min of history", "bw4", "bw7"),
             ("Block matching, 60 min of history", "bw7", "bw13"), ("Whole-map vector, last pair of scans", "gw2", "gw2"),
             ("Whole-map vector, 10 min of history", "gw2", "gw3"), ("Whole-map vector, 30 min of history", "gw4", "gw7"),
             ("Whole-map vector, 60 min of history", "gw7", "gw13"), ("pysteps Lucas-Kanade, 30 min of history", "pysteps-lk", "pysteps-lk7"),
             ("pysteps Lucas-Kanade, 60 min of history", "pysteps-lk7", "pysteps-lk13")]
    both = [dict(r, model="10:" + r["model"]) for r in rows("c10")] + [dict(r, model="5:" + r["model"]) for r in rows("c5")]
    out = ["| Method | Scans 10 min apart | Scans 5 min apart | 5 min minus 10 min [95% CI] | Episodes where 5 min is better | Rain ratio, 10 / 5 min |",
           "|---|---|---|---|---|---|"]
    lead = 60
    out.append(f"| *Persistence FSS (reference)* | {S['c10'][('persistence', lead)]['FSS9']:.2f} | {S['c5'][('persistence', lead)]['FSS9']:.2f} | | | |")
    for lab, m10, m5 in pairs:
        e10, e5 = S["c10"][(m10, lead)], S["c5"][(m5, lead)]
        if m10 == m5 in ("gw2", "block"):      # the last pair spans 10 min on one axis and 5 on the other: not paired by history
            d = "(different gap)"; w = ""
        else:
            dd, (lo, hi), ww = report.paired_fss(both, "5:" + m5, "10:" + m10, lead)
            d, w = f"{sg(dd)} [{lo:+.3f}, {hi:+.3f}]", f"{ww * 100:.0f}%"
        out.append(f"| {lab} | {sg(e10['dFSS9'])} | {sg(e5['dFSS9'])} | {d} | {w} | {e10['ratio']:.2f} / {e5['ratio']:.2f} |")
    return "\n".join(out)


# ---------------------------------------------------------------- probabilities (results/probs.json, scripts/compare_probs.py)
PB_NAMES = {"bw7": "Block matching (1 h)", "gw4": "Whole-map vector (30 min)", "pysteps-lk": "pysteps Lucas-Kanade",
            "pysteps-sprog": "pysteps S-PROG", "pysteps-steps-mean": "pysteps STEPS, 8 members",
            "pysteps-steps-default-mean": "pysteps STEPS, 24 members (defaults)"}


def pb():
    return json.loads((R / "probs.json").read_text())


def t_probs():
    """Brier improvement over persistence's own 0/1 forecast, by neighbourhood window, at +60 and +180 min."""
    P = pb()
    wins = list(P["windows_km"])
    head = " | ".join("cell alone" if w == "" else f"{P['windows_km'][w]} km" for w in wins)
    out = [f"| Method | Lead | {head} |", "|---|---|" + "---|" * len(wins)]
    for lead in (60, 180):
        for m, lab in PB_NAMES.items():
            vals = [P["improvement"][f"{m}{w}_at_{lead}"]["d"] for w in wins]
            best = max(vals)
            cells = [f"**{sg(v, 4)}**" if v == best else sg(v, 4) for v in vals]
            out.append(f"| {lab} | +{lead} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def t_probs_paired():
    """Head to head on probabilities, each method at its best window (at +60 min)."""
    P = pb()
    km = lambda w: "cell" if w == "" else f"{P['windows_km'][w]} km"
    comps = [("pysteps-steps-default-mean", "pysteps-lk"), ("pysteps-steps-default-mean", "bw7"), ("pysteps-lk", "bw7"), ("bw7", "gw4")]
    out = ["| A (window) | B (window) | " + " | ".join(f"A − B, +{L} min" for L in (30, 60, 120, 180)) + " |", "|---|---|" + "---|" * 4]
    B = P["best_window"]
    for a, b in comps:
        cells = []
        for L in (30, 60, 120, 180):
            x = P["paired"][f"{a}{B[a]}_vs_{b}{B[b]}_at_{L}"]
            cells.append(f"{sg(x['d'], 4)} [{x['lo']:+.4f}, {x['hi']:+.4f}]")
        out.append(f"| {PB_NAMES[a]} ({km(B[a])}) | {PB_NAMES[b]} ({km(B[b])}) | " + " | ".join(cells) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- rain gauges (results/radar-vs-gauges.json, scripts/radar_vs_gauges.py)
def t_gauges():
    G = json.loads((R / "radar-vs-gauges.json").read_text())
    names = {"Romo": "Rømø", "Samso": "Samsø"}
    rows_ = [("All gauges", G["all"]["cell"], sum(1 for x in G["stations"].values() if not x.get("faulty")))]
    rows_ += [(f"Nearest radar: {names.get(k, k)}", v, v["stations"]) for k, v in sorted(G["by_radar"].items(), key=lambda kv: kv[1]["ratio"])]
    out = ["| Gauges | Number | Radar over gauge, season | Hour-by-hour correlation | Rainy hours caught | False alarms |", "|---|---|---|---|---|---|"]
    for lab, x, n in rows_:
        out.append(f"| {lab} | {n} | {x['ratio']:.2f} | {x['corr']:.2f} | {x['pod'] * 100:.0f}% | {x['far'] * 100:.0f}% |")
    return "\n".join(out)


# ---------------------------------------------------------------- winds aloft (results/era5-vs-rain.json, scripts/era5_vs_rain.py)
def t_era5():
    """The wind at each pressure level against the rain's tracked motion at the same place and time."""
    E = json.loads((R / "era5-vs-rain.json").read_text())
    names = {"850": "850 hPa (about 1.5 km)", "700": "700 hPa (about 3 km)", "500": "500 hPa (about 5.5 km)",
             "300": "300 hPa (about 9 km)", "layer": "Mean of the four"}
    out = ["| Wind | Speed over the rain's | Turn from the rain's direction | Within 30° | Typical difference |", "|---|---|---|---|---|"]
    for l in E["levels"]:
        t = E["track"][l]
        out.append(f"| {names[l]} | {t['speed_ratio']['median']:.2f} | {(lambda d: f"{d:+.0f}" if round(d) else "0")(t['turn_deg']['median'])}° | {t['turn_within_30'] * 100:.0f}% | "
                   f"{t['diff_kmh']['median']:.0f} km/h |")
    return "\n".join(out)


# ---------------------------------------------------------------- robustness (results/robustness.json, scripts/robustness.py)
RB_NAMES = {"bw2": "latest pair", "bw4": "30 min", "bw7": "1 h", "bw13": "2 h", "gw2": "latest pair", "gw3": "20 min", "gw4": "30 min",
            "gw5": "40 min", "gw7": "1 h", "gw10": "1.5 h", "gw13": "2 h", "gwx3": "2 h, recent weighted", "gwx6": "2 h, recent weighted",
            "pysteps-lk": "30 min", "pysteps-lk7": "1 h", "pysteps-lk13": "2 h", "gw4f": "repaired field", "block": "26 km",
            "block-13km": "13 km", "block-51km": "51 km", "block-102km": "102 km", "block-smooth-13km": "13 km, blended",
            "block-smooth-26km": "26 km, blended", "block-smooth-51km": "51 km, blended", "block-smooth-102km": "102 km, blended"}


def rb():
    return json.loads((R / "robustness.json").read_text())


def t_units():
    """Intervals from resampling event blocks, calendar days and rainy spells."""
    I = rb()["intervals"]
    iv = lambda x: f"[{x['lo']:+.3f}, {x['hi']:+.3f}]"
    out = [f"| Comparison | Lead | Difference | Rain episodes ({I['units']['block']}) | Days ({I['units']['day']}) | Spells ({I['units']['spell']}) |",
           "|---|---|---|---|---|---|"]
    rows_ = [("gain", "bw7", None, "Block matching over persistence"), ("gain", "gw4", None, "Whole-map vector over persistence"),
             ("gain", "pysteps-lk", None, "pysteps Lucas-Kanade over persistence"),
             ("paired", "pysteps-lk", "bw7", "pysteps Lucas-Kanade − block matching"),
             ("paired", "pysteps-lk", "gw4", "pysteps Lucas-Kanade − whole-map vector"),
             ("paired", "bw7", "gw4", "Block matching − whole-map vector")]
    for lead in (60, 180):
        for kind, a, b, lab in rows_:
            x = I[kind][f"{a}_at_{lead}" if kind == "gain" else f"{a}_vs_{b}_at_{lead}"]
            out.append(f"| {lab} | +{lead} | {sg(x['block']['d'])} | {iv(x['block'])} | {iv(x['day'])} | {iv(x['spell'])} |")
    return "\n".join(out)


def t_heldout():
    """Each setting chosen on one half of the season and scored on the other."""
    H = rb()["held_out"]
    out = ["| Setting | Section 5 uses | Chosen on Apr–Jun | Its gain on Jul–Sep (regret) | Chosen on Jul–Sep | Its gain on Apr–Jun (regret) |",
           "|---|---|---|---|---|---|"]
    cap = lambda t: t if t.startswith("pysteps") else t[0].upper() + t[1:]
    for d in H["decisions"]:
        a, b = d["folds"]["Apr-Jun_to_Jul-Sep"], d["folds"]["Jul-Sep_to_Apr-Jun"]
        nm = dict(RB_NAMES, gw4="own matches") if "smoothed" in d["label"] else RB_NAMES
        out.append(f"| {cap(d['label'].replace('smoothed field', 'repaired field'))} | {nm[d['report']]} | {nm[a['pick']]} | {sg(a['pick_test'])} ({a['regret']:.3f}) | "
                   f"{nm[b['pick']]} | {sg(b['pick_test'])} ({b['regret']:.3f}) |")
    return "\n".join(out)


def t_heldout_final():
    """The methods at settings chosen on the other half, compared on the held-out half alone, +60 min."""
    F = rb()["held_out"]["final"]
    iv = lambda x: f"{sg(x['d'])} [{x['lo']:+.3f}, {x['hi']:+.3f}]"
    folds = [("Apr-Jun_to_Jul-Sep", "Jul–Sep"), ("Jul-Sep_to_Apr-Jun", "Apr–Jun")]
    out = ["| Comparison, +60 min | " + " | ".join(f"Held out: {lab} ({F[k]['events']} episodes)" for k, lab in folds) + " |", "|---|---|---|"]
    for a, b in (("pysteps Lucas-Kanade", "block matching"), ("pysteps Lucas-Kanade", "whole-map vector"), ("block matching", "whole-map vector")):
        out.append(f"| {a if a.startswith('pysteps') else a[0].upper() + a[1:]} − {b} | " + " | ".join(iv(F[k]["paired"][f"{a} vs {b}_at_60"]) for k, _ in folds) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- rain at cities (results/cities.jsonl)
CITY_FILE = R / "cities.jsonl"
CITY_MODELS = [("persistence", "Persistence (nothing moves)"), ("bw7", "Block matching"),
               ("gw4", "Whole-map vector"), ("pysteps-lk", "pysteps Lucas-Kanade")]
CITY_THR = 0.5          # mm in the hour


def city_rows():
    if "cities" not in _rows:
        _rows["cities"] = report.load(CITY_FILE)
    return _rows["cities"]


def city_scores(rows, m):
    """Counts and sums for 'at least CITY_THR mm in the hour' and the amount, pooled over the rows."""
    o = np.array([r["obs"] for r in rows]); f = np.array([r[m] for r in rows])
    O, F = o >= CITY_THR, f >= CITY_THR
    return dict(hit=int((O & F).sum()), miss=int((O & ~F).sum()), fa=int((~O & F).sum()),
                ae=float(np.abs(f - o).sum()), n=len(o), sf=float(f.sum()), so=float(o.sum()))


def city_csi_ci(rows, m, n_boot=2000, seed=3):
    """CSI with a 95% interval from resampling whole event blocks."""
    by = {}
    for r in rows:
        by.setdefault(r["event"], []).append(r)
    ev = sorted(by)
    sums = {e: city_scores(by[e], m) for e in ev}
    csi = lambda es: (lambda h, mi, fa: h / (h + mi + fa) if h + mi + fa else float("nan"))(
        sum(sums[e]["hit"] for e in es), sum(sums[e]["miss"] for e in es), sum(sums[e]["fa"] for e in es))
    rng = np.random.default_rng(seed)
    boots = [csi(rng.choice(ev, len(ev), replace=True)) for _ in range(n_boot)]
    return csi(ev), np.nanpercentile(boots, [2.5, 97.5])


def t_cities(hour=1):
    rows = [r for r in city_rows() if r["hour"] == hour]
    out = ["| Model type | Method | Rainy hours caught | False alarms | CSI [95% CI] | Typical error (mm) | Rain total ratio |",
           "|---|---|---|---|---|---|---|"]
    for i, (m, lab) in enumerate(CITY_MODELS):
        c = city_scores(rows, m)
        v, (lo, hi) = city_csi_ci(rows, m)
        pod = c["hit"] / (c["hit"] + c["miss"]); far = c["fa"] / (c["hit"] + c["fa"])
        out.append(f"| {group_of(m, CITY_MODELS[i - 1][0] if i else None)} | {lab} | {pod * 100:.0f}% | {far * 100:.0f}% | {v:.2f} [{lo:.2f}, {hi:.2f}] | {c['ae'] / c['n']:.2f} | {c['sf'] / c['so']:.2f} |")
    return "\n".join(out)


def t_cities_by_city(hour=1):
    rows = [r for r in city_rows() if r["hour"] == hour]
    cities = list(dict.fromkeys(r["city"] for r in rows))
    out = ["| City | Hours with rain | " + " | ".join(lab.replace(" (nothing moves)", "") for _, lab in CITY_MODELS) + " |",
           "|---|---|" + "---|" * len(CITY_MODELS)]
    for city in cities:
        rs = [r for r in rows if r["city"] == city]
        wet = sum(r["obs"] >= CITY_THR for r in rs)
        cells = []
        for m, _ in CITY_MODELS:
            c = city_scores(rs, m)
            d = c["hit"] + c["miss"] + c["fa"]
            cells.append(f"{c['hit'] / d:.2f}" if d else "n/a")
        out.append(f"| {city} | {wet} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def city_n(what):
    rows = city_rows()
    if what == "hours":
        return f"{len({(r['city'], r['issue']) for r in rows if r['hour'] == 1}):,}"
    if what == "wet":
        return f"{sum(r['obs'] >= CITY_THR for r in rows if r['hour'] == 1):,}"
    raise KeyError(what)


# ---------------------------------------------------------------- cell-size study (Appendix B.2)
sys.path.insert(0, str(ROOT / "scripts"))
import compare_grids as CG                                   # noqa: E402

GRID_NAMES = ["3.2km", "2km", "1km"]
GRID_LABEL = {"3.2km": "3.2 km", "2km": "2 km", "1km": "1 km"}
GRID_MODELS = [("block", "Block matching"), ("gw4", "Whole-map vector (30 min)"), ("pysteps-lk", "pysteps Lucas-Kanade")]
_grid_rows, _grid_gain, _grid_cmp = {}, {}, {}


def grid_rows(g):
    if g not in _grid_rows:
        _grid_rows[g] = CG.load(g)
    return _grid_rows[g]


def grid_gain(model, lead, key, g):
    k = (model, int(lead), key, g)
    if k not in _grid_gain:
        _grid_gain[k] = CG.gain(grid_rows(g), model, int(lead), key)
    return _grid_gain[k]


def grid_cmp(model, lead, key, g):
    """Gain on grid g minus gain on 3.2 km: (difference, low, high, share of blocks where g is better)."""
    k = (model, int(lead), key, g)
    if k not in _grid_cmp:
        _grid_cmp[k] = CG.compare(grid_gain(model, lead, key, "3.2km"), grid_gain(model, lead, key, g))
    return _grid_cmp[k]


def grid_key(nb):
    return {"30": "fss9_0.5", "10": "fss3_0.5"}.get(nb, f"fss9_{nb}")    # 30 km, 10 km, or a distance band


def t_grid(nb="30", lead=60):
    key = grid_key(nb)
    out = ["| Method | " + " | ".join(GRID_LABEL[g] for g in GRID_NAMES) + " | 2 km minus 3.2 km [95% CI] | 1 km minus 3.2 km [95% CI] | Episodes better at 1 km |",
           "|---|" + "---|" * (len(GRID_NAMES) + 3)]
    for m, lab in GRID_MODELS:
        vals = [f"{CG.pooled_gain(grid_gain(m, lead, key, g), sorted(grid_gain(m, lead, key, g))):+.3f}" for g in GRID_NAMES]
        d2, l2, h2, _ = grid_cmp(m, lead, key, "2km")
        d1, l1, h1, w1 = grid_cmp(m, lead, key, "1km")
        out.append(f"| {lab} | " + " | ".join(vals) + f" | {d2:+.3f} [{l2:+.3f}, {h2:+.3f}] | {d1:+.3f} [{l1:+.3f}, {h1:+.3f}] | {w1 * 100:.0f}% |")
    return "\n".join(out)


def t_grid_leads(nb="10"):
    key = grid_key(nb)
    leads = (30, 60, 120, 180)
    out = ["| Method | " + " | ".join(f"+{l} min" for l in leads) + " |", "|---|" + "---|" * len(leads)]
    for m, lab in GRID_MODELS:
        cells = []
        for l in leads:
            d, lo, hi, _ = grid_cmp(m, l, key, "1km")
            cells.append(f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        out.append(f"| {lab} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def t_grid_bands(lead=60):
    out = ["| Method | Distance from the nearest radar | " + " | ".join(GRID_LABEL[g] for g in GRID_NAMES) + " | 1 km minus 3.2 km [95% CI] |",
           "|---|---|" + "---|" * (len(GRID_NAMES) + 1)]
    for m, lab in GRID_MODELS:
        for band, blab in CG.BANDS:
            key = f"fss9_{band}"
            vals = [f"{CG.pooled_gain(grid_gain(m, lead, key, g), sorted(grid_gain(m, lead, key, g))):+.3f}" for g in GRID_NAMES]
            d, lo, hi, _ = grid_cmp(m, lead, key, "1km")
            out.append(f"| {lab} | {blab} | " + " | ".join(vals) + f" | {d:+.3f} [{lo:+.3f}, {hi:+.3f}] |")
    return "\n".join(out)


def t_grid_cities():
    out = ["| Method | " + " | ".join(GRID_LABEL[g] for g in GRID_NAMES) + " |", "|---|" + "---|" * len(GRID_NAMES)]
    rows = {g: [r for r in report.load(R / f"cities-grid-{g}.jsonl") if r["hour"] == 1] for g in GRID_NAMES
            if (R / f"cities-grid-{g}.jsonl").exists()}
    # the cell-size study (Appendix B.2) uses block matching on the latest pair
    for m, lab in [("block", "Block matching") if m == "bw7" else (m, lab) for m, lab in CITY_MODELS]:
        cells = []
        for g in GRID_NAMES:
            if g not in rows:
                cells.append("–"); continue
            c = city_scores(rows[g], m)
            cells.append(f"{c['hit'] / (c['hit'] + c['miss'] + c['fa']):.2f}")
        out.append(f"| {lab} | " + " | ".join(cells) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- block-size study (Appendix B.3)
BS_SIZES = [13, 26, 51, 102]
_bs = {}


def bs_rows(g):
    if g not in _bs:
        _bs[g] = report.load(R / f"blocksize-{g}.jsonl")
    return _bs[g]


def bs_name(km, blend=False):
    return ("block-smooth" if blend else "block") + ("" if km == 26 and not blend else f"-{km}km")


def bs_gain(model, lead, g):
    gs = CG.gain(bs_rows(g), model, int(lead))
    return CG.pooled_gain(gs, sorted(gs))


def bs_cmp(model, lead, g):
    """model minus the 26 km blocks, same grid: (d, lo, hi, share of blocks better)."""
    k = ("bs", model, int(lead), g)
    if k not in _bs:
        _bs[k] = CG.compare(CG.gain(bs_rows(g), "block", int(lead)), CG.gain(bs_rows(g), model, int(lead)))
    return _bs[k]


def t_blocksize(g="3.2km"):
    out = ["| Block size | Per block, +60 min | Per block minus 26 km [95% CI] | Blended, +60 min | Blended minus 26 km per block [95% CI] | Rain ratio at +180, per block |",
           "|---|---|---|---|---|---|"]
    S180 = {}
    for km in BS_SIZES:
        cells = []
        for blend in (False, True):
            m = bs_name(km, blend)
            cells.append(sg(bs_gain(m, 60, g)))
            if m == "block":
                cells.append("(reference)")
            else:
                d, lo, hi, _ = bs_cmp(m, 60, g)
                cells.append(f"{sg(d)} [{lo:+.3f}, {hi:+.3f}]")
        rows = [r for r in bs_rows(g) if r["model"] == bs_name(km) and r["lead"] == 180]
        ratio = sum(r["sum_f"] for r in rows) / sum(r["sum_t"] for r in rows)
        kmpc = 3.2 * 224 / CG.GRID_CELLS[g][0]            # km per cell on that grid, as grid.py computes it
        out.append(f"| {km} km ({max(1, int(round(km / kmpc)))} cells) | " + " | ".join(cells) + f" | {ratio:.2f} |")
    d, lo, hi, _ = bs_cmp("gw4", 60, g)
    out.append(f"| whole map (one vector, 30 min) | {sg(bs_gain('gw4', 60, g))} | {sg(d)} [{lo:+.3f}, {hi:+.3f}] | | | |")
    return "\n".join(out)


TABLES = {"blocksize32": t_blocksize, "blocksize2": lambda: t_blocksize("2km"),
          "grid30": t_grid, "grid10": lambda: t_grid("10"), "gridleads": t_grid_leads, "gridbands": t_grid_bands,
          "gridcities": t_grid_cities,
          "cities": t_cities, "cities2": lambda: t_cities(2), "citiesbycity": t_cities_by_city,
          "probs": t_probs, "probspaired": t_probs_paired,
          "gauges": t_gauges, "era5": t_era5, "units": t_units, "heldout": t_heldout, "heldoutfinal": t_heldout_final,
          "headline": t_headline_compact, "headline_full": t_headline, "leads": t_leads, "windows": t_windows, "longleads": t_longleads, "months": t_months,
          "paired": t_paired, "ratioq": t_ratioq, "cadence": t_cadence}


def render(text):
    def sub(m):
        body = m.group(1)
        parts = body.split(":")
        if parts[0] == "table":
            return TABLES[parts[1]]()
        return scalar(parts[0], parts[1:])
    return re.sub(r"\{\{([^{}]+)\}\}", sub, text)


if __name__ == "__main__":
    for src, dst in (("docs/REPORT.template.md", "docs/REPORT.md"), ("README.template.md", "README.md")):
        out = render((ROOT / src).read_text())
        left = re.findall(r"\{\{[^}]*\}\}", out)
        assert not left, left
        (ROOT / dst).write_text(out)
        print("wrote", dst, len(out.splitlines()), "lines")
