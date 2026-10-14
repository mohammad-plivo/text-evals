#!/bin/bash
# Run every scenario in a workspace with N workers, one process per scenario.
# The CLI has no parallelism flag and 165 sequential scenarios take ~3h.
#
# Resumable: anything already in exits.txt is skipped, because 6 workers
# OOM-killed the box mid-run and a rerun must not redo an hour of work.
# Worker count is the OOM knob — 6 died, 3 is stable on this machine.
set -u
WS="${1:?workspace}"; JOBS="${2:-3}"; OUT="${3:?outdir}"
export SUITE_MODALITY="${4:-text}"
export SUITE_WS="$WS" SUITE_OUT="$OUT"
export SUITE_REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/Vapi Flow/repo"
export SUITE_ENV="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"

mkdir -p "$OUT"; touch "$OUT/exits.txt"
cd "$SUITE_REPO" || exit 1

ls "$WS/scenarios" | grep '\.yaml$' | sed 's/\.yaml$//' \
  | grep -vxF -f <(awk '{print $2}' "$OUT/exits.txt") \
  | xargs -P "$JOBS" -I{} bash -c '
      uv run python -m src.simulation.cli run "$SUITE_WS" \
        --scenario "$1" --no-open --modality "$SUITE_MODALITY" \
        --env-file "$SUITE_ENV" > "$SUITE_OUT/$1.log" 2>&1
      echo "$? $1" >> "$SUITE_OUT/exits.txt"
    ' _ {}

echo "DONE $(wc -l < "$OUT/exits.txt") scenarios [modality=$SUITE_MODALITY]"
