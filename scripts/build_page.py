#!/usr/bin/env python3
"""Build the report as web pages from docs/REPORT.md.

  docs/report.html   a full page for GitHub Pages serving docs/, with figures linked from docs/figures/
                     (the blog post, docs/index.html, links to it)
  docs/page.html     a self-contained HTML fragment (title + style + content), with figures embedded
                     as data: URIs so it is one self-contained file
"""
import base64, re
from pathlib import Path
import markdown

DOCS = Path(__file__).resolve().parents[1] / "docs"
md = (DOCS / "REPORT.md").read_text()

# title / intro
lines = md.split("\n")
h1 = lines[0].lstrip("# ").strip()
byline = re.match(r"\*(.*)\*", lines[2]).group(1)
body_md = "\n".join(lines[3:])


SMALL_FIGURES = {"20-cities.svg"}          # shown at a modest width, not across the whole column


def fig(m):
    alt, src = m.group(1), m.group(2)
    small = " small" if Path(src).name in SMALL_FIGURES else ""
    return (f'<figure class="plate{small}"><div class="plate-in"><img alt="{alt}" title="Tap to enlarge" '
            f'loading="lazy" src="@@SRC {src}@@"></div><figcaption>{alt}</figcaption></figure>')


body_md = re.sub(r"!\[([^\]]*)\]\((figures/[^)]+)\)", lambda m: "@@FIG@@" + fig(m) + "@@/FIG@@", body_md)
html = markdown.markdown(body_md, extensions=["tables", "fenced_code", "toc"], extension_configs={"toc": {"toc_depth": "2-2"}})
html = re.sub(r"<p>@@FIG@@(.*?)@@/FIG@@</p>", r"\1", html, flags=re.S)
html = html.replace("@@FIG@@", "").replace("@@/FIG@@", "")
html = re.sub(r"<table>", '<div class="tablewrap"><table>', html)
html = html.replace("</table>", "</table></div>")
# model-type tables: a blank first cell continues the type above it, so merge them into one cell
def merge_types(m):
    rows = re.findall(r"<tr>\n(.*?)</tr>", m.group(2), flags=re.S)
    out, first = [], None
    for r in rows:
        cell = re.match(r"<td>(.*?)</td>\n", r, flags=re.S)
        if cell and cell.group(1) == "" and first is not None:
            out[first][0] += 1
            out.append([0, r[cell.end():]])
        else:
            first = len(out)
            out.append([1, r])
    body = ""
    for span, r in out:
        if span:
            r = r.replace("<td>", f'<td rowspan="{span}" class="group">' if span > 1 else '<td class="group">', 1)
        body += f"<tr>\n{r}</tr>\n"
    return m.group(1) + body + "</tbody>"


html = re.sub(r"(<th>Model type</th>.*?<tbody>\n)(.*?)</tbody>", merge_types, html, flags=re.S)
# two-column prose tables (Score / What it tells you) wrap normally
html = html.replace('<div class="tablewrap"><table>\n<thead>\n<tr>\n<th>Score</th>', '<div class="tablewrap prose"><table>\n<thead>\n<tr>\n<th>Score</th>')

# table of contents from h2s
toc = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', html)
nav = "".join(f'<a href="#{i}">{re.sub(r"^\d+\. ", "", t)}</a>' for i, t in toc)

