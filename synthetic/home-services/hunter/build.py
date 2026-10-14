#!/usr/bin/env python3
"""Write the 14 Hunter scenarios for the V2.9 example flow into hunter/scenarios/.

    python3 V29-Hunter-Example/hunter/build.py

Re-run the morning of every board, after 05:30 IST (Hunter judges in UTC): every date is computed in IST and
written into both the persona and the rubric, and each file carries `_built_ist`, which create.py and
run_board.py check. Full walks do not fit Hunter's ~290 s persona window (MK 2026-09-24), so only 01 and 14
walk the whole flow; every other edge case stresses its own fields and then asks for a person.
`_expected_variables` is ours, not Hunter's: the planned value per Input, converted to Hunter's stored
form after the smoke call, and stripped before POST by create.py.
"""
from __future__ import annotations

import datetime
import json
import zoneinfo
from pathlib import Path

HERE = Path(__file__).parent
U = json.loads((HERE / "urls.json").read_text())
OUT = HERE / "scenarios"
FLOW = json.loads((HERE.parent / "v29-hunter-example-flow.json").read_text())

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(IST).date()


def spoken(d: datetime.date) -> str:
    n = d.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{d.strftime('%A')} the {n}{suffix} of {d.strftime('%B')}"


VISIT = TODAY + datetime.timedelta(days=3)
VISIT_CHANGED = TODAY + datetime.timedelta(days=5)
TOMORROW = TODAY + datetime.timedelta(days=1)

NAME = "Ananya Rao"
BASE = {"caller_id": U["from_number"], "customer_name": NAME, "city": "Pune"}
PARAMS = ["caller_id", "customer_name", "customer_phone", "city"]
BODY_TEMPLATE = json.dumps({p: "{{INBOUND_NUMBER}}" if p == "customer_phone" else "{{%s}}" % p for p in PARAMS}, indent=2)

# The planned answers, in the order the flow asks them. A scenario overrides only what it stresses.
HAPPY = {
    "caller_name": ("Yes, that's right.", NAME),
    "service_type": ("Plumbing.", "Plumbing"),
    "issue_description": ("The kitchen sink is leaking under the cabinet.", "The kitchen sink is leaking under the cabinet."),
    "rooms_affected": ("Just one room.", "1"),
    "preferred_visit_date": (f"{spoken(VISIT)} works for me.", VISIT.isoformat()),
    "max_budget": ("Up to five thousand rupees.", "INR 5000.0"),
    "service_address": ("Flat 4B, 22 Baner Road, Pune.", "Flat 4B, 22 Baner Road, Pune"),
    "gate_code": ("It's four eight two one.", "4821"),
    "onsite_contact_name": ("My brother, Sam Pereira.", "Sam Pereira"),
    "contact_email": ("ananya dot rao at example dot com.", "ananya.rao@example.com"),
    "alternate_phone": ("Plus nine one, nine eight seven six five, four three two one one.", "+919876543211"),
    "pets_at_home": ("Yes, we have a dog.", "yes"),
    "date_of_birth": ("The fourteenth of March, nineteen ninety.", "1990-03-14"),
    "booking_confirmed": ("Yes, please book it.", "yes"),
    "reminder_preference": ("SMS, please.", "SMS"),
}
ORDER = list(HAPPY)
SERVICE_FIELDS = ORDER[1:13]

