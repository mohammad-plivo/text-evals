#!/bin/bash
# Both arms in parallel, REP runs each; output under sim/out/chooseslot-<arm>/.
set -u; REP="${1:-10}"; NODE="${2:?choose-slot uuid}"
REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/FHCSD/repo"
ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
SIM="$(pwd)"; mkdir -p "$SIM/out"
for ARM in A B; do
  ( cd "$REPO" && uv run --no-sync python -m src.simulation.cli run "$SIM/chooseslot/arm$ARM" --scenario first-slot --repeat "$REP" --no-open --env-file "$ENVF" --node "$NODE" > "$SIM/out/chooseslot-$ARM.log" 2>&1; echo "arm$ARM exit=$?" ) &
done
wait; echo "DONE both arms"
