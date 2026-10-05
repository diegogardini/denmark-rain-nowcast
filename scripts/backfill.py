#!/usr/bin/env python3
"""Download DMI radar composites for a date range and convert them to grids.

  python scripts/backfill.py 2026-08-25 2026-09-23      # inclusive, UTC days

Raw ODIM files go to data/raw/YYYYMMDD/, converted grids to
data/grids/YYYYMMDD.npz (arrays: times [unix s], rate [n,160,224] mm/h,
mean-over-cell "area" mode, NaN where the radar has no data). Safe to re-run:
existing files are skipped.

  python scripts/backfill.py 2026-04-01 2026-09-23 --regrid   # rebuild grids from data/raw only
"""
import sys, json, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nowcastlab import radar

ROOT = Path(__file__).resolve().parents[1] / "data"
API = "https://opendataapi.dmi.dk/v1/radardata"
BBOX = "5,53.9,16.5,58.5"
S = requests.Session()


def get(url, tries=5, **kw):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                time.sleep(5 * (i + 1)); continue
            r.raise_for_status()
        except requests.RequestException:
            time.sleep(2 * (i + 1))
    raise RuntimeError("failed: " + url)


def list_day(day):
    items, off = [], 0
    while True:
        r = get(f"{API}/collections/composite/items", params=dict(
            bbox=BBOX, datetime=f"{day:%Y-%m-%d}T00:00:00Z/{day:%Y-%m-%d}T23:59:59Z", limit=300, offset=off)).json()
        f = r.get("features", [])
        items += [(x["properties"]["datetime"], x["id"], x["asset"]["data"]["href"]) for x in f]
        if len(f) < 300:
            break
        off += 300
    return sorted(set(items))


def fetch(item, day):
    _, ident, href = item
    p = ROOT / "raw" / f"{day:%Y%m%d}" / ident
    if p.exists() and p.stat().st_size > 1000:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_bytes(get(href).content)
    tmp.rename(p)
    return p


def do_day(day):
    out = ROOT / "grids" / f"{day:%Y%m%d}.npz"
    if out.exists():
        return day, "skip", 0
    items = list_day(day)
    with ThreadPoolExecutor(4) as ex:
        paths = list(ex.map(lambda it: fetch(it, day), items))
    times = [dt.datetime.fromisoformat(it[0].replace("Z", "+00:00")).timestamp() for it in items]
    write_grids(out, times, paths)
    return day, "ok", len(items)


def write_grids(out, times, paths):
    grids = []
    for p in paths:
        rate, geo = radar.read_rate(p)
        grids.append(radar.to_grid(rate, geo, mode="area"))
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out.with_suffix(".tmp.npz"), times=np.array(times), rate=np.stack(grids).astype(np.float32))
    out.with_suffix(".tmp.npz").rename(out)


def regrid_day(day):
    """Rebuild one day's grids from the raw files already on disk (no download).
    The scan time is taken from the file name (dk.com.YYYYMMDDHHMM....)."""
    paths = sorted((ROOT / "raw" / f"{day:%Y%m%d}").glob("*.h5"))
    times = [dt.datetime.strptime(p.name.split(".")[2], "%Y%m%d%H%M").replace(tzinfo=dt.timezone.utc).timestamp()
             for p in paths]
    write_grids(ROOT / "grids" / f"{day:%Y%m%d}.npz", times, paths)
    return day, "regridded", len(paths)


if __name__ == "__main__":
    a, b = (dt.date.fromisoformat(x) for x in sys.argv[1:3])
    days = [a + dt.timedelta(d) for d in range((b - a).days + 1)]
    if "--regrid" in sys.argv:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(10) as ex:
            for day, status, n in ex.map(regrid_day, days):
                print(f"{day} {status} scans={n}", flush=True)
        sys.exit()
    for d in days:
        t0 = time.time()
        day, status, n = do_day(d)
        print(f"{day} {status} scans={n} {time.time()-t0:.0f}s", flush=True)
