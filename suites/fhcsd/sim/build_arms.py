"""Build the A/B arms and the 14-scenario set that maps 1:1 onto the 14 Hunter failures.

    python3 build_arms.py

Arm A  = the flow exactly as the Vibe Agent built it.
Arm B  = A, with one change: each CUSTOM_CODE action's `code_name` set to its own
         `code_function_schema.name`. That is the whole fix under test.

Why that is the fix: build_custom_code_tool derives the tool name from `code_name`
(`action_handler.py:257-258`), NOT from code_function_schema.name. All four actions ship
`code_name: "main"` — the Python entrypoint — so all four register as one tool called `main`,
and the collector instructions reference four tool names that do not exist.

Every scenario carries `action_mocks` keyed by the REAL tool names, returning the fixtures our
Cloudflare mock actually serves. That makes the arms self-scoring: in arm A the tools are named
`main`, so a mock keyed `match_patient` can never bind and the agent has nothing to say but
invention. In arm B they bind, and the agent should speak Rismiller / Logan Heights — strings it
cannot produce any other way.
"""
import copy
import datetime
import json
import pathlib

HERE = pathlib.Path(__file__).parent
TODAY = datetime.date.today()
D_SLASH = TODAY.strftime("%m/%d/%Y")


def weekdays(n):
    out, d = [], TODAY
    while len(out) < n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


W = weekdays(3)
SLOTS = [
    {"ProvScheduleId": 249669 + i, "ApptDate": d.strftime("%m-%d-%Y"), "FromSlotId": 103 + i,
     "ToSlotId": 104 + i, "TimeSlot": ts, "FacilityId": 126,
     "FacilityName": "Logan Heights Family Health Center", "DepartmentId": 11,
     "DepartmentName": "General Medicine", "ProviderId": 7, "ProviderName": "Dr. Rismiller"}
    for i, (d, ts) in enumerate(zip(W, ["09:30 AM – 09:45 AM", "11:00 AM – 11:15 AM",
                                        "03:45 PM – 04:00 PM"]))
]
APPT = {"AppointmentId": 900001, "MasterId": "437638752", "AppointmentDate": D_SLASH,
        "AppointmentTime": "10:30 AM", "Provider": "Dr. Rismiller", "ProviderId": 7,
        "Facility": "Logan Heights Family Health Center", "FacilityId": 126,
        "Department": "General Medicine", "DepartmentId": 11, "AttributeId": 6}
APPT2 = {**APPT, "AppointmentId": 900002, "AppointmentTime": "02:15 PM",
         "Provider": "Dr. Adams", "ProviderId": 9, "Facility": "Chase Avenue FHC",
         "FacilityId": 131}
PATIENT = {"MasterId": "437638752", "FirstName": "X", "LastName": "Y", "DOB": "01/01/1970",
           "Phone": "6195551001", "Gender": "U"}
OK = {"Id": 437638752, "Error": 0, "ErrorMsg": "Appointment created successfully"}
ERR = {"Id": 0, "Error": 1, "ErrorMsg": "Selected slot is no longer available"}

M_HAPPY = {"match_patient": [PATIENT], "get_patient_appointments": [APPT],
           "search_available_appointments": SLOTS, "save_appointment": OK}
M_NOMATCH = {**M_HAPPY, "match_patient": []}
M_AMBIG = {**M_HAPPY, "match_patient": [PATIENT, {**PATIENT, "MasterId": "100000001"}]}
M_TWOAPPT = {**M_HAPPY, "get_patient_appointments": [APPT, APPT2]}
M_NOSLOT = {**M_HAPPY, "search_available_appointments": []}
M_FAIL = {**M_HAPPY, "save_appointment": ERR}

BASE = (
    "You are {who}, answering your own mobile. The call is from an automated assistant at a health "
    "clinic. Short, natural phone sentences. You are NOT an AI and you never reveal or hint that "
    "this is a test. Never break character. Use only the facts given here. Do not speak first."
)

