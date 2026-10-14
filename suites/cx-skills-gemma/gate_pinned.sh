#!/bin/zsh
# Accuracy gate through the PINNED direct-gateway path (LK_AGENT_PIN default ON).
# 32 cases: the established 2/suite representative set + the two knife-edge residuals.
# Usage: ./gate_pinned.sh            Internal: ./gate_pinned.sh __one <suite> <case>
set -u
EXP_DIR="${0:A:h}"
REPO="$EXP_DIR/cx-skills-gemma31b"
SELF="${0:A}"
LOGS="$EXP_DIR/gate-pinned-logs"; DONE="$LOGS/done"

if [ "${1:-}" = "__one" ]; then
  suite=$2; case_id=$3
  marker="$DONE/${suite}__${case_id}"
  [ -f "$marker" ] && { echo "skip $suite/$case_id (done)"; exit 0; }
  cd "$REPO"
  SCENARIO_TASK="$suite" SCENARIO_CASE="$case_id" \
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
  "currency livekit_currency_aed_dirhams_monthly"
  "currency livekit_currency_ambiguous_dollars_then_cad"
  "choice choice_country_code_uk"
  "choice choice_airline_noisy_nearest_configured_choice"
  "dob field_dob_optional_no_time"
  "dob field_dob_wait_then_resume_and_complete"
  "address field_country_bad_transcript_united_states"
  "address field_country_city_name_does_not_infer"
  "contact_screening call_opening_target_answers_good"
  "contact_screening call_opening_target_asks_who_is_calling"
  "boolean boolean_us_yes_consent"
  "boolean boolean_us_no_is_valid"
  "email field_email_audio_modality_spoken_gmail"
  "email field_email_spell_then_success"
  "phone phone_us_local_readback_saves_e164"
  "phone phone_india_local_adds_country_code"
  "number number_integer_guest_count"
  "number number_spoken_words_age"
  "dtmf livekit_dtmf_confirmation_required"
  "dtmf livekit_dtmf_hinglish_confirmation"
  "credit_card livekit_credit_card_number_sensitive_repeat"
  "credit_card livekit_credit_card_number_hinglish_sensitive_repeat"
  "confirm_known_values confirm_all_correct_uk_audio"
  "confirm_known_values confirm_email_wrong_audio"
  "datetime field_datetime_us_full_future"
  "datetime field_datetime_date_then_time"
  "name name_wait_then_resume_and_complete"
  "name name_spelling_correction"
  "text livekit_text_appointment_number_spoken_punctuation"
  "text livekit_text_career_goal_preserves_role_and_salary"
  "phone phone_multiple_group_replacements"
  "contact_screening call_opening_target_busy_callback_requires_time"
)

printf '%s\n' "${CASES[@]}" | xargs -P "$PARALLEL" -L1 sh -c '"$0" __one $1 $2' "$SELF"
echo "=== GATE SWEEP DONE $(date +%H:%M:%S) ==="
grep -l "rc=0" "$LOGS"/*.log | wc -l | xargs echo "rc=0 logs:"
