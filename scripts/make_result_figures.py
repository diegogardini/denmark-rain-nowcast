#!/usr/bin/env python3
"""Figures built from real data and benchmark results (docs/figures/1x-*.svg).

  python scripts/make_result_figures.py [real scantypes headline rain month windows cadence]   # default: all
Uses results/benchmark-10min.jsonl, benchmark-10min-window.jsonl and check-cadence-{10,5}min.jsonl
(the archive's 10-minute axis of full-range scans; see the report, section 2).

Every figure is dark (scripts/mapstyle.py) and laid out for one narrow column, so it stays
readable on a phone: panels are stacked or in a 2 x 2 grid, and legends sit underneath.
"""
import sys, json, datetime as dt
from pathlib import Path
import numpy as np
import matplotlib
import matplotlib.ticker
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab import motion, report, models
from nowcastlab.data import Archive
from nowcastlab.radar import BOUNDS
sys.path.insert(0, str(ROOT / "scripts"))
import mapstyle as MS

MS.use_dark_charts()
OUT = ROOT / "docs" / "figures"
FINAL = ROOT / "results" / "benchmark-10min.jsonl"
WINDOW = ROOT / "results" / "benchmark-10min-window.jsonl"
CAD10 = ROOT / "results" / "check-cadence-10min.jsonl"
CAD5 = ROOT / "results" / "check-cadence-5min.jsonl"
W = MS.WIDTH

# display names (short: they must fit a phone) and colours (warm = the simple models, amber whole-map vector and raspberry per block)
LAB = {"persistence": "Persistence (nothing moves)", "block": "Block matching, last pair",
       "bw2": "Block matching, last pair", "bw4": "Block matching, 30 min", "bw7": "Block matching, 1 h",
       "bw13": "Block matching, 2 h",
       "gw2": "Whole-map vector, last pair", "gw4": "Whole-map vector, 30 min",
       "gw7": "Whole-map vector, 1 h", "gw13": "Whole-map vector, 2 h",
       "pysteps-lk": "pysteps Lucas-Kanade", "pysteps-lk13": "pysteps Lucas-Kanade, 2 h",
       "pysteps-sprog": "pysteps S-PROG", "pysteps-steps-mean": "pysteps STEPS ensemble"}
COL = MS.SERIES
# plain method names for figures outside the history studies (section 5 states each method's history once)
NAME = {"persistence": "Persistence", "bw7": "Block matching", "block": "Block matching", "gw4": "Whole-map vector",
        "pysteps-lk": "pysteps Lucas-Kanade", "pysteps-sprog": "pysteps S-PROG", "pysteps-steps-mean": "pysteps STEPS mean"}


def save(fig, name):
    fig.savefig(OUT / name, facecolor=MS.BG, bbox_inches="tight", pad_inches=0.15); plt.close(fig)
    # SVG text names DejaVu Sans, which phones lack; give the browser sans-serif fallbacks instead of its serif default
    f = OUT / name
    f.write_text(f.read_text().replace("font-family: 'DejaVu Sans'",
                                       "font-family: 'DejaVu Sans', 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"))


def legend_below(fig, handles, ncol=1, y=0.0):
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, y), ncol=ncol, fontsize=11,
               handlelength=1.8, columnspacing=1.2)


def lines(models_, **kw):
    return [Line2D([0], [0], color=COL[m], marker="o", lw=2.4, ms=5, label=LAB[m], **kw) for m in models_]


