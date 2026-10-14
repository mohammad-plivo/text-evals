#!/bin/bash
# run_arm.sh <gpt|gemma> <a|b> <campaign-tag> [preflight-case-id]
# Lane A: tests/v29_model_eval core suite (or one --session-case for a pre-flight). Lane B: the v29-agent-node pack.
# Writes under stress-evals/gemma-arms/<tag>-<arm>-lane<lane>/. Never prints an env value.
set -uo pipefail
ARM="$1"; LANE="$2"; TAG="$3"; ONE="${4:-}"
SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
T="$SE/trees/33afca9c"
GPT_ENV="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/b582d26b-de64-45d3-bb4c-49e0bf8f99c5/scratchpad/regression-gate/v29-eval.env"
GEMMA_ENV="${GEMMA_ENV:-/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/e4e421e8-e52c-4582-8600-df886be5a50d/scratchpad/gemma-arm/gemma.env}"
OUT="$SE/gemma-arms/$TAG-$ARM-lane$LANE"
mkdir -p "$OUT"

case "$ARM" in
  gpt)   MODEL="gpt-4.1"; ENV_FILE="$GPT_ENV" ;;
  gemma) MODEL="google/gemma-4-31b-it"; ENV_FILE="$GEMMA_ENV" ;;
  *) echo "REFUSED: arm must be gpt or gemma"; exit 2 ;;
esac
[ -f "$ENV_FILE" ] || { echo "REFUSED: env file missing for $ARM"; exit 2; }
[ "$(stat -f %Lp "$ENV_FILE")" = "600" ] || { echo "REFUSED: env file is not mode 600"; exit 2; }
[ "$(git -C "$T" rev-parse --abbrev-ref HEAD)" = "mk/v29-gemma-eval-arm" ] || { echo "REFUSED: tree is not on mk/v29-gemma-eval-arm"; exit 2; }

printf 'arm %s lane %s tag %s: tree %s (%s), model %s, env keys %s, started %s\n' \
  "$ARM" "$LANE" "$TAG" "$(git -C "$T" rev-parse --short HEAD)" "$(git -C "$T" rev-parse --abbrev-ref HEAD)" "$MODEL" \
  "$(grep -o '^[A-Z_]*' "$ENV_FILE" | sort | tr '\n' ' ')" "$(date '+%H:%M:%S')" | tee "$OUT/RUN-INFO.txt"

if [ "$LANE" = "a" ]; then
  SEL=(--suite core)
  [ -n "$ONE" ] && SEL=(--session-case "$ONE"); [ -n "${SNAP:-}" ] && SEL=(--snapshot-case "$SNAP")
  (cd "$T" && PREPARED_SPEECH_MODE=off V29_EVAL_MODEL="$MODEL" .venv/bin/python -m tests.v29_model_eval.live \
      --env-file "$ENV_FILE" --ledger "$OUT/ledger.json" --campaign-id "$TAG-$ARM" --output "$OUT/results.jsonl" \
      --repetitions 1 --continue-on-oracle-failure "${SEL[@]}") > "$OUT/run.out" 2>&1
  echo "lane A exit $? $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
else
  WS="$SE/gemma-arms/ws-$ARM"
  [ -d "$WS" ] || cp -R "$T/examples/simulation/v29-agent-node" "$WS"
  # the gemma arm stamps the workspace node's model; the gpt arm keeps what the pack ships
  "$T/.venv/bin/python" - "$WS/flow.json" "$ARM" "$MODEL" <<'PY'
import json, sys
path, arm, model = sys.argv[1], sys.argv[2], sys.argv[3]
flow = json.load(open(path))
nodes = [n for n in flow.get("nodes", []) if (n.get("data") or {}).get("config", {}).get("model_config")]
if arm == "gemma":
    for n in nodes:
        n["data"]["config"]["model_config"]["model"] = model
    json.dump(flow, open(path, "w"), indent=2)
print("model_config.model:", [(n.get("id"), n["data"]["config"]["model_config"].get("model")) for n in nodes])
PY
  REPS="${REPS:-5}"
  [ -n "$ONE" ] && REPS=1
  SC=()
  [ -n "$ONE" ] && SC=(--scenario "$ONE")
  (cd "$T" && PREPARED_SPEECH_MODE=prepared .venv/bin/python -m src.simulation.cli run "$WS" \
      --env-file "$ENV_FILE" --no-open --repeat "$REPS" --max-parallel 2 --verbose "${SC[@]+${SC[@]}}") \
      > "$OUT/run.out" 2> "$OUT/run.err"
  echo "lane B exit $? $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
fi
