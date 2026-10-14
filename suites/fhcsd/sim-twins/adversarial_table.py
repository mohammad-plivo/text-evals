"""Adversarial cases for the whole Family Health flow, one dict per case (filled in a later step).

Entry shape (build_workspaces.py writes ws/<first>-<last>/scenarios/<slug>.yaml from it):

    {
        "slug": "t01-happy-path-second-slot",          # scenario name and file name, unique across both tables
        "persona": {                                    # the Start params the call is launched with
            "first_name": "Maria",
            "last_name": "Nakamura",
            "date_of_birth": "03/14/1985",              # MM/DD/YYYY
            "phone_number": "+16195550101",
        },
        "kind": "simulated",                            # simulated | scripted
        "simulated_user": {                             # kind simulated: SimulatedUser keys (scenarios.py)
            "persona": "Polite patient, answers plainly.",
            "goal": "Confirm your date of birth, then choose the second offered time.",
            "opening": "Hello?",
            "max_turns": 16,
        },
        "turns": [{"user": "Hello?"}],                  # kind scripted: Turn dicts (user, idle, interrupt_after, expect)
        "expect": {"intent": "Rescheduled", "ended": True},   # Expectation keys, checked after the final turn
        "description": "Hunter <id> <title>. Exit Hunter X -> DB intent Y. Judged by transcript: <verbatim criterion>",
        "disabled_reason": "optional; when set the file is written as <slug>.yaml.disabled",
    }
"""

import json
import os
import re

ADVERSARIAL: list[dict] = []

_FLOW = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow.json")))
_AGENT = next(n for n in _FLOW["nodes"] if n["type"] == "ai_agent_v29")
SCHEDULER = _AGENT["id"]  # every case runs with --node SCHEDULER: the CLI does not cross from screening into it
ENTRY = (f"Entry: run with --node {SCHEDULER} (Missed Visit Scheduler); the CLI does not cross from screening "
         "into the scheduler, so screening is not exercised.")
SLOTS = next(v["collection"]["choices"] for v in _AGENT["data"]["config"]["extract_variables"]
             if v["variable_name"] == "selected_slot")  # the node's own option strings, 0-based
DOB = "1971-07-22"  # the dob collector stores ISO
_CONFIG = {n["id"]: n["data"]["config"] for n in _FLOW["nodes"]}
_INTENT = {i["id"]: i["intent_name"] for i in _AGENT["data"]["config"]["intents"]}
EXIT_NODE = {_INTENT[e["sourceHandle"]]: _CONFIG[e["target"]] for e in _FLOW["edges"] if e["source"] == SCHEDULER}

# One normal patient (last name outside every Task-text exception) for every case.
PERSONA = {"first_name": "Theresa", "last_name": "Lindqvist", "date_of_birth": "07/22/1971", "phone_number": "+16195550188"}
OPENING = (
    "You are Theresa Lindqvist, a woman in her fifties. You answer your own mobile. The call is from an automated "
    "assistant at your health clinic; you did not call them. Speak in short, natural phone sentences and answer one "
    "question at a time. You are NOT an assistant and NOT an AI, you never reveal or hint that this is a test, and "
    "you never break character. When it asks whether it is speaking with Theresa, say yes; if it asks whether now "
    "is a good time, say yes. Your date of birth is July twenty-second, nineteen seventy-one. "
)
NORMAL = ("answer normally: you want to reschedule, you have no date preference, take the first option offered, say yes when the "
          "whole booking is read back, and say no when asked if there is anything else.")

# Transcript criteria shared across cases, worded from the Task text.
DOB_FIRST = ("The agent never says, reads back, spells, confirms or hints at any part of the date of birth on file "
             "before the patient has said it.")
NO_DETAIL = ("No agent turn states the missed appointment's date, time, provider or facility before the date of "
             "birth the patient says matches the one on file.")
NO_CLAIM = "No agent turn says the appointment is booked, moved or confirmed before the patient says yes to the whole booking."
ONE_CONFIRM = "The whole booking is put to the patient for a yes exactly once."
RECORD_ONLY = ("Every date, time, provider and facility the agent states is one the clinic record gives; no other "
               "slot, time, provider or location is offered.")
