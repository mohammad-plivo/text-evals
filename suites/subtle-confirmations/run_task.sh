#!/bin/zsh
# Sharded suite runner for the subtle-confirmations sandbox.
# Usage: ./run_task.sh <task> [total_shards] [parallel] [label]   (AGENT=gemma31b|gpt41 env override honored)
# Sources run_env.sh (mints the LiveKit JWT / exports LK_*), runs the full task suite sharded,
# logs per-shard to logs/<task>_<label>/shard_<i>.log. Store (ground truth) accrues in the sandbox.
TASK="${1:?usage: run_task.sh <task> [shards] [parallel] [label]}"
SHARDS="${2:-10}"; PAR="${3:-5}"; LABEL="${4:-run}"
DIR="${0:A:h}"
source "$DIR/run_env.sh"
SB="$DIR/cx-skills-subtle"
LOGDIR="$DIR/logs/${TASK}_${LABEL}"
mkdir -p "$LOGDIR"
cd "$SB"
export TASK SHARDS SB LOGDIR
echo "sweep start: task=$TASK shards=$SHARDS parallel=$PAR label=$LABEL agent=$LK_AGENT_MODEL"
seq 0 $((SHARDS-1)) | xargs -P "$PAR" -I{} zsh -c '
  SCENARIO_TASK="$TASK" SCENARIO_TOTAL_SHARDS="$SHARDS" SCENARIO_SHARD_INDEX="$1" \
    "$SB/.venv/bin/python" -m pytest tests/test_task.py -q > "$LOGDIR/shard_$1.log" 2>&1
  echo "shard $1 rc=$?"
' _ {}
echo "=== sweep DONE: $TASK ($LABEL) ==="
grep -hE "[0-9]+ (passed|failed)" "$LOGDIR"/shard_*.log | tail -20