# ------------------------------------------------------------------ real-data illustrations
def example_index(arch):
    """Fixed example (2026-09-04 10:40Z), chosen once for plenty of rain and clearly measurable motion,
    not re-picked from results."""
    return int((dt.datetime(2026, 9, 4, 10, 40, tzinfo=dt.UTC).timestamp() - arch.t0) // arch.step)


def fig_vectors(arch, i):
    """The two simple methods on one real scan pair: a vector per block, or one for the whole map."""
    a, b = (np.nan_to_num(arch.rate[j]) for j in (i - 1, i))
    f = motion.fill_motion_field(motion.compute_block_motion(a, b, 8, 6))
    gx, gy = models.GlobalWindows().pair_vectors([a, b])[0]      # the whole-map vector, as the model measures it
    fig, axs = plt.subplots(2, 1, figsize=(W, 9.4), facecolor=MS.BG)
    MS.rain_map(axs[0], b, "One vector per block", dim=True)
    MS.rain_map(axs[1], b, "One vector for the whole map", dim=True)
    ys, xs = np.mgrid[0:f.conf.shape[0], 0:f.conf.shape[1]]
    lon = BOUNDS["west"] + (xs * 8 + 4) / 224 * (BOUNDS["east"] - BOUNDS["west"])
    lat = BOUNDS["north"] - (ys * 8 + 4) / 160 * (BOUNDS["north"] - BOUNDS["south"])
    w = motion.motion_weight(f.conf)
    br, bc = f.conf.shape
    rain = np.array([[b[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8].mean() for c in range(bc)] for r in range(br)])
    m = (f.conf > 0.3) & (rain > 0.3) & (xs % 2 == 0) & (ys % 2 == 0)   # over rain, confident, every other block
    clon, clat = (BOUNDS["east"] - BOUNDS["west"]) / 224, (BOUNDS["north"] - BOUNDS["south"]) / 160    # one cell
    dlon, dlat = 8 * clon, 8 * clat
    for lo, la in zip(lon[m], lat[m]):                         # outline the blocks, so each arrow sits in its own
            axs[0].add_patch(plt.Rectangle((lo - dlon / 2, la - dlat / 2), dlon, dlat, fill=False, ec=MS.INK, lw=0.5, alpha=0.35, zorder=3))
    bx, by = (f.dx * w)[m], (f.dy * w)[m]                      # each block's shift between the scans, in cells
    fit = 14 / max(np.hypot(bx, by).max(), np.hypot(gx, gy))      # longest arrow 14 cells: fits the 2 x 2 blocks around it
    kw = dict(angles="xy", scale_units="xy", scale=1, pivot="middle", width=0.006, headwidth=3.5, headlength=3.5, headaxislength=3, zorder=4)
    axs[0].quiver(lon[m], lat[m], bx * clon * fit, -by * clat * fit, color=MS.MODEL["block"], **kw)
    axs[1].quiver(lon[m], lat[m], np.full(m.sum(), gx * clon * fit), np.full(m.sum(), -gy * clat * fit), color=MS.MODEL["gw4"], **kw)
    fig.tight_layout(); save(fig, "10-vectors.svg")


def fig_scan_types():
    """The same moment in the two kinds of DMI scan: where each has data, and the rain it shows."""
    arch = Archive(stride=1)
    i = int((dt.datetime(2026, 9, 4, 10, 40, tzinfo=dt.UTC).timestamp() - arch.t0) // arch.step)
    fig, axs = plt.subplots(2, 1, figsize=(W, 9.0), facecolor=MS.BG)
    for ax, j, ttl in [(axs[0], i, "Full range, 10:40 UTC"), (axs[1], i + 1, "Doppler, 10:45 UTC")]:
        g = arch.rate[j]
        MS.rain_map(ax, g, ttl)
        ax.imshow(np.ma.masked_where(np.isfinite(g), np.ones_like(g)), extent=MS.EXT, cmap=ListedColormap(["#3a4654"]),
                  origin="upper", aspect=MS.ASPECT, alpha=0.9, zorder=1.5)
    fig.tight_layout(); save(fig, "16-scan-types.svg")


# ------------------------------------------------------------------ benchmark charts
def fig_headline(S):
    """The summary chart: the simple motion models (warm) against the state of the art (pysteps, cool)."""
    groups = [("Simple motion models (this project)", [("bw7", "Block matching"), ("gw4", "Whole-map vector")]),
              ("State of the art (pysteps)", [("pysteps-lk", "Lucas-Kanade"), ("pysteps-sprog", "S-PROG"),
                                              ("pysteps-steps-mean", "STEPS, ensemble mean")])]
    leads = [30, 60, 90, 120, 180]
    fig, axs = plt.subplots(2, 1, figsize=(W, 11.0), gridspec_kw=dict(height_ratios=[1.0, 1.15]))
    # top: one hour ahead, how much more accurately the rain is placed than by "nothing moves"
    ax = axs[0]; ax.set_axisbelow(True); y = 0.35; ticks, labels = [], []
    p60 = S[("persistence", 60)]["FSS9"]
    for g, (head, ms) in enumerate(groups):
        ax.text(0, y - 0.15, head, color=MS.INK, fontsize=12, fontweight="bold", va="bottom")
        y += 0.75
        for m, lab in ms:
            v = (S[(m, 60)]["FSS9"] / p60 - 1) * 100
            ax.barh(y, v, height=0.62, color=COL[m])
            ax.text(v + 0.8, y, f"+{v:.0f}%", va="center", color=MS.INK, fontsize=11)
            ticks.append(y); labels.append(lab); y += 0.85
        y += 0.55
    ax.set_yticks(ticks); ax.set_yticklabels(labels, color=MS.INK, fontsize=11)
    ax.set_ylim(y - 0.35, -0.2)                                     # top to bottom, room for the first heading
    ax.set_xlim(0, 50); ax.grid(axis="y", visible=False)
    ax.set_xlabel('rain placed more accurately than by "nothing moves" (%)')
    ax.set_title("One hour ahead", loc="left", fontsize=12.5, pad=10)
    # bottom: accuracy across lead times, "nothing moves" dashed
    ax = axs[1]
    ax.plot(leads, [S[("persistence", l)]["FSS9"] for l in leads], "--", color=MS.MUTED, lw=2.2, marker="o", ms=5)
    for head, ms in groups:
        for m, lab in ms:
            ax.plot(leads, [S[(m, l)]["FSS9"] for l in leads], "-", color=COL[m], lw=2.4, marker="o", ms=5)
    ax.set_xticks(leads); ax.set_xlabel("minutes ahead"); ax.set_ylabel("spatial accuracy (1 = perfect)")
    ax.set_title("Further ahead: accuracy falls, and the methods converge", loc="left", fontsize=12.5)
    fig.tight_layout()
    head = lambda t: Line2D([], [], color="none", label=t)
    h = [head("Simple motion models")] + [Line2D([0], [0], color=COL[m], marker="o", lw=2.4, ms=5, label=lab) for m, lab in groups[0][1]]
    h += [Line2D([0], [0], color=MS.MUTED, ls="--", marker="o", lw=2.2, ms=5, label='"Nothing moves" (reference)')]
    h += [head("State of the art (pysteps)")] + [Line2D([0], [0], color=COL[m], marker="o", lw=2.4, ms=5, label=lab) for m, lab in groups[1][1]]
    leg = fig.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2, fontsize=11, handlelength=3.2, columnspacing=1.6)
    for t in leg.get_texts():
        if t.get_text() in ("Simple motion models", "State of the art (pysteps)"):
            t.set_fontweight("bold")
    save(fig, "12-headline.svg")


def fig_rain_total(rows, leads=(30, 60, 120)):
    """Forecast over observed rain, one value per rain episode, at three lead times side by side (section 5.4)."""
    order = ["persistence", "bw7", "gw4", "pysteps-lk", "pysteps-sprog", "pysteps-steps-mean"]
    names = {"persistence": "Persistence", "bw7": "Block matching", "gw4": "Whole-map vector",
             "pysteps-lk": "pysteps Lucas-Kanade", "pysteps-sprog": "pysteps S-PROG", "pysteps-steps-mean": "pysteps STEPS mean"}
    ev = {}
    for r in rows:
        if r["lead"] in leads and r["model"] in order:
            d = ev.setdefault((r["lead"], r["event"], r["model"]), [0.0, 0.0]); d[0] += r["sum_f"]; d[1] += r["sum_t"]
    fig, axs = plt.subplots(len(leads), 1, figsize=(W, 10.5), sharex=True)
    for ax, lead in zip(axs, leads):
        data = [[v[0] / v[1] for (l, e, m), v in ev.items() if l == lead and m == mod and v[1] > 0] for mod in order]
        bp = ax.boxplot(data, orientation="horizontal", widths=0.6, patch_artist=True, whis=(10, 90),
                        flierprops=dict(marker="o", markersize=2.5, markerfacecolor=MS.MUTED, markeredgecolor="none"))
        for patch, mod in zip(bp["boxes"], order):
            patch.set_facecolor(COL[mod]); patch.set_alpha(0.45); patch.set_edgecolor(COL[mod])
        for key in ("whiskers", "caps"):
            for ln in bp[key]:
                ln.set_color(MS.MUTED)
        for med in bp["medians"]:
            med.set_color(MS.INK); med.set_linewidth(2)
        ax.axvline(1, color=MS.MUTED, lw=1); ax.set_xscale("log"); ax.set_xlim(0.3, 3.2)
        ax.set_xticks([0.5, 0.7, 1, 1.4, 2]); ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter()); ax.minorticks_off()
        ax.grid(axis="y", visible=False)
        ax.set_title(f"+{lead} minutes", loc="left", fontsize=12.5)
        ax.set_yticks(range(1, len(order) + 1)); ax.set_yticklabels([names[m] for m in order], color=MS.INK)
        ax.invert_yaxis()
    fig.supxlabel("forecast / observed rain, one value per rain episode (1 = right amount)", fontsize=11, color=MS.MUTED)
    fig.tight_layout(); save(fig, "13-rain-total.svg")


