"""The analysis grid: one regular lon/lat grid over the map domain, at a chosen cell size.

Chosen per run with the environment variable NOWCAST_GRID (3.2km, the default, 2km or 1km), read
once at import, so every process of a run, including forked workers, uses the same grid.

Everything that elsewhere is a number of cells is derived here from a physical size, so a finer grid
keeps the same scales in km: the block used for matching (about 26 km), the search radius (about
19 km, 115 km/h between scans 10 minutes apart), and the FSS neighbourhoods (about 30 and 10 km;
their result keys keep the names fss9 and fss3 from the 3.2 km grid, where they are 9 and 3 cells).
"""
from __future__ import annotations

import os
import numpy as np

BOUNDS = dict(west=5.0, south=53.9, east=16.5, north=58.5)
GRIDS = {"3.2km": (224, 160), "2km": (358, 256), "1km": (717, 512)}      # (cols, rows)

NAME = os.environ.get("NOWCAST_GRID", "3.2km")
if NAME not in GRIDS:
    raise ValueError(f"NOWCAST_GRID must be one of {sorted(GRIDS)}, not {NAME!r}")
COLS, ROWS = GRIDS[NAME]
KM = 3.2 * 224 / COLS                       # km per cell near 56 N (square cells there)
SUFFIX = "" if NAME == "3.2km" else f"-{NAME}"   # data/days{SUFFIX}, data/index{SUFFIX}.npz


def cells(km: float) -> int:
    """Nearest whole number of cells for a length in km (at least 1)."""
    return max(1, int(round(km / KM)))


def odd_cells(km: float) -> int:
    """Nearest odd number of cells for a length in km (a window with a centre cell)."""
    return 2 * int(round((km / KM - 1) / 2)) + 1


BLOCK = cells(25.6)                          # 8 cells at 3.2 km, 13 at 2 km, 26 at 1 km
RADIUS = cells(19.2)                         # 6, 10, 19
FSS_WIN = {9: odd_cells(28.8), 3: odd_cells(9.6)}   # {9: 9, 3: 3} at 3.2 km; {9: 15, 3: 5} at 2 km; {9: 29, 3: 9} at 1 km

# DMI's weather radars (https://www.dmi.dk/friedata/dokumentation/radar-data), for distances
RADARS = {"Romo": (55.1726, 8.5505), "Sindal": (57.4888, 10.1351), "Bornholm": (55.1128, 14.8875),
          "Stevns": (55.3256, 12.4482), "Samso": (55.8120, 10.5855)}
BANDS = {"near": (0, 60), "mid": (60, 120), "far": (120, 1e9)}     # km from the nearest radar


def lonlat():
    """Cell-centre longitudes and latitudes, [ROWS, COLS] each (row 0 = north)."""
    lon = BOUNDS["west"] + (np.arange(COLS) + 0.5) * (BOUNDS["east"] - BOUNDS["west"]) / COLS
    lat = BOUNDS["north"] - (np.arange(ROWS) + 0.5) * (BOUNDS["north"] - BOUNDS["south"]) / ROWS
    return np.meshgrid(lon, lat)


def radar_distance():
    """Distance of every cell centre from the nearest DMI radar, km."""
    LON, LAT = lonlat()
    la, lo = np.radians(LAT), np.radians(LON)
    best = np.full(LAT.shape, np.inf)
    for rla, rlo in RADARS.values():
        rla, rlo = np.radians(rla), np.radians(rlo)
        a = np.sin((la - rla) / 2) ** 2 + np.cos(la) * np.cos(rla) * np.sin((lo - rlo) / 2) ** 2
        best = np.minimum(best, 2 * 6371 * np.arcsin(np.sqrt(a)))
    return best


def cell_of(lat: float, lon: float):
    """(row, col) of the cell containing a point."""
    c = int((lon - BOUNDS["west"]) / (BOUNDS["east"] - BOUNDS["west"]) * COLS)
    r = int((BOUNDS["north"] - lat) / (BOUNDS["north"] - BOUNDS["south"]) * ROWS)
    return r, c
