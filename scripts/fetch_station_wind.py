#!/usr/bin/env python3
"""Wind at DMI's weather stations at the benchmark's issue times (report, Appendix B.3).

Fetches the 10-minute mean wind speed and direction for every Danish station (IDs starting with 06)
from the DMI Open Data API, one day per request, and keeps the observations at the main benchmark's
issue times. Writes results/station-wind.json: {stations: {id: [lon, lat]}, obs: {issue: {id: [speed m/s, dir deg]}}}.

  python scripts/fetch_station_wind.py
"""
import sys, json, time, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"
OUT = ROOT / "results" / "station-wind.json"
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
    issues = sorted({r["issue"] for r in map(json.loads, open(ROOT / "results" / "benchmark-10min.jsonl")) if r["model"] == "persistence"})
    want = set(issues)
    days = sorted({dt.datetime.fromtimestamp(t, dt.UTC).date() for t in issues})
    stations, obs = {}, {}
    for n, day in enumerate(days):
        for par in ("wind_speed", "wind_dir"):
            d = get(dict(parameterId=par, datetime=f"{day}T00:00:00Z/{day}T23:59:59Z", limit=300000))
            for f in d.get("features", []):
                p = f["properties"]
                sid = p["stationId"]
                if not sid.startswith("06"):
                    continue
                t = int(dt.datetime.fromisoformat(p["observed"].replace("Z", "+00:00")).timestamp())
                if t not in want:
                    continue
                stations[sid] = f["geometry"]["coordinates"]
                o = obs.setdefault(str(t), {}).setdefault(sid, [None, None])
                o[0 if par == "wind_speed" else 1] = p["value"]
        if n % 20 == 0:
            print(f"{day}: {len(stations)} stations, {len(obs)} issue times so far", flush=True)
    obs = {t: {s: v for s, v in o.items() if None not in v} for t, o in obs.items()}
    OUT.write_text(json.dumps(dict(stations=stations, obs=obs)))
    print(f"{len(stations)} stations, {len(obs)} issue times, {sum(len(o) for o in obs.values())} observations -> {OUT}")


if __name__ == "__main__":
    main()
