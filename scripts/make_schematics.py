#!/usr/bin/env python3
"""Hand-drawn SVG schematics for docs/REPORT.md (docs/figures/*.svg).

Plain SVG on the same dark background as the other figures.
Run:  python scripts/make_schematics.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BG, INK, MUTED = "#0f151b", "#e6ebef", "#93a1ae"          # dark, like the map figures and charts
RAIN = ["#1b242d", "#244a74", "#3a78c2", "#7fb6ee", "#cfe6fb"]   # dry, then light to heavy
VEC, BAD, GOOD, BOX = "#f0a030", "#ee7b6c", "#5cc08a", "#b58be8"
NOTITLE, TITLE_DY = "<!--notitle-->", 38         # figures carry no title (the caption is the title); the space it used is cut
CW, TS, LS, SS = 600, 19, 16, 14.5          # canvas width; title, label and small text sizes (phone-legible)
FONT = "font-family='Inter,Segoe UI,Helvetica,Arial,sans-serif'"


def svg(w, h, body, title, desc):
    if NOTITLE in body:                                  # drop the space the title used
        body, h = f"<g transform='translate(0,{-TITLE_DY})'>{body}</g>", h - TITLE_DY
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' width='{w}' height='{h}' role='img' "
            f"aria-labelledby='t d'><title id='t'>{title}</title><desc id='d'>{desc}</desc>"
            f"<defs>" + "".join(
                f"<marker id='ah{c[1:]}' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
                f"<path d='M0 0L10 5L0 10z' fill='{c}'/></marker>" for c in (INK, MUTED, VEC, BAD, GOOD, BOX)) + "</defs>"
            f"<rect width='{w}' height='{h}' fill='{BG}'/>{body}</svg>")


def text(x, y, s, size=14, fill=INK, anchor="start", weight="normal", italic=False):
    st = " font-style='italic'" if italic else ""
    return f"<text x='{x}' y='{y}' {FONT} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'{st}>{s}</text>"


def rect(x, y, w, h, fill="none", stroke=INK, sw=1, rx=0, dash=None, op=1):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' fill='{fill}' stroke='{stroke}' stroke-width='{sw}' opacity='{op}'{d}/>"


def arrow(x1, y1, x2, y2, color=VEC, sw=2.5, dash=None):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    m = "url(#ah" + color[1:] + ")"
    return f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' stroke-width='{sw}' marker-end='{m}'{d}/>"


def line(x1, y1, x2, y2, color=MUTED, sw=1, dash=None):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    return f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' stroke-width='{sw}'{d}/>"


def field(x, y, cells, cs, vals, stroke="#26313c"):
    """A rows x cols grid of squares shaded by vals (0..4)."""
    out = []
    for r, row in enumerate(vals):
        for c, v in enumerate(row):
            out.append(rect(x + c * cs, y + r * cs, cs, cs, RAIN[v] if v else "#1b242d", stroke, 0.6))
    return "".join(out)


def blob(rows, cols, cx, cy, r):
    return [[max(0, 4 - int(((c - cx) ** 2 + (r_ - cy) ** 2) ** 0.5 / r * 3)) if ((c - cx) ** 2 + (r_ - cy) ** 2) ** 0.5 < r else 0
             for c in range(cols)] for r_ in range(rows)]


def save(name, s):
    (OUT / name).write_text(s)
    print("wrote", OUT / name)


# ---------------------------------------------------------------- 1. pipeline
def pipeline():
    SHARED, OWN = ("#161e26", MUTED), ("#2e2410", VEC)          # (fill, outline): same for every method / differs by method
    bw, bh, xs = 172, 92, (14, 214, 414)
    b = [NOTITLE]

    def box(x, y, t, sub, style):
        return [rect(x, y, bw, bh, style[0], style[1], 1.8, 8), text(x + bw / 2, y + 38, t, LS, weight="bold", anchor="middle")] + \
               [text(x + bw / 2, y + 62 + 18 * k, ln, SS, MUTED, "middle") for k, ln in enumerate(sub)]
    y1, y2 = 56, 200
    b += box(xs[0], y1, "Radar scan", ["every 10 minutes"], SHARED) + box(xs[1], y1, "Rain-rate map", ["224 x 160 cells"], SHARED) + \
         box(xs[2], y1, "Measure motion", ["from the last scans"], OWN)
    b += box(xs[2], y2, "Move the rain", ["along the motion"], OWN) + box(xs[1], y2, "Forecast maps", ["+10 to +360 min"], SHARED) + \
         box(xs[0], y2, "Scores", ["against the radar", "that followed"], SHARED)
    b += [arrow(xs[0] + bw + 2, y1 + bh / 2, xs[1] - 3, y1 + bh / 2, INK, 2), arrow(xs[1] + bw + 2, y1 + bh / 2, xs[2] - 3, y1 + bh / 2, INK, 2),
          arrow(xs[2] + bw / 2, y1 + bh + 2, xs[2] + bw / 2, y2 - 3, INK, 2),
          arrow(xs[2] - 2, y2 + bh / 2, xs[1] + bw + 3, y2 + bh / 2, INK, 2), arrow(xs[1] - 2, y2 + bh / 2, xs[0] + bw + 3, y2 + bh / 2, INK, 2)]
    ly = y2 + bh + 44
    b += [rect(14, ly - 15, 28, 20, *SHARED, 1.8, 4), text(52, ly, "Same for every method", SS, INK),
          rect(300, ly - 15, 28, 20, *OWN, 1.8, 4), text(338, ly, "Differs between methods", SS, INK)]
    save("01-pipeline.svg", svg(CW, ly + 22, "".join(b), "Pipeline", "Radar scan to rain-rate map, then the two method-specific steps, measuring the motion and moving the rain, to forecast maps scored against the radar that followed."))


# ---------------------------------------------------------------- 2. persistence
def persistence():
    cs = 15
    now = blob(9, 12, 4, 4, 4)
    b = [NOTITLE]
    for k, (x, lab) in enumerate([(16, "now"), (216, "+30 min"), (416, "+2 hours")]):
        b += [field(x, 78, 12, cs, now), rect(x, 78, 12 * cs, 9 * cs, "none", INK, 1.2), text(x + 6 * cs, 68, lab, LS, anchor="middle", weight="bold")]
        if k < 2:
            b.append(arrow(x + 12 * cs + 4, 78 + 4.5 * cs, x + 12 * cs + 28, 78 + 4.5 * cs, MUTED, 2))
    b += [text(CW / 2, 78 + 9 * cs + 34, "Every lead time shows the latest scan, unchanged.", SS + 0.5, INK, "middle")]
    save("02-persistence.svg", svg(CW, 78 + 9 * cs + 56, "".join(b), "Persistence", "The same rain field is shown now, at 30 minutes and at 2 hours."))


# ---------------------------------------------------------------- 3. block matching
def block_matching():
    # drawn to scale: an 8 x 8 block, searched within +-6 cells (a 20 x 20 window), best shift (+2, +1)
    cs, n = 10, 22
    A = blob(n, n, 10, 10, 7)
    B = blob(n, n, 12, 11, 7)
    b = [NOTITLE]
    xa, xb, y = 16, 262, 76
    bx, by = 6, 6                                   # the block's top-left cell
    b += [text(xa + n * cs / 2, 66, "scan A, 10 min ago", LS, anchor="middle", weight="bold"), field(xa, y, n, cs, A),
          text(xb + n * cs / 2, 66, "scan B, now", LS, anchor="middle", weight="bold"), field(xb, y, n, cs, B)]
    b += [rect(xa + bx * cs, y + by * cs, 8 * cs, 8 * cs, "none", INK, 3),
          rect(xb + (bx - 6) * cs, y + (by - 6) * cs, 20 * cs, 20 * cs, "none", MUTED, 1.4, dash="5 4"),
          rect(xb + bx * cs, y + by * cs, 8 * cs, 8 * cs, "none", INK, 1.6, dash="3 3"),
          rect(xb + (bx + 2) * cs, y + (by + 1) * cs, 8 * cs, 8 * cs, "none", GOOD, 3),
          arrow(xb + (bx + 4) * cs, y + (by + 4) * cs, xb + (bx + 6) * cs, y + (by + 5) * cs, VEC, 2.4),
          text(xb + n * cs + 10, y + (by + 4) * cs - 6, "shift", SS, VEC, "start"),
          text(xb + n * cs + 10, y + (by + 4) * cs + 14, "+2, +1", LS, VEC, "start", "bold")]
    ly = y + n * cs + 34
    items = [(rect(16, ly - 14, 16, 16, "none", INK, 3), "the 8 x 8-cell block in scan A"),
             (rect(16, ly + 14, 16, 16, "none", INK, 1.6, dash="3 3"), "the same place in scan B"),
             (rect(16, ly + 42, 16, 16, "none", MUTED, 1.4, dash="5 4"), "search window, 6 cells each way"),
             (rect(16, ly + 70, 16, 16, "none", GOOD, 3), "best match: 2 cells right, 1 down")]
    for k, (mark, lab) in enumerate(items):
        b += [mark, text(42, ly + 28 * k, lab, SS, INK, "start")]
    b += [text(16, ly + 116, "Each square is one grid cell, about 3.2 km.", SS, MUTED, "start", italic=True)]
    save("03-block-matching.svg", svg(CW, ly + 136, "".join(b), "Block matching", "A block in scan A is searched for in scan B; the best offset is the motion vector."))


# ---------------------------------------------------------------- 4. backward tracing
def backward_tracing():
    """Filling one cell of the forecast map by looking upstream, drawn on a single map. The motion is
    deliberately fractional (1.5 cells per step): that is where looking upstream differs from pushing."""
    cs, cols, rows = 35, 16, 7
    x0, y0 = 20, 112
    b = [NOTITLE,
         text(x0, 62, "The radar now; the rain moves 1.5 cells east every 10 min.", SS, MUTED)]
    now = blob(rows, cols, 4, 3, 3.6)
    b += [field(x0, y0, cols, cs, now)]
    b.append(arrow(x0 + 5 * cs, y0 - 20, x0 + 9 * cs, y0 - 20, VEC, 3))
    b.append(text(x0 + 9 * cs + 10, y0 - 14, "motion", LS, VEC, "start", "bold"))
    tx, ty = 11, 3                                       # the forecast cell being filled
    yc = y0 + ty * cs + cs / 2
    b += [rect(x0 + tx * cs, y0 + ty * cs, cs, cs, "none", BAD, 4)]
    pts = [tx + 0.5 - 1.5 * k for k in range(4)]         # cell centre, then 10, 20, 30 minutes upstream (in cells)
    for k in range(3):                                   # three 10-minute steps back, against the motion
        xa_, xb_ = x0 + pts[k] * cs, x0 + pts[k + 1] * cs
        b.append(arrow(xa_ - (6 if k == 0 else 3), yc, xb_ + 6, yc, INK, 2, "5 4"))
        mx = (xa_ + xb_) / 2
        b += [rect(mx - 26, yc - 36, 52, 22, BG, "none", 0, 4, op=0.9), text(mx, yc - 19, f"-{(k + 1) * 10}", SS, INK, "middle", "bold")]
    land = x0 + pts[3] * cs                              # lands on the border between two cells
    b += [rect(land - cs, y0 + ty * cs, cs, cs, "none", GOOD, 4), rect(land, y0 + ty * cs, cs, cs, "none", GOOD, 4),
          f"<circle cx='{land}' cy='{yc}' r='6' fill='{GOOD}' stroke='{BG}' stroke-width='2'/>"]
    ly = y0 + rows * cs + 34
    b += [rect(x0, ly - 14, 18, 18, "none", BAD, 3.5), text(x0 + 28, ly, "the cell to forecast, 30 minutes ahead", SS),
          rect(x0, ly + 16, 18, 18, "none", GOOD, 3.5), text(x0 + 28, ly + 30, "30 minutes upstream, 4.5 cells back:", SS),
          text(x0 + 28, ly + 50, "the forecast copies the average of these two", SS)]
    t = ly + 92
    steps = ["1. Pick one cell of the forecast map.", "2. Step upstream, 10 minutes at a time.",
             "3. Copy what the radar shows there now.", "4. Repeat for every cell."]
    b += [text(x0, t + 24 * i, st, LS - 0.5) for i, st in enumerate(steps)]
    save("04-backward-tracing.svg", svg(CW, t + 24 * len(steps) + 8, "".join(b), "Looking upstream", "A forecast cell is filled by stepping back against the motion and copying the radar value found there."))


# ---------------------------------------------------------------- 5. failure mode
def failure_mode():
    cs, n, x0 = 36, 12, 140
    b = [NOTITLE]

    def row(y, vals, label):
        out = [text(14, y + cs / 2 + 5, label, SS, MUTED)]
        for i, v in enumerate(vals):
            out.append(rect(x0 + i * cs, y, cs, cs, RAIN[v] if v else "#1b242d", "#3a4654", 0.8))
            if v:
                out.append(text(x0 + i * cs + cs / 2, y + cs / 2 + 6, str(v), SS, "#fff" if v > 2 else INK, "middle"))
        return "".join(out)

    def edge(y):
        return line(x0 + 6 * cs, y - 8, x0 + 6 * cs, y + cs + 8, INK, 2.5, "5 3") + text(x0 + 6 * cs + 6, y - 12, "block edge", SS - 1, INK, "start")

    def case(y, title, rain, fast_first, note):
        out = [text(14, y - 44, title[0], LS, BAD, weight="bold"), text(14, y - 24, title[1], SS, MUTED)]
        out += [row(y, rain, "scan"), edge(y)]
        res = [0] * n
        for x in range(n):
            v = (3 if x < 6 else 0) if fast_first else (0 if x < 6 else 3)
            res[x] = rain[x - v] if 0 <= x - v < n else 0
        out += [row(y + 56, res, "forecast"),
                text(x0, y + 56 + cs + 26, f"rain total: {sum(rain)} in the scan, {sum(res)} in the forecast", SS, BAD),
                text(x0, y + 56 + cs + 46, note, SS, MUTED)]
        return out
    b += case(118, ("A. Part of the rain is dropped", "left block moves 3 cells, right block stays"), [0, 3, 4, 3, 0, 0, 0, 0, 0, 0, 0, 0], True,
              "no forecast cell looks far enough back for the last 3")
    b += case(340, ("B. Part of the rain is copied twice", "left block stays, right block moves 3 cells"), [0, 0, 0, 0, 0, 3, 4, 3, 0, 0, 0, 0], False,
              "cells on both sides of the edge copy the same 3")
    save("05-failure-mode.svg", svg(CW, 500, "".join(b), "Dropping and copying rain", "Two one-dimensional rows show rain lost or copied twice where neighbouring blocks move at different speeds."))


# ---------------------------------------------------------------- 6. three motion fields
def motion_fields():
    b = [text(450, 34, "Three motion fields from the same measurement", 20, weight="bold", anchor="middle")]
    import math
    titles = ["One vector per block", "Blended between blocks", "One vector for the whole map"]
    for k in range(3):
        x0 = 30 + k * 290
        b += [text(x0 + 120, 70, titles[k], 15, anchor="middle", weight="bold"), rect(x0, 84, 240, 180, "#161e26", "#3a4654", 1)]
        for r in range(4):
            for c in range(4):
                cxp, cyp = x0 + 30 + c * 60, 84 + 25 + r * 45
                if k == 0:
                    dx, dy = [(2.0, .5), (0.2, .1), (1.4, -.4), (-.8, .6), (1.0, .9), (0.0, 0.0), (1.9, .2), (.5, -.8), (1.2, .4), (-.3, .2), (0.6, .7), (1.6, -.2), (0.1, .5), (1.1, .8), (-.4, -.3), (1.7, .6)][r * 4 + c]
                elif k == 1:
                    dx, dy = 1.0 + 0.5 * math.sin((c + r) / 2.0), 0.35 + 0.3 * math.cos(c / 2.0)
                else:
                    dx, dy = 1.0, 0.4
                b.append(arrow(cxp - dx * 9, cyp - dy * 9, cxp + dx * 9, cyp + dy * 9, VEC, 2.2))
    b += [text(30, 300, "Same block matches, three ways of turning them into a field to move the rain with.", 14),
          text(30, 326, "Per block: every 8 x 8 block keeps its own vector. Detailed, but neighbours can disagree (see the failure-mode figure).", 13, MUTED),
          text(30, 348, "Blended: vectors interpolated between block centres. Disagreements are softer but not gone (Appendix B.3).", 13, MUTED),
          text(30, 370, "Whole map: the confidence-weighted mean, applied everywhere. Cannot follow shear or rotation, but cannot tear rain either.", 13, MUTED)]
    save("06-motion-fields.svg", svg(900, 400, "".join(b), "Motion fields", "Per-block vectors vary between blocks, smoothed vectors vary gently, and the global field is uniform."))


# ---------------------------------------------------------------- 7. FSS
def fss_concept():
    cs, R_, C_ = 22, 11, 12
    b = [NOTITLE]
    A = [[0] * C_ for _ in range(R_)]
    B = [[0] * C_ for _ in range(R_)]
    for r in range(4, 6):
        for c in range(3, 5):
            A[r][c] = 3
        for c in range(6, 8):
            B[r][c] = 3
    top, xs = 76, (20, 316)
    b += [text(xs[0] + C_ * cs / 2, 64, "forecast", LS, weight="bold", anchor="middle"), field(xs[0], top, C_, cs, A),
          text(xs[1] + C_ * cs / 2, 64, "radar (truth)", LS, weight="bold", anchor="middle"), field(xs[1], top, C_, cs, B)]
    for x0 in xs:                                        # the 9 x 9-cell window around one cell, the same on both maps
        b += [rect(x0 + 1 * cs, top + 1 * cs, 9 * cs, 9 * cs, "none", GOOD, 2.5, dash="6 4"),
              rect(x0 + 5 * cs + 3, top + 5 * cs + 3, cs - 6, cs - 6, "none", GOOD, 2.5)]
    y = top + R_ * cs
    b += [text(CW / 2, y + 28, "dashed: the 9 x 9-cell window around one cell (solid)", SS, GOOD, "middle"),
          text(CW / 2, y + 58, "The shower is three cells off. Cell by cell that is a miss", SS, INK, "middle"),
          text(CW / 2, y + 78, "and a false alarm; within the window, rain is in both maps.", SS, INK, "middle")]
    save("07-fss.svg", svg(CW, y + 98, "".join(b), "Fractions skill score", "A displaced shower scores zero cell by cell but well when compared over a 9 x 9-cell neighbourhood."))


def bootstrap():
    """How the uncertainty intervals are made: resample whole rain episodes, recompute, repeat."""
    cs = 30
    pal = ["#6aa8ec", "#5cc08a", "#f0b43c", "#ee7b6c", "#b58be8", "#7fb6ee", "#e6ebef", "#93a1ae"]
    b = [NOTITLE]
    x0 = 150

    def row(y, ids, label):
        out = [text(14, y + cs / 2 + 6, label, SS, INK, "start", "bold")]
        for k, i in enumerate(ids):
            x = x0 + k * (cs + 8)
            out += [rect(x, y, cs, cs, "#161e26", pal[i - 1], 2.5, 6), text(x + cs / 2, y + cs / 2 + 6, str(i), LS, pal[i - 1], "middle", "bold")]
        return out

    b += row(62, range(1, 9), "Episodes")
    b += [text(x0, 120, "8 of the 157 shown", SS, MUTED)]
    draws = [([3, 3, 7, 1, 5, 5, 8, 2], "+0.231"), ([1, 4, 4, 6, 2, 8, 8, 7], "+0.238"), ([6, 2, 2, 2, 5, 1, 7, 3], "+0.226")]
    b += [text(14, 160, "Draw 157 at random, with repeats, and score again:", SS, MUTED)]
    y = 178
    for k, (ids, score) in enumerate(draws):
        b += row(y, ids, f"Resample {k + 1}") + [text(CW - 14, y + cs / 2 + 6, score, SS, MUTED, "end")]
        y += cs + 12
    b += [text(x0, y + 16, "... 2,000 times", LS, INK, "start", "bold")]
    import math
    hx, hy, hw, hh = 40, y + 44, 520, 110                # histogram of the 2,000 results, the middle 95% shaded
    nb = 26
    xs_ = [-2.8 + 5.6 * (k + 0.5) / nb for k in range(nb)]
    bw = hw / nb
    for k, x in enumerate(xs_):
        h = math.exp(-x * x / 2)
        b.append(rect(hx + k * bw + 1, hy + hh - h * hh, bw - 2, h * hh, "#3a78c2" if -1.96 <= x <= 1.96 else "#26313c", "none", 0))
    lo, hi = hx + hw * (2.8 - 1.96) / 5.6, hx + hw * (2.8 + 1.96) / 5.6
    b += [line(hx, hy + hh, hx + hw, hy + hh, MUTED, 1),
          line(lo, hy - 6, lo, hy + hh + 6, VEC, 1.6, "4 3"), line(hi, hy - 6, hi, hy + hh + 6, VEC, 1.6, "4 3"),
          text(lo, hy + hh + 26, "+0.209", SS, VEC, "middle", "bold"), text(hi, hy + hh + 26, "+0.259", SS, VEC, "middle", "bold"),
          text(hx + hw / 2, hy + hh + 26, "+0.233", SS, INK, "middle", "bold"),
          text(CW / 2, hy + hh + 54, "The middle 95% of the 2,000 scores is the interval.", SS, INK, "middle")]
    save("07-bootstrap.svg", svg(CW, hy + hh + 74, "".join(b), "Bootstrap", "Rain episodes are drawn at random with repeats, the score is recomputed, and the middle 95% of 2,000 results is the interval."))


# ---------------------------------------------------------------- 8. motion window
def motion_window():
    """Four scans, the three consecutive pairs between them, each pair's whole-cell vector, and their average.
    True motion in the example: 1.4 cells east, 0.4 south per 10 minutes; each pair can only report whole cells."""
    cs = 10
    b = [NOTITLE,
         text(CW / 2, 56, "The rain really moves 1.4 cells east, 0.4 south per 10 min.", SS, MUTED, "middle")]
    true = (1.4, 0.4)
    centres = [(3.0 + true[0] * k, 3.6 + true[1] * k) for k in range(4)]
    pair_v = [(1, 0), (2, 1), (1, 0)]                    # what whole-cell block matching reports for each pair
    xs = [14 + i * 148 for i in range(4)]
    times = ["-30 min", "-20 min", "-10 min", "now"]
    for i, (x, (cx, cy)) in enumerate(zip(xs, centres)):
        b += [field(x, 94, 12, cs, blob(9, 12, cx, cy, 3.2)), rect(x, 94, 12 * cs, 9 * cs, "none", INK, 1),
              text(x + 6 * cs, 86, f"scan {i + 1}: {times[i]}", SS, anchor="middle", weight="bold")]
    K = 26                                               # arrow length per cell, the same for every arrow
    yb = 94 + 9 * cs + 18                                # brackets joining the two scans of each pair
    for i, (dx, dy) in enumerate(pair_v):
        x1, x2 = xs[i] + 6 * cs + 10, xs[i + 1] + 6 * cs - 10
        xm = (x1 + x2) / 2
        b += [line(x1, yb, x1, yb + 8, VEC, 1.5), line(x1, yb + 8, x2, yb + 8, VEC, 1.5), line(x2, yb, x2, yb + 8, VEC, 1.5),
              text(xm, yb + 30, f"pair {i + 1}", SS, INK, "middle", "bold"),
              arrow(xm - 36, yb + 50, xm - 36 + dx * K, yb + 50 + dy * K, VEC, 3),
              text(xm + 30, yb + 58, f"{dx:+d}, {dy:+d}", SS, VEC, "start", "bold")]
    ya = yb + 106
    av = (sum(v[0] for v in pair_v) / 3, sum(v[1] for v in pair_v) / 3)
    b += [line(14, ya, CW - 14, ya, "#3a4654", 1),
          text(CW / 2, ya + 28, "average of the three pairs", LS, weight="bold", anchor="middle"),
          arrow(80, ya + 56, 80 + av[0] * K * 2.6, ya + 56 + av[1] * K * 2.6, VEC, 4),
          arrow(80, ya + 56, 80 + true[0] * K * 2.6, ya + 56 + true[1] * K * 2.6, INK, 1.6, "5 4"),
          text(230, ya + 56, f"average: {av[0]:+.2f}, {av[1]:+.2f} cells", SS, VEC, "start", "bold"),
          text(230, ya + 78, f"dashed: the true motion, {true[0]:+.1f}, {true[1]:+.1f}", SS, INK, "start"),
          text(CW / 2, ya + 116, "Each pair alone is off by up to half a cell;", SS, MUTED, "middle"),
          text(CW / 2, ya + 136, "their errors differ, so the average comes closer.", SS, MUTED, "middle")]
    save("08-motion-window.svg", svg(CW, ya + 156, "".join(b), "Motion window", "Three consecutive scan pairs each give a whole-cell vector; their average is close to the true motion."))


# ---------------------------------------------------------------- 9. state-of-the-art methods
def state_of_the_art():
    import math, random
    random.seed(3)
    b = [NOTITLE]
    pw, ph, xs = 180, 150, (14, 210, 406)
    for x, t in zip(xs, ("Lucas-Kanade", "S-PROG", "STEPS")):
        b += [text(x + pw / 2, 66, t, LS, anchor="middle", weight="bold"), rect(x, 78, pw, ph, "#161e26", "#3a4654", 1)]
    x0 = xs[0]                                           # (a) a dense, smoothly varying flow field
    for r in range(4):
        for c in range(5):
            cx, cy = x0 + 22 + c * 34, 78 + 24 + r * 34
            dx, dy = 1.0 + 0.5 * math.sin(c / 2.5 + r / 3), 0.3 + 0.4 * math.cos(c / 3.0 - r / 2)
            b.append(arrow(cx - dx * 6, cy - dy * 6, cx + dx * 7, cy + dy * 7, VEC, 1.8))
    x1 = xs[1]                                           # (b) each scale fades at its own rate
    for j, (lab, *ops) in enumerate([("large", 1.0, 0.9, 0.8), ("medium", 1.0, 0.6, 0.3), ("small", 1.0, 0.3, 0.05)]):
        y = 96 + j * 40
        b.append(text(x1 + 8, y + 2, lab, SS - 1.5, MUTED))
        for i, op in enumerate(ops):
            b.append(rect(x1 + 10 + i * 56, y + 6, 46, 20, "#3a78c2", "none", 0, 4, op=op))
    for i, lab in enumerate(["now", "+30", "+2 h"]):
        b.append(text(x1 + 33 + i * 56, 220, lab, SS - 1.5, MUTED, "middle"))
    x2 = xs[2]                                           # (c) an ensemble of futures, and the chance of rain
    for k in range(4):
        gx, gy = x2 + 10 + (k % 2) * 50, 92 + (k // 2) * 52
        v = blob(6, 7, 3 + random.uniform(-1, 1), 2.5 + random.uniform(-0.7, 0.7), 2.4 + random.uniform(-0.3, 0.6))
        b += [field(gx, gy, 7, 6.4, v), rect(gx, gy, 44.8, 38.4, "none", INK, 0.8)]
    b += [arrow(x2 + 112, 150, x2 + 128, 150, INK, 2)]
    prob = [[0, 1, 2, 2, 1, 0, 0], [1, 2, 3, 3, 2, 1, 0], [1, 3, 4, 4, 3, 1, 0], [0, 2, 3, 3, 2, 1, 0], [0, 1, 1, 1, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0]]
    b += [field(x2 + 132, 128, 7, 6.4, prob), rect(x2 + 132, 128, 44.8, 38.4, "none", INK, 1)]
    caps = [("a smooth motion", "field, a vector", "at every point"), ("fine detail fades", "first, broad rain", "areas persist"),
            ("many possible", "futures; their share", "with rain is a chance")]
    for x, lines_ in zip(xs, caps):
        b += [text(x + pw / 2, 78 + ph + 26 + 19 * k, ln, SS, MUTED, "middle") for k, ln in enumerate(lines_)]
    save("09-state-of-the-art.svg", svg(CW, 78 + ph + 92, "".join(b), "pysteps methods", "Lucas-Kanade flow, S-PROG scale-dependent decay and the STEPS ensemble."))


# ---------------------------------------------------------------- rain episodes (section 3.1)
def rain_episodes():
    """Three worked examples of how rainy moments become rain episodes, with a forecast every hour."""
    W, x0, x1 = 760, 70, 720
    EP, DOT = "#5cc08a", "#e6ebef"
    b = [text(W / 2, 40, "From rainy moments to rain episodes", 24, weight="bold", anchor="middle"),
         text(W / 2, 70, "blue: rain on at least 2% of the scoring area · green: a rain episode · dots: a hindcast every hour", 15, MUTED, anchor="middle")]

    def row(y, title, hours, start, rain, episodes, note=None, note_color=MUTED):
        """rain: [(from h, to h)]; episodes: [(from h, to h, label)]; hours: span shown, from clock hour `start`."""
        X = lambda h: x0 + (h / hours) * (x1 - x0)
        out = [text(x0, y, title, 18, weight="bold")]
        out.append(line(x0, y + 58, x1, y + 58, MUTED, 1))
        step = 1 if hours <= 8 else 2
        for h in range(0, hours + 1, step):
            out += [line(X(h), y + 54, X(h), y + 62, MUTED, 1), text(X(h), y + 78, f"{(start + h) % 24:02d}:00", 12.5, MUTED, "middle")]
        for a, c in rain:
            out.append(rect(X(a), y + 24, X(c) - X(a), 30, RAIN[3], "none", 0, 3))
        for a, c, lab in episodes:
            out.append(rect(X(a), y + 92, X(c) - X(a), 26, EP, "none", 0, 5, op=0.28))
            out.append(rect(X(a), y + 92, X(c) - X(a), 26, "none", EP, 1.8, 5))
            out.append(text((X(a) + X(c)) / 2, y + 138, lab, 14, EP, "middle"))
            for h in range(int(a), int(c)):                              # from the start, every hour
                out.append(f"<circle cx='{X(h) + 9}' cy='{y + 105}' r='4.5' fill='{DOT}'/>")
        if note:
            out.append(text(x0, y + 112, note, 15, note_color))
        return out

    b += row(110, "1. A dry break of less than an hour does not end an episode", 8, 9,
             rain=[(1, 4), (4 + 40 / 60, 7)], episodes=[(1, 7, "one episode, 10:00 to 16:00")])
    b += row(290, "2. A shower shorter than an hour is left out", 8, 9,
             rain=[(1, 1 + 40 / 60)], episodes=[], note="no episode: 40 minutes of rain", note_color=BAD)
    b += row(450, "3. A long spell is cut into episodes of at most 12 hours", 22, 0,
             rain=[(1, 21)], episodes=[(1, 13, "episode 1: 12 hours"), (13, 21, "episode 2: 8 hours")])
    return svg(W, 620, "".join(b), "From rainy moments to rain episodes",
               "Three examples: a short dry break is bridged, a brief shower is left out, and a long spell is cut into 12-hour episodes; a hindcast is issued every hour inside an episode.")


# ---------------------------------------------------------------- whole-map vector: raw matches or repaired field
def vector_paths():
    """Two ways to build the whole-map vector from the same block matches (Appendix B.4): average the raw matches
    (used), or the field after block matching's repairs (tested, slower)."""
    BW, BH = 250, 84
    USED, TRIED = ("#2e2410", VEC, None), ("#161e26", MUTED, "6 4")        # fill, outline, dash

    def box(x, y, title, lines, style=("#161e26", MUTED, None)):
        fill, edge, dash = style
        out = [rect(x, y, BW, BH, fill, edge, 1.8, 8, dash), text(x + BW / 2, y + 32, title, LS, weight="bold", anchor="middle")]
        out += [text(x + BW / 2, y + 54 + 18 * k, ln, SS, MUTED, "middle") for k, ln in enumerate(lines)]
        return out

    xl, xr = 26, 324
    b = [NOTITLE]
    b += box((CW - BW) / 2, 56, "Match each block", ["one vector and a confidence", "per block, for each scan pair"])
    y0 = 56 + BH
    b += [line(CW / 2, y0 + 2, CW / 2, y0 + 22, INK, 2), line(xl + BW / 2, y0 + 22, xr + BW / 2, y0 + 22, INK, 2),
          arrow(xl + BW / 2, y0 + 22, xl + BW / 2, y0 + 50, VEC, 2.5), arrow(xr + BW / 2, y0 + 22, xr + BW / 2, y0 + 50, MUTED, 2, "6 4")]
    ys = [y0 + 54 + k * (BH + 30) for k in range(4)]
    left = [("Weighted average", ["of the raw matches;", "empty blocks do not count"]), ("Whole-map vector", ["used in the report", "(section 4.3)"])]
    right = [("Borrow", ["weak blocks take their", "neighbours' average"]), ("Fill", ["empty blocks take the", "nearest measured ones"]),
             ("Weighted average", ["of the repaired", "block vectors"]), ("Whole-map vector", ["slower, places rain worse", "(Appendix B.4)"])]
    for k, (t, ls) in enumerate(left):
        b += box(xl, ys[k], t, ls, USED)
        if k:
            b.append(arrow(xl + BW / 2, ys[k - 1] + BH + 2, xl + BW / 2, ys[k] - 3, VEC, 2.5))
    for k, (t, ls) in enumerate(right):
        b += box(xr, ys[k], t, ls, TRIED)
        if k:
            b.append(arrow(xr + BW / 2, ys[k - 1] + BH + 2, xr + BW / 2, ys[k] - 3, MUTED, 2, "6 4"))
    ly = ys[3] + BH + 40
    b += [rect(xl, ly - 15, 28, 20, *USED[:2], 1.8, 4), text(xl + 38, ly, "used in the report", SS, INK),
          rect(xr, ly - 15, 28, 20, TRIED[0], TRIED[1], 1.8, 4, TRIED[2]), text(xr + 38, ly, "tested in Appendix B.4", SS, INK)]
    save("24-vector-paths.svg", svg(CW, ly + 22, "".join(b), "Whole-map vector: two ways",
                                    "The same block matches are either averaged directly into the whole-map vector, or first repaired by borrowing and filling and then averaged, which gives a slower vector."))