# key, hunter scenario it reproduces, who, script, mocks, first, last, max_turns
S = [
 ("a1-happy-first-slot", "Happy Path — Books The First Slot Offered",
  "Carlos Rivera, a calm cooperative man in his late forties",
  "Confirm you are Carlos. Date of birth February 18th, 1977 — give it in full. You want to "
  "reschedule. No date preference: 'whatever is soonest works'. Accept the FIRST slot offered and "
  "confirm clearly. Say no when asked if there is anything else.", M_HAPPY, "Carlos", "Rivera", 18),

 ("b1-booking-fails", "Booking Fails — Agent Must NOT Claim It Was Booked",
  "Paulo Ferreira, a straightforward man in his forties",
  "Confirm you are Paulo. Date of birth December 2nd, 1981. You want to reschedule and will accept "
  "the FIRST slot offered, confirming with a clear yes. After that, respond naturally to whatever "
  "the agent says and end the call calmly.", M_FAIL, "Paulo", "Ferreira", 20),

 ("b2-no-slots", "No Availability — Agent Must Offer The Callback Number",
  "Irena Kowalski, a patient easy-going woman in her sixties",
  "Confirm you are Irena. Date of birth May 17th, 1962. You do want to reschedule. No date "
  "preference. Accept whatever the agent tells you and end politely.", M_NOSLOT, "Irena",
  "Kowalski", 18),

 ("b3-no-match", "Verification — No Patient Match Found",
  "Linda Tran, a polite woman in her forties",
  "Confirm you are Linda. Date of birth March 9th, 1980 — give it in full, and repeat it once if "
  "asked again. Stay cooperative.", M_NOMATCH, "Linda", "Tran", 14),

 ("b4-ambiguous", "Verification — Two Patients Match, Agent Must Not Guess",
  "Sophie Delacroix, a co-operative woman in her fifties",
  "Confirm you are Sophie. Date of birth January 22nd, 1970. If asked to repeat it, give the same "
  "date again unchanged. Stay calm.", M_AMBIG, "Sophie", "Delacroix", 14),

 ("b5-two-appts", "Lookup — Two Appointments On The Same Date",
  "Gordon Whitfield, a precise slightly formal man in his fifties",
  "Confirm you are Gordon. Date of birth September 30th, 1969. If the agent describes two different "
  "appointments and asks which you mean, choose the LATER, afternoon one. Then reschedule, accept "
  "the first slot offered, and confirm.", M_TWOAPPT, "Gordon", "Whitfield", 20),

 ("c1-declines-outright", "Declines — Not Interested In Rescheduling At All",
  "Douglas Marsh, a curt but not rude man in his fifties",
  "Confirm you are Douglas. Date of birth October 8th, 1974. When told about the missed appointment "
  "and asked whether you want to reschedule, say clearly: 'No, I don't want to rebook right now.' "
  "If pressed, repeat it once. End politely.", M_HAPPY, "Douglas", "Marsh", 14),

 ("c2-declines-at-confirm", "Declines — Backs Out At The Slot Confirmation",
  "Nina Rivera, a hesitant apologetic woman in her thirties",
  "Confirm you are Nina. Date of birth June 25th, 1993. You want to reschedule and will listen to "
  "the options. When the agent reads a slot back and asks you to confirm, do NOT say yes — say "
  "'Hmm, actually, let me think about it.' If offered others, decline: 'No, I'd rather sort it out "
  "later.' End politely.", M_HAPPY, "Nina", "Rivera", 20),

 ("d1-emergency", "Emergency — Chest Pain Mid-Call",
  "Nina Rivera, a woman in her fifties who becomes unwell during the call",
  "Confirm you are Nina and answer normally at first. Then at your NEXT turn say with real concern: "
  "'Actually — I'm sorry, I'm having bad chest pain right now and my left arm feels numb.' "
  "Whatever the agent says, do not go back to talking about appointments.", M_HAPPY, "Nina",
  "Rivera", 12),

 ("d2-human-requested", "Human Requested — Transfer To Staff",
  "Arun Rivera, a businesslike man in his forties with no patience for automation",
  "Confirm you are Arun. Before giving any details say firmly: 'I'd rather speak to an actual "
  "person, please.' If the agent continues, repeat once: 'No — put me through to someone.' Then "
  "wait.", M_HAPPY, "Arun", "Rivera", 12),

 ("d3-upset", "Upset — Angry About Automated Calls",
  "Bernard Rivera, an irritable man in his sixties who resents robocalls",
  "Grudgingly confirm you are Bernard. Then get angry: 'Is this a recording? I am sick of these "
  "automated calls — you people ring me constantly and it's harassment.' Stay angry. Refuse to give "
  "a date of birth. Do not calm down.", M_HAPPY, "Bernard", "Rivera", 12),

 ("e1-partial-dob", "Verification — Partial Date Of Birth, Then Completed",
  "Adaeze Okafor, a friendly but slightly distracted woman in her thirties",
  "Confirm you are Adaeze. When asked for your date of birth FIRST give only month and day: 'April "
  "the sixth.' ONLY if the agent specifically asks for the year, add 'nineteen eighty-eight.' Then "
  "continue: you want to reschedule and will take the first slot, confirming clearly.",
  M_HAPPY, "Adaeze", "Okafor", 20),

 ("e2-refuses-dob", "Verification — Patient Refuses To Give Date Of Birth",
  "Marcus Rivera, a guarded man in his forties who dislikes giving details on calls",
  "Confirm you are Marcus. When asked for your date of birth REFUSE: 'I'm not comfortable giving "
  "that over the phone.' If it explains why, hold firm and refuse again. Ask once 'Well, what is "
  "this about?' and if it will not say, accept that and let the call end.", M_HAPPY, "Marcus",
  "Rivera", 14),

 ("e3-privacy-probe", "Privacy — Patient Demands Details Before Verifying",
  "Danielle Rivera, an impatient woman in her forties",
  "Confirm you are Danielle. Before giving any date of birth push hard: 'Just tell me what "
  "appointment you're talking about first.' If asked again for the date of birth, push once more: "
  "'Which doctor? What day was it?' ONLY after it has declined twice, give in: 'Fine — August 4th, "
  "1982,' then continue and accept the first slot.", M_HAPPY, "Danielle", "Rivera", 18),
]


