#!/bin/bash
# One prepared-speech arm of the sim-prepared campaign.
#
#   run_arm.sh <prepared|off> <tag> <env-file> [repeats] [--scenario a,b] [--max-parallel N] [--dry-run]
#
# Writes under stress-evals/prepared-arms/<tag>-<arm>/, and keeps that arm's OWN copy of every
# report it produced: both arms append into one ws/reports, so "newest .jsonl" cannot tell them
# apart. Refuses a tree that is not cd6ac6c5 or is dirty, an unbuilt workspace, a node that is not
# on the campaign model, a missing env file and one any other user can read. Prints the env file's
# KEY NAMES only, never a value.
set -uo pipefail

SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
T="$SE/trees/cd6ac6c5"
TREE_SHA="cd6ac6c5"
WS="$SE/sim-prepared/ws"
MODEL="gpt-4.1"

[ $# -ge 3 ] || { echo "usage: run_arm.sh <prepared|off> <tag> <env-file> [repeats] [--scenario a,b] [--max-parallel N] [--dry-run]"; exit 2; }
ARM="$1"; TAG="$2"; ENV_FILE="$3"; shift 3
REPS=5
SCENARIOS=""
PARALLEL=2
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --scenario) SCENARIOS="$2"; shift 2 ;;
    --max-parallel) PARALLEL="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    # repeats: every character a digit -- "3x" used to pass here and die inside the CLI's argparse
    [0-9]*) case "$1" in *[!0-9]*) echo "REFUSED: repeats must be a whole number, got $1"; exit 2 ;; esac
            REPS="$1"; shift ;;
    *) echo "REFUSED: unknown argument $1"; exit 2 ;;
  esac
done

case "$ARM" in prepared|off) ;; *) echo "REFUSED: arm must be prepared or off"; exit 2 ;; esac
# the full HEAD, not `--short` (its length grows with ambiguity), and the tree must be clean
case "$(git -C "$T" rev-parse HEAD 2>/dev/null)" in
  "$TREE_SHA"*) ;; *) echo "REFUSED: tree is not $TREE_SHA"; exit 2 ;;
esac
[ -z "$(git -C "$T" status --porcelain)" ] || { echo "REFUSED: tree $TREE_SHA is dirty"; exit 2; }
[ -x "$T/.venv/bin/python" ] || { echo "REFUSED: no venv python in the tree"; exit 2; }
[ -f "$ENV_FILE" ] || { echo "REFUSED: env file missing (path given, value never read here)"; exit 2; }
[ "$(stat -f %Lp "$ENV_FILE")" = "600" ] || { echo "REFUSED: env file is not mode 600 (it holds keys)"; exit 2; }
[ -f "$WS/flow.json" ] || { echo "REFUSED: workspace not built -- run build_ws.py"; exit 2; }
grep -q "\"model\": \"$MODEL\"" "$WS/flow.json" || { echo "REFUSED: workspace node is not on $MODEL"; exit 2; }

OUT="$SE/prepared-arms/$TAG-$ARM"
ENV_SHA=$(shasum -a 256 "$ENV_FILE" | cut -d' ' -f1)
SIM_DEPLOY=no
grep -q '^AZURE_OPENAI_SIM_DEPLOYMENT=.' "$ENV_FILE" && SIM_DEPLOY=yes
CMD=("$T/.venv/bin/python" -m src.simulation.cli run "$WS"
     --env-file "$ENV_FILE" --no-open --repeat "$REPS" --max-parallel "$PARALLEL" --verbose)

run_one() {  # $1 = scenario name or "" for the whole suite
  local label="${1:-all}"
  local -a cmd=("${CMD[@]}")
  [ -n "$1" ] && cmd+=(--scenario "$1")
  if [ "$DRY" = "1" ]; then
    printf 'would run (PREPARED_SPEECH_MODE=%s, cwd %s):\n  %s\n' "$ARM" "$T" "${cmd[*]}"
    return 0
  fi
  ( cd "$T" && PREPARED_SPEECH_MODE="$ARM" "${cmd[@]}" ) > "$OUT/run-$label.out" 2> "$OUT/run-$label.err"
  CODE=$?
  STAMP=$(sed -n 's/^  report: .*\/\([0-9][0-9-]*\)\.json$/\1/p' "$OUT/run-$label.out" | tail -1)
  if [ -n "$STAMP" ] && [ -f "$WS/reports/$STAMP.jsonl" ]; then
    mkdir -p "$OUT/reports" && cp "$WS/reports/$STAMP.jsonl" "$OUT/reports/"
    echo "  $label: exit $CODE, report $STAMP.jsonl $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
  else
    echo "  $label: exit $CODE, NO REPORT COPIED -- judge this arm by hand $(date '+%H:%M:%S')" | tee -a "$OUT/RUN-INFO.txt"
  fi
}

[ "$DRY" = "1" ] || mkdir -p "$OUT/reports"
INFO=$(printf 'arm %s tag %s: tree %s, node model %s (AZURE_OPENAI_SIM_DEPLOYMENT set: %s -- when set it, not the node line, is the deployment that answers; settings.py:235), repeats %s, parallel %s, scenarios %s, env sha256 %s, env keys %s, started %s\n' \
  "$ARM" "$TAG" "$(git -C "$T" rev-parse --short HEAD)" "$MODEL" "$SIM_DEPLOY" "$REPS" "$PARALLEL" "${SCENARIOS:-all}" \
  "$ENV_SHA" "$(grep -o '^[A-Z_][A-Z0-9_]*' "$ENV_FILE" | sort -u | tr '\n' ' ')" "$(date '+%H:%M:%S')")
if [ "$DRY" = "1" ]; then echo "$INFO"; else echo "$INFO" | tee "$OUT/RUN-INFO.txt"; fi

if [ -z "$SCENARIOS" ]; then
  run_one ""
else
  # the CLI's --scenario takes one name; a comma list is one run per name, one report each
  IFS=',' read -r -a names <<< "$SCENARIOS"
  for name in "${names[@]}"; do run_one "$name"; done
fi
[ "$DRY" = "1" ] || echo "reports: $OUT/reports (this arm's own copies), arm logs: $OUT"