PERSONA_HEAD = (
    "You are {name}, a homeowner in Pune. You answer your own mobile. The call is from HomeFix Services about the home "
    "service request you made. Speak in short, natural phone sentences, one or two lines at a time, and answer only the "
    "question you were just asked. Never volunteer a later answer early unless the facts below tell you to. You are NOT an "
    "assistant and NOT an AI, you never reveal or hint that this is a test, and you never break character. Use only the "
    "facts below; if you are asked something they do not cover, give a short plausible answer in one line. Do not speak "
    "first, wait for the agent. When it first asks whether it is speaking with {first}, say yes; when it asks whether now "
    "is a good time, say yes. Keep that opening to a few words. Answer every question promptly."
)
ALWAYS = [
    "You cannot press phone keys. If the agent asks you to enter, key in, press or type a code, say the digits aloud instead.",
    "If asked to spell a name or your email, spell it letter by letter: Ananya is A, N, A, N, Y, A; Rao is R, A, O; Sam is "
    "S, A, M; Pereira is P, E, R, E, I, R, A; your email is a, n, a, n, y, a, dot, r, a, o, at, e, x, a, m, p, l, e, dot, com.",
    "If the agent asks which country the other number is in, or for its country code, say: \"India, plus nine one.\"",
]
TARGET = (
    "TARGET is achieved only when the AGENT ends the call: you hear its closing message, or the line drops. You never hang "
    "up yourself and never say goodbye first. If the agent is slow or silent, wait patiently and say nothing. When the "
    "agent only says a detail back or says it has it, without asking you anything, say nothing and wait for its next "
    "question. When it reads a detail back and asks whether it is right, and the detail matches your facts, say only: "
    "\"Yes, that's right.\" If it does not match, say \"No,\" and give the right detail from your facts. If it asks "
    "whether you are still there, say: \"Yes, I'm here.\" Stay on the call until it ends."
)
LABELS = {
    "caller_name": "to confirm your name", "service_type": "which service you need", "issue_description": "the problem",
    "rooms_affected": "how many rooms are affected", "preferred_visit_date": "when you want the visit",
    "max_budget": "your budget", "service_address": "the address", "gate_code": "the gate code",
    "onsite_contact_name": "who will be at the property", "contact_email": "your email",
    "alternate_phone": "for another phone number", "pets_at_home": "whether you have pets",
    "date_of_birth": "your date of birth", "booking_confirmed": "whether to book the visit as read back",
    "reminder_preference": "how you want a reminder",
}

JUDGE_HEAD = (
    "You are judging an OUTBOUND home service booking call placed by HomeFix Services' AI agent to a customer. SPEAKER "
    "LABELS: the CALLER is the simulated customer, the AGENT is the system under test; in the transcript, turns labelled "
    "'user' are the AGENT and turns labelled 'assistant' are the CALLER. Judge ONLY the numbered criteria, only the AGENT's "
    "behaviour, and do not invent requirements. Today is {today} (India time); every date below is already worked out for "
    "you, never compute one yourself. The transcript is speech-to-text, so a different spelling of the same sounds is the "
    "same word.\n"
    "The screening step runs first and asks two questions of its own, whether it is speaking with the customer and whether "
    "now is a good time; both are expected, correct, and out of scope for every criterion.{name_check}\n"
    "Evaluate these criteria:"
)
NAME_CHECK = (
    " Right after the screening, the agent confirms the caller's full name once against the name on file (for example "
    "'I have your name as Ananya Rao, is that right?'); that one confirmation is expected, is not a repeat of the "
    "screening's question, and is where the caller's name is confirmed."
)
C_NO_REPEAT = ("NO QUESTION IS ASKED TWICE: no question is put again later in the same substance, except a single clarifying "
               "follow-up on an answer that was unclear, incomplete or invalid, a re-ask the caller asked for, a read-back of a "
               "value the caller just gave, the booking read-back before confirmation, a question put again because the caller "
               "corrected an earlier value instead of answering it, or a check-in after the caller was silent.")
C_ONE_VALUE = ("ONE VALUE PER QUESTION: every question the agent asks is about one detail and then waits for the answer; it never "
               "puts questions about two different details in one turn. A street address together with its city is one detail, "
               "and 'is that all correct, and shall I book it?' is one yes-or-no question.")
C_NO_CODE = ("NO CODE SPOKEN: no agent turn says an underscore-joined identifier (such as service_type or gate_code), curly "
             "braces, a double-brace expression, or a stored value read out as code (such as 'INR 5000.0' or "
             f"'{VISIT.isoformat()}'). Plain English words for a detail, such as 'gate code', 'visit date' or 'budget', are fine.")
C_NO_INVENTED = ("NOTHING INVENTED: every detail the agent states back (service, date, address, names, amounts) is one the caller "
                 "gave on this call, the name or city on file, or a state or country that follows from that city (Maharashtra, "
                 "India); never a different value.")
C_CLOSES_ONCE = ("THE CALL CLOSES ONCE: after the caller's last answer the agent may acknowledge that answer in a few words, then "
                 "speaks one closing message; across those turns it says goodbye only once and asks nothing further.")
