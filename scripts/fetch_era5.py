#!/usr/bin/env python3
"""Download ERA5 winds at cloud height over the map area (report, Appendix B.3).

Hourly u and v wind at 850, 700, 500 and 300 hPa (roughly 1.5 to 9 km up, the cloud layer that carries rain,
Appendix B.3) on ERA5's 0.25 degree grid, for the archive's period, one request per month, from the Copernicus
Climate Data Store. Needs a CDS account, the ERA5 licence accepted, and ~/.cdsapirc with the API key.

  python scripts/fetch_era5.py            # data/era5/era5-2026MM.nc
"""
import sys, calendar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nowcastlab.radar import BOUNDS

OUT = ROOT / "data" / "era5"
FIRST, LAST = (2026, 4, 1), (2026, 9, 23)
LEVELS = ["850", "700", "500", "300"]


def main():
    import cdsapi
    OUT.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client(quiet=True)
    year = FIRST[0]
    for month in range(FIRST[1], LAST[1] + 1):
        target = OUT / f"era5-{year}{month:02d}.nc"
        if target.exists():
            print("have", target.name); continue
        last_day = LAST[2] if month == LAST[1] else calendar.monthrange(year, month)[1]
        c.retrieve("reanalysis-era5-pressure-levels", {
            "product_type": ["reanalysis"], "variable": ["u_component_of_wind", "v_component_of_wind"],
            "pressure_level": LEVELS, "year": [str(year)], "month": [f"{month:02d}"],
            "day": [f"{d:02d}" for d in range(1, last_day + 1)], "time": [f"{h:02d}:00" for h in range(24)],
            "area": [BOUNDS["north"], BOUNDS["west"], BOUNDS["south"], BOUNDS["east"]],
            "data_format": "netcdf", "download_format": "unarchived"}).download(str(target))
        print("got", target.name, target.stat().st_size // 1_000_000, "MB", flush=True)


if __name__ == "__main__":
    main()
