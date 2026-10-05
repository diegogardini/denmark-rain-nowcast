#!/bin/bash
# Runs `forecast-verify.cjs collect` every 30 minutes until the given local
# time (default 23:59 today), logging to the verify directory.
#   bash tools/forecast-verify-loop.sh [HH:MM]
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
dir=${RAIN_VERIFY_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/cache/rain-radar-denmark-verify}
mkdir -p "$dir"
until_ts=$(date -d "today ${1:-23:59}" +%s)
while [ "$(date +%s)" -lt "$until_ts" ]; do
  echo "$(date +%T) $(node "$here/forecast-verify.cjs" collect 2>&1)" >> "$dir/loop.log"
  sleep 1800
done
echo "$(date +%T) loop finished" >> "$dir/loop.log"
