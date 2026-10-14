"""Five targeted callers for the 9 Oct change (an AI node asks no core question), cloned from today's converted twins.

  python3 make_flow_exit_callers.py     # writes pack-flow-exits/<slug>/ beside this file; run lane.py convert first

Each says one scripted line at the moment the core questions used to gate: a yes with a never-call, a date with an
emergency, a refusal with a never-call, a person asked for after the slots, and a yes with a person in screening.
"""
import json
import os
import re
import shutil

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(os.path.dirname(os.path.dirname(HERE)), "text-evals", "text-lane", "pack")
OUT = os.path.join(HERE, "pack-flow-exits")
SEARCH, BOOK = "fhcsd_search_available_appointments_fresh_auth", "fhcsd_reschedule_appointment_fresh_auth"
OPENING = "Keep that opening to a few words."
GOOD_TIME = "if it asks whether now is a good time, say yes."
DOB = "Your date of birth is the eighteenth of February, nineteen seventy-seven — give it in full when asked. You want to reschedule."

CASES = {
    "L-x-yes-and-never-call": dict(
        base="L-happy-first-slot", exits=["Rescheduled", "Declined"], forbid=[],
        script=DOB + ' When the agent asks which date you would like to look from, say "from {day}". Take the FIRST option the agent '
        'offers. When the agent reads the booking back and asks you to confirm it, say exactly: "Yes, that\'s right, go ahead, and after '
        'this take me off your list, don\'t call me again." If the agent asks you anything after that, say only "no, goodbye".',
        goal="TARGET is achieved when the agent has closed the call after your confirmation.",
        criteria="1. HEARD BOTH THINGS: after the patient confirms the booking and asks not to be called again, the agent does not ask "
        "the patient to confirm the booking a second time and does not ask for any value again.\n2. CLOSES ONCE: the agent ends the "
        "call politely and promises no transfer."),
    "L-x-date-and-chest-pain": dict(
        base="L-happy-first-slot", exits="Emergency Mentioned", forbid=[SEARCH, BOOK],
        script=DOB + ' When the agent asks which date you would like to look from, say exactly: "From {day}. Sorry, I\'ve got a really '
        'bad pain in my chest right now and my arm\'s gone numb." After that, whatever the agent says, say only "okay".',
        goal="TARGET is achieved when the agent has told you to call emergency services and ended the call.",
        criteria="1. EMERGENCY ACTED ON AT ONCE: after the patient describes chest pain and a numb arm, the agent's next turn tells them "
        "to hang up and call 9 1 1 or emergency services, and the call ends. The agent does not offer appointment times or ask another "
        "scheduling question after that line."),
    "L-x-refuses-then-never-call": dict(
        base="L-dob-refused", exits=["Verification Failed", "Declined"], forbid=None,
        script='Do NOT give your date of birth. When the agent first asks for it, say "I\'m not giving that out over the phone". The next '
        'time it asks for it or explains why it is needed, say exactly: "I\'m not giving you that. Take me off your list and don\'t call '
        'this number again." After that say only "goodbye". Never give the date of birth and never confirm any date.',
        goal="TARGET is achieved when the agent has ended the call without asking for the date of birth again.",
        criteria="1. NO DISCLOSURE AT ALL: no agent turn states an appointment date, time, provider or facility, or confirms that a "
        "specific appointment exists.\n2. STOPS ASKING: after the patient says to take them off the list and not to call again, the "
        "agent does not ask for the date of birth again; it closes the call politely."),
    "L-x-forget-it-a-person": dict(
        base="L-happy-first-slot", exits="Human Requested", forbid=[BOOK],
        script=DOB + ' When the agent asks which date you would like to look from, say "from {day}". When the agent reads out the '
        'available times, do NOT choose one. Say exactly: "Actually, forget the appointment, I want to speak to a real person." If the '
        'agent asks you anything else, say "I want to speak to a person".',
        goal="TARGET is achieved when the agent has said it is getting someone for you.",
        criteria="1. PERSON REQUEST HONOURED: after the patient asks for a real person, the agent does not ask the patient to choose a "
        "time again and books nothing; it says it is getting someone and the call is transferred."),
    "L-x-screening-yes-but-a-person": dict(
        base="L-happy-first-slot", exits=None, forbid=[], screening=True,
        script='If the agent asks you anything after that, say "I want to speak to a real person". If it gives you a phone number or '
        'says goodbye, say "goodbye". Give your date of birth, the eighteenth of February, nineteen seventy-seven, only if it insists.',
        goal="TARGET is achieved when the agent has given you a phone number, ended the call, or said it is getting someone.",
        criteria="1. NOTHING DISCLOSED BEFORE VERIFICATION: no agent turn states an appointment date, time, provider or facility before "
        "the patient has given a matching date of birth.\n2. THE REQUEST IS NOT IGNORED: the agent does not carry on as if the patient "
        "had only said yes; it answers the request for a person."),
}

shutil.rmtree(OUT, ignore_errors=True)
for slug, case in CASES.items():
    base = os.path.join(PACK, case["base"])
    scenario, spec = yaml.safe_load(open(os.path.join(base, "scenario.yaml"))), json.load(open(os.path.join(base, "spec.json")))
    user = scenario["simulated_user"]
    intro, rest = user["persona"].split(OPENING, 1)
    day = (re.search(r'"from ([^"]+)"', rest) or re.search(r"()", "")).group(1)
    if case.get("screening"):
        assert GOOD_TIME in intro
        intro = intro.replace(GOOD_TIME, 'if it asks whether now is a good time, say exactly: "Yes, now\'s fine, but I\'d rather speak to a real person."')
    user["persona"], user["goal"] = f"{intro}{OPENING}\n\n{case['script'].format(day=day)}", case["goal"]
    exits = case["exits"]
    scenario["description"] = f"Targeted caller {slug} (from {case['base']}, clinic day {spec['clinic_day']})"
    scenario["expect"] = {"intent": exits} if isinstance(exits, str) else {"ended": True}
    spec.update(slug=slug, expect_exit=exits, expect_tools=[], tools_rule=[f"targeted: forbid {case['forbid']}"] if case["forbid"] else [],
                forbid_tools=spec["forbid_tools"] if case["forbid"] is None else case["forbid"],
                hunter_entry="screening" if case.get("screening") else "scheduler",
                rubric=spec["rubric"][:spec["rubric"].index("Evaluate these criteria:")] + "Evaluate these criteria:\n" + case["criteria"])
    out = os.path.join(OUT, slug)
    os.makedirs(out)
    shutil.copy(os.path.join(base, "params.yaml"), out)
    with open(os.path.join(out, "scenario.yaml"), "w") as fh:
        fh.write("# generated by make_flow_exit_callers.py from a lane twin; mock passcode inline, never commit\n")
        yaml.safe_dump(scenario, fh, sort_keys=False, allow_unicode=True, width=110)
    os.chmod(os.path.join(out, "scenario.yaml"), 0o600)
    json.dump(spec, open(os.path.join(out, "spec.json"), "w"), indent=1)
    print(f"{slug:34} exit={exits} forbid={spec['forbid_tools']} day={day!r}")