C_USES_NAME = ("USES THE CONFIRMED NAME: after the caller confirms their full name at the name check that follows the screening, "
               "the agent never asks for the caller's own name again; it may address them by that name.")
C_BOOKED = ("BOOKING COMPLETED: the agent reads back the booking, the caller confirms it, the agent asks how they would like a "
            "reminder, and the call ends with the booking confirmed.")
C_PERSON = ("A PERSON IS REQUESTED: once the caller says they want to speak to a real person, the agent asks no further booking "
            "question, tells them a team member will follow up, and closes.")
COMMON = [C_NO_REPEAT, C_ONE_VALUE, C_NO_CODE, C_NO_INVENTED, C_CLOSES_ONCE]
PERSON_LINE = "I want to speak to a real person, please."


def readback(v: dict, contact_note: str = "") -> str:
    date = datetime.date.fromisoformat(v["preferred_visit_date"][1])
    return (f"READ-BACK IS RIGHT: before asking for confirmation the agent reads back the booking with the service "
            f"{v['service_type'][1]}, the visit date {spoken(date)} (the weekday may be left out, but if it is said it must be "
            f"{date.strftime('%A')}), the address {v['service_address'][1]} (its parts in any order; a speech-to-text spelling "
            f"such as 'Banner Road' or 'four B', or an added state or country such as Maharashtra or India, is the same address) "
            f"and the on-site contact {v['onsite_contact_name'][1]}{contact_note} (any spelling of the same sounds); it may add "
            f"other details, but none that contradict these.")


def asks(fields: list[str]) -> str:
    return "ASKS FOR EVERY DETAIL: the agent asks for each of these at least once: " + ", ".join(
        LABELS[f].removeprefix("to ").removeprefix("for ") for f in fields) + "."


def answers(v: dict, fields: list[str]) -> list[str]:
    return [f"When the agent asks {LABELS[f]}: \"{v[f][0]}\"" for f in fields]


def persona(facts: list[str], name: str = NAME, head: str | None = None, always: bool = True) -> str:
    lines = facts + (ALWAYS if always else [])
    return (head or PERSONA_HEAD).format(name=name, first=name.split()[0]) + "\n\nFACTS:\n" + "\n".join(
        f"- {f}" for f in lines) + "\n\n" + TARGET


SCENARIOS: list[dict] = []


def scenario(slug: str, title: str, exit_: str, facts: list[str], criteria: list[str], expected: dict, *,
             name: str = NAME, voice: str = "female", head: str | None = None, name_check: bool = True,
             always: bool = True, note: str = "") -> None:
    SCENARIOS.append({"slug": slug, "title": title, "exit": exit_, "facts": facts, "criteria": criteria,
                      "expected": expected, "name": name, "voice": voice, "head": head, "name_check": name_check,
                      "always": always, "note": note})


def short_walk(slug: str, title: str, over: dict | None, upto: str, extra_facts: list[str], stressed: list[str],
               note: str = "") -> None:
    """Answer the flow in order through `upto`, then ask for a person at the next question: exit Human Followup End."""
    v = dict(HAPPY) | (over or {})
    fields = ORDER[: ORDER.index(upto) + 1]
    nxt = ORDER[ORDER.index(upto) + 1]
    facts = extra_facts + answers(v, fields) + [f"When the agent asks {LABELS[nxt]}, say: \"{PERSON_LINE}\""]
    scenario(slug, title, "Human Followup End", facts, [*stressed, C_USES_NAME, C_PERSON, *COMMON],
             {f: v[f][1] for f in fields if v[f][1] is not None}, note=note)


# 01: the one full walk of the happy path
scenario("01-happy-full-walk", "every value given cleanly, all three nodes", "Booking Complete End",
         answers(HAPPY, ORDER),
         [asks(SERVICE_FIELDS), C_USES_NAME, readback(HAPPY), C_BOOKED, *COMMON],
         {f: HAPPY[f][1] for f in ORDER},
         note="Fits only a fast run of the ~290 s persona window; the smoke call measures it.")

