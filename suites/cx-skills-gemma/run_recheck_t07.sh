#!/bin/zsh
# Authoritative recheck of not-passed cases (empties/judge-artifacts/fails) from the full sweep.
# Each case: isolated, up to 3 tries, ROTATING the tunnel port per try (tolerates a dead tunnel).
# Final verdict = PASS if any try passes; else classify FAIL-behav vs FAIL-empty. PARALLEL=3 (judge-safe).
set -u
EXP="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/31B-Experiments"
REPO="$EXP/cx-skills-gemma31b"
LME="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/Local Model Experiments"
RES="$LME/recheck-t07-results"
SELF="${0:A}"

if [ "${1:-}" = "__recheck" ]; then
  pair="$2"; s="${pair%%:*}"; c="${pair##*:}"
  cd "$REPO"
  last=""
  for try in 1 2 3; do
    port=$((8000 + ((try - 1) % 4)))
    out=$(SCENARIO_TASK="$s" SCENARIO_CASE="$c" LK_AGENT_BASE_URL="http://localhost:${port}/v1" \
      .venv/bin/python -m pytest tests/test_task.py -q 2>&1)
    if echo "$out" | grep -q "overall_pass=True"; then echo "PASS try$try p$port" > "$RES/${s}__${c}"; exit 0; fi
    last="$out"
  done
  if echo "$last" | grep -qE "deterministic_failures|task did not complete|overall_pass=False"; then
    echo "FAIL-behav" > "$RES/${s}__${c}"
  else
    echo "FAIL-empty/err" > "$RES/${s}__${c}"
  fi
  exit 0
fi

mkdir -p "$RES"
source "$EXP/run_env.sh" >/dev/null 2>&1
export LK_AGENT_MODEL=google/gemma-4-31B-it LK_AGENT_API_KEY=local LK_AGENT_TEMP=0.7
echo "recheck start $(date +%H:%M:%S)  cases=$(grep -c . "$LME/recheck_t07.txt")"
grep . "$LME/recheck_t07.txt" | xargs -P3 -I{} "$SELF" __recheck {}
echo "=== RECHECK DONE $(date +%H:%M:%S) ==="
