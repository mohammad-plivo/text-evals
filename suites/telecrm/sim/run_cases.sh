#!/bin/bash
# Run every per-scenario case workspace and collect the reports into one directory.
# One workspace per scenario because params.yaml is per-workspace and each Hunter persona
# uses its own name — a shared identity makes the screener exit wrong_contact in three turns.
set -u
OUT="${1:?outdir}"; REP="${2:-5}"
REPO="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/agent-runner"
ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
CASES="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/TeleCRM/sim/cases"
mkdir -p "$OUT"
cd "$REPO" || exit 1
for d in "$CASES"/*/; do
  s=$(basename "$d")
  rm -f "$d/reports/"* 2>/dev/null
  uv run python -m src.simulation.cli run "$d" --repeat "$REP" --max-parallel 3 --stagger 2 \
      --no-open --env-file "$ENVF" > "$OUT/$s.log" 2>&1
  echo "$? $s" >> "$OUT/exits.txt"
  cp "$d"/reports/*.json "$OUT/$s.json" 2>/dev/null
done
echo "DONE $(ls "$OUT"/*.json 2>/dev/null | wc -l) case reports -> $OUT"
