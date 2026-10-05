#!/usr/bin/env python3
"""Build the project's web page, a short animated blog post, from docs/BLOG.template.html.

The template's {{...}} numbers are filled from the results, like the report's, and the data it draws live
(coastlines, one radar rain field, the motion arrows: results/blog-data.json, from scripts/blog_data.py) is
embedded. Writes docs/index.html, a full page for GitHub Pages serving docs/ (figures linked, not embedded).

  python scripts/blog_data.py && python scripts/build_blog.py

The full report is linked from the page as docs/report.html (scripts/build_page.py), next to it on GitHub Pages.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_report import render

DOCS = ROOT / "docs"
page = render((DOCS / "BLOG.template.html").read_text())
left = re.findall(r"\{\{[^}]*\}\}", page)
assert not left, left
page = page.replace("/*DATA*/null", (ROOT / "results" / "blog-data.json").read_text())

REPORT_WEB = "report.html"                                              # docs/report.html, from scripts/build_page.py

head, body = page.split('<div class="wrap">', 1)
title = re.search(r"<title>(.*?)</title>", head).group(1)
desc = ("Six months of Danish weather radar: how well does simply moving the rain forward predict the next hour, "
        "and how close does it get to the state of the art?")
body = body.replace("%%REPORT%%", REPORT_WEB)
index = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="figures/22-case-late-summer.gif">
<meta name="theme-color" content="#0b1117">
{head.strip()}
</head>
<body>
<div class="wrap">{body}</body>
</html>
"""
(DOCS / "index.html").write_text(index)
print("wrote", DOCS / "index.html", len(index) // 1024, "KB")