def fig_by_month(rows, lead=60):
    meta = json.loads(FINAL.with_suffix(".meta.json").read_text())
    agg = {}
    for r in rows:
        if r["lead"] == lead:
            mo = dt.datetime.fromtimestamp(meta["events"][r["event"]][0], dt.UTC).strftime("%b")
            a = agg.setdefault((mo, r["model"]), [0.0, 0.0]); a[0] += r["fss9_0.5_e"]; a[1] += r["fss9_0.5_r"]
    months = ["Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    f = lambda a: 1 - a[0] / a[1]
    order = ["bw7", "gw4", "pysteps-lk"]
    fig, ax = plt.subplots(figsize=(W, 5.2))
    w = 0.26
    for j, mod in enumerate(order):
        ys = [f(agg[(m, mod)]) - f(agg[(m, "persistence")]) for m in months]
        ax.bar(np.arange(len(months)) + (j - 1) * w, ys, w * 0.92, color=COL[mod], label=NAME[mod])
    ax.axhline(0, color=MS.MUTED, lw=1); ax.set_xticks(range(len(months))); ax.set_xticklabels(months, color=MS.INK)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("FSS gain over persistence")
    fig.tight_layout()
    legend_below(fig, [plt.Rectangle((0, 0), 1, 1, color=COL[m], label=NAME[m]) for m in order], ncol=1)
    save(fig, "14-by-month.svg")


def fig_windows(S):
    wins = [2, 3, 4, 5, 7, 10, 13]
    minutes = [(n - 1) * 10 for n in wins]
    fig, axs = plt.subplots(2, 1, figsize=(W, 10.2))
    bwins = [2, 4, 7, 13]
    for lead, ls in ((60, "-"), (180, "--")):
        axs[0].plot(minutes, [S[(f"gw{n}", lead)]["dFSS9"] for n in wins], ls, marker="o", color=COL["gw4"], lw=2.4, ms=5,
                    label=f"Whole-map vector, +{lead} min")
        axs[0].plot([(n - 1) * 10 for n in bwins], [S[(f"bw{n}", lead)]["dFSS9"] for n in bwins], ls, marker="o",
                    color=COL["bw7"], lw=2.4, ms=5, label=f"Block matching, +{lead} min")
    axs[0].set_xticks([10, 30, 60, 90, 120]); axs[0].set_xlabel("minutes of history for the motion")
    lo, hi = axs[0].get_ylim()
    axs[0].set_ylim(lo - 0.6 * (hi - lo), hi)          # room for the legend below the curves
    axs[0].set_ylabel("FSS gain over persistence"); axs[0].legend(fontsize=10, ncol=2, loc="lower center")
    axs[0].set_title("More history: a little for block matching", fontsize=12.5, loc="left")
    leads = [30, 60, 90, 120, 180, 240, 360]
    shown = [("bw2", "--"), ("bw7", "-"), ("gw4", ":"), ("pysteps-lk", "-"), ("pysteps-lk13", "--")]
    for m, ls in shown:
        axs[1].plot(leads, [S[(m, l)]["dFSS9"] for l in leads], ls, marker="o", color=COL[m], lw=2.4, ms=5)
    axs[1].axhline(0, color=MS.MUTED, lw=1); axs[1].set_xscale("log"); axs[1].set_xticks([30, 60, 120, 240, 360])
    axs[1].get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter()); axs[1].minorticks_off()
    axs[1].set_xlabel("lead time (minutes)"); axs[1].set_ylabel("FSS gain over persistence")
    axs[1].set_title("Against pysteps Lucas-Kanade, to 6 hours", fontsize=12.5, loc="left")
    fig.tight_layout()
    legend_below(fig, [Line2D([0], [0], color=COL[m], ls=ls, marker="o", lw=2.4, ms=5, label=LAB[m]) for m, ls in shown], ncol=1)
    save(fig, "15-windows.svg")