# ---------------------------------------------------------------- chance of rain from a single forecast
def neighbourhood_probability():
    """How a single (rain / no rain) forecast gives a chance of rain: the share of rainy cells in a window around
    each cell (Appendix C). Drawn with a 5 x 5-cell window; the report tries about 10 to 80 km."""
    cs, N, K = 22, 11, 5
    rain = [[0] * N for _ in range(N)]
    for r in range(N):
        for c in range(N):
            if ((c - 3.2) ** 2 / 7 + (r - 4.0) ** 2 / 4.5 < 1) or ((c - 6.8) ** 2 / 3 + (r - 6.5) ** 2 / 5 < 1):
                rain[r][c] = 1
    h = K // 2
    prob = [[sum(rain[rr][cc] for rr in range(r - h, r + h + 1) for cc in range(c - h, c + h + 1)
                 if 0 <= rr < N and 0 <= cc < N) / K ** 2 for c in range(N)] for r in range(N)]
    ramp = ["#1b242d", "#1f3a58", "#244a74", "#3a78c2", "#7fb6ee", "#cfe6fb"]
    shade = lambda p: ramp[0] if p == 0 else ramp[min(5, 1 + int(p * 5))]
    tr, tc = 6, 4                                              # the cell whose window is shown
    top, x1, x2 = 90, 30, 330
    b = [NOTITLE,
         text(x1 + N * cs / 2, 76, "1. rain or no rain", LS, weight="bold", anchor="middle"),
         text(x2 + N * cs / 2, 76, "2. chance of rain", LS, weight="bold", anchor="middle")]
    for r in range(N):
        for c in range(N):
            b.append(rect(x1 + c * cs, top + r * cs, cs, cs, RAIN[3] if rain[r][c] else "#1b242d", "#26313c", 0.6))
            b.append(rect(x2 + c * cs, top + r * cs, cs, cs, shade(prob[r][c]), "#26313c", 0.6))
    wet = sum(rain[rr][cc] for rr in range(tr - h, tr + h + 1) for cc in range(tc - h, tc + h + 1))
    b += [rect(x1 + (tc - h) * cs, top + (tr - h) * cs, K * cs, K * cs, "none", GOOD, 2.5, dash="6 4")]
    for x0 in (x1, x2):
        b += [rect(x0 + tc * cs + 3, top + tr * cs + 3, cs - 6, cs - 6, "none", GOOD, 2.5)]
    y = top + N * cs
    b += [arrow(x1 + N * cs + 8, top + N * cs / 2, x2 - 8, top + N * cs / 2, INK, 2),
          text(x1 + N * cs / 2, y + 26, f"{wet} of {K * K} cells in the", SS, GOOD, "middle"),
          text(x1 + N * cs / 2, y + 46, "window have rain", SS, GOOD, "middle"),
          text(x2 + N * cs / 2, y + 26, f"so that cell's chance", SS, GOOD, "middle"),
          text(x2 + N * cs / 2, y + 46, f"is {wet}/{K * K} = {wet / K ** 2:.0%}", SS, GOOD, "middle")]
    ly = y + 84                                                # legend for the chance of rain, in one row
    for k, (lab, p_) in enumerate((("0%", 0), ("1-20", .1), ("20-40", .3), ("40-60", .5), ("60-80", .7), ("80-100%", .9))):
        b += [rect(84 + k * 72, ly - 14, 72, 18, shade(p_), "#26313c", 0.6), text(84 + k * 72 + 36, ly + 22, lab, SS - 1, MUTED, "middle")]
    save("25-neighbourhood-probability.svg", svg(CW, ly + 40, "".join(b), "Chance of rain from a single forecast",
         "A rain or no-rain forecast map, a 5 by 5-cell window around one cell with its share of rainy cells, and the resulting map of chances of rain."))


if __name__ == "__main__":
    save("07-episodes.svg", rain_episodes())
    pipeline(); persistence(); block_matching(); backward_tracing(); failure_mode(); motion_fields(); fss_concept(); bootstrap(); motion_window(); state_of_the_art(); vector_paths(); neighbourhood_probability()
