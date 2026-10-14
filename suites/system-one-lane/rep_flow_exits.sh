#!/bin/bash
# Repeats of chosen callers on one product commit, to tell chance from change: the same scratch lane tree as ab_flow_exits.sh.
#   rep_flow_exits.sh <product rev> <arm name> <tag> <repeats> <scenario> [scenario ...]
set -uo pipefail
V="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev"
LANE="$V/s1-thin-audit/lane"
export LANE_TREE="$V/s1-flowexits-lane" S1_DUMP_ASKS=1
PY="$LANE_TREE/.venv/bin/python"
REV="$1"; ARM="$2"; TAG="$3"; REPEAT="$4"; shift 4
cd "$V" || exit 1
git -C "$LANE_TREE" checkout -q --detach "$REV" && git -C "$LANE_TREE" apply --index "$LANE/lane-only-simulator.patch" || { echo "lane tree: cannot move to $REV"; exit 1; }
commit=$(git -C "$LANE_TREE" commit-tree "$(git -C "$LANE_TREE" write-tree)" -p HEAD -m "lane only: the text-lane simulator patch on $REV (scratch, never pushed)")
git -C "$LANE_TREE" update-ref --no-deref HEAD "$commit"
echo "== repeats $ARM: product $REV, lane commit $commit, $(date '+%H:%M:%S')"
"$PY" "$LANE/s1_lane.py" run --main-shaped --campaign "s1-fx-$ARM-$TAG-rep" --campaign-cap 20 --run-usd 1.0 --max-parallel 4 --timeout 540 \
  --repeat "$REPEAT" --only "$@" 2>&1 | tail -n 3
echo "== repeats $ARM done $(date '+%H:%M:%S')"
