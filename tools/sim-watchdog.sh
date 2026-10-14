#!/bin/bash
# stops a simulation CLI run whose newest campaign log has not grown for STALE seconds; exits when no rerun.sh is alive
SE="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals"
STALE=60
LOG="$SE/sim-watchdog.log"
while pgrep -f "[r]erun.sh" >/dev/null 2>&1; do
  now=$(date +%s)
  for pid in $(pgrep -f "[s]imulation.cli run" 2>/dev/null || true); do
    cmd=$(ps -o command= -p "$pid" 2>/dev/null) || continue
    scen=$(echo "$cmd" | grep -o -- "--scenario [a-zA-Z0-9_-]*" | awk '{print $2}')
    ws=$(echo "$cmd" | grep -o "sim-fh/ws/[a-z-]*" | sed 's#sim-fh/ws/##')
    newest=$(ls -t "$SE"/campaign-*/lane-b/"$ws"/*${scen:+__$scen}.stderr.log 2>/dev/null | head -1)
    [ -z "$newest" ] && continue
    age=$(( now - $(stat -f %m "$newest") ))
    if [ "$age" -gt "$STALE" ]; then
      echo "$(date '+%H:%M:%S') killing pid $pid ws=$ws scenario=${scen:-all} log silent ${age}s: $newest" >> "$LOG"
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 10
done
echo "$(date '+%H:%M:%S') watchdog exit: no rerun.sh alive" >> "$LOG"