def fig_cadence(S10, S5):
    """Same footprint, same issue times: motion from full-range scans 10 minutes apart against every 5-minute scan."""
    pairs = [("Block\nlast pair", "block", "block"), ("Block\n30 min", "bw4", "bw7"), ("Block\n60 min", "bw7", "bw13"),
             ("Map vector\nlast pair", "gw2", "gw2"),
             ("Map vector\n30 min", "gw4", "gw7"), ("Map vector\n60 min", "gw7", "gw13"),
             ("pysteps\nLK", "pysteps-lk", "pysteps-lk7")]
    fig, axs = plt.subplots(2, 1, figsize=(W, 9.4), sharex=True)
    x = np.arange(len(pairs))
    for ax, lead in zip(axs, (60, 180)):
        a = [S10[(m10, lead)]["dFSS9"] for _, m10, _ in pairs]
        b = [S5[(m5, lead)]["dFSS9"] for _, _, m5 in pairs]
        ax.bar(x - 0.2, a, 0.38, color="#a9b6c2", label="scans 10 minutes apart")
        ax.bar(x + 0.2, b, 0.38, color="#5d6b78", label="scans 5 minutes apart")
        ax.axhline(0, color=MS.MUTED, lw=1); ax.set_ylabel("FSS gain over persistence"); ax.grid(axis="x", visible=False)
        ax.set_title(f"+{lead} min", fontsize=12.5, loc="left")
    axs[1].set_xticks(x); axs[1].set_xticklabels([p[0] for p in pairs], fontsize=9.5, color=MS.INK)
    fig.tight_layout()
    legend_below(fig, [plt.Rectangle((0, 0), 1, 1, color=c, label=l) for c, l in
                       (("#a9b6c2", "scans 10 minutes apart"), ("#5d6b78", "scans 5 minutes apart"))], ncol=2)
    save(fig, "17-cadence.svg")


def fig_grid(lead=60):
    """Cell-size study: FSS gain over persistence at +60 min on the 3.2, 2 and 1 km grids."""
    import compare_grids as CG
    grids, xs = ["3.2km", "2km", "1km"], [3.2, 2.0, 1.0]
    rows = {g: CG.load(g) for g in grids}
    models = [("block", "Block matching"), ("gw4", "Whole-map vector"), ("pysteps-lk", "pysteps Lucas-Kanade")]
    fig, axs = plt.subplots(2, 1, figsize=(W, 9.0), sharex=True)
    for ax, (key, title) in zip(axs, (("fss9_0.5", "Judged over about 30 km"), ("fss3_0.5", "Judged over about 10 km"))):
        for m, lab in models:
            ys = [CG.pooled_gain(CG.gain(rows[g], m, lead, key), sorted(CG.gain(rows[g], m, lead, key))) for g in grids]
            ax.plot(xs, ys, "-o", color=COL[m], lw=2.4, ms=6, label=lab)
        ax.set_title(f"{title}: FSS gain over persistence, +{lead} min", loc="left", fontsize=12.5)
        ax.set_ylabel("FSS gain over persistence")
    axs[1].set_xlim(3.4, 0.8); axs[1].set_xticks(xs); axs[1].set_xticklabels(["3.2 km", "2 km", "1 km"])
    axs[1].set_xlabel("grid cell size (finer to the right)")
    fig.tight_layout()
    legend_below(fig, [Line2D([0], [0], color=COL[m], marker="o", lw=2.4, ms=6, label=lab) for m, lab in models], ncol=1)
    save(fig, "18-grid.svg")


