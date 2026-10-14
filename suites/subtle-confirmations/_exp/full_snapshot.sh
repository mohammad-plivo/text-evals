#!/bin/zsh
# Full production-state runs of the suites not already fresh today (subtle 7 already current).
ROOT="${0:A:h}/.."
for t in email phone credit_card dob name datetime confirm_known_values contact_screening; do
  echo ">>>> SUITE $t  $(date '+%H:%M:%S')"
  ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "snapshot" ) || echo "  !! $t nonzero"
done
echo "==== FULL SNAPSHOT DONE $(date '+%H:%M:%S') ===="
