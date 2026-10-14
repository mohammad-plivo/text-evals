#!/bin/zsh
# Re-judge an existing run_live board with the current judge.py (verify pass included), into <dir>-rejudged.
#   rejudge.sh <board dir> <payloads dir> <env file> [tree]
set -u
D="$1"; P="$2"; E="$3"; TREE="${4:-/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/repo-dev}"
HERE="${0:A:h}"; OUT="${D}-rejudged"; mkdir -p "$OUT"
python3 - "$D" "$P" > "$OUT/pairs.txt" <<'PY'
import json,sys,os,glob
board=json.load(open(os.path.join(sys.argv[1],"board.json")))
sys.path.insert(0, os.path.dirname(os.path.abspath(os.environ.get("SIMFH","/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals/sim-fh/judge.py"))))
from build_live_twins import slug_of
ids={slug_of(json.load(open(f))["payload"]["event"]): f for f in glob.glob(os.path.join(sys.argv[2],"*.json")) if os.path.basename(f)[0].isdigit()}
for slug,res in board.items():
    if res.get("report") and slug in ids: print(res["report"], "\t", ids[slug])
PY
n=0
while IFS=$'\t' read -r report payload; do
  report="${report## }"; report="${report%% }"; payload="${payload## }"; payload="${payload%% }"
  ( cd "$TREE" && .venv/bin/python "$HERE/judge.py" --report "$report" --hunter "$payload" --out "$OUT" --env-file "$E" ) >> "$OUT/judge.log" 2>&1
  n=$((n+1))
done < "$OUT/pairs.txt"
echo "re-judged $n twins -> $OUT"
