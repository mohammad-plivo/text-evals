#!/bin/bash
set -u
ARM="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/FHCSD/repo"
ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
cd "$REPO" || exit 1
echo "arm=$(basename "$ARM") sha=$(git rev-parse --short HEAD)"
N=0; for s in d1-emergency d2-human-requested d3-upset; do N=$((N+1)); [ $((N % 2)) -eq 0 ] && wait
  uv run python -m src.simulation.cli run "$ARM/per/$s" --scenario "$s" --repeat 5 --no-open \
    --env-file "$ENVF" > "$ARM/per/$s/run.log" 2>&1 &
done
wait
echo "done: $(ls "$ARM"/per/*/reports/*.json 2>/dev/null | wc -l | tr -d ' ') report files"