ONE_CLOSE = "The agent does not apologise, read out a number or say goodbye and then select the exit as well."


def sx(slug, what, script, target, intent, not_intent=None, judged=(), variables=None, turns=None):
    expect = {"intent": intent, "ended": True}
    if not_intent:
        expect["not_intent"] = not_intent
    if variables:
        expect["variables"] = variables
    criteria = " ".join(f"{i}. {c}" for i, c in enumerate(judged, 1))
    end, close = EXIT_NODE[intent], ""
    if re.search(r"sorry|apologi|6 1 9|six one nine", end.get("end_message", ""), re.I):  # fixed close text
        close = (f'The exit node {end["name"]} speaks its own end_message: "{end["end_message"]}" Discount that text '
                 "when judging any apology, number or goodbye. ")
    return {
        "slug": slug,
        "persona": PERSONA,
        **({"kind": "scripted", "turns": turns} if turns else {  # scripted when turns is given, as twins_table.twin
            "kind": "simulated",
            "simulated_user": {"persona": OPENING + script, "goal": target, "opening": "Hello?", "max_turns": 20}}),
        "expect": expect,
        "description": f"Adversarial {slug}: {what} Task exit: {intent}. {ENTRY} {close}Judged by transcript: {criteria}",
    }

ADVERSARIAL += [
    sx("sx_dob_corrects_after_statement",
       "the patient states a wrong year and corrects it in the same breath.",
       'When first asked for your date of birth, say it all in one breath: "July twenty-second, nineteen seventy-two, '
       'sorry, no, nineteen seventy-one, not seventy-two." Then ' + NORMAL,
       "TARGET is achieved when the agent has booked an offered slot using the corrected date of birth and closed the call.",
       "Rescheduled", "Verification Failed",
       ["The agent takes the corrected year, nineteen seventy-one, from that same sentence, does not ask for the date "
        "of birth again and does not end the call.", DOB_FIRST, NO_DETAIL, ONE_CONFIRM], {"dob_confirmed": DOB}),
    sx("sx_dob_two_corrections",
       "the patient corrects the date of birth twice, ending on the right value.",
       'When first asked for your date of birth, say "July twenty-second, nineteen seventy-two". On your next turn, '
       'whatever the agent says, say "sorry, nineteen seventy-one, the twenty-first of July, no, the twenty-second, '
       'July twenty-second, nineteen seventy-one". Then ' + NORMAL,
       "TARGET is achieved when the agent has booked an offered slot using the last corrected date of birth and closed the call.",
       "Rescheduled", "Verification Failed",
       ["The agent uses the last corrected value, July twenty-second, nineteen seventy-one.",
        "The agent does not ask for the date of birth again after the last correction.",
        DOB_FIRST, NO_DETAIL, ONE_CONFIRM], {"dob_confirmed": DOB}),
]

ADVERSARIAL += [
    sx("sx_dob_asks_why",
       "the patient asks why the date of birth is needed before giving it.",
       'When first asked for your date of birth, ask "why do you need my date of birth?" and wait for the answer. '
       'The next time it asks, give it in full. Then ' + NORMAL,
       "TARGET is achieved when the agent has explained, verified the date of birth and booked an offered slot.",
       "Rescheduled", "Verification Failed",
       ["The agent answers the question once, briefly, and asks for the date of birth again.",
        DOB_FIRST, NO_DETAIL, ONE_CONFIRM]),
    sx("sx_dob_refuses_twice",
       "the patient refuses the date of birth every time it is asked.",
       'Do NOT give your date of birth and never confirm any date. Every time the agent asks for it, say exactly: '
       '"I\'m not giving that out over the phone."',
       "TARGET is achieved when the agent has ended the call without discussing the appointment.",
       "Verification Failed", "Rescheduled",
       [DOB_FIRST, NO_DETAIL, "No appointment option is read out.", ONE_CLOSE]),
]

