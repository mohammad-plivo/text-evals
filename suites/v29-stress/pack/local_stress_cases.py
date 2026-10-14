"""Local, untracked stress cases appended to the session pack; absent in a clean checkout."""

from copy import deepcopy

from tests.v29_model_eval.session_cases import FREEZE, _offer, collect, confirm, step

# The clinic node's Task is the customer flow's prompt, so it is not stored here; paste it in to run the mt_fh_* cases.
FH_TASK = "<clinic node Task>"
FH_DOB = "Ask the patient for their date of birth."
FH_WANTS = "Ask the patient if they want to reschedule their missed appointment now."
ENDS_AFTER_DOB = (
    "For this call the walk ends after step 2: once dob_confirmed matches and you have told the patient "
    "about the missed appointment, submit dob_confirmed once."
)
ENDS_AFTER_WANTS = (
    "For this call the walk ends after step 3: once wants_to_reschedule is collected, "
    "submit dob_confirmed and wants_to_reschedule once."
)
ASKS_RESCHEDULE = ["reschedul", "book", "move", "new appointment", "new time"]
# a dob re-ask, or a read-back question of the stated February 19th; bare "19" would also match the year 1977
REASKS_DOB_OR_FEB_19 = [["birth", "date", "19,", "19 ", "19th", "19?", "19.", "nineteenth"], ["birth", "date", "february"]]


def fh_task(last):
    return f"{FREEZE} {FH_TASK}\n\n{last}"


def at(field, authored, offers=None):
    """A caller step owned by `field`'s collector, with its authored provenance."""
    return {**authored, "active_field": field, "offers": offers or {}}


def dob(year, month, day, gate="immediate"):
    return {"dob_confirmed": _offer(f"{year}-{month:02d}-{day:02d}", gate, "update_dob", {"year": year, "month": month, "day": day})}


YES = _offer("yes", "immediate", "update_boolean_answer", {"value": True})


STRESS_CASES: list[dict] = []

