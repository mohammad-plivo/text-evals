#!/bin/bash
# One arm of the exit_collection A/B: 3 scenarios x 5 repeats, one process each.
set -u
WS_ABS="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/FHCSD/repo"
ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
cd "$REPO" || exit 1
echo "arm=$1 sha=$(git rev-parse --short HEAD)"
for s in d1-emergency d2-human-requested d3-upset; do
  uv run python -m src.simulation.cli run "$WS_ABS" --scenario "$s" --repeat 5 --no-open \
    --env-file "$ENVF" > "$WS_ABS/$s.log" 2>&1 &
done
wait
echo "arm $1 done: $(ls "$WS_ABS"/reports/*.json 2>/dev/null | wc -l) report files"
