#!/bin/bash
# rerun.sh <sha> <campaign-number> <lane-a-ids-file> <lane-b-slugs-file> [repetitions]: pinned tree, pack copy, both lanes, results
set -uo pipefail
SHA="$1"; N="$2"; A_IDS="$3"; B_SLUGS="$4"; REPS="${5:-3}"
SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
REPO="$SE/../repo"
ENV_FILE="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/cd27465f-3644-41c6-9c4c-1e7142e58b3b/scratchpad/v29-eval.env"
T="$SE/trees/$SHA"; C="$SE/campaign-$N"
if [ ! -d "$T" ]; then git -C "$REPO" worktree add --detach "$T" "$SHA" || { echo "REFUSED: cannot create tree at $SHA"; exit 2; }; ln -s "$REPO/.venv" "$T/.venv"; fi
[ "$(git -C "$T" rev-parse HEAD)" = "$(git -C "$REPO" rev-parse "$SHA")" ] || { echo "REFUSED: tree HEAD is not $SHA"; exit 2; }
cp "$SE/pack/local_stress_cases.py" "$T/tests/v29_model_eval/local_stress_cases.py"
mkdir -p "$C/lane-a" "$C/lane-b"
PACK_SHA=$(shasum -a 256 "$SE/pack/local_stress_cases.py" | cut -c1-16)
IMPORTS=$(cd "$T" && .venv/bin/python -c "import src; print(src.__file__)")
case "$IMPORTS" in "$T"/*) ;; *) echo "REFUSED: src imports from $IMPORTS, not the pinned tree"; exit 2;; esac
printf 'campaign %s: tree %s, pack sha256 %s, reps %s, lane A %s ids, lane B %s slugs, started %s IST\n' "$N" "$SHA" "$PACK_SHA" "$REPS" "$(grep -c . "$A_IDS" || true)" "$(grep -c . "$B_SLUGS" || true)" "$(date '+%H:%M')" | tee "$C/RUN-INFO.txt"
(
  if [ -s "$A_IDS" ]; then
    STRESS_REPO="$T" python3 "$SE/run_campaign.py" --cases-from "$A_IDS" --repetitions "$REPS" --campaign-id "fh-stress-c$N" --env-file "$ENV_FILE" --ledger "$C/lane-a/ledger.json" --output "$C/lane-a/results.jsonl" --configured --cap-usd 200 > "$C/lane-a/run_campaign.out" 2>&1
    STRESS_REPO="$T" python3 "$SE/run_campaign.py" --report --campaign-id "fh-stress-c$N" --output "$C/lane-a/results.jsonl" --ledger "$C/lane-a/ledger.json" > "$C/lane-a/report.out" 2>&1
    echo "lane A done $(date '+%H:%M')"
  fi
) &
A_PID=$!
if [ -s "$B_SLUGS" ]; then
  # shellcheck disable=SC2046
  if [ "$(tr -d '[:space:]' < "$B_SLUGS")" = "ALL" ]; then SLUG_ARGS=(); else SLUG_ARGS=(--slug $(tr '\n' ' ' < "$B_SLUGS")); fi  # ALL runs every enabled scenario, one CLI per workspace
  (cd "$T" && STRESS_REPO="$T" PYTHONUNBUFFERED=1 .venv/bin/python "$SE/sim-fh/run_pack.py" --campaign "$N" --repeat "$REPS" --max-parallel 2 --concurrency "${CONC:-3}" --split "${SPLIT:-1}" --cap-usd 100 ${SLUG_ARGS[@]+"${SLUG_ARGS[@]}"} > "$C/lane-b/run_pack.out" 2>&1)
  echo "lane B done $(date '+%H:%M')"
fi
wait "$A_PID"
echo "campaign $N finished $(date '+%H:%M')" | tee -a "$C/RUN-INFO.txt"