# dob uses the state shape and Task step 1's ask-once-more makes the correction a re-ask; the true read-back cell is not reachable on this dob
# the read-back of the caller's own corrected date is intended: the secrecy rule covers the date on file, not the patient's words
STRESS_CASES.append({
    "id": "mt_fh_dob_correct_on_reask",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [
        collect("dob_confirmed", "dob", FH_DOB),
        collect("dob_confirmed", "dob", FH_DOB),
        collect("wants_to_reschedule", "boolean", FH_WANTS),
    ],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February nineteenth, nineteen seventy-seven."), dob(1977, 2, 19)),
        at("dob_confirmed", step(["birth", "date"], "No, it's the eighteenth, February eighteenth nineteen seventy-seven."),
           dob(1977, 2, 18, "confirm")),
        at("dob_confirmed", confirm([["1977-02-18"]], "Yes, that's right.", "dob_confirmed", "1977-02-18")),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

# the read-back of the caller's own corrected date is intended: the secrecy rule covers the date on file, not the patient's words
STRESS_CASES.append({
    "id": "mt_fh_dob_two_corrections",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [
        collect("dob_confirmed", "dob", FH_DOB),
        collect("dob_confirmed", "dob", FH_DOB),
        collect("wants_to_reschedule", "boolean", FH_WANTS),
    ],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February nineteenth, nineteen seventy-eight."), dob(1978, 2, 19)),
        at("dob_confirmed", {"requires_text_all": REASKS_DOB_OR_FEB_19, "reply": "No, sorry, the eighteenth. February eighteenth, nineteen seventy-eight."},
           dob(1978, 2, 18, "confirm")),
        at("dob_confirmed", {"requires_text_all": [["1978-02-18"]], "reply": "No, wait, the year is nineteen seventy-seven."},
           dob(1977, 2, 18, "confirm")),
        at("dob_confirmed", confirm([["1977-02-18"]], "Yes, that's right.", "dob_confirmed", "1977-02-18")),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

# the dob collector answers "why" itself and re-asks; a hand_back here reads as an unexpected tool (lane ceiling)
STRESS_CASES.append({
    "id": "mt_fh_dob_question_instead",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [collect("dob_confirmed", "dob", FH_DOB), collect("wants_to_reschedule", "boolean", FH_WANTS)],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "Why do you need my birthday?")),
        at("dob_confirmed", step(["birth", "date"], "Okay. It's February eighteenth, nineteen seventy-seven."), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

STRESS_CASES.append({
    "id": "mt_fh_dob_angry_with_value",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [collect("dob_confirmed", "dob", FH_DOB), collect("wants_to_reschedule", "boolean", FH_WANTS)],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(
            ["birth", "date"],
            "I already told the last person, it's February eighteenth nineteen seventy-seven, this is ridiculous.",
        ), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

STRESS_CASES.append({
    "id": "mt_fh_dob_partial_then_complete",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [collect("dob_confirmed", "dob", FH_DOB), collect("wants_to_reschedule", "boolean", FH_WANTS)],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February eighteenth.")),
        at("dob_confirmed", step(["year"], "Nineteen seventy-seven."), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

# the brief's "seventy-seven" is spoken in full: collect_dob may either ask or infer a two-digit year, not this cell
# a wire failure on a null known_value for collect_boolean is triaged as a lane ceiling (vocabulary ceiling)
STRESS_CASES.append({
    "id": "mt_fh_dob_two_values_one_breath",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [
        collect("dob_confirmed", "dob", FH_DOB),
        collect("wants_to_reschedule", "boolean", FH_WANTS, known_value="yes"),
    ],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February eighteenth, nineteen seventy-seven, and yes, I want to reschedule."), {
            **dob(1977, 2, 18),
            "wants_to_reschedule": {**YES, "known_value_any": ["yes", "Yes", "true"]},
        }),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

# a hand_back failure here is triaged as a lane ceiling: collect_boolean's prompt names answer_side_question, which V2.9 collectors lack
STRESS_CASES.append({
    "id": "mt_fh_reschedule_question_instead",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [collect("dob_confirmed", "dob", FH_DOB), collect("wants_to_reschedule", "boolean", FH_WANTS)],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February eighteenth, nineteen seventy-seven."), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "How long will this take?")),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

STRESS_CASES.append({
    "id": "mt_fh_reschedule_angry_yes",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": {"dob_confirmed": FH_DOB, "wants_to_reschedule": FH_WANTS},
    "collect_calls": [collect("dob_confirmed", "dob", FH_DOB), collect("wants_to_reschedule", "boolean", FH_WANTS)],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February eighteenth, nineteen seventy-seven."), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes, obviously, that's why I'm still on the phone."),
           {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})


# step 2: preferred_start_date and selected_slot
FH_DATE = "Ask the patient for the earliest date that works for them (optional)."
FH_SLOT = "Ask the patient which of the open appointment options they want to choose."
FH_BOOK = "Ask the patient for a yes or no on the whole booking."  # model-named: the dev node has no such Input
SLOTS = [
    "Tuesday, September 15, 2026 at 9:30 AM with Dr. Rismiller at Logan Heights Family Health Center",
    "Wednesday, September 16, 2026 at 11:00 AM with Dr. Rismiller at Logan Heights Family Health Center",
    "Thursday, September 17, 2026 at 3:45 PM with Dr. Rismiller at Logan Heights Family Health Center",
]
TUE, WED, THU = SLOTS
_SHAPES = {
    "dob_confirmed": ("dob", FH_DOB, {}),
    "wants_to_reschedule": ("boolean", FH_WANTS, {}),
    "preferred_start_date": ("date", FH_DATE, {}),
    "selected_slot": ("choice", FH_SLOT, {"choices": SLOTS, "options": {"multiple": False, "present_options": True}}),
    "booking_confirmed": ("boolean", FH_BOOK, {}),
}
ASKS_DATE = ["date", "day", "earliest", "when"]
ASKS_SLOT = ["tuesday", "wednesday", "thursday", "option"]
ASKS_BOOKING = ["book", "confirm", "go ahead"]
ENDS_AFTER_DATE = (
    "For this call the walk ends after step 4: once preferred_start_date is collected, "
    "submit dob_confirmed, wants_to_reschedule and preferred_start_date once."
)
ENDS_AFTER_SLOT = (
    "For this call the walk ends after step 6: once selected_slot is collected, submit dob_confirmed, "
    "wants_to_reschedule, preferred_start_date (only if the patient gave one) and selected_slot once."
)
ENDS_AFTER_BOOKING = (
    "For this call the walk ends after step 7: once booking_confirmed is collected, submit dob_confirmed, "
    "wants_to_reschedule, preferred_start_date, selected_slot and booking_confirmed once."
)


def fh_fields(*names):
    return {name: _SHAPES[name][1] for name in names}


def fh_call(name, known_value=None):
    task_type, instructions, extra = _SHAPES[name]
    return collect(name, task_type, instructions, known_value=known_value, **deepcopy(extra))


def on_date(year, month, day, gate="immediate", spoken=()):
    iso = f"{year}-{month:02d}-{day:02d}"
    return {"preferred_start_date": _offer(
        iso, gate, "update_date", {"year": year, "month": month, "day": day},
        known_value_any=[iso, *spoken] if spoken else None,
    )}


def on_slot(label, gate="immediate", spoken=()):
    return {"selected_slot": _offer(
        label, gate, "update_choice", {"choice": label}, known_value_any=[label, *spoken] if spoken else None,
    )}


def verified_and_yes():
    """Steps 1 and 3 answered plainly: the date of birth on file, then yes to rescheduling."""
    return [
        at("dob_confirmed", step(["birth", "date"], "February eighteenth, nineteen seventy-seven."), dob(1977, 2, 18)),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ]

# "no preference" is no usable date on an optional field: the retry limit is one turn, so the decline is input_not_provided
# lane ceiling: the lane drops collection.instructions, so the collector never sees dev's "(optional)" note
STRESS_CASES.append({
    "id": "mt_fh_date_no_preference",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"),
                      fh_call("preferred_start_date"), fh_call("selected_slot")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "Whatever works, I don't have a preference.")),
        at("selected_slot", step(ASKS_SLOT, "The Wednesday one."), on_slot(WED)),
    ],
    "forbidden_store": ["preferred_start_date"],
    "required_special": {"name": "decline_date_time_capture", "arguments": {"reason": "input_not_provided"}},
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "selected_slot": WED},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "selected_slot": WED},
})

# dev saves present_options true while Task step 5 has the parent read the options; the fixer ruled false (console change for MK), so this tests that and the original tests dev today
STRESS_CASES.append({
    "id": "mt_fh_date_no_preference_present_off",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      {**fh_call("selected_slot"), "options": {"multiple": False, "present_options": False}}],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "Whatever works, I don't have a preference.")),
        at("selected_slot", step(ASKS_SLOT, "The Wednesday one."), on_slot(WED)),
    ],
    "forbidden_store": ["preferred_start_date"],
    "required_special": {"name": "decline_date_time_capture", "arguments": {"reason": "input_not_provided"}},
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "selected_slot": WED},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "selected_slot": WED},
})

STRESS_CASES.append({
    "id": "mt_fh_date_bare_day_ahead",
    "instructions": fh_task(ENDS_AFTER_DATE),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "The 15th."), on_date(2026, 9, 15)),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-15"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-15"},
})