CSS = """
:root{
  --paper:#f5f6f3; --card:#ffffff; --ink:#15202b; --muted:#5b6875; --rule:#d9ded9; --accent:#1f5fa8; --accent-ink:#ffffff;
  --code:#eceeea; --good:#2e8b57; --bad:#b83a2c; --plate:#0f151b;
  --serif:"Newsreader",Georgia,"Times New Roman",serif; --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --paper:#0f151b; --card:#161e26; --ink:#e6ebef; --muted:#93a1ae; --rule:#26313c; --accent:#6aa8ec; --accent-ink:#0f151b; --code:#1b252f; --good:#5cc08a; --bad:#ee7b6c; --plate:#0f151b;}}
:root[data-theme="dark"]{
  --paper:#0f151b; --card:#161e26; --ink:#e6ebef; --muted:#93a1ae; --rule:#26313c; --accent:#6aa8ec; --accent-ink:#0f151b; --code:#1b252f; --good:#5cc08a; --bad:#ee7b6c; --plate:#0f151b;}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.62;margin:0;padding-inline:16px}
.layout{max-width:1180px;margin-inline:auto;display:grid;grid-template-columns:minmax(0,1fr);gap:0 56px;padding-block:32px 72px}
@media (min-width:1080px){.layout{grid-template-columns:200px minmax(0,780px)}}
nav.toc{display:none}
@media (min-width:1080px){nav.toc{display:flex;flex-direction:column;gap:2px;position:sticky;top:32px;align-self:start;font-size:13.5px}}
nav.toc .label{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
nav.toc a{color:var(--muted);text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid var(--rule)}
nav.toc a:hover,nav.toc a:focus-visible{color:var(--ink);border-left-color:var(--accent);outline:none}
header.top{grid-column:1/-1;max-width:780px;margin-bottom:28px}
@media (min-width:1080px){header.top{margin-left:256px}}
.kicker{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(30px,5.2vw,46px);line-height:1.08;margin:10px 0 14px;letter-spacing:-.01em;text-wrap:balance}
.byline{color:var(--muted);font-size:14.5px;margin:0}
main{min-width:0}
h2{font-family:var(--serif);font-weight:600;font-size:27px;line-height:1.2;margin:56px 0 14px;padding-top:22px;border-top:1px solid var(--rule);text-wrap:balance;scroll-margin-top:16px}
h2:first-child{margin-top:0}
h3{font-family:var(--serif);font-weight:600;font-size:20px;margin:34px 0 8px}
p,li{max-width:68ch}
li{margin:5px 0}
a{color:var(--accent)}
strong{font-weight:600}
code{font-family:var(--mono);font-size:.88em;background:var(--code);padding:1px 5px;border-radius:4px}
pre{background:var(--code);padding:14px 16px;border-radius:6px;overflow-x:auto;font-size:13px;line-height:1.5}
pre code{background:none;padding:0}
.plate{margin:26px 0;padding:0}
.plate-in{background:var(--plate);border:1px solid #26313c;border-radius:6px;padding:8px}
.plate img{display:block;width:100%;height:auto;cursor:zoom-in}
.plate.small{max-width:440px;margin-inline:auto}
dialog.zoom{padding:0;border:0;background:#0f151b;width:100vw;height:100dvh;max-width:none;max-height:none;margin:0;color:#e6ebef;touch-action:pan-x pan-y}
dialog.zoom *{touch-action:pan-x pan-y}
dialog.zoom::backdrop{background:rgba(0,0,0,.8)}
dialog.zoom .zoom-bar{position:sticky;top:0;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 16px;background:#161e26;font-size:14px}
dialog.zoom .zoom-cap{font-size:13px;color:#93a1ae}
dialog.zoom button{font:inherit;font-weight:600;color:#0f151b;background:#6aa8ec;border:0;border-radius:6px;padding:10px 18px;cursor:pointer;flex:none}
dialog.zoom .zoom-in{overflow:auto;height:calc(100dvh - 52px);display:flex;align-items:flex-start;justify-content:center}
dialog.zoom img{display:block;width:auto;max-width:none;min-width:min(100%,1000px);height:auto;margin:auto;cursor:zoom-out}
@media (max-width:640px){dialog.zoom img{min-width:200%}}
details.toc-m{margin:0 0 8px;border:1px solid var(--rule);border-radius:6px;background:var(--card)}
details.toc-m summary{cursor:pointer;padding:10px 14px;font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
details.toc-m a{display:block;padding:7px 14px;color:var(--ink);text-decoration:none;border-top:1px solid var(--rule);font-size:15px}
@media (min-width:1080px){details.toc-m{display:none}}
figcaption{font-size:13px;color:var(--muted);margin-top:8px;font-family:var(--mono)}
.tablewrap{overflow-x:auto;margin:20px 0;border:1px solid var(--rule);border-radius:6px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500;white-space:nowrap}
tr:last-child td{border-bottom:0}
td:first-child{white-space:nowrap}
td.group{vertical-align:middle;border-right:1px solid var(--rule);color:var(--muted)}
td:not(:first-child){white-space:nowrap}
.prose td:not(:first-child){white-space:normal;min-width:16em}
@media (max-width:640px){
  body{font-size:16px;padding-inline:14px}
  .layout{padding-block:20px 56px}
  h2{font-size:23px;margin-top:44px}
  h3{font-size:18.5px}
  .plate{margin:20px -6px}
  .plate-in{padding:4px}
  table{font-size:13px}
  th,td{padding:6px 8px}
  th{white-space:normal;font-size:10.5px}
  td:first-child{white-space:normal;min-width:9.5em}
  td:not(:first-child){white-space:normal;min-width:4.5em}
  .prose td:first-child{min-width:7em}
  .prose td:not(:first-child){min-width:0}
  pre{font-size:11.5px;padding:12px}
}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""

page = f"""<title>Rain Nowcasting in Denmark</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap">
<style>{CSS}</style>
<div class="layout">
<header class="top"><div class="kicker">Denmark-rain-nowcast &middot; benchmark report</div><h1>{h1}</h1><p class="byline">{byline}</p></header>
<nav class="toc" aria-label="Sections"><div class="label">Contents</div>{nav}</nav>
<main><details class="toc-m"><summary>Contents</summary>{nav}</details>{html}</main>
</div>
<dialog class="zoom" aria-label="Enlarged figure"><div class="zoom-bar"><span class="zoom-cap">Tap anywhere to close</span><button type="button">Close</button></div>
<div class="zoom-in"><img alt=""></div></dialog>
<script>
(() => {{
  // Enlarged figure: browser zoom is switched off inside it (a double tap used to zoom the page and push
  // the Close button out of reach), any tap closes it, and so do Escape and the Back gesture.
  const dlg = document.querySelector("dialog.zoom");
  const big = dlg.querySelector("img");
  let openedAt = 0, closedAt = 0, pushed = false;
  document.addEventListener("click", (e) => {{
    const img = e.target.closest(".plate img");
    if (!img || dlg.open || Date.now() - closedAt < 400) return;   // nor reopen on the second tap of a closing double tap
    big.src = img.src; big.alt = img.alt;
    try {{ history.pushState({{zoom: true}}, ""); pushed = true; }} catch (err) {{ pushed = false; }}
    openedAt = Date.now();
    dlg.showModal();
    dlg.querySelector(".zoom-in").scrollTo(0, 0);
  }});
  const shut = () => {{ if (dlg.open) dlg.close(); }};
  dlg.addEventListener("click", () => {{ if (Date.now() - openedAt > 400) shut(); }});   // ignore the second tap of a double tap
  dlg.addEventListener("close", () => {{ closedAt = Date.now(); if (pushed) {{ pushed = false; history.back(); }} }});
  window.addEventListener("popstate", () => {{ pushed = false; shut(); }});
  document.querySelectorAll("details.toc-m a").forEach((a) => a.addEventListener("click", () => a.closest("details").open = false));
}})();
</script>
"""
def embed(m):
    src = m.group(1)
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".gif": "image/gif"}[Path(src).suffix]
    return f"data:{mime};base64,{base64.b64encode((DOCS / src).read_bytes()).decode()}"


art = re.sub(r"@@SRC (.+?)@@", embed, page)
(DOCS / "page.html").write_text(art)
print("wrote", DOCS / "page.html", len(art) // 1024, "KB")

head, body = page.split('<div class="layout">', 1)
back = lambda b: b.replace('<div class="kicker">', '<div class="kicker"><a href="index.html" style="color:inherit">&larr; Will it rain?</a> &middot; ', 1)
web = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{re.sub(r'<[^>]+>', '', byline)}">
{head.strip()}
</head>
<body>
<div class="layout">{back(re.sub(r"@@SRC (.+?)@@", r"\1", body))}</body>
</html>
"""
(DOCS / "report.html").write_text(web)
print("wrote", DOCS / "report.html", len(web) // 1024, "KB")