def fig_timing(thr="0.5"):
    """Timing at one spot (Appendix C): for each statement and horizon, how much of calibrated STEPS' Brier
    improvement over persistence the whole-map vector reaches, as rain or no rain and as 40 shifted copies."""
    J = json.loads((ROOT / "results" / "local-timing.json").read_text())["results"]
    names = {"start": "rain starts within", "stop": "dry for good within", "any": "rain within"}
    rows_ = [(ev, h) for ev in ("start", "any", "stop") for h in (30, 60, 120)]
    fig, ax = plt.subplots(figsize=(W, 7.4))
    for j, (ev, h) in enumerate(rows_):
        r = J[f"{thr}|{ev}|{h}"]["improvement"]
        a, b = r["gw"] / r["steps_cal"] * 100, r["gw_shift"] / r["steps_cal"] * 100
        ax.barh(j - 0.18, a, height=0.34, color=COL["gw4"], alpha=0.45)
        ax.barh(j + 0.18, b, height=0.34, color=COL["gw4"])
        ax.text(b + 1.5, j + 0.18, f"{b:.0f}%", va="center", color=MS.INK, fontsize=10.5)
    ax.axvline(100, color=COL["pysteps-steps-mean"], lw=2.4)
    ax.set_yticks(range(len(rows_))); ax.set_yticklabels([f"{names[ev]} {h if h < 60 else h // 60} {'min' if h < 60 else 'h'}" for ev, h in rows_])
    ax.invert_yaxis(); ax.grid(axis="y", visible=False); ax.set_xlim(0, 112)
    ax.set_xlabel("share of STEPS' Brier improvement over persistence (%)")
    fig.tight_layout()
    legend_below(fig, [plt.Rectangle((0, 0), 1, 1, color=COL["gw4"], alpha=0.45, label="Whole-map vector, rain or no rain"),
                       plt.Rectangle((0, 0), 1, 1, color=COL["gw4"], label="Whole-map vector, 40 shifted copies"),
                       Line2D([0], [0], color=COL["pysteps-steps-mean"], lw=2.4, label="pysteps STEPS, calibrated (100%)")], ncol=1)
    save(fig, "29-local-timing.svg")


def fig_local(thr="0.5"):
    """A chance of rain at one spot (Appendix C): Brier improvement over persistence at every 10-minute step,
    scored cell by cell, every setting chosen on the other half of the season."""
    J = json.loads((ROOT / "results" / "local-probs.json").read_text())
    I, L = J["by_threshold"][thr]["improvement"], J["leads"]
    shown = [("steps_grow_cal", "pysteps STEPS, best window, calibrated", COL["pysteps-steps-mean"], "-"),
             ("gw_grow", "Whole-map vector, the probability model", COL["gw4"], "-"),
             ("gw_fixed", "Whole-map vector, one fixed spread for all lead times", COL["gw4"], (0, (5, 3))),
             ("gw", "Whole-map vector, rain or no rain in the cell", COL["gw4"], (0, (1.5, 2)))]
    fig, ax = plt.subplots(figsize=(W, 4.8))
    for v, lab, c, ls in shown:
        ax.plot(L, I[v], ls=ls, marker="o", color=c, lw=2.4, ms=4.5, label=lab)
    ax.axhline(0, color=MS.MUTED, lw=1)
    ax.set_xticks([10, 30, 60, 90, 120]); ax.set_xlabel("minutes ahead"); ax.set_ylabel("Brier improvement over persistence")
    fig.tight_layout()
    legend_below(fig, [Line2D([0], [0], color=c, ls=ls, marker="o", lw=2.4, ms=4.5, label=lab) for v, lab, c, ls in shown], ncol=1)
    save(fig, "28-local-chance.svg")