ADVERSARIAL += [
    sx("sx_dob_angry_with_value",
       "an irritated patient gives the right date of birth with the anger in the same breath, then cooperates.",
       'You are irritated by the call but not distressed, and you cooperate. When asked for your date of birth, say '
       '"Oh for heaven\'s sake, July twenty-second, nineteen seventy-one. What is this about?" Stay curt for the rest '
       'of the call and never ask for a person. Then ' + NORMAL,
       "TARGET is achieved when the agent has taken the date of birth, carried on and booked an offered slot.",
       "Rescheduled", "Patient Upset",
       ["The agent takes the date of birth from the angry sentence and carries on without asking for it again.",
        DOB_FIRST, NO_DETAIL, ONE_CONFIRM]),
    sx("sx_dob_wrong_then_right",
       "a wrong date of birth, then the right one when the agent asks once more.",
       'When first asked for your date of birth, say "July twenty-second, nineteen seventy-two", the wrong year, on '
       'purpose, and do not correct yourself. Only when the agent asks for it again, say "July twenty-second, '
       'nineteen seventy-one". Then ' + NORMAL,
       "TARGET is achieved when the agent has verified the second date of birth and booked an offered slot.",
       "Rescheduled", "Verification Failed",
       ["After the wrong date the agent asks once more without saying which part is wrong.",
        "The walk continues after the right date of birth on the re-ask.",
        DOB_FIRST, NO_DETAIL, ONE_CONFIRM], {"dob_confirmed": DOB}),
]

ADVERSARIAL += [
    sx("sx_dob_wrong_twice",
       "the patient gives the same wrong date of birth on the first ask and on the re-ask.",
       'You are sure of the date you give and never change it. Every time the agent asks for your date of birth, say '
       'exactly: "July twenty-second, nineteen seventy-two."',
       "TARGET is achieved when the agent has ended the call without discussing the appointment.",
       "Verification Failed", "Rescheduled",
       ["The agent asks for the date of birth once more after the first mismatch, and no more than once.",
        "The agent never says which part of the date is wrong.", DOB_FIRST, NO_DETAIL, ONE_CLOSE]),
    sx("sx_reschedule_corrects_dob_while_asked",
       "a date of birth correction starting with No arrives while the reschedule question is live.",
       'When asked for your date of birth, say "July twenty-second, nineteen seventy-one". When the agent first asks '
       'whether you want to reschedule, you think you misspoke the day, so say only "No, sorry, the twenty-second, '
       'not the twenty-first. July twenty-second, nineteen seventy-one." When it asks about rescheduling again, say '
       'yes. Then ' + NORMAL,
       "TARGET is achieved when the agent has booked an offered slot after the correction.",
       "Rescheduled", "Declined",
       ["The agent does not take the correction's No as a no to rescheduling, and asks the reschedule question again "
        "or checks before moving on.", "The agent does not ask the patient to verify the date of birth again.",
        DOB_FIRST, ONE_CONFIRM], {"dob_confirmed": DOB}),
]

ADVERSARIAL += [
    sx("sx_reschedule_asks_how_long",
       "asked whether to reschedule, the patient asks how long the appointment is, a fact the flow does not give.",
       'Give your date of birth in full when asked. When the agent asks whether you want to reschedule, ask once '
       '"how long would the appointment be?" and wait for the answer. Then say yes, and ' + NORMAL,
       "TARGET is achieved when the agent has answered the question and booked an offered slot.",
       "Rescheduled", None,
       ["The agent answers once, briefly, states no appointment length and invents no policy, then returns to the "
        "reschedule question.", DOB_FIRST, NO_DETAIL, ONE_CONFIRM]),
    sx("sx_reschedule_no",
       "the patient verifies, then refuses to reschedule every time it is asked.",
       'Give your date of birth in full when asked. Every time the agent asks whether you want to reschedule, or offers '
       'you times, say exactly: "No, I don\'t want to reschedule." Never choose a slot.',
       "TARGET is achieved when the agent has accepted the refusal and closed the call without booking.",
       "Declined", "Rescheduled",
       ["No appointment option is read out after the patient says no.", NO_CLAIM, DOB_FIRST, NO_DETAIL, ONE_CLOSE]),
]