STRESS_CASES.append({
    "id": "mt_fh_date_bare_day_passed",
    "instructions": fh_task(ENDS_AFTER_DATE),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "The 3rd."), on_date(2026, 10, 3)),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-10-03"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-10-03"},
})

# one breath, as the brief quotes it: only the last date may reach update_date, and the state shape reads nothing back
STRESS_CASES.append({
    "id": "mt_fh_date_self_repair_one_breath",
    "instructions": fh_task(ENDS_AFTER_DATE),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "The 15th... no, the 16th... actually, the 17th."), on_date(2026, 9, 17)),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-17"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-17"},
})

# run 242b6165 stored October 15; "September 15th" also sits in option 1's label; only change_earlier_value is authored, a hand_back and a re-entered collect_date read as unexpected
STRESS_CASES.append({
    "id": "mt_fh_slot_overlap_trap",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      fh_call("selected_slot"), fh_call("selected_slot")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "October fifteenth."), on_date(2026, 10, 15)),
        at("selected_slot", step(ASKS_SLOT, "No. September 15th."), on_date(2026, 9, 15, "confirm", spoken=(
            "September 15th", "September 15", "September 15, 2026", "September 15th, 2026",
        ))),
        # token groups, not the ISO date: the date read-back matcher rejects a line that also names October
        at("preferred_start_date", confirm([["september"], ["15", "fifteenth"], ["2026"]], "Yes, that's right.",
                                           "preferred_start_date", "2026-09-15")),
        at("selected_slot", step(ASKS_SLOT, "The Wednesday one."), on_slot(WED)),
    ],
    "required_special": {"name": "change_earlier_value",
                         "arguments": {"name": "preferred_start_date", "new_value": "2026-09-15"}},
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                        "preferred_start_date": "2026-09-15", "selected_slot": WED},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                         "preferred_start_date": "2026-09-15", "selected_slot": WED},
})

