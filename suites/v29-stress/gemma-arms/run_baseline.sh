#!/bin/bash
# run_baseline.sh <sha> <tag>: lane A core suite, GPT arm, on a pinned tree with NO harness changes.
# The "before" side of the latency comparison; separate from run_arm.sh so a live run is never edited.
set -uo pipefail
SHA="$1"; TAG="$2"
SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
T="$SE/trees/$SHA"
ENV_FILE="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/b582d26b-de64-45d3-bb4c-49e0bf8f99c5/scratchpad/regression-gate/v29-eval.env"
OUT="$SE/gemma-arms/$TAG-gpt-lanea"
mkdir -p "$OUT"
if [ ! -d "$T" ]; then
  git -C "$SE/../repo" worktree add --detach "$T" "$SHA" >/dev/null 2>&1 || { echo "REFUSED: cannot create tree at $SHA"; exit 2; }
  ln -s "$SE/../repo/.venv" "$T/.venv"
fi
[ "$(git -C "$T" rev-parse HEAD)" = "$(git -C "$SE/../repo" rev-parse "$SHA")" ] || { echo "REFUSED: tree HEAD is not $SHA"; exit 2; }
[ -z "$(git -C "$T" status --porcelain | grep -v '^?? .venv$')" ] || { echo "REFUSED: baseline tree is dirty"; exit 2; }

printf 'baseline %s: tree %s, model gpt-4.1, suite core, reps 1, PREPARED_SPEECH_MODE=off, started %s\n' \
  "$TAG" "$(git -C "$T" rev-parse --short HEAD)" "$(date '+%H:%M:%S')" | tee "$OUT/RUN-INFO.txt"
(cd "$T" && PREPARED_SPEECH_MODE=off V29_EVAL_PROVIDER=azure V29_EVAL_MODEL=gpt-4.1 .venv/bin/python -m tests.v29_model_eval.live \
    --env-file "$ENV_FILE" --ledger "$OUT/ledger.json" --campaign-id "$TAG-gpt" --output "$OUT/results.jsonl" \
    --repetitions 1 --continue-on-oracle-failure --suite core) > "$OUT/run.out" 2>&1
echo "baseline exit $? $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