short_walk("02-volunteers-ahead", "service, rooms and date volunteered together", None, "max_budget",
           [f"When the agent first asks which service you need, answer in one breath: \"A plumber please, it's just one room, "
            f"and {spoken(VISIT)} would be ideal.\" After that, answer each question as below; if the agent reads the rooms or "
            "the date back and asks whether it is right, say: \"Yes, that's right.\""],
           ["NO RE-ASK OF VOLUNTEERED VALUES: after the caller volunteers the service, the number of rooms and the visit date "
            "together, the agent does not ask for any of those three again; a brief confirmation of what it heard is fine."])

short_walk("03-corrections", "a self-correction in one breath, and an earlier value changed later",
           {"preferred_visit_date": (f"{spoken(VISIT)}.", VISIT_CHANGED.isoformat()),
            "max_budget": ("Five thousand rupees. No wait, make that four thousand.", "INR 4000.0")},
           "service_address",
           [f"When the agent asks the address, do not answer it yet; first say: \"Actually, before that, can we change the "
            f"visit date to {spoken(VISIT_CHANGED)}?\" Answer the address question when it is put to you again."],
           [f"CORRECTIONS TAKEN: the agent keeps four thousand rupees as the budget, never five thousand; it accepts the change "
            f"of visit date without arguing, and every mention of the visit date after that change is {spoken(VISIT_CHANGED)}. "
            f"A read-back of {spoken(VISIT)} spoken before the caller changed it is expected and is not a fault."])

short_walk("04-optional-skips", "no gate code and no other number: two optional fields declined",
           {"gate_code": ("I don't have a gate code, it's an open building.", None),
            "alternate_phone": ("No.", None)},
           "alternate_phone", [],
           ["OPTIONAL NOT PRESSED: when the caller says there is no gate code, and answers 'No' to another phone number, the "
            "agent moves on at once each time: no silence of more than a few seconds, no second ask, no insisting, and no "
            "explanation of why it needs them."],
           note="Expected RED until two runtime defects are fixed: an optional DTMF Input has no decline path "
                "(collect_dtmf.py), and a bare 'No.' to an optional phone is rejected in a loop (turn_evidence.py, "
                "dev call 50405930).")

short_walk("05-date-edges", "today refused, then tomorrow",
           {"preferred_visit_date": ("Today, if possible.", TOMORROW.isoformat())}, "preferred_visit_date",
           ["When the agent says it cannot book today, or asks for another date, say: \"Tomorrow then.\""],
           [f"TODAY IS NOT BOOKED: the agent does not accept today as the visit date, asks for a later one, and takes "
            f"tomorrow, {spoken(TOMORROW)}."],
           note="The birth-date edge (an impossible date) is not covered: date_of_birth is the 12th value and only a full "
                "walk reaches it inside today's persona window.")

short_walk("06-number-and-currency", "a fractional room count, a loose budget",
           {"rooms_affected": ("About two and a half rooms.", "3"),
            "max_budget": ("Around five grand, in rupees.", "INR 5000.0")}, "max_budget",
           ["The FIRST time the agent asks about rooms, even if it says it needs a whole number, say: \"About two and a half "
            "rooms.\" Only after it says it needs a whole number, or asks again, say: \"Call it three then.\""],
           ["WHOLE NUMBER OF ROOMS: the agent does not record two and a half, or twenty-five, rooms; it asks for a whole number "
            "and takes three."])

short_walk("07-choice-edges", "an unlisted service, then a paraphrased pick",
           {"service_type": ("Do you do pest control?", "Electrical"),
            "issue_description": ("The kitchen lights keep flickering.", "The kitchen lights keep flickering.")},
           "issue_description",
           ["The FIRST time the agent asks which service you need, even though it lists Plumbing, Electrical and Cleaning, ask: "
            "\"Do you do pest control?\" Only after it answers that, say: \"Oh, then the electric one.\""],
           ["ONLY OFFERED SERVICES: the agent does not accept pest control or invent a service or a description of one; it "
            "offers Plumbing, Electrical or Cleaning and takes Electrical."])