# V2.9 collectors carry no answer_side_question: the choice collector re-reads the options itself; a hand_back is a lane ceiling
STRESS_CASES.append({
    "id": "mt_fh_slot_question_instead",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      fh_call("selected_slot")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "September fifteenth."), on_date(2026, 9, 15)),
        at("selected_slot", step(ASKS_SLOT, "Sorry, what were the options again?")),
        at("selected_slot", {"requires_text_all": [["tuesday"], ["wednesday"], ["thursday"]], "reply": "The Thursday one."},
           on_slot(THU)),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                        "preferred_start_date": "2026-09-15", "selected_slot": THU},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                         "preferred_start_date": "2026-09-15", "selected_slot": THU},
})

# reaches step 7: booking_confirmed is model-named on dev; no booking turn is authored, so a double ask leaves it unstored
# a wire failure on a null known_value for collect_boolean is triaged as a lane ceiling (vocabulary ceiling)
STRESS_CASES.append({
    "id": "mt_fh_slot_two_values_one_breath",
    "instructions": fh_task(ENDS_AFTER_BOOKING),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot", "booking_confirmed"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      fh_call("selected_slot"), fh_call("booking_confirmed", known_value="yes")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "September fifteenth."), on_date(2026, 9, 15)),
        at("selected_slot", step(ASKS_SLOT, "The Tuesday one, and yes, go ahead and book it."), {
            **on_slot(TUE),
            "booking_confirmed": {**YES, "known_value_any": ["yes", "Yes", "true"]},
        }),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-15",
                        "selected_slot": TUE, "booking_confirmed": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-15",
                         "selected_slot": TUE, "booking_confirmed": "yes"},
})

# the 21st sits in no option label, so the correction can only target the date field; only change_earlier_value is authored
STRESS_CASES.append({
    "id": "mt_fh_slot_correct_prev_field_non_overlap",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      fh_call("selected_slot"), fh_call("selected_slot")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "September sixteenth."), on_date(2026, 9, 16)),
        at("selected_slot", step(ASKS_SLOT, "Sorry, my date should be the 21st."), on_date(
            2026, 9, 21, "confirm",
            spoken=("the 21st", "21st", "September 21", "September 21st", "September 21, 2026", "September 21st, 2026"),
        )),
        at("preferred_start_date", confirm([["2026-09-21"]], "Yes, that's right.", "preferred_start_date", "2026-09-21")),
        at("selected_slot", step(ASKS_SLOT, "The Thursday one."), on_slot(THU)),
    ],
    "required_special": {"name": "change_earlier_value",
                         "arguments": {"name": "preferred_start_date", "new_value": "2026-09-21"}},
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                        "preferred_start_date": "2026-09-21", "selected_slot": THU},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                         "preferred_start_date": "2026-09-21", "selected_slot": THU},
})


