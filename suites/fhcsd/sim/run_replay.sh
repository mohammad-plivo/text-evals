#!/bin/bash
# Replay the 18 real Hunter personas in the sim. args: <repo-dir> <outdir-suffix> [repeats] [jobs]
set -u
REPO="$1"; TAG="$2"; REP="${3:-3}"; JOBS="${4:-3}"
ENVF="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized/services/plivo-cx-livekit/.env"
SIM="$(pwd)"; OUT="$SIM/out/replay-$TAG"; mkdir -p "$OUT"; touch "$OUT/exits.txt"
export REPO ENVF SIM OUT REP
cd "$REPO" || exit 1
echo "arm=$TAG sha=$(git rev-parse --short HEAD) repeats=$REP"
ls "$SIM/hunter-replay" | grep -vxF -f <(awk '$1==0{print $2}' "$OUT/exits.txt") \
 | xargs -P "$JOBS" -I{} bash -c '
     mkdir -p "$OUT/$1"; cp -R "$SIM/hunter-replay/$1/." "$OUT/$1/"
     uv run --no-sync python -m src.simulation.cli run "$OUT/$1" --scenario "$1" --repeat "$REP" --no-open \
       --env-file "$ENVF" > "$OUT/$1/run.log" 2>&1
     echo "$? $1" >> "$OUT/exits.txt"' _ {}
echo "DONE $TAG: $(awk '"'"'$1==0'"'"' "$OUT/exits.txt" | wc -l | tr -d " ")/18 ok"
