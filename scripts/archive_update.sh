#!/usr/bin/env bash
# Keep the radar archive growing. DMI's open API serves only about the last 180 days, so without a regular
# download older data (winter, for a start) is lost for good. Downloads every complete UTC day that is not
# archived yet, up to yesterday, and extends the 3.2 km archive and its index. Meant to run daily from cron:
#
#   15 4 * * * $HOME/denmark-rain-nowcast/scripts/archive_update.sh >> $HOME/denmark-rain-nowcast/data/archive.log 2>&1
#
# The last archived day is taken from data/grids (written only when a day is complete), so a day that failed
# half-way is fetched again. Stops if less than MIN_FREE_GB of disk is free.
set -euo pipefail
cd "$(dirname "$0")/.."
MIN_FREE_GB=${MIN_FREE_GB:-15}
stamp() { date -u +%FT%TZ; }

exec 9>data/.archive.lock
flock -n 9 || { echo "$(stamp) another update is running"; exit 0; }

free_gb=$(df --output=avail -BG data | tail -1 | tr -dc 0-9)
if (( free_gb < MIN_FREE_GB )); then
  echo "$(stamp) only ${free_gb} GB free (need ${MIN_FREE_GB}); not downloading"
  exit 1
fi

last=$(ls data/grids | sed -n 's/^\([0-9]\{8\}\)\.npz$/\1/p' | sort | tail -1)
start=$(date -u -d "${last} +1 day" +%F)
end=$(date -u -d yesterday +%F)
if [[ "$start" > "$end" ]]; then
  echo "$(stamp) up to date (last day ${last})"
  exit 0
fi
echo "$(stamp) archiving ${start} to ${end}"
.venv/bin/python scripts/backfill.py "$start" "$end"
.venv/bin/python scripts/build_index.py | tail -1
echo "$(stamp) done; $(ls data/grids | grep -c '\.npz$') days archived, ${free_gb} GB free before this run"
