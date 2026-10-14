#!/bin/zsh
# Full cx-skills task sweep at temp 0.7 (Gemma agent) — answers "are all tasks fine at 0.7?".
# Mirrors run_baseline.sh, but forces LK_AGENT_TEMP=0.7 after run_env.sh and logs to temp07-logs/.
set -u
EXP_DIR="${0:A:h}"; REPO="$EXP_DIR/cx-skills-gemma31b"; SELF="${0:A}"

if [ "${1:-}" = "__shard" ]; then
  suite=$2; total=$3; idx=$4
  LOGS="$EXP_DIR/temp07-logs"; DONE="$LOGS/done"
  marker="$DONE/${suite}_${idx}of${total}"
  [ -f "$marker" ] && { echo "skip $suite $idx (done)"; exit 0; }
  cd "$REPO"
  SCENARIO_TASK="$suite" SCENARIO_TOTAL_SHARDS="$total" SCENARIO_SHARD_INDEX="$idx" \
    .venv/bin/python -m pytest tests/test_task.py -q > "$LOGS/${suite}_shard${idx}.log" 2>&1
  rc=$?; echo "rc=$rc" >> "$LOGS/${suite}_shard${idx}.log"
  touch "$marker"; echo "done $suite $idx/$total rc=$rc"
  exit 0
fi

LOGS="$EXP_DIR/temp07-logs"; DONE="$LOGS/done"; mkdir -p "$LOGS" "$DONE"
PARALLEL="${PARALLEL:-5}"
source "$EXP_DIR/run_env.sh" || exit 1
export LK_AGENT_TEMP=0.7          # <<< the whole point of this driver
echo "TEMP=$LK_AGENT_TEMP agent=$LK_AGENT_MODEL  sweep start $(date +%H:%M:%S)"
cd "$REPO"
SUITES=(address boolean choice confirm_known_values contact_screening credit_card currency datetime dob dtmf email name number phone text)
shards_for() {
  .venv/bin/python - "$1" <<'PY'
import sys, yaml
d = yaml.safe_load(open(f"tests/scenarios/tasks/{sys.argv[1]}.yml"))
print((d.get("suite") or {}).get("default_shards", 10))
PY
}
for suite in $SUITES; do
  total=$(shards_for "$suite")
  echo "=== [$(date +%H:%M:%S)] suite=$suite shards=$total ==="
  seq 0 $((total-1)) | xargs -P "$PARALLEL" -I{} "$SELF" __shard "$suite" "$total" {}
done
echo "=== SWEEP COMPLETE $(date +%H:%M:%S) ==="
