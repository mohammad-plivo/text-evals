#!/usr/bin/env bash
# Run every full-length Sigma case N times on the model the env file routes to, K at a time.
# Usage: bash run_phase2.sh <worktree> <reps> <tag> [parallel=3]   (bash, never zsh: word splitting)
set -uo pipefail
WT="$1"; REPS="$2"; TAG="$3"; PAR="${4:-3}"
SP="/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/cd27465f-3644-41c6-9c4c-1e7142e58b3b/scratchpad"
RUN="$(cd "$(dirname "$0")" && pwd)/run_case.sh"
mkdir -p "$SP/eval/$TAG"
cd "$WT"
mapfile -t CASES < <(uv run --frozen python -c "
from tests.v29_model_eval.session_cases import MULTI_TURN_CASES
print('\n'.join(c['id'] for c in MULTI_TURN_CASES if c['id'].startswith('sigma_full_')))")
echo "cases: ${#CASES[@]}  reps: $REPS  parallel: $PAR  tag: $TAG"
running=0
for c in "${CASES[@]}"; do
  ( bash "$RUN" "$WT" "$c" "$REPS" "$TAG" > "$SP/eval/$TAG/$c.summary" 2>&1; echo "done $c $(date +%H:%M:%S)" ) &
  running=$((running+1))
  if [ "$running" -ge "$PAR" ]; then wait -n; running=$((running-1)); fi
done
wait
echo "ALL-DONE $(date +%H:%M:%S)"