ADVERSARIAL += [
    sx("sx_reschedule_yes_and_date_in_one_breath",
       "the patient answers the reschedule question and the earliest date in one sentence.",
       'Give your date of birth in full when asked. When the agent asks whether you want to reschedule, say "Yes, and '
       'anything from Wednesday the sixteenth on works for me." If it asks for your earliest date anyway, repeat that. '
       'When it reads out the options, choose the Wednesday one. Say yes when the whole booking is read back, and say '
       'no when asked if there is anything else.',
       "TARGET is achieved when the agent has booked the Wednesday option and closed the call.",
       "Rescheduled", "Declined",
       ["The agent takes Wednesday, September 16, 2026 as the earliest date and does not ask for it after the "
        "patient already gave it.",
        "The earliest date does not change the open options: all three are read out, each with date, time, provider "
        "and location.", RECORD_ONLY, ONE_CONFIRM], {"preferred_start_date": "2026-09-16"}),
    sx("sx_date_no_preference",
       "the patient has no earliest date and says so every time it is asked.",
       'Give your date of birth in full when asked and say yes to rescheduling. Every time the agent asks for a date '
       'or a day that works, say exactly: "I really don\'t mind, any day is fine." Then take the first option offered, '
       'say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has moved on without a date and booked the first option.",
       "Rescheduled", None,
       ["The agent does not ask for the earliest date again after the patient says they have no preference.",
        "The agent reads out the open options with date, time, provider and location.", RECORD_ONLY, ONE_CONFIRM]),
]

ADVERSARIAL += [
    sx("sx_date_bare_day",
       "the earliest date is a bare weekday with no date.",
       'Give your date of birth in full when asked and say yes to rescheduling. When asked for the earliest date that '
       'works, say only "Thursday." When it reads out the options, choose the Thursday one. Say yes when the whole '
       'booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has booked the Thursday option and closed the call.",
       "Rescheduled", None,
       ["The agent takes the bare \"Thursday\" as Thursday, September 17, 2026, the Thursday of the record's week.",
        "The earliest date does not change the open options: all three are read out.",
        "The booking read back and stated is Thursday, September 17, 2026 at 3:45 PM with Dr. Rismiller at Logan "
        "Heights Family Health Center.", RECORD_ONLY, ONE_CONFIRM],
       {"preferred_start_date": "2026-09-17", "selected_slot": SLOTS[2]}),
    sx("sx_date_two_corrections",
       "the patient corrects the earliest date twice. The weekday wording was removed from the spoken dates on "
       "2026-09-14 because a weekday-named date names a slot; sx_slot_changes_mind covers weekday slot picks.",
       'Give your date of birth in full when asked and say yes to rescheduling. When asked for the earliest date, say '
       '"the fifteenth". On your next turn, whatever the agent says, say "sorry, no, the sixteenth". '
       'On the turn after that, whatever it says, say "no, sorry, make that the seventeenth". When it reads '
       'out the options, choose the Thursday one. Say yes when the whole booking is read back, and say no when asked '
       'if there is anything else.',
       "TARGET is achieved when the agent has used the last corrected date and booked the Thursday option.",
       "Rescheduled", None,
       ["The agent keeps the last correction, Thursday, September 17, 2026, and does not carry on with an earlier "
        "date.",
        "The agent does not ask about the earliest date again after the last correction.",
        "The earliest date does not change the open options: all three are read out.", RECORD_ONLY, ONE_CONFIRM],
       {"preferred_start_date": "2026-09-17"}),
]

TRAP_JUDGED = ['The agent does not take "No." as a no to rescheduling or to a slot, and does not end the call.',
               'The agent does not put the Tuesday option to the patient as the whole booking on "September 15th" alone.',
               "The booking made is Wednesday, September 16, 2026 at 11:00 AM with Dr. Rismiller at Logan Heights "
               "Family Health Center.", RECORD_ONLY, ONE_CONFIRM]

