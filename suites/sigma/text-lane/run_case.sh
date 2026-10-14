#!/usr/bin/env bash
# Run one text-lane session case N times on whatever model the env file routes to, then classify.
# Usage: run_case.sh <worktree> <case_id> <reps> <campaign_tag> [extra live.py args]
# Output: $SP/eval/<tag>-<case>.jsonl, its own ledger, and the classifier's summary on stdout.
set -euo pipefail
WT="$1"; CASE="$2"; REPS="$3"; TAG="$4"; shift 4
SP="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/cd27465f-3644-41c6-9c4c-1e7142e58b3b/scratchpad"
ENV="$SP/v29-eval.env"
OUT="$SP/eval/$TAG-$CASE.jsonl"; LEDGER="$SP/eval/$TAG-$CASE-ledger.json"; LOG="$SP/eval/$TAG-$CASE.log"
[ -f "$ENV" ] || { echo "missing $ENV (rebuild from repos/cx-dev-dockerized-v29/services/plivo-cx-livekit/.env + V29_EVAL_PROVIDER/MODEL)"; exit 2; }
mkdir -p "$SP/eval"; rm -f "$OUT" "$LEDGER"
cd "$WT"
set +e
uv run --frozen python -m tests.v29_model_eval.live --env-file "$ENV" --ledger "$LEDGER" --campaign-id "$TAG-$CASE" \
  --output "$OUT" --repetitions "$REPS" --configured --continue-on-oracle-failure --session-case "$CASE" "$@" > "$LOG" 2>&1
RC=$?
set -e
echo "exit=$RC  rows=$( [ -f "$OUT" ] && wc -l < "$OUT" || echo 0 )  log=$LOG"
[ -f "$OUT" ] && python3 "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/Sigma/text-lane/classify_campaign.py" "$OUT" "$LEDGER" || true
grep -oE '"message": "[^"]*(GuardError|RequestDenied|ModelMismatch|BudgetExhausted)[^"]*"' "$LOG" | sort -u | head -3 || true
