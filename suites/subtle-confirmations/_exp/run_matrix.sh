#!/bin/zsh
# Temperature-vs-prompt 2x2 experiment driver.
# Cells: prompt in {W=50e77db wordy/humanized-v5, C=HEAD crisp} x temp in {0.3, 0.7}.
# Isolates the two changes made after Venky's "still bad": temp 0.3->0.7 AND crisp de-scaffolding.
# Runs SERIALLY in the main tree, flipping only tasks/ via git checkout + temp via env.
# Records per-cell [since, until] windows to _exp/windows.txt for the scorer.
set -e
ROOT="${0:A:h}/.."          # subtle tasks/
SB="$ROOT/cx-skills-subtle"
TASKS="choice text currency"
WIN="$ROOT/_exp/windows.txt"
: > "$WIN"
cd "$SB"

restore() { git checkout HEAD -- tasks/ 2>/dev/null || true; }
trap restore EXIT INT TERM

run_cell() {  # $1=git-ref  $2=temp  $3=label
  local ref="$1" temp="$2" label="$3"
  git checkout "$ref" -- tasks/
  export LK_AGENT_TEMP="$temp"
  local since; since="$(date '+%Y-%m-%d %H:%M:%S')"
  echo ">>> CELL $label  (prompt=$ref temp=$temp)  since=$since"
  for t in ${(z)TASKS}; do
    ( cd "$ROOT" && ./run_task.sh "$t" 10 5 "exp_${label}_${t}" ) || echo "  !! $t sweep nonzero"
  done
  local until; until="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "${label}|${temp}|${ref}|${since}|${until}" >> "$WIN"
  echo "<<< CELL $label done  until=$until"
}

# Order: reproduce the original bad, then the temp-only fix (the user's hypothesis),
# then current good, then prompt-only-at-low-temp.
run_cell 50e77db 0.3 W03
run_cell 50e77db 0.7 W07
run_cell HEAD    0.7 C07
run_cell HEAD    0.3 C03

restore
echo "=== MATRIX DONE ==="
cat "$WIN"