short_walk("08-contact-details", "an address without its city, a spelled name, a spelled email, a country code",
           {"service_address": ("Flat 4B, 22 Baner Road.", "Flat 4B, 22 Baner Road, Pune"),
            "onsite_contact_name": ("Siobhan Pereira. That's S, I, O, B, H, A, N.", "Siobhan Pereira"),
            "contact_email": ("It's a, n, a, n, y, a, dot, r, a, o, at example dot com.", "ananya.rao@example.com")},
           "alternate_phone",
           ["When the agent asks for the address, even if it asks for the city too, say only: \"Flat 4B, 22 Baner Road.\" Do "
            "not name the city until the agent asks for it on its own; then say: \"Pune.\" If it asks whether the address is "
            "in Pune, say: \"Yes, Pune.\"",
            "If asked to spell the on-site contact's name, say: \"Siobhan is S, I, O, B, H, A, N. Pereira is P, E, R, E, I, R, A.\""],
           ["CITY ASKED FOR: the address was given without a city; the agent asks for the city, or asks whether it is Pune (the "
            "city on file), and the address it keeps is in Pune.",
            "SPELLED VALUES KEPT: whenever the agent says the on-site contact's name or the email back, it is the name and email "
            "the caller spelled; a spelling of the same sounds (for example 'Shivon' for Siobhan) or the email read letter by "
            "letter is the same value, a different name or different letters is not."])

short_walk("09-digit-code", "three digits, then four",
           {"gate_code": ("Four eight two.", "4821")}, "gate_code",
           ["The FIRST time the agent asks for the gate code, even if it says it needs four digits, say only: \"Four eight "
            "two.\" Only after it says that is not enough, or asks you again, say: \"Four eight two one.\""],
           ["FOUR-DIGIT CODE: the agent does not accept the three-digit code; it says four digits are needed or asks again, and "
            "moves on once the caller gives four digits."])

v10 = dict(HAPPY) | {"caller_name": ("Yes, it's Ananya, but my surname is Iyer now, not Rao.", "Ananya Iyer")}
scenario("10-name-corrected-upstream", "a corrected surname at Caller Check, carried into Service Request",
         "Human Followup End",
         ["At the very first question, whether the agent is speaking with Ananya or Ananya Rao, say only: \"Yes, speaking.\" "
          "Do not mention your surname then.",
          "Later, when the agent reads your full name back as Ananya Rao or asks you to confirm your full name, say: \"Yes, it's "
          "Ananya, but my surname is Iyer now, not Rao.\"",
          "When the agent then says or spells Ananya Iyer back and asks if it is right, say only: \"Yes, that's right.\" Never "
          "repeat the correction once it has said Iyer. If asked to spell your surname, say: \"I, Y, E, R.\""]
         + answers(v10, ORDER[1:3]) + [f"When the agent asks {LABELS[ORDER[3]]}, say: \"{PERSON_LINE}\""],
         ["NAME CORRECTION CARRIED: from the agent's first turn after the caller says the surname is Iyer, the agent never calls "
          "them Rao again and never asks for their name again; one read-back or spelling of Ananya Iyer right after the "
          "correction is expected.", C_PERSON, *COMMON],
         {f: v10[f][1] for f in ORDER[:3]},
         head=PERSONA_HEAD.replace("You are {name}, a homeowner", "You are Ananya Iyer, a homeowner").replace(
             "home service request you made.", "home service request you made. HomeFix still has you on file under your old "
             "surname, Rao."))

scenario("11-wrong-person", "not the account holder", "Wrong Person End",
         ["When the agent asks whether it is speaking with Ananya, say: \"No, you have the wrong number. There's no Ananya here.\""],
         ["WRONG PERSON ENDS IT: as soon as the person says they are not Ananya, the agent asks no service question, shares no "
          "booking, address or account detail, does not offer to call back or ask for Ananya again, and closes with an apology "
          "for the mix-up.", C_NO_CODE,
          "THE CALL CLOSES ONCE: after the person says they are not Ananya, the agent says at most a brief apology and one "
          "closing message, says goodbye only once, and asks nothing further."],
         {}, name="Kiran Das", voice="male", name_check=False, always=False,
         head=("You are {name}. You answer your mobile, which used to belong to someone else. You have never heard of HomeFix "
               "Services and never made a service request. Speak in short, natural phone sentences. You are NOT an assistant "
               "and NOT an AI, you never reveal or hint that this is a test, and you never break character. Do not speak "
               "first, wait for the agent."))