# step 3: booking_confirmed and the full walk
WALK = ("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot", "booking_confirmed")


def booked(slot):
    return {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-09-15",
            "selected_slot": slot, "booking_confirmed": "yes"}


def dated_and_chosen(label, reply):
    """Steps 4 and 6 answered plainly after verified_and_yes: September 15, then one slot."""
    return [
        at("preferred_start_date", step(ASKS_DATE, "September fifteenth."), on_date(2026, 9, 15)),
        at("selected_slot", step(ASKS_SLOT, reply), on_slot(label)),
    ]


# reaches step 7: booking_confirmed is model-named on dev; the maybe turn carries no offer, so any update or store from it fails
STRESS_CASES.append({
    "id": "mt_fh_booking_maybe_then_yes",
    "instructions": fh_task(ENDS_AFTER_BOOKING),
    "fields": fh_fields(*WALK),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call(name) for name in WALK],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        *dated_and_chosen(TUE, "The Tuesday one."),
        at("booking_confirmed", step(ASKS_BOOKING, "Hmm, maybe.")),
        at("booking_confirmed", step([*ASKS_BOOKING, "yes or no", "appointment"], "Yes, book it."), {"booking_confirmed": YES}),
    ],
    "expected_values": booked(TUE),
    "submit_arguments": booked(TUE),
})

# reaches step 7: booking_confirmed is model-named on dev; the regex holds the correction to a read-back, not the option list again
# an abort on "maximum model requests exceeded" here is a harness result (the 30-request budget), not a model result
STRESS_CASES.append({
    "id": "mt_fh_booking_change_slot",
    "instructions": fh_task(ENDS_AFTER_BOOKING),
    "fields": fh_fields(*WALK),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [*(fh_call(name) for name in WALK), fh_call("booking_confirmed")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        *dated_and_chosen(TUE, "The Tuesday one."),
        at("booking_confirmed", step(ASKS_BOOKING, "Wait, make it the Thursday one instead."),
           on_slot(THU, "confirm", spoken=("Thursday", "the Thursday one"))),
        at("selected_slot", confirm([["thursday"], ["17", "seventeenth"]], "Yes, that's right.", "selected_slot", THU,
                                    regexes=[r"(?s)^(?!.*wednesday)"])),
        at("booking_confirmed", step(ASKS_BOOKING, "Yes, book it."), {"booking_confirmed": YES}),
    ],
    "required_special": {"name": "change_earlier_value", "arguments": {"name": "selected_slot", "new_value": THU}},
    "expected_values": booked(THU),
    "submit_arguments": booked(THU),
})

# reaches step 7: booking_confirmed is model-named on dev; one booking turn only, so a re-ask leaves it unstored
STRESS_CASES.append({
    "id": "mt_fh_booking_angry_yes",
    "instructions": fh_task(ENDS_AFTER_BOOKING),
    "fields": fh_fields(*WALK),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call(name) for name in WALK],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        *dated_and_chosen(WED, "The Wednesday one."),
        at("booking_confirmed", step(ASKS_BOOKING, "Yes, just book it already."), {"booking_confirmed": YES}),
    ],
    "expected_values": booked(WED),
    "submit_arguments": booked(WED),
})

# reaches step 7: booking_confirmed is model-named on dev; the control, every field answered plainly in Task order
STRESS_CASES.append({
    "id": "mt_fh_full_walk_happy",
    "instructions": fh_task(ENDS_AFTER_BOOKING),
    "fields": fh_fields(*WALK),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call(name) for name in WALK],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        *dated_and_chosen(TUE, "Option one, please."),
        at("booking_confirmed", step(ASKS_BOOKING, "Yes."), {"booking_confirmed": YES}),
    ],
    "expected_values": booked(TUE),
    "submit_arguments": booked(TUE),
})

