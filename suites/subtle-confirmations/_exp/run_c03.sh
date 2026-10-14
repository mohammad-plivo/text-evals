#!/bin/zsh
set -e
ROOT="${0:A:h}/.."
cd "$ROOT/cx-skills-subtle"
git checkout HEAD -- tasks/
export LK_AGENT_TEMP=0.3
since="$(date '+%Y-%m-%d %H:%M:%S')"
for t in choice text currency; do
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "exp_C03b_${t}" ) || echo "!! $t nonzero"
done
until="$(date '+%Y-%m-%d %H:%M:%S')"
echo "C03|0.3|HEAD|${since}|${until}" >> "$ROOT/_exp/windows.txt"
echo "=== C03 DONE ==="