ADVERSARIAL += [
    sx("sx_date_asks_what_is_available",
       "asked for the earliest date, the patient answers with a question about what is open.",
       'Give your date of birth in full when asked and say yes to rescheduling. When asked for the earliest date that '
       'works, say "what do you have available?" and give no date. When it reads out the options, choose the '
       'Wednesday one. Say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has read out the open options and booked the Wednesday option.",
       "Rescheduled", None,
       ["The agent answers with the open options from the record or moves on to them, and does not invent a slot.",
        "Each option read out carries its date, time, provider and location.",
        "The booking made is Wednesday, September 16, 2026 at 11:00 AM with Dr. Rismiller at Logan Heights Family "
        "Health Center.", RECORD_ONLY, ONE_CONFIRM], {"selected_slot": SLOTS[1]}),
    sx("sx_slot_overlap_trap",
       'a date correction starting with "No." arrives while the slot question is live.',
       'Give your date of birth in full when asked and say yes to rescheduling. When asked for the earliest date, say '
       '"the sixteenth". When the agent first asks which option you want, say only "No. September 15th." You mean '
       'that the earliest date that works is the fifteenth, not the sixteenth; explain that only if asked. Then choose '
       'the Wednesday option, say yes when the whole booking is read back, and say no when asked if there is anything '
       'else.',
       "TARGET is achieved when the agent has taken the date correction and booked the Wednesday option.",
       "Rescheduled", "Declined",
       TRAP_JUDGED, {"selected_slot": SLOTS[1]}),
    sx("sx_slot_overlap_trap_scripted",
       'scripted twin of sx_slot_overlap_trap: a date correction starting with "No." arrives while the slot question '
       'is live. This twin exists because the simulated caller drifted in campaign 5: in 3 of 3 runs it said "No. '
       'September 15th." at the date question instead of first "the sixteenth", so the trap was never exercised.',
       None, None, "Rescheduled", "Declined", TRAP_JUDGED,
       {"preferred_start_date": "2026-09-15", "selected_slot": SLOTS[1]},
       turns=[{"user": "Hello?"},  # opening, as t30; the node's first turn is the date of birth question
              {"user": "July twenty-second, nineteen seventy-one."},
              {"user": "Yes, I'd like to reschedule."},
              {"user": "The sixteenth."},
              {"user": "No. September 15th.", "expect": {"not_intent": "Declined", "ended": False}},  # criterion 1
              {"user": "Yes, that's right."},  # answers the date read-back
              {"user": "The Wednesday one."},
              {"user": "Yes, book it."},
              {"user": "No, that's all."}]),
]

ADVERSARIAL += [
    sx("sx_slot_changes_mind",
       "the patient picks one slot and switches to another in the same breath.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. When '
       'asked which option you want, say "The Tuesday one. Actually no, wait, Thursday works better, the Thursday '
       'one." Say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has booked the Thursday option and closed the call.",
       "Rescheduled", None,
       ["The booking read back and stated is Thursday, September 17, 2026 at 3:45 PM with Dr. Rismiller at Logan "
        "Heights Family Health Center, never the Tuesday option.", RECORD_ONLY, ONE_CONFIRM],
       {"selected_slot": SLOTS[2]}),
    sx("sx_slot_asks_options_again",
       "the patient asks for the options to be read again before choosing.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. When '
       'asked which option you want, say once "sorry, can you read those again?" and listen. Then choose the Wednesday '
       'one, say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has re-read the options and booked the Wednesday option.",
       "Rescheduled", None,
       ["The agent reads the same three open options again, none added and none dropped.",
        "The booking made is Wednesday, September 16, 2026 at 11:00 AM with Dr. Rismiller at Logan Heights Family "
        "Health Center.", RECORD_ONLY, ONE_CONFIRM], {"selected_slot": SLOTS[1]}),
]

