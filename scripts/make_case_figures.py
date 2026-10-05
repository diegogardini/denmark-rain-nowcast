#!/usr/bin/env python3
"""Real-case animations: what three models do to real rain, against what the radar saw.

For three cases (one per season, picked by a rule fixed in advance: lots of rain and fast motion as
measured on the radar over the next hour; no model's forecast or motion estimate is used) it writes

  docs/figures/22-case-<id>.gif   the next 2 hours, radar beside the three models, each forecast with the
                                  outline of where the radar actually saw rain (the scoring threshold)
  results/cases.json              the numbers quoted in the report (observed and assumed movement, scores)

  python scripts/make_case_figures.py
"""
import sys, json, math, datetime as dt, io
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from mapstyle import plt, rain_map, rain_legend, use_dark, INK, NAME
from nowcastlab import models, motion, metrics
from nowcastlab.data import Archive, box_mask
from nowcastlab.radar import BOUNDS
from PIL import Image

use_dark()
OUT = ROOT / "docs" / "figures"
KM_PER_CELL = 3.2
STEP_MIN = 10          # the archive's axis of full-range scans
SPH = 60 // STEP_MIN   # steps per hour
SHOWN = ["block", "gw4", "pysteps-lk"]            # the models drawn in the figures
SCORED = ["persistence"] + SHOWN                  # numbers kept for the text

WINDOWS = {"spring": ("Spring", (4, 5)), "early-summer": ("Early summer", (6, 7)),
           "late-summer": ("Late summer", (8, 9))}


# ------------------------------------------------------------------ case selection (rule fixed in advance)
def pick_cases(arch):
    """Per window: among hourly issue times with >= 10% of the scoring area wet and no missing scan from
    one hour back to +3 h, take the 30 wettest, and choose the one with the largest wet fraction x the
    speed the radar itself shows over the next hour (observed_motion; capped at 6 cells per 10-minute
    step). No model's forecast or motion estimate plays a part."""
    hourly = range(0, len(arch), SPH)
    mask_month = np.array([dt.datetime.fromtimestamp(arch.time(i), dt.UTC).month for i in hourly])
    cases = {}
    for key, (label, months) in WINDOWS.items():
        cand = []
        for k, i in enumerate(hourly):
            if mask_month[k] not in months or arch.wet[i] < 0.10 or i < SPH or i + 3 * SPH >= len(arch):
                continue
            if arch.missing[i - SPH:i + 3 * SPH + 1].any():
                continue
            cand.append((float(arch.wet[i]), i))
        cand.sort(reverse=True)
        best = None
        for wet, i in cand[:30]:
            obs = observed_motion(arch, i)
            if obs is None:
                continue
            speed = float(np.hypot(*obs["mean"]))
            score = wet * min(speed, 6.0)
            if best is None or score > best[0]:
                best = (score, i, wet, speed)
        cases[key] = dict(label=label, index=int(best[1]), wet=best[2], speed_cells=best[3])
    return cases