def fig_turning(rating="era5"):
    """History in steady and turning flow (Appendix B.1): FSS gain against the amount of history, relative to the
    history section 5 uses, in the third of issue times where the 700 hPa wind changed least over the next hour
    and the third where it changed most."""
    J = json.loads((ROOT / "results" / "turning-flow.json").read_text())["ratings"][rating]
    fams = [("Whole-map vector", [("gw2", 10), ("gw3", 20), ("gw4", 30), ("gw5", 40), ("gw7", 60), ("gw10", 90), ("gw13", 120)], "gw4"),
            ("Block matching", [("bw2", 10), ("bw4", 30), ("bw7", 60), ("bw13", 120)], "bw7")]
    groups = [("steady", "steady flow", "#6f7d8a", "o"), ("turning", "turning flow", MS.INK, "D")]
    fig, axs = plt.subplots(2, 2, figsize=(W, 7.6), sharex=True, sharey=True)
    for r, (name, ms, ref) in enumerate(fams):
        for c, lead in enumerate((60, 180)):
            ax = axs[r][c]
            for g, lab, col, mk in groups:
                base = J["gain"][f"{ref}_{g}_at_{lead}"]
                ys = [J["gain"][f"{m}_{g}_at_{lead}"] - base for m, _ in ms]
                ax.plot([x for _, x in ms], ys, "-", marker=mk, color=col, lw=2.2, ms=5, label=lab)
            ref_x = dict(ms)[ref]
            ax.axhline(0, color=MS.MUTED, lw=1); ax.axvline(ref_x, color=MS.MUTED, lw=1, ls=(0, (2, 2)))
            ax.set_xscale("log"); ax.set_xticks([10, 30, 60, 120]); ax.set_xticklabels(["10 min", "30 min", "1 h", "2 h"])
            ax.minorticks_off()
            ax.set_title(f"{name}, +{lead} min", loc="left", fontsize=12)
        axs[r][0].set_ylabel("FSS against section 5's history")
    for ax in axs[1]:
        ax.set_xlabel("history")
    fig.tight_layout()
    legend_below(fig, [Line2D([0], [0], color=col, lw=2.2, marker=mk, ms=5, label=f"{lab} (median change {J['median'][g]:.0f} km/h)")
                       for g, lab, col, mk in groups]
                 + [Line2D([0], [0], color=MS.MUTED, lw=1, ls=(0, (2, 2)), label="history used in section 5")], ncol=1)
    save(fig, "27-turning-flow.svg")


def fig_units():
    """Interval widths by resampling unit (Appendix D.3): each interval drawn around its own estimate, so their
    sizes can be compared directly."""
    I = json.loads((ROOT / "results" / "robustness.json").read_text())["intervals"]
    rows_ = [("gain", "bw7", None, "Block matching − persistence"), ("gain", "gw4", None, "Whole-map vector − persistence"),
             ("gain", "pysteps-lk", None, "Lucas-Kanade − persistence"),
             ("paired", "pysteps-lk", "bw7", "Lucas-Kanade − block matching"),
             ("paired", "pysteps-lk", "gw4", "Lucas-Kanade − whole-map vector"),
             ("paired", "bw7", "gw4", "Block matching − whole-map vector")]
    units = [("block", f"rain episodes ({I['units']['block']})", MS.INK), ("day", f"days ({I['units']['day']})", "#a9b6c2"),
             ("spell", f"rainy spells ({I['units']['spell']})", "#6f7d8a")]
    fig, axs = plt.subplots(2, 1, figsize=(W, 9.6), sharex=True)
    for ax, lead in zip(axs, (60, 180)):
        labels = []
        for r, (kind, a, b, lab) in enumerate(rows_):
            x = I[kind][f"{a}_at_{lead}" if kind == "gain" else f"{a}_vs_{b}_at_{lead}"]
            d = x["block"]["d"]
            for k, (u, _, c) in enumerate(units):
                y = r + (k - 1) * 0.22
                ax.plot([x[u]["lo"] - d, x[u]["hi"] - d], [y, y], color=c, lw=3, solid_capstyle="butt")
            if abs(d) < 0.035:                                  # where a difference of 0 lies, when it is on the chart
                ax.plot([-d, -d], [r - 0.38, r + 0.38], color=MS.MUTED, lw=1.6, ls=(0, (2, 2)))
            labels.append(f"{lab}\n{d:+.3f}")
        ax.axvline(0, color=MS.MUTED, lw=1)
        ax.set_yticks(range(len(rows_))); ax.set_yticklabels(labels, fontsize=10.5, color=MS.INK)
        ax.set_ylim(len(rows_) - 0.5, -0.5); ax.grid(axis="y", visible=False)
        ax.set_title(f"+{lead} minutes", loc="left", fontsize=12.5)
    axs[-1].set_xlabel("95% interval around the estimate (FSS)")
    fig.tight_layout()
    legend_below(fig, [Line2D([0], [0], color=c, lw=3, label=lab) for _, lab, c in units]
                 + [Line2D([0], [0], color=MS.MUTED, lw=1.6, ls=(0, (2, 2)), label="no difference (0)")], ncol=2)
    save(fig, "26-resampling-units.svg")