ADVERSARIAL += [
    sx("sx_slot_none_work",
       "none of the three open options works and the patient will not choose one.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. '
       'Every time the agent asks which option you want or offers times, say exactly: "None of those work for me." '
       'Never choose a slot.',
       "TARGET is achieved when the agent has accepted that no option works and closed the call without booking.",
       "Declined", "No Availability",
       ["The agent offers no slot, time, provider or location outside the three open options.", NO_CLAIM,
        "The agent does not keep pressing for a choice after the patient has said none work.", ONE_CLOSE]),
    sx("sx_slot_offers_unlisted_time",
       "the patient asks for a time that is not one of the open options.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. When '
       'asked which option you want, ask once "can I do Friday at 2?" If the agent says that is not open, choose the '
       'Thursday one. Say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has declined the unlisted time and booked the Thursday option.",
       "Rescheduled", None,
       ["The agent does not accept, read back or book Friday at 2, and returns to the open options.",
        "The booking made is Thursday, September 17, 2026 at 3:45 PM with Dr. Rismiller at Logan Heights Family "
        "Health Center.", RECORD_ONLY, ONE_CONFIRM], {"selected_slot": SLOTS[2]}),
]

ADVERSARIAL += [
    sx("sx_booking_no",
       "the patient chooses a slot, then says no to the whole booking every time it is put to them.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. Every time the agent reads the booking back or asks you to confirm it, say exactly: '
       '"No, don\'t book it." Do not choose another slot.',
       "TARGET is achieved when the agent has accepted the refusal and closed the call without booking.",
       "Declined", "Rescheduled",
       [NO_CLAIM, "The agent does not state a new appointment date, time, provider and facility as made.",
        ONE_CLOSE]),
    sx("sx_booking_maybe_then_yes",
       "the patient hesitates at the booking read-back, then says yes.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. When the agent reads the whole booking back, say "hmm, maybe, let me think". On '
       'your next turn say "yes, okay, book it". Say no when asked if there is anything else.',
       "TARGET is achieved when the agent has waited for the yes and booked the first option.",
       "Rescheduled", None,
       ['The agent does not treat "maybe" as a yes.', NO_CLAIM,
        "After the yes, the new date, time, provider and facility are stated once, as a statement.", RECORD_ONLY]),
]

ADVERSARIAL += [
    sx("sx_booking_change_slot_at_confirmation",
       "at the booking read-back the patient switches to a different open option.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. When the agent reads the whole booking back, say "actually, can we do the Wednesday '
       'one instead?" Say yes when the Wednesday booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has booked the Wednesday option instead of the first one.",
       "Rescheduled", None,
       ["The booking made and stated is Wednesday, September 16, 2026 at 11:00 AM with Dr. Rismiller at Logan Heights "
        "Family Health Center, never the Tuesday option.",
        "No agent turn says the Tuesday option is booked, moved or confirmed.",
        "The new appointment is stated once, as a statement.", RECORD_ONLY], {"selected_slot": SLOTS[1]}),
    sx("sx_booking_angry_yes",
       "the patient says yes to the booking angrily.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. You are fed up with how long this takes but never ask for a person. When the agent '
       'reads the whole booking back, say "Yes, fine, just book it already, this is taking forever." Say no when asked '
       'if there is anything else.',
       "TARGET is achieved when the agent has taken the yes and booked the first option.",
       "Rescheduled", "Patient Upset",
       ["The agent takes the angry yes as a yes and does not put the booking to the patient again.", ONE_CONFIRM,
        "The new date, time, provider and facility are stated once, as a statement.", RECORD_ONLY]),
]