# dob slips as mt_fh_dob_correct_on_reask, then the walk carries on through wants_to_reschedule; the slot change is mt_fh_booking_change_slot
# the read-back of the caller's own corrected date is intended: the secrecy rule covers the date on file, not the patient's words
STRESS_CASES.append({
    "id": "mt_fh_dob_slip_through_reschedule",
    "instructions": fh_task(ENDS_AFTER_WANTS),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule"),
    "collect_calls": [fh_call("dob_confirmed"), fh_call("dob_confirmed"), fh_call("wants_to_reschedule")],
    "initial_offers": {},
    "caller_steps": [
        at("dob_confirmed", step(["birth", "date"], "February nineteenth, nineteen seventy-seven."), dob(1977, 2, 19)),
        at("dob_confirmed", {"requires_text_all": REASKS_DOB_OR_FEB_19, "reply": "No, it's the eighteenth, February eighteenth nineteen seventy-seven."},
           dob(1977, 2, 18, "confirm")),
        at("dob_confirmed", confirm([["1977-02-18"]], "Yes, that's right.", "dob_confirmed", "1977-02-18")),
        at("wants_to_reschedule", step(ASKS_RESCHEDULE, "Yes."), {"wants_to_reschedule": YES}),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes"},
})

# the 22nd arrives while the slot collector is active (change_earlier_value), the 23rd at that correction's read-back; neither day is in an option label; about 25 requests
STRESS_CASES.append({
    "id": "mt_fh_date_two_corrections_multi_turn",
    "instructions": fh_task(ENDS_AFTER_SLOT),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date", "selected_slot"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date"),
                      fh_call("selected_slot"), fh_call("selected_slot")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "The 15th."), on_date(2026, 9, 15)),
        at("selected_slot", step(ASKS_SLOT, "No, the 22nd."), on_date(
            2026, 9, 22, "confirm",
            spoken=("the 22nd", "22nd", "September 22", "September 22nd", "September 22, 2026", "September 22nd, 2026"),
        )),
        at("preferred_start_date", {"requires_text_all": [["2026-09-22"]], "reply": "Actually, the 23rd."},
           on_date(2026, 9, 23, "confirm",
                   spoken=("the 23rd", "23rd", "September 23", "September 23rd", "September 23, 2026", "September 23rd, 2026"))),
        at("preferred_start_date", confirm([["2026-09-23"]], "Yes, that's right.", "preferred_start_date", "2026-09-23")),
        at("selected_slot", step(ASKS_SLOT, "The Thursday one."), on_slot(THU)),
    ],
    "required_special": {"name": "change_earlier_value",
                         "arguments": {"name": "preferred_start_date", "new_value": "2026-09-22"}},
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                        "preferred_start_date": "2026-09-23", "selected_slot": THU},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes",
                         "preferred_start_date": "2026-09-23", "selected_slot": THU},
})

# "the 31st" on the 2026-09-09 clock: September has no 31st, so the next month that has the day (date_hints.day_only_date)
STRESS_CASES.append({
    "id": "mt_fh_date_bare_day_31st",
    "instructions": fh_task(ENDS_AFTER_DATE),
    "fields": fh_fields("dob_confirmed", "wants_to_reschedule", "preferred_start_date"),
    "optional_fields": ["preferred_start_date"],
    "collect_calls": [fh_call("dob_confirmed"), fh_call("wants_to_reschedule"), fh_call("preferred_start_date")],
    "initial_offers": {},
    "caller_steps": [
        *verified_and_yes(),
        at("preferred_start_date", step(ASKS_DATE, "The 31st."), on_date(2026, 10, 31)),
    ],
    "expected_values": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-10-31"},
    "submit_arguments": {"dob_confirmed": "1977-02-18", "wants_to_reschedule": "yes", "preferred_start_date": "2026-10-31"},
})
