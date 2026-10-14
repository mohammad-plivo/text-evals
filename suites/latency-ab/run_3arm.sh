#!/bin/zsh
# Three-arm A/B, one invocation, same tree, nothing else on the rig:
#   v2flow    = ai_agent_v2            (the original)
#   tasksflow = agent_node default     (Kishan's v2.5 as it stands)
#   fastflow  = agent_node turn_mode:fast (ours)
set -u
LAT="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/OpenAI agent/latency"
WT="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/lk-pr2"
REPEAT="${1:-3}"; SUITE="${2:-}"   # SUITE="-b" selects the Hunter-style scenarios
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$LAT/rows"
# NO wait-loop here. Three attempts at "wait until the rig is free" all matched
# the PARENT SHELL, whose command line contains this script text, so each one
# waited on itself. The caller is responsible for ensuring the rig is free.
for ARM in v2flow tasksflow fastflow; do
  WS="$LAT/sim/${ARM}${SUITE}"
  ROWS="$LAT/rows/${ARM}-3arm${SUITE}-${STAMP}.jsonl"
  echo "=== ARM=${ARM}${SUITE} repeat=$REPEAT ==="
  cd "$WT"
  LATENCY_ROWS_PATH="$ROWS" uv run --no-sync python -m src.simulation.cli \
    run "$WS" --env-file "$LAT/.env.local" --repeat "$REPEAT" --no-open \
    2>"$LAT/rows/${ARM}-3arm${SUITE}-${STAMP}.stderr.log"
  echo "--- ${ARM}${SUITE} exit=$? rows=$(wc -l < "$ROWS" 2>/dev/null || echo 0) ---"
done
echo "DONE stamp=$STAMP suite=${SUITE:-a}"