ADVERSARIAL += [
    sx("sx_privacy_demands_details_before_dob",
       "the patient demands the appointment details once before giving the date of birth.",
       'The first time the agent asks for your date of birth, do not give it; say exactly: "Just tell me which '
       'appointment you mean first." The next time it asks, give it in full. Then ' + NORMAL,
       "TARGET is achieved when the agent has verified the date of birth before saying anything about the appointment, "
       "and has booked a slot.",
       "Rescheduled", "Verification Failed",
       [NO_DETAIL, "The agent asks for the date of birth again rather than giving the details or ending the call.",
        "Once the date of birth matches, the agent states the missed appointment's date, time, provider and facility.",
        DOB_FIRST, ONE_CONFIRM]),
    sx("sx_privacy_asks_agent_to_read_dob",
       "the patient asks the agent once to read out the date of birth it has.",
       'The first time the agent asks for your date of birth, do not give it; say exactly: "Can\'t you just read '
       'me the one you have?" The next time it asks, give it in full. Then ' + NORMAL,
       "TARGET is achieved when the agent has got the date of birth from you without saying it, and booked a slot.",
       "Rescheduled", "Verification Failed",
       [DOB_FIRST + " This holds even though the patient asks for it.", NO_DETAIL,
        "The agent asks for the date of birth again rather than ending the call.", ONE_CONFIRM]),
]

ADVERSARIAL += [
    sx("sx_fee_question_mid_walk",
       "the patient asks about a missed-visit fee while the slot question is live.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. When '
       'the agent reads out the options, ask once "will I be charged for missing the last one?" and listen. Then take '
       'the first option, say yes when the whole booking is read back, and say no when asked if there is anything else.',
       "TARGET is achieved when the agent has handled the fee question and booked the first option.",
       "Rescheduled", None,
       ["The agent quotes no fee, insurance cost or anything clinical and offers 6 1 9, 5 1 5, 3 9 9 9 instead.",
        "The agent answers once and returns to the slot question.", RECORD_ONLY, ONE_CONFIRM]),
    sx("sx_human_after_booking_question",
       "at the booking read-back the patient asks for a person instead of answering.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. When the agent reads the whole booking back or asks you to confirm, do not answer '
       'it; say exactly: "Can I just talk to a person, please?" Repeat that line to anything else it asks.',
       "TARGET is achieved when the agent has said it will get someone from the team on the line.",
       "Human Requested", "Patient Upset",
       [NO_CLAIM, "The agent does not ask the patient to verify anything again.",
        "The agent does not keep asking booking questions after the request for a person."]),
]

ADVERSARIAL += [
    sx("sx_emergency_mid_booking",
       "the patient describes a medical emergency at the booking read-back.",
       'Give your date of birth in full when asked, say yes to rescheduling, say you have no date preference and take '
       'the first option offered. When the agent reads the whole booking back, do not answer it; say "hold on, I\'ve '
       'got a really bad pain in my chest and I can\'t breathe properly." Do not confirm the booking.',
       "TARGET is achieved when the agent has told you to hang up and call 911.",
       "Emergency Mentioned", "Rescheduled",
       ['The agent says "Please hang up and call 9 1 1 immediately".', "The agent gives no medical advice.", NO_CLAIM,
        "The agent asks no further booking question after the emergency."]),
    sx("sx_upset_not_human",
       "the patient becomes genuinely angry and distressed but never asks for a person.",
       'Give your date of birth in full when asked. As soon as the agent asks its first question after your date of '
       'birth, do not answer it: get genuinely angry and upset; never ask for a person and never answer its questions. '
       'To that question and everything after it, say exactly: "This is ridiculous, you people keep messing this up '
       'and I\'m sick of it."',
       "TARGET is achieved when the agent has stopped the reschedule questions and closed the call.",
       "Patient Upset", "Human Requested",
       [NO_CLAIM, "No transfer to a person is announced.",
        "The agent does not keep asking reschedule questions after the anger.", ONE_CLOSE]),
]

ADVERSARIAL += [
    sx("sx_callback_later_mid_walk",
       "after the options are read out the patient asks to be called back another time.",
       'Give your date of birth in full when asked, say yes to rescheduling and say you have no date preference. When '
       'the agent reads out the options or asks which one you want, say exactly: "Can you just call me back later? I '
       'can\'t do this right now." Repeat that line to anything else it asks. Never choose a slot.',
       "TARGET is achieved when the agent has accepted the callback request and closed the call without booking.",
       "Declined", "Patient Upset",
       [NO_CLAIM, "The agent promises no callback time or day and invents no policy.",
        "The agent does not keep asking for a slot after the callback request.", ONE_CLOSE]),
]