def fig_probs():
    """The chance of rain (section 5.5): Brier improvement against the neighbourhood window, and reliability."""
    P = json.loads((ROOT / "results" / "probs.json").read_text())
    wins = list(P["windows_km"]); xs = [3.2 if w == "" else P["windows_km"][w] for w in wins]
    shown = [("bw7", "Block matching", COL["bw7"], "-"), ("gw4", "Whole-map vector", COL["gw4"], "-"),
             ("pysteps-lk", "pysteps Lucas-Kanade", COL["pysteps-lk"], "-"),
             ("pysteps-steps-default-mean", "pysteps STEPS, 24 members", COL["pysteps-steps-mean"], "-")]
    fig, axs = plt.subplots(3, 1, figsize=(W, 14.0))
    for ax, lead in zip(axs[:2], (60, 180)):
        for m, lab, c, ls in shown:
            ax.plot(xs, [P["improvement"][f"{m}{w}_at_{lead}"]["d"] for w in wins], ls, marker="o", color=c, lw=2.4, ms=5, label=lab)
        ax.set_xscale("log"); ax.set_xticks([3.2, 10, 16, 29, 48, 80]); ax.set_xticklabels(["cell", "10", "16", "29", "48", "80"])
        ax.minorticks_off(); ax.set_ylabel("Brier improvement"); ax.set_xlabel("neighbourhood window (km)")
        ax.set_title(f"Chance of rain at +{lead} min, by neighbourhood", loc="left", fontsize=12.5)
    ax = axs[2]
    ax.plot([0, 1], [0, 1], color=MS.MUTED, lw=1)
    for m, lab, c, ls in shown:                       # each method at its best window at +60 min, as in the Brier comparison
        kind = "rel" + (P["best_window"][m] or "_n1")
        r = P["reliability"][f"{m}_{kind}_at_60"]
        ok = [i for i, n in enumerate(r["n"]) if n > 2000]
        ax.plot([r["p"][i] for i in ok], [r["o"][i] for i in ok], "-o", color=c, lw=2.2, ms=5, label=lab)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("forecast chance of rain"); ax.set_ylabel("how often it rained")
    ax.set_title("Reliability at +60 min (on the diagonal = honest)\neach method at its best window", loc="left", fontsize=12.5)
    fig.tight_layout()
    km = lambda m: "cell by cell" if not P["best_window"][m] else f"best window {P['windows_km'][P['best_window'][m]]} km"
    legend_below(fig, [Line2D([0], [0], color=c, marker="o", lw=2.4, ms=5, label=f"{lab} ({km(m)})") for m, lab, c, ls in shown], ncol=1)
    save(fig, "21-probabilities.svg")


def fig_cities():
    """Where the five cities of section 5.6 are, on the dark map with coastlines."""
    import run_cities
    fig, ax = plt.subplots(figsize=(4.8, 5.4), facecolor=MS.BG)
    MS.rain_map(ax, np.zeros((MS.grid_rows(), MS.grid_cols())))
    ax.set_xlim(7.8, 13.4); ax.set_ylim(54.45, 57.9)
    offsets = {"Copenhagen": (-8, 8), "Aarhus": (8, 4), "Odense": (-8, -14), "Aalborg": (8, 4), "Esbjerg": (-8, 6)}
    for name, (lat, lon) in run_cities.CITIES.items():
        ax.plot(lon, lat, "o", ms=9, color=MS.INK, mec=MS.BG, mew=1.5, zorder=5)
        dx, dy = offsets.get(name, (8, 4))
        ax.annotate(name, (lon, lat), xytext=(dx, dy), textcoords="offset points", color=MS.INK, fontsize=12,
                    ha="left" if dx > 0 else "right", zorder=6)
    fig.tight_layout(); save(fig, "20-cities.svg")


def fig_gauges():
    """Radar against rain gauges (Appendix A.4): each gauge coloured by the radar's season total over the gauge's."""
    from matplotlib.colors import LogNorm, LinearSegmentedColormap
    from nowcastlab import grid
    G = json.loads((ROOT / "results" / "radar-vs-gauges.json").read_text())
    fig, ax = plt.subplots(figsize=(W, 5.6), facecolor=MS.BG)
    MS.rain_map(ax, np.zeros((MS.grid_rows(), MS.grid_cols())))
    ax.set_xlim(7.8, 15.4); ax.set_ylim(54.45, 57.9)
    cmap = LinearSegmentedColormap.from_list("ratio", ["#3a78c2", "#b9d6f7", "#e6ebef", "#f5c07a", "#ee7b6c"])
    norm = LogNorm(0.5, 2.0)
    ok = [s for s, x in G["stations"].items() if not x.get("faulty")]
    sc = ax.scatter([G["stations"][s]["lon"] for s in ok], [G["stations"][s]["lat"] for s in ok],
                    c=[min(max(G["stations"][s]["cell"]["ratio"], 0.5), 2.0) for s in ok], cmap=cmap, norm=norm,
                    s=70, edgecolors=MS.BG, linewidths=1.2, zorder=5)
    for name, (la, lo) in grid.RADARS.items():
        ax.plot(lo, la, "^", ms=10, color=MS.INK, mec=MS.BG, zorder=6)
        ax.annotate({"Romo": "Rømø", "Samso": "Samsø"}.get(name, name), (lo, la), xytext=(7, -3), textcoords="offset points",
                    color=MS.INK, fontsize=10.5, zorder=7)
    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.05, pad=0.08, ticks=[0.5, 0.7, 1, 1.4, 2])
    cb.ax.minorticks_off(); cb.ax.set_xticklabels(["0.5", "0.7", "1", "1.4", "2"], color=MS.INK)
    cb.set_label("radar rain over gauge rain, whole season (1 = agree)", color=MS.INK)
    fig.tight_layout(); save(fig, "23-gauges.svg")


