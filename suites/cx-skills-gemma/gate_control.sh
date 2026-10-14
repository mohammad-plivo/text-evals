#!/bin/zsh
# Accuracy gate through the PINNED direct-gateway path (CONTROL: LK_AGENT_PIN=0).
# 32 cases: the established 2/suite representative set + the two knife-edge residuals.
# Usage: ./gate_pinned.sh            Internal: ./gate_pinned.sh __one <suite> <case>
set -u
EXP_DIR="${0:A:h}"
REPO="$EXP_DIR/cx-skills-gemma31b"
SELF="${0:A}"
LOGS="$EXP_DIR/gate-control-logs"; DONE="$LOGS/done"

if [ "${1:-}" = "__one" ]; then
  suite=$2; case_id=$3
  marker="$DONE/${suite}__${case_id}"
  [ -f "$marker" ] && { echo "skip $suite/$case_id (done)"; exit 0; }
  cd "$REPO"
  LK_AGENT_PIN=0 SCENARIO_TASK="$suite" SCENARIO_CASE="$case_id" \
    .venv/bin/python -m pytest tests/test_task.py -q \
    > "$LOGS/${suite}__${case_id}.log" 2>&1
  rc=$?
  echo "rc=$rc" >> "$LOGS/${suite}__${case_id}.log"
  touch "$marker"
  echo "done $suite/$case_id rc=$rc"
  exit 0
fi

mkdir -p "$LOGS" "$DONE"
PARALLEL="${PARALLEL:-4}"
source "$EXP_DIR/run_env.sh" || exit 1

CASES=(
  "dob field_dob_wait_then_resume_and_complete"
  "email field_email_spell_then_success"
  "phone phone_us_local_readback_saves_e164"
  "datetime field_datetime_date_then_time"
  "name name_wait_then_resume_and_complete"
  "contact_screening call_opening_target_asks_who_is_calling"
  "boolean boolean_us_yes_consent"
  "credit_card livekit_credit_card_number_sensitive_repeat"
  "address field_country_bad_transcript_united_states"
  "text livekit_text_appointment_number_spoken_punctuation"
)

printf '%s\n' "${CASES[@]}" | xargs -P "$PARALLEL" -L1 sh -c '"$0" __one $1 $2' "$SELF"
echo "=== GATE SWEEP DONE $(date +%H:%M:%S) ==="
grep -l "rc=0" "$LOGS"/*.log | wc -l | xargs echo "rc=0 logs:"
