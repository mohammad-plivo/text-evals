#!/bin/zsh
ROOT="${0:A:h}/.."
cd "$ROOT/cx-skills-subtle"
source "$ROOT/run_env.sh" >/dev/null 2>&1
for t in email phone credit_card dob name; do
  echo ">>> $t sample (shard 0 of 8)"
  SCENARIO_TASK=$t SCENARIO_TOTAL_SHARDS=8 SCENARIO_SHARD_INDEX=0 \
    .venv/bin/python -m pytest tests/test_task.py -q 2>&1 | tail -2
done
echo "=== STRICT SAMPLES DONE ==="
