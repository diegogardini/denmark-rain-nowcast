#!/usr/bin/env bash
# The cell-size study (report, next step 1): the same benchmark on the 3.2, 2 and 1 km grids, at the
# main benchmark's issue times, with FSS also scored by distance from the nearest radar, and the
# rain-at-cities check. Block size, search radius and FSS neighbourhoods stay fixed in km (grid.py).
#
#   bash scripts/run_grid_study.sh            # about 3 hours on 14 cores; needs results/benchmark-10min.jsonl
#
# Needs the 3.2 km archive (backfill.py --regrid, build_index.py); builds the 2 and 1 km archives.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
PROCS=${PROCS:-26}
MODELS=persistence,block,global-windows,pysteps-lk
log() { echo "$(date '+%F %T') $*"; }

for g in 3.2km 2km 1km; do
  if [ "$g" != 3.2km ]; then
    log "building the $g archive"
    NOWCAST_GRID=$g $PY scripts/build_grid.py --procs "$PROCS" > "results/grid-build-$g.log" 2>&1
  fi
  log "benchmark on the $g grid"
  NOWCAST_GRID=$g $PY scripts/run_eval.py --issues-from results/benchmark-10min.jsonl --hist 7 \
    --leads 30,60,90,120,180 --models "$MODELS" --procs "$PROCS" --out "results/grid-$g.jsonl" > "results/grid-$g.log" 2>&1
  log "cities on the $g grid"
  NOWCAST_GRID=$g $PY scripts/run_cities.py --out "results/cities-grid-$g.jsonl" --procs "$PROCS" > "results/cities-grid-$g.log" 2>&1
done
log "done"
