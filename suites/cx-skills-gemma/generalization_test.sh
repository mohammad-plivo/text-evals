#!/bin/zsh
# Does V2 (Gemma-tuned) preserve the PRODUCTION gpt-4.1 model on the hard cases?
# Runs each hard case under gpt-4.1 (temp 0.7 = the repo's gpt-4.1 setting) with BOTH
# V1 (baseline ec8b057) and V2 (HEAD) prompts. 2 rounds each. Prompts are the only thing swapped.
set -u
EXP_DIR="${0:A:h}"; REPO="$EXP_DIR/cx-skills-gemma31b"
LOG="$EXP_DIR/baseline-logs/gpt41-generalization"; mkdir -p "$LOG"
source "$EXP_DIR/run_env.sh" >/dev/null || exit 1
export LK_AGENT_AZURE=1 LK_AGENT_MODEL=gpt-4.1 LK_AGENT_TEMP=0.7
cd "$REPO"

# Hard cases chosen to stress the RISKIEST tweaks (bucket B/C), one per touched suite:
typeset -A CASES
CASES[datetime]="livekit_datetime_this_friday_reference_week,livekit_datetime_next_friday_following_week"
CASES[name]="name_mononym_with_spelling_completes"
CASES[phone]="phone_us_too_many_digits_challenged,phone_partial_last_digit_correction_after_readback"
CASES[currency]="livekit_currency_negative_amount_then_corrected"
CASES[email]="field_email_zoho_provider_alias"
CASES[boolean]="boolean_known_value_opens_with_readback"

run_ver() {
  local ver=$1
  for suite in ${(k)CASES}; do
    for round in 1 2; do
      SCENARIO_TASK=$suite SCENARIO_CASE=${CASES[$suite]} \
        .venv/bin/python -m pytest tests/test_task.py -q > "$LOG/${ver}_${suite}_r${round}.log" 2>&1
      echo "$ver $suite r$round rc=$?"
    done
  done
}

echo "===== V2 (HEAD, tweaked prompts) under gpt-4.1 ====="
run_ver v2

echo "===== switch to V1 (baseline ec8b057) prompts ====="
git checkout ec8b057 -- tasks/ && echo "V1 prompts in place"
run_ver v1

echo "===== restore V2 (HEAD) prompts ====="
git checkout HEAD -- tasks/ && echo "V2 restored"
git status --short tasks/ | head
echo "=== GENERALIZATION TEST DONE ==="