scenario("12-declines-mid-walk", "stops wanting the service after three answers", "Declined End",
         answers(HAPPY, ORDER[:4])
         + ["When the agent asks when you want the visit, say: \"Actually, please stop here. I've decided to fix it myself.\""],
         ["A REFUSAL ENDS IT ONCE: the agent accepts the refusal, does not try to change the caller's mind, asks no further "
          "service question, and closes by acknowledging the decision, without saying that a team member will call them or "
          "that HomeFix will call back.", C_USES_NAME, *COMMON],
         {f: HAPPY[f][1] for f in ORDER[:4]})

scenario("13-human-requested", "asks for a person mid-walk", "Human Followup End",
         answers(HAPPY, ORDER[:3]) + [f"When the agent asks {LABELS[ORDER[3]]}, say: \"{PERSON_LINE}\""],
         [C_PERSON, C_USES_NAME, C_NO_CODE, C_CLOSES_ONCE],
         {f: HAPPY[f][1] for f in ORDER[:3]})

v14 = dict(HAPPY) | {"booking_confirmed": ("No, please don't book it. I've changed my mind.", "no")}
scenario("14-not-confirmed", "says no at the read-back", "Not Confirmed End",
         answers(v14, ORDER[:14])
         + ["If the agent asks what is wrong or what to change, say: \"Nothing needs changing, I just don't want to book it now.\""],
         ["NOT CONFIRMED ENDS IT: when the caller says no at the read-back, the agent does not ask about reminders, does not "
          "book, and closes saying the booking was not made.", asks(SERVICE_FIELDS), readback(v14), *COMMON],
         {f: v14[f][1] for f in ORDER[:14]},
         note="A full walk, like 01: fits only a fast run of the persona window.")

VOICES = {"female": "21m00Tcm4TlvDq8ikWAM", "male": "ErXwobaYiN019PkySvjV"}


def agent_config() -> dict:
    return {"name": FLOW["name"], "flowId": U["flow_uuid"],
            "nodes": [{"id": n["id"], "type": n["type"], "data": {"meta": {"name": n["data"]["config"]["name"]},
                                                                 "config": n["data"]["config"]}} for n in FLOW["nodes"]],
            "edges": [{k: e[k] for k in ("id", "source", "target", "sourceHandle")} for e in FLOW["edges"]]}


def payload(s: dict) -> dict:
    head = JUDGE_HEAD.format(today=TODAY.strftime("%A %d %B %Y"), name_check=NAME_CHECK if s["name_check"] else "")
    return {
        "testType": "outbound-agent",
        "initiationRequest": {
            "method": "POST",
            "url": f"{U['runner_share']}/v1/account/{U['auth_id']}/flow/{U['flow_uuid']}",
            "headers": {"Content-Type": "application/json"},
            "bodyTemplate": BODY_TEMPLATE,
            "inboundNumberPlaceholder": "{{INBOUND_NUMBER}}",
        },
        "initiationVariables": dict(BASE),
        "botGreetsFirst": False,
        "allowInterruptions": True,
        "conversationPrompt": persona(s["facts"], s["name"], s["head"], s["always"]),
        "evaluationPrompt": head + "\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(s["criteria"], 1)),
        "evaluationThreshold": 0.8,
        "maxTurns": 150,
        "evaluationConfig": {"autoDisconnectEnabled": True, "maxConsecutiveOffContext": 50,
                             "maxNonActualIntentRetries": 3, "maxResponseTime": 60.0},
        "voiceId": VOICES[s["voice"]],
        "webhookBaseUrl": U["webhook_base_url"],
        "event": "v29ex_" + s["slug"].split("-", 1)[1].replace("-", "_"),
        "testId": f"voice-v29ex-{s['slug']}",
        "testRegion": "us-east",
        "agentConfig": agent_config(),
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for s in SCENARIOS:
        desc = f"{s['title']}. Expected exit: {s['exit']}." + (f" {s['note']}" if s["note"] else "")
        doc = {"name": f"V29EX {s['slug']}", "description": desc, "category": U["category"], "payload": payload(s),
               "_built_ist": TODAY.isoformat(),
               "_expected_variables": {"exit": s["exit"], "planned": s["expected"]}}
        (OUT / f"{s['slug']}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(SCENARIOS)} scenarios (built {TODAY} IST; visit {VISIT}, changed {VISIT_CHANGED}, "
          f"tomorrow {TOMORROW}); flow {U['flow_uuid']}")


if __name__ == "__main__":
    main()