def fig_blocksize(lead=60):
    """Block-size study: how fast motion changes with distance (rain tracks and station winds), and FSS gain
    against block size, plain and blended, on each grid run so far."""
    coh = json.loads((ROOT / "results" / "motion-coherence.json").read_text())
    sta = json.loads((ROOT / "results" / "station-vs-rain.json").read_text())["station_structure"]
    fig, axs = plt.subplots(2, 1, figsize=(W, 10.0))
    r, rms = np.array(coh["all"]["r_km"]), np.sqrt(np.array(coh["all"]["D"], float))
    axs[0].plot(r, rms, "-", color="#6aa8ec", lw=2.6, label="rain, tracked on the radar")
    sr = np.array(sta["r_km"]); srms = np.array([x if x is not None else np.nan for x in sta["rms_kmh"]], float)
    axs[0].plot(sr, srms, "-", color=MS.MUTED, lw=2.2, label="wind at ground stations")
    e5f = ROOT / "results" / "era5-vs-rain.json"
    if e5f.exists():
        e5 = json.loads(e5f.read_text())["structure"]["700"]
        er = [x for x, y in zip(e5["r_km"], e5["rms_kmh"]) if y is not None]; ey = [y for y in e5["rms_kmh"] if y is not None]
        axs[0].plot(er, ey, "--", color="#5cc08a", lw=2.2, label="wind at 700 hPa (about 3 km up, ERA5)")
    for km in (13, 26, 51, 102):
        axs[0].axvline(km, color="#3a4654", lw=1, ls=":")
        axs[0].text(km, 1, f" {km} km", color=MS.MUTED, fontsize=9.5, rotation=90, va="bottom")
    axs[0].set_xlim(0, 400); axs[0].set_ylim(0, None)
    axs[0].set_xlabel("distance between two places (km)"); axs[0].set_ylabel("typical difference in motion (km/h)")
    axs[0].set_title("How much the motion differs between two places", loc="left", fontsize=12.5)
    axs[0].legend(fontsize=10.5, loc="lower right")
    sizes = [13, 26, 51, 102]
    for g, ls in (("3.2km", "-"), ("2km", "--")):
        f = ROOT / "results" / f"blocksize-{g}.jsonl"
        if not f.exists():
            continue
        S = report.summarize(report.load(f), n_boot=1)
        name = lambda km, blend: ("block-smooth" if blend else "block") + ("" if km == 26 and not blend else f"-{km}km")
        for blend, col in ((False, MS.SERIES["block"]), (True, MS.SERIES["bw2"])):
            ys = [S[(name(km, blend), lead)]["dFSS9"] for km in sizes]
            axs[1].plot(sizes, ys, ls, marker="o", color=col, lw=2.4, ms=6,
                        label=f"{'blended' if blend else 'per block'}, {g.replace('km', ' km')} grid")
        axs[1].axhline(S[("gw4", lead)]["dFSS9"], color=MS.SERIES["gw4"], lw=1.4, ls=ls)
    axs[1].text(104, axs[1].get_ylim()[0], " ", fontsize=1)
    axs[1].set_xscale("log"); axs[1].set_xticks(sizes); axs[1].set_xticklabels([f"{k} km" for k in sizes])
    axs[1].minorticks_off()
    axs[1].set_xlabel("block size"); axs[1].set_ylabel("FSS gain over persistence")
    axs[1].set_title(f"Forecast skill by block size, +{lead} min (amber line: one vector for the map)", loc="left", fontsize=12)
    fig.tight_layout()
    handles, labels = axs[1].get_legend_handles_labels()
    legend_below(fig, handles, ncol=1)
    save(fig, "19-blocksize.svg")


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"real", "scantypes", "headline", "rain", "month", "windows", "cadence", "grid", "blocksize", "cities", "probs", "gauges"}
    if "timing" in which and (ROOT / "results" / "local-timing.json").exists():
        fig_timing()
    if "local" in which and (ROOT / "results" / "local-probs.json").exists():
        fig_local()
    if "turning" in which and (ROOT / "results" / "turning-flow.json").exists():
        fig_turning()
    if "units" in which and (ROOT / "results" / "robustness.json").exists():
        fig_units()
    if "probs" in which and (ROOT / "results" / "probs.json").exists():
        fig_probs()
    if "gauges" in which and (ROOT / "results" / "radar-vs-gauges.json").exists():
        fig_gauges()
    if "cities" in which:
        fig_cities()
    if "blocksize" in which and (ROOT / "results" / "blocksize-3.2km.jsonl").exists():
        fig_blocksize()
    if "grid" in which and all((ROOT / "results" / f"grid-{g}.jsonl").exists() for g in ("3.2km", "2km", "1km")):
        fig_grid()
    if "real" in which:
        arch = Archive(); i = example_index(arch)
        fig_vectors(arch, i)
    if "scantypes" in which:
        fig_scan_types()
    if "cadence" in which:
        fig_cadence(report.summarize_file(CAD10), report.summarize_file(CAD5))
    if {"headline", "rain", "month"} & which:
        Sf = report.summarize_file(FINAL)
        if "headline" in which:
            fig_headline(Sf)
        rows = report.load(FINAL)
        if "rain" in which:
            fig_rain_total(rows)
        if "month" in which:
            fig_by_month(rows)
    if "windows" in which:
        fig_windows(report.summarize_file(WINDOW))
    print("figures written")
