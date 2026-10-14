#!/bin/zsh
ROOT="${0:A:h}/.."
for t in choice currency number boolean text datetime address; do
  echo ">>>> $t  $(date '+%H:%M:%S')"
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "checkword" ) || echo "  !! $t nonzero"
done
echo "==== RERUN DONE $(date '+%H:%M:%S') ===="
