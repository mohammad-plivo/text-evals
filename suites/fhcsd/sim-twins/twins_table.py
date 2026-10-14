"""Text twins of the 29 FHCSD v2.9 Hunter scenarios, one dict per scenario (filled in a later step).

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

twin() builds that shape from the Hunter file itself, so persona, goal, title and criteria stay verbatim.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUNTER = os.path.join(_HERE, "..", "..", "..", "FHCSD", "hunter", "v29")
_IDS = json.load(open(os.path.join(_HUNTER, "created.json")))["ids"]
_FLOW = json.load(open(os.path.join(_HERE, "flow.json")))
_AGENT = next(n for n in _FLOW["nodes"] if n["type"] == "ai_agent_v29")
SLOTS = next(v["collection"]["choices"] for v in _AGENT["data"]["config"]["extract_variables"]
             if v["variable_name"] == "selected_slot")  # the node's own option strings, 0-based
INTENTS = {i["intent_name"] for i in _AGENT["data"]["config"]["intents"]}
_SCREEN = next(n["id"] for n in _FLOW["nodes"] if n["type"] == "outbound_screening")
# screening edge handles; the sim reports the disposition as the final intent (src/units/screening.py:374)
SCREENING = {e["sourceHandle"] for e in _FLOW["edges"] if e["source"] == _SCREEN}

# last-name steers from the node's Task text; any other surname is a normal patient
STEERS = {
    "Tran": "no patient record matches",
    "Delacroix": "two patient records match",
    "Kaminski": "the clinic record is unavailable",
    "Achterberg": "the record matches but there is no appointment on file",
    "Kowalski": "no options are open",
    "Bergstrom": "only Option 1 is open",
    "Nakamura": "only Option 1 and Option 2 are open",
    "Ferreira": "the booking is not held",
    "Okonkwo": "the booking is not held",
    "Oyelaran": "the booking is not held",
}
CLINIC_NOTE = ("Clinic record: the Missed Visit Scheduler Task text in flow.json is the record for this run; "
               "the dates quoted in the Hunter criteria come from the Hunter daily build and differ, "
               "so judge by option number and by that Task text, not by those dates.")
DISCLOSURE_NOTE = ("Before reading an intent red, check the Task step 2 disclosure: this caller acts only after the agent "
                   "tells them about the appointment, so a skipped disclosure leaves the trigger unfired.")
SAME_TURN_NOTE = ("Criterion {} is not exercisable when the exit fires in the same turn as the bad news (Task step {}), "
                  "because the call ends before the caller's follow-up question; judge it not applicable then.")


def twin(stem, phone, opening, hunter_exit, expect, turns=None, disabled_reason=None, note=""):
    """Twin of FHCSD/hunter/v29/scenarios/<stem>.json, simulated unless turns is given; hunter_exit is the Hunter-side exit."""
    src = json.load(open(os.path.join(_HUNTER, "scenarios", stem + ".json")))
    p = src["payload"]
    cp = p["conversationPrompt"]
    persona, sep, target = cp.rpartition("\n\nTARGET " if "\n\nTARGET " in cp else " TARGET ")  # 32 inlines it
    assert sep and persona.strip() and target.strip(), f"{stem}: no TARGET sentence"
    criteria = re.findall(r"^\d+\. .+$", p["evaluationPrompt"].split("Evaluate these criteria:")[1], re.M)
    assert criteria, f"{stem}: no numbered criteria"
    named = {expect.get("intent"), expect.get("not_intent")} - {None}
    assert named <= INTENTS | SCREENING, f"{stem}: unknown intent in {expect}"
    last = p["initiationVariables"]["last_name"]
    steer = STEERS.get(last, "a normal patient with the appointment and all three options")
    intent = expect.get("intent")
    renamed = "" if hunter_exit == intent or not intent else " (renamed)"
    target_label = ("screening disposition " if intent in SCREENING else "DB intent ") + intent if intent else "no intent asserted"
    body = {"kind": "scripted", "turns": turns} if turns else {
        "kind": "simulated",
        "simulated_user": {"persona": persona, "goal": "TARGET " + target, "opening": opening, "max_turns": 20}}
    entry = {
        "slug": "t" + stem,
        "persona": {**p["initiationVariables"], "phone_number": phone},
        **body,
        "expect": expect,
        "description": (f"Hunter {_IDS[stem + '.json']} {src['name']}. {src['description']}\n"
                        f"Steer: {last}, {steer}.\nExit Hunter {hunter_exit} -> {target_label}{renamed}.\n"
                        + (note + "\n" if note else "")
                        + f"{CLINIC_NOTE}\nJudged by transcript:\n" + "\n".join(criteria)),
    }
    if disabled_reason:
        entry["disabled_reason"] = disabled_reason
    return entry


TWINS: list[dict] = []
TWINS.append(twin("01-happy-first-slot", "+16195550101", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled"}))
TWINS.append(twin("02-happy-second-slot", "+16195550102", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"selected_slot": SLOTS[1]}}))
TWINS.append(twin("03-happy-named-day", "+16195550103", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled"}))  # the named day is relative to run day, so no literal preferred_start_date
TWINS.append(twin("07-no-slots", "+16195550107", "Hello?", "No Slots",
                  {"intent": "No Availability", "not_intent": "Conflict Or API Failure"}))
TWINS.append(twin("08-declines-upfront", "+16195550108", "Hello?", "Declined",
                  {"intent": "Declined"}))
TWINS.append(twin("11-dob-refused", "+16195550111", "Yeah, hello?", "Verification Failed",
                  {"intent": "Verification Failed"}))
TWINS.append(twin("12-lookup-no-match", "+16195550112", "Hello?", "Verification Failed",
                  {"intent": "Verification Failed"}))
TWINS.append(twin("13-lookup-two-matches", "+16195550113", "Hello?", "Verification Failed",
                  {"intent": "Verification Failed"}))
TWINS.append(twin("16-dob-partial-then-complete", "+16195550116", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled"}))
TWINS.append(twin("17-dob-corrected-after-stating", "+16195550117", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"dob_confirmed": "1959-01-08"}}))  # dob collector stores ISO
TWINS.append(twin("18-slot-corrected-after-choosing", "+16195550118", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"selected_slot": SLOTS[2]}}))
TWINS.append(twin("22-human-requested", "+16195550122", "Hello?", "Transfer to Staff",
                  {"intent": "Human Requested", "not_intent": "Patient Upset"}, note=DISCLOSURE_NOTE))
TWINS.append(twin("23-emergency", "+16195550123", "Hello?", "Emergency Mentioned",
                  {"intent": "Emergency Mentioned", "not_intent": "Rescheduled"}, note=DISCLOSURE_NOTE))
TWINS.append(twin("24-upset", "+16195550124", "Hello?", "Patient Upset",
                  {"intent": "Patient Upset", "not_intent": "Human Requested"}, note=DISCLOSURE_NOTE))
TWINS.append(twin("26-booking-fails", "+16195550126", "Hello?", "Slot Taken",
                  {"intent": "Conflict Or API Failure", "not_intent": "Rescheduled"}, note=SAME_TURN_NOTE.format(4, 8)))
TWINS.append(twin("30-interrupts-readback", "+16195550130", "Hello?", "Rescheduled", {"intent": "Rescheduled"}, turns=[
    {"user": "Hello?"},
    {"user": "The ninth of September, nineteen eighty."},
    {"user": "Yes, I want to reschedule."},
    {"user": "No date preference."},
    {"user": "The first one."},
    {"user": "yes yes, that's fine, book it", "interrupt_after": "confirm"},
    {"user": "No."},
], note=("Scripted for the scheduler entry (run with --node ee727068-51d5-4019-92d7-56f1324c2914): the CLI does not "
         "cross from screening into the scheduler, so the screening lines are left out. The caller lines follow the "
         "Hunter persona in order. Turn 6 barges in on the agent's reply after its first \"confirm\", a word only the "
         "booking read-back carries, so the cut lands before the details and a drifted turn order raises "
         "ScenarioAbort instead of cutting the options readout.")))
TWINS.append(twin("31-hangs-up-midflow", "+16195550131", "Hello?", "none named (the persona goes silent)",
                  {"not_intent": "Rescheduled"},  # criterion 1, NOTHING BOOKED
                  disabled_reason=("a real hang-up and a silent caller cannot be simulated: the simulated caller "
                                   "cannot send silence (engine.py _next_user_message aborts on an empty reply), and "
                                   "scripted idle turns drive one reminder each without the idle retry count or the "
                                   "terminal hangup (runner.py _drive_idle_reminder docstring), so criterion 3 "
                                   "cannot be exercised")))
TWINS.append(twin("32-voicemail", "+16195550132",
                  "Hi, you've reached the Mendes family. Please leave a message after the beep.",
                  "Voicemail Detected", {"intent": "Voicemail Detected"},
                  note=("Runs at the screening entry without --node, max_turns 3 as in Hunter. It exercises the identify "
                        "task's text voicemail status (src/units/tasks/contact_screening.py:132-136), not audio "
                        "detection (src/amd/controller.py, built only by src/agent.py).")))
TWINS[-1]["simulated_user"]["max_turns"] = 3  # Hunter maxTurns 3
TWINS.append(twin("34-wrong-person-spouse", "+16195550134", "Hello?", "wrong_contact / unavailable",
                  {"not_intent": "reached", "ended": True},  # the rubric accepts unavailable, wrong_contact and callback
                  note=("Screening: runs at the screening entry without --node. Any disposition that closes without "
                        "handing this person to the scheduler passes (unavailable and wrong_contact reach End Wrong "
                        "Person, callback reaches End Declined), so the twin asserts only not_intent reached and ended.\n"
                        "Documented deviation from Hunter's initiationVariables: first_name is Diego, because "
                        "FHCSD/hunter/v29/build.py:544-548 names Marisol while the persona answers for Diego.")))
TWINS[-1]["persona"]["first_name"] = "Diego"  # documented deviation, see the note
TWINS.append(twin("36-two-values-one-breath", "+16195550136", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled",  # description: "Both must be captured"; boolean stores yes (collectors.py:74)
                   "variables": {"dob_confirmed": "1986-10-27", "wants_to_reschedule": "yes"}}))
TWINS.append(twin("38-asks-second-appointment", "+16195550138", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled"}))
TWINS.append(twin("39-subtlety-three-shapes", "+16195550139", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"selected_slot": SLOTS[1]}}))  # TARGET: booked the second option
TWINS.append(twin("40-dob-mismatch", "+16195550140", "Hello?", "Verification Failed",
                  {"intent": "Verification Failed"}))
TWINS.append(twin("41-no-appointment-on-file", "+16195550141", "Hello?", "No Appointment",
                  {"intent": "Conflict Or API Failure"},
                  note=("End No Appointment is from the README row; the node's Task text step 2 selects Conflict Or API Failure for no appointment on file.\n"
                        + SAME_TURN_NOTE.format(3, 2))))
TWINS.append(twin("42-token-401", "+16195550142", "Hello?", "API Failure",
                  {"intent": "Conflict Or API Failure", "not_intent": "Verification Failed"},  # criterion 3
                  note=("End API Failure is the retired graph's ending for a failed Druid call "
                        "(FHCSD/parked/build-v29-real-flow.py:433-442); criterion 4 also rules out No Availability.")))
TWINS.append(twin("43-already-has-appointment", "+16195550143", "Hello?", "Already Has Appointment",
                  {"intent": "Conflict Or API Failure", "not_intent": "Rescheduled"},  # criterion 1
                  note="End Already Has Appointment is from the README row; the node's Task text step 8 selects Conflict Or API Failure when the booking is not held."))
TWINS.append(twin("44-save-html-409", "+16195550144", "Hello?", "Scheduling Conflict",
                  {"intent": "Conflict Or API Failure", "not_intent": "Rescheduled"},  # criterion 1
                  note=("The Hunter description names a scheduling conflict (End Scheduling Conflict in the retired graph); the node's Task text step 8 selects Conflict Or API Failure when the booking is not held.\n"
                        + SAME_TURN_NOTE.format(2, 8))))
TWINS.append(twin("45-one-slot-returned", "+16195550145", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"selected_slot": SLOTS[0]}}))  # TARGET: booked the only slot
TWINS.append(twin("46-two-slots-returned", "+16195550146", "Hello?", "Rescheduled",
                  {"intent": "Rescheduled", "variables": {"selected_slot": SLOTS[1]}}))  # criterion 3, BOOKS THE SECOND
