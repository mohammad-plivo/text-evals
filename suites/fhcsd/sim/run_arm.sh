#!/bin/bash
# One process per scenario (the CLI has no parallelism flag), N in flight.
# Resumable: anything already in exits.txt is skipped.
set -u
ARM="${1:?arm dir}"; JOBS="${2:-8}"; REP="${3:-5}"
OUT="$(pwd)/out/$ARM"; mkdir -p "$OUT"; touch "$OUT/exits.txt"
export REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/Vapi Flow/repo"
export ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
export ARMDIR="$(pwd)/$ARM/per" OUT REP
cd "$REPO" || exit 1
ls "$ARMDIR" | grep -vxF -f <(awk '$1==0{print $2}' "$OUT/exits.txt") \
 | xargs -P "$JOBS" -I{} bash -c '
     uv run python -m src.simulation.cli run "$ARMDIR/$1" --scenario "$1" \
       --repeat "$REP" --no-open --env-file "$ENVF" > "$OUT/$1.log" 2>&1
     echo "$? $1" >> "$OUT/exits.txt"' _ {}
echo "DONE $ARM: $(wc -l < "$OUT/exits.txt") scenarios"
