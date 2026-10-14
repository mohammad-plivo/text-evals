#!/bin/bash
# Text A/B for the 9 Oct change (an AI node asks no core question): old commit, then new, on one scratch lane tree.
#   ab_flow_exits.sh <old product rev> <new product rev> <tag>
# Per arm: the 48 FHCSD callers once, then the five targeted callers three times. 4 in parallel, Jev requests dumped.
set -uo pipefail
V="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev"
LANE="$V/s1-thin-audit/lane"
export LANE_TREE="$V/s1-flowexits-lane" S1_DUMP_ASKS=1
PY="$LANE_TREE/.venv/bin/python"
PATCH="$LANE/lane-only-simulator.patch"
OLD="$1"; NEW="$2"; TAG="$3"
cd "$V" || exit 1

arm() {  # product rev, arm name
  git -C "$LANE_TREE" checkout -q --detach "$1" && git -C "$LANE_TREE" apply --index "$PATCH" || { echo "lane tree: cannot move to $1"; exit 1; }
  local commit; commit=$(git -C "$LANE_TREE" commit-tree "$(git -C "$LANE_TREE" write-tree)" -p HEAD -m "lane only: the text-lane simulator patch on $1 (scratch, never pushed)")
  git -C "$LANE_TREE" update-ref --no-deref HEAD "$commit"
  echo "== arm $2: product $1, lane commit $commit, $(date '+%H:%M:%S')"
  "$PY" "$LANE/s1_lane.py" run --main-shaped --campaign "s1-fx-$2-$TAG" --campaign-cap 20 --run-usd 1.0 --max-parallel 4 --timeout 540 \
    --only $(ls "$V/text-evals/text-lane/pack") 2>&1 | tail -n 3
  "$PY" "$LANE/s1_lane.py" run --main-shaped --pack "$LANE/pack-flow-exits" --campaign "s1-fx-$2-$TAG-t" --campaign-cap 20 --run-usd 1.0 \
    --max-parallel 4 --timeout 540 --repeat 3 --only $(ls "$LANE/pack-flow-exits") 2>&1 | tail -n 3
  echo "== arm $2 done $(date '+%H:%M:%S')"
}

[ "$OLD" = - ] || arm "$OLD" old   # "-" skips the old arm; a fourth argument names the new one
arm "$NEW" "${4:-new}"
