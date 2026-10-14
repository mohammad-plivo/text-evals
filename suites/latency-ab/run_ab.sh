#!/bin/zsh
# Baseline A/B: tasksflow (agent_node) vs v2flow (ai_agent_v2), same scenarios.
# Usage: run_ab.sh [repeat] [scenario-name]   (scenario optional → whole battery)
set -u
LAT_DIR="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/OpenAI agent/latency"
WT="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/plivo-cx-livekit-ser5959"
REPEAT="${1:-5}"
SCEN="${2:-}"
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LAT_DIR/rows"

for ARM in tasksflow v2flow; do
  ROWS="$LAT_DIR/rows/${ARM}-${STAMP}.jsonl"
  echo "=== ARM=$ARM repeat=$REPEAT rows=$ROWS ==="
  cd "$WT"
  EXTRA=()
  [[ -n "$SCEN" ]] && EXTRA+=(--scenario "$SCEN")
  LATENCY_ROWS_PATH="$ROWS" uv run python -m src.simulation.cli \
    run "$LAT_DIR/sim/$ARM" \
    --env-file "$LAT_DIR/.env.local" \
    "${EXTRA[@]}" --repeat "$REPEAT" --no-open \
    2>"$LAT_DIR/rows/${ARM}-${STAMP}.stderr.log"
  echo "--- $ARM exit: $? ; rows: $(wc -l < "$ROWS" 2>/dev/null || echo 0) ---"
done
echo "DONE stamp=$STAMP"
