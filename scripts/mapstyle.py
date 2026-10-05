"""Shared look for the map figures (radar and forecasts): dark panels, faint coastlines,
the rain colour scale, and a white outline for where the radar actually saw rain.

Coastlines: Natural Earth 1:10m Admin 0 countries (public domain), exported from the
widget's MapData.js into scripts/coast.json.
"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

from nowcastlab.radar import BOUNDS

BG = "#0f151b"          # figure background (the page's dark paper)
PANEL = "#161e26"       # map background
INK = "#e6ebef"
MUTED = "#93a1ae"
COAST = "#4a5a6b"
TRUTH = "#ffffff"       # outline of the rain the radar actually saw
MODEL = {"radar": "#ffffff", "block": "#df5f86", "gw4": "#c08318", "pysteps-lk": "#4a8ae0"}   # warm: simple models; cool: pysteps
NAME = {"radar": "Radar", "block": "Block matching", "gw4": "Whole-map vector",
        "pysteps-lk": "pysteps Lucas-Kanade"}

THRESHOLD = 0.5                        # mm/h: the scoring threshold (FSS, CSI, Brier), also the outline and colour edge
BINS = [0.1, THRESHOLD, 4, 1000]       # light, moderate, heavy (mm/h)
CMAP = ListedColormap(["#213f63", "#7fb6ee", "#f0a030"])
NORM = BoundaryNorm(BINS, CMAP.N)
EXT = [BOUNDS["west"], BOUNDS["east"], BOUNDS["south"], BOUNDS["north"]]
ASPECT = 1 / np.cos(np.radians(56))
_COAST = json.loads((Path(__file__).with_name("coast.json")).read_text())



def grid_rows():
    from nowcastlab.grid import ROWS
    return ROWS


def grid_cols():
    from nowcastlab.grid import COLS
    return COLS


def use_dark():
    """Dark defaults for a script that draws only map figures (charts elsewhere stay light)."""
    plt.rcParams.update({"font.size": 11, "svg.fonttype": "none", "figure.facecolor": BG, "savefig.facecolor": BG,
                         "axes.facecolor": PANEL, "text.color": INK, "axes.labelcolor": INK,
                         "font.family": "DejaVu Sans"})


def rain_map(ax, field, title=None, truth=None, dim=False):
    """Rain in colour on a dark map with coastlines; `truth` adds the outline of rain at or above THRESHOLD."""
    ax.set_facecolor(PANEL)
    g = np.nan_to_num(np.asarray(field, float))
    ax.imshow(np.ma.masked_less(g, 0.1), extent=EXT, cmap=CMAP, norm=NORM, origin="upper", aspect=ASPECT,
              alpha=0.45 if dim else 1.0, interpolation="nearest", zorder=1)
    for ring in _COAST["denmark"] + [r for n in _COAST["neighbours"] for r in n["rings"]]:
        xy = np.asarray(ring)
        ax.plot(xy[:, 0], xy[:, 1], color=COAST, lw=0.6, zorder=2)
    if truth is not None:
        t = np.nan_to_num(np.asarray(truth, float))
        if (t >= THRESHOLD).any():
            h, w = t.shape
            lon = np.linspace(EXT[0], EXT[1], w)
            lat = np.linspace(EXT[3], EXT[2], h)
            ax.contour(lon, lat, (t >= THRESHOLD).astype(float), levels=[0.5], colors=TRUTH, linewidths=0.9, zorder=3)
    ax.set_xlim(EXT[0], EXT[1]); ax.set_ylim(EXT[2], EXT[3])
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#26313c")
    if title:
        ax.set_title(title, fontsize=11, color=INK, loc="left", pad=6)


def rain_legend(fig, outline=True, y=0.01, ncol=None):
    """One compact legend row: the rain colours, and the meaning of the white outline."""
    items = [Patch(facecolor=CMAP(0), label="light rain (under 0.5 mm/h)"), Patch(facecolor=CMAP(1), label="moderate (0.5-4)"),
             Patch(facecolor=CMAP(2), label="heavy (4 or more)")]
    if outline:
        items.append(Patch(facecolor="none", edgecolor=TRUTH, label="where it actually rained 0.5 mm/h or more"))
    fig.legend(handles=items, loc="lower center", ncol=ncol or len(items), frameon=False, fontsize=10,
               labelcolor=INK, bbox_to_anchor=(0.5, y))


# ---------------------------------------------------------------- charts
GRID = "#26313c"
SERIES = {"persistence": "#93a1ae",
          # the simple motion models in warm hues: block matching raspberry, the whole-map vector amber
          "block": "#df5f86", "bw2": "#f0a3bb", "bw4": "#e87ea0", "bw7": "#df5f86", "bw13": "#b8466c",
          "gw2": "#e3b560", "gw4": "#c08318", "gw7": "#a6710f", "gw13": "#8a5e0c",
          # the state of the art (pysteps) in cool hues
          "pysteps-lk": "#4a8ae0", "pysteps-lk13": "#9cc0f0", "pysteps-sprog": "#2e9f86", "pysteps-steps-mean": "#9a74d6",
          "pysteps-steps-default-mean": "#9a74d6"}
WIDTH = 6.4             # inches; with 12 pt text a phone shows it at about 10 px, a desktop column at about 18


def use_dark_charts():
    """Dark, phone-readable defaults for charts: one narrow column, large text, light ink on the page's dark."""
    plt.rcParams.update({"font.size": 12, "font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "figure.facecolor": BG, "savefig.facecolor": BG, "axes.facecolor": BG,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                         "legend.frameon": False, "legend.labelcolor": INK})
