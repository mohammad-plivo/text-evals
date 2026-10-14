#!/bin/zsh
# Fast-lane A/B: fastflow (turn_mode:fast) vs tasksflow (default agent_node),
# BOTH from the same tree, same invocation, so the only variable is the lane.
set -u
LAT_DIR="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/OpenAI agent/latency"
WT="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/lk-pr2"
REPEAT="${1:-3}"
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LAT_DIR/rows"
# Wait out any run already using the rig — concurrent runs contend for Azure and
# skew both sets of numbers.
# Wait out any OTHER run using the rig. Match the actual python process, not
# any shell whose command line merely mentions it — an earlier version matched
# this script's own heredoc and waited on itself forever.
while pgrep -f "python -m src.simulation.cli" >/dev/null; do sleep 60; done
for ARM in fastflow tasksflow; do
  ROWS="$LAT_DIR/rows/${ARM}-fastab-${STAMP}.jsonl"
  echo "=== ARM=$ARM repeat=$REPEAT rows=$ROWS ==="
  cd "$WT"
  LATENCY_ROWS_PATH="$ROWS" uv run --no-sync python -m src.simulation.cli \
    run "$LAT_DIR/sim/$ARM" --env-file "$LAT_DIR/.env.local" \
    --repeat "$REPEAT" --no-open 2>"$LAT_DIR/rows/${ARM}-fastab-${STAMP}.stderr.log"
  echo "--- $ARM exit: $? ; rows: $(wc -l < "$ROWS" 2>/dev/null || echo 0) ---"
done
echo "DONE stamp=$STAMP"
