#!/bin/zsh
ROOT="${0:A:h}/.."
for t in currency number text; do
  echo ">>>> $t  $(date '+%H:%M:%S')"
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "notag" ) || echo "  !! $t nonzero"
done
echo "==== NOTAG RERUN DONE $(date '+%H:%M:%S') ===="