# ------------------------------------------------------------------ forecasts and motion
def compass(dx, dy):
    """Heading the rain moves TOWARD (dx: east, dy: south, in cells per step)."""
    bearing = (90 - math.degrees(math.atan2(-dy, dx))) % 360
    names = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return names[int((bearing + 22.5) // 45) % 8]


def kmh(dx, dy):
    return math.hypot(dx, dy) * KM_PER_CELL * 60 / STEP_MIN


def forecasts(arch, i, steps=2 * SPH):
    frames = arch.frames(i, SPH + 1)
    gw = models.make("global-windows")
    fc = {"persistence": models.make("persistence").forecast(frames, steps),
          "block": models.make("block").forecast(frames, steps),
          "gw4": gw.forecast_multi(frames, steps)["gw4"],
          "pysteps-lk": models.make("pysteps-lk").forecast(frames, steps)}
    return frames, fc, gw.pair_vectors(frames)


def model_motion(frames, pv, rain):
    """Each model's mean motion over the rain now (cells per step)."""
    f = models.make("block").field(frames)
    w = motion.motion_weight(f.conf) * (f.conf > 0)
    rb = np.array([[rain[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8].mean() > 0.3 for c in range(f.dx.shape[1])]
                   for r in range(f.dx.shape[0])])
    out = {"block": (float((f.dx * w)[rb].mean()), float((f.dy * w)[rb].mean())) if rb.any() else (0.0, 0.0),
           "gw4": models.GlobalWindows._mean(pv[-3:])}
    from pysteps import motion as pm
    from pysteps.utils import transformation
    rdb, _ = transformation.dB_transform(np.stack(frames[-4:]).astype(np.float64), threshold=0.1, zerovalue=-15.0)
    V = pm.get_method("LK")(rdb)
    wet = rain > 0.3
    out["pysteps-lk"] = (float(V[0][wet].mean()), float(V[1][wet].mean()))
    return out


def observed_motion(arch, i):
    """How the rain actually moved between now and +60 min: block matching of the radar scan at i against
    the scan one hour later (large search window, 16x16 blocks); only confident blocks over rain.
    Displacements are returned per 10-minute step (divided by the steps per hour)."""
    a, b = np.nan_to_num(arch.rate[i]), np.nan_to_num(arch.rate[i + SPH])
    f = motion.compute_block_motion(a, b, 16, 24)
    br, bc = f.conf.shape
    rain = np.array([[a[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16].mean() for c in range(bc)] for r in range(br)])
    ok = (f.conf > 0.35) & (rain > 0.3)
    wts = (f.conf * rain)[ok]
    if ok.sum() == 0:
        return None
    return dict(mean=(float((f.dx[ok] * wts).sum() / wts.sum() / SPH), float((f.dy[ok] * wts).sum() / wts.sum() / SPH)))


def fss_case(pred, truth, mask):
    s = metrics.score(pred, truth, mask & np.isfinite(truth))
    return 1 - s["fss9_0.5_e"] / s["fss9_0.5_r"] if s["fss9_0.5_r"] else float("nan"), s["sum_f"] / max(s["sum_t"], 1e-9)


# ------------------------------------------------------------------ drawing
def motion_stats(mm, obs):
    """Observed movement over the next hour against each model's, in km/h, for the text."""
    stats = {"observed": dict(dx=obs["mean"][0], dy=obs["mean"][1], kmh=kmh(*obs["mean"]), toward=compass(*obs["mean"]))}
    for name in SHOWN:
        dx, dy = mm[name]
        err = math.hypot(dx - obs["mean"][0], dy - obs["mean"][1]) * KM_PER_CELL * 60 / STEP_MIN
        stats[name] = dict(dx=dx, dy=dy, kmh=kmh(dx, dy), toward=compass(dx, dy), err_kmh=err)
    return stats


def draw_gif(cid, meta, arch, i, fc):
    cols = ["radar"] + SHOWN
    frames = []
    n = 2 * SPH + 1
    for k in range(n):
        truth = arch.rate[i + k]
        fig, axs = plt.subplots(2, 2, figsize=(6.4, 6.0))
        for ax, name in zip(axs.flat, cols):
            field = truth if name == "radar" else (arch.rate[i] if k == 0 else fc[name][k - 1])
            rain_map(ax, field, truth=None if name == "radar" else truth, title=NAME[name])
        t = dt.datetime.fromtimestamp(arch.time(i + k), dt.UTC).strftime("%H:%M UTC")
        for ax in axs.flat:
            ax.title.set_fontsize(10.5)
        fig.suptitle(f"{meta['label']}   +{k * STEP_MIN} min   ({t})", fontsize=13, color=INK, x=0.02, ha="left", y=0.99)
        fig.subplots_adjust(left=0.03, right=0.97, top=0.88, bottom=0.14, hspace=0.2, wspace=0.06)   # room for each title
        rain_legend(fig, ncol=2)
        buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=150); plt.close(fig)
        frames.append(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    # 256 colours and no dithering: dithering scatters the anti-aliased text into a fog of dots
    pal = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(OUT / f"22-case-{cid}.gif", save_all=True, append_images=pal[1:],
                duration=[1200] + [700] * (n - 2) + [2000], loop=0, optimize=True)


if __name__ == "__main__":
    arch = Archive()
    mask = box_mask()
    cases = pick_cases(arch)
    summary = {}
    for cid, meta in cases.items():
        i = meta["index"]
        frames, fc, pv = forecasts(arch, i)
        obs = observed_motion(arch, i)
        mm = model_motion(frames, pv, np.nan_to_num(arch.rate[i]))
        stats = motion_stats(mm, obs)
        draw_gif(cid, meta, arch, i, fc)
        per = {}
        for name in SCORED:
            for lead in (30, 60, 120):
                fss, ratio = fss_case(fc[name][lead // STEP_MIN - 1], arch.rate[i + lead // STEP_MIN], mask)
                per[f"{name}:{lead}"] = dict(fss=fss, ratio=ratio)
        summary[cid] = dict(label=meta["label"], time=dt.datetime.fromtimestamp(arch.time(i), dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
                            wet=meta["wet"], speed_kmh=meta["speed_cells"] * KM_PER_CELL * SPH, motion=stats, scores=per)
        print(cid, summary[cid]["time"], {k: round(v["kmh"]) for k, v in stats.items()}, flush=True)
    (ROOT / "results" / "cases.json").write_text(json.dumps(summary, indent=1, default=float))
    print("done")
