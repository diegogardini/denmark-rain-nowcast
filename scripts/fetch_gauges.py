#!/usr/bin/env python3
"""Hourly rain at DMI's rain gauges over the archive's period (report, Appendix A.4).

Fetches `precip_past1h` (mm in the hour ending at the time stamp) for every Danish station (IDs starting with
06) from the DMI Open Data API, one day per request. Writes results/gauges.json:
{stations: {id: [lon, lat]}, obs: {hour (unix): {id: mm}}}.

  python scripts/fetch_gauges.py
"""
import json, time, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"
OUT = ROOT / "results" / "gauges.json"
FIRST, LAST = dt.date(2026, 4, 1), dt.date(2026, 9, 23)
S = requests.Session()


def get(params, tries=5):
    for k in range(tries):
        try:
            r = S.get(API, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (k + 1))
    raise RuntimeError(f"failed: {params}")


def main():
    stations, obs = {}, {}
    day = FIRST
    while day <= LAST:
        d = get(dict(parameterId="precip_past1h", datetime=f"{day}T00:00:00Z/{day}T23:59:59Z", limit=300000))
        for f in d.get("features", []):
            p = f["properties"]
            sid = p["stationId"]
            if not sid.startswith("06") or p["value"] is None:
                continue
            t = int(dt.datetime.fromisoformat(p["observed"].replace("Z", "+00:00")).timestamp())
            if t % 3600:
                continue
            stations[sid] = f["geometry"]["coordinates"]
            obs.setdefault(str(t), {})[sid] = float(p["value"])
        if day.day == 1:
            print(f"{day}: {len(stations)} stations, {len(obs)} hours so far", flush=True)
        day += dt.timedelta(days=1)
    OUT.write_text(json.dumps(dict(stations=stations, obs=obs)))
    print(f"{len(stations)} stations, {len(obs)} hours, {sum(len(o) for o in obs.values())} observations -> {OUT}")


if __name__ == "__main__":
    main()
