#!/bin/bash
# run_confirm.sh <sha> <tag> <reps>: re-run the regressed case ids on a pinned tree, GPT arm, to separate a
# real regression from one-repetition variance. Ids come from confirm-ids.json (session and snapshot lists).
set -uo pipefail
SHA="$1"; TAG="$2"; REPS="${3:-3}"
SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
T="$SE/trees/$SHA"
ENV_FILE="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/b582d26b-de64-45d3-bb4c-49e0bf8f99c5/scratchpad/regression-gate/v29-eval.env"
OUT="$SE/gemma-arms/$TAG-gpt-lanea"
mkdir -p "$OUT"
[ -d "$T" ] || { echo "REFUSED: no tree at $SHA"; exit 2; }
# the tree may sit on the prep branch whose base is $SHA (harness-only commits); anything else is refused
git -C "$T" merge-base --is-ancestor "$SHA" HEAD 2>/dev/null || { echo "REFUSED: $SHA is not in this tree's history"; exit 2; }
case "$(git -C "$T" rev-parse --abbrev-ref HEAD)" in HEAD|mk/v29-gemma-eval-arm) ;; *) echo "REFUSED: unexpected branch"; exit 2;; esac

SEL=()  # bash 3.2 on macOS has no mapfile
while IFS= read -r line; do SEL+=("$line"); done < <(python3 -c "
import json
d=json.load(open('$SE/gemma-arms/confirm-ids.json'))
for c in d['session']: print('--session-case'); print(c)
for c in d['snapshot']: print('--snapshot-case'); print(c)
")
printf 'confirm %s: tree %s, gpt-4.1, %s reps, %s ids, started %s\n' \
  "$TAG" "$(git -C "$T" rev-parse --short HEAD)" "$REPS" "$(( ${#SEL[@]} / 2 ))" "$(date '+%H:%M:%S')" | tee "$OUT/RUN-INFO.txt"
(cd "$T" && PREPARED_SPEECH_MODE=off V29_EVAL_PROVIDER=azure V29_EVAL_MODEL=gpt-4.1 .venv/bin/python -m tests.v29_model_eval.live \
    --env-file "$ENV_FILE" --ledger "$OUT/ledger.json" --campaign-id "$TAG-gpt" --output "$OUT/results.jsonl" \
    --repetitions "$REPS" --continue-on-oracle-failure "${SEL[@]}") > "$OUT/run.out" 2>&1
echo "confirm exit $? $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
