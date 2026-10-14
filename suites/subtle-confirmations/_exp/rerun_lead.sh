#!/bin/zsh
ROOT="${0:A:h}/.."
for t in currency number; do
  echo ">>>> $t  $(date '+%H:%M:%S')"
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "lead" ) || echo "  !! $t nonzero"
done
echo "==== LEAD RERUN DONE ===="