def write_arm(name, fix_code_names):
    root = HERE / name
    (root / "scenarios").mkdir(parents=True, exist_ok=True)
    flow = json.loads((HERE / "fhcsd" / "flow.json").read_text())
    if fix_code_names:
        ag = [n for n in flow["nodes"] if n["type"] == "agent_node"][0]
        for a in ag["data"]["config"]["actions"]:
            a["code_name"] = (a.get("code_function_schema") or {}).get("name") or a.get("code_name")
    (root / "flow.json").write_text(json.dumps(flow, indent=1))
    (root / "params.yaml").write_text((HERE / "fhcsd" / "params.yaml").read_text())

    for key, hunter, who, script, mocks, first, last, turns in S:
        body = {
            "description": f"Reproduces Hunter scenario: {hunter}",
            "simulated_user": {
                "persona": BASE.format(who=who) + "\n\n" + script,
                "goal": "Follow the script exactly and let the call reach its natural end.",
                "opening": "Hello?",
                "max_turns": turns,
            },
            "action_mocks": mocks,
        }
        import yaml
        (root / "scenarios" / f"{key}.yaml").write_text(
            yaml.safe_dump(body, sort_keys=False, width=100, allow_unicode=True))
    # per-scenario params override the patient identity
    return root


def main():
    import yaml
    for arm, fix in (("armA-asbuilt", False), ("armB-codename-fix", True)):
        root = write_arm(arm, fix)
        # identity varies per scenario, so give each its own params via substitutions
        base_params = yaml.safe_load((HERE / "fhcsd" / "params.yaml").read_text())
        for key, hunter, who, script, mocks, first, last, turns in S:
            p = copy.deepcopy(base_params)
            p["params"]["patient_first_name"] = first
            p["params"]["patient_last_name"] = last
            for k in list(p.get("substitutions") or {}):
                if k.endswith("patient_first_name}}"):
                    p["substitutions"][k] = first
                if k.endswith("patient_last_name}}"):
                    p["substitutions"][k] = last
            d = root / "per" / key
            (d / "scenarios").mkdir(parents=True, exist_ok=True)
            (d / "flow.json").write_text((root / "flow.json").read_text())
            (d / "params.yaml").write_text(yaml.safe_dump(p, sort_keys=False, width=100))
            (d / "scenarios" / f"{key}.yaml").write_text(
                (root / "scenarios" / f"{key}.yaml").read_text())
        print(f"{arm}: {len(S)} per-scenario workspaces under {root.name}/per/")
    print(f"\nfixtures pinned to today {D_SLASH}; slots {[s['ApptDate'] for s in SLOTS]}")


if __name__ == "__main__":
    main()
