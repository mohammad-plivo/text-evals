#!/bin/zsh
# Baseline sweep driver — runs every task suite against the gemma-31b arm, sharded.
# Usage: ./run_baseline.sh <rep>                       (rep = 1|2|3; resumable via done-markers)
# Internal: ./run_baseline.sh __shard <rep> <suite> <total> <idx>
# Case failures do NOT stop the sweep — the JSONL run store is the source of truth.
set -u
EXP_DIR="${0:A:h}"
REPO="$EXP_DIR/cx-skills-gemma31b"
SELF="${0:A}"

if [ "${1:-}" = "__shard" ]; then
  REP=$2; suite=$3; total=$4; idx=$5
  LOGS="$EXP_DIR/baseline-logs/rep$REP"; DONE="$EXP_DIR/baseline-logs/done"
  marker="$DONE/rep${REP}_${suite}_${idx}of${total}"
  [ -f "$marker" ] && { echo "skip $suite shard $idx (done)"; exit 0; }
  cd "$REPO"
  SCENARIO_TASK="$suite" SCENARIO_TOTAL_SHARDS="$total" SCENARIO_SHARD_INDEX="$idx" \
    .venv/bin/python -m pytest tests/test_task.py -q \
    > "$LOGS/${suite}_shard${idx}.log" 2>&1
  rc=$?
  echo "rc=$rc" >> "$LOGS/${suite}_shard${idx}.log"
  touch "$marker"
  echo "done $suite shard $idx/$total rc=$rc"
  exit 0
fi

REP="${1:?usage: run_baseline.sh <rep>}"
LOGS="$EXP_DIR/baseline-logs/rep$REP"; DONE="$EXP_DIR/baseline-logs/done"
mkdir -p "$LOGS" "$DONE"
PARALLEL="${PARALLEL:-5}"          # concurrent shards (watch 429s before raising)

source "$EXP_DIR/run_env.sh" || exit 1
cd "$REPO"

SUITES=(${=SUITES_OVERRIDE:-address boolean choice confirm_known_values contact_screening credit_card currency datetime dob dtmf email name number phone text})

shards_for() {  # default_shards from the suite YAML, fallback 10
  .venv/bin/python - "$1" <<'PY'
import sys, yaml
d = yaml.safe_load(open(f"tests/scenarios/tasks/{sys.argv[1]}.yml"))
print((d.get("suite") or {}).get("default_shards", 10))
PY
}

for suite in $SUITES; do
  total=$(shards_for "$suite")
  echo "=== [$(date +%H:%M:%S)] rep$REP suite=$suite shards=$total ==="
  seq 0 $((total-1)) | xargs -P "$PARALLEL" -I{} "$SELF" __shard "$REP" "$suite" "$total" {}
done
echo "=== rep$REP sweep complete $(date +%H:%M:%S) ==="
