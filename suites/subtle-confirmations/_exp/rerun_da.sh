#!/bin/zsh
ROOT="${0:A:h}/.."
for t in datetime address; do
  echo ">>>> $t  $(date '+%H:%M:%S')"
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "notag" ) || echo "  !! $t nonzero"
done
echo "==== DA DONE ===="
