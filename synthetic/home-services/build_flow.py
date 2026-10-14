#!/usr/bin/env python3
"""Build the V2.9 Hunter example flow in the console's builder (paste) format.

    python3 V29-Hunter-Example/build_flow.py              # writes v29-hunter-example-flow.json
    python3 V29-Hunter-Example/build_flow.py --clipboard  # also loads it on the clipboard

Start (API) -> Screening Contact -> Caller Check -> Service Request (all 12 types) -> Booking Confirmation -> End.
Values flow Start -> Caller Check -> Service Request -> Booking Confirmation through {{Node Name.x}} refs.
Node shapes mirror Sigma/sigma-v29-two-node-flow.json, a paste MK has already used. Ids are uuid5, so a
rebuild keeps every id stable.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import uuid
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
OUT = HERE / "v29-hunter-example-flow.json"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "v29-hunter-example")


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


PAYLOAD = ["caller_id", "customer_name", "customer_phone", "city"]


def start_node() -> dict:
    sigma = json.loads((ROOT / "Sigma/sigma-v29-two-node-flow.json").read_text())
    node = copy.deepcopy(next(n for n in sigma["nodes"] if n["type"] == "start"))
    node["id"] = uid("node", "Start")
    node["data"]["config"]["payload_format"] = {k: "string" for k in PAYLOAD}
    # Hunter triggers without Basic auth; the console defaults this to true and exports strip the key
    node["data"]["config"]["require_http_auth"] = False
    return node


def screening_node() -> dict:
    p = "{{Start.http.params.%s}}"
    return {
        "id": uid("node", "Screening Contact"),
        "type": "outbound_screening",
        "data": {
            "meta": {"name": "Initiate call and screen"},
            "_meta": None,
            "config": {
                "events": [],
                "from": p % "caller_id",
                "to": p % "customer_phone",
                "is_validate_caller_id": True,
                "ring_timeout": 30,
                "max_call_duration": 20,
                "context": (
                    f"Home service booking call from HomeFix Services. The intended contact is {p % 'customer_name'}. "
                    "Confirm you are speaking with them, then confirm now is a good time before the booking conversation begins."
                ),
                "ask_permission": True,
                "initial_wait_time": 2,
                "name": "Screening Contact",
                "description": "Confirms the right person answered and that now is a good time.",
            },
        },
    }


def end_node(name: str, message: str) -> dict:
    return {
        "id": uid("node", name),
        "type": "end_conversation",
        "data": {"meta": {"name": "End conversation"}, "_meta": None,
                 "config": {"name": name, "description": "", "end_message": message}},
    }


def field(node: str, name: str, ctype: str, description: str, instructions: str, *,
          required: bool = True, options: dict | None = None, choices: list | None = None,
          num_digits: int | None = None) -> dict:
    options = options or {}
    settings = dict(options)
    if choices is not None:
        settings["choices"] = choices
    if num_digits is not None:
        settings["num_digits"] = num_digits
    # the author's type and settings are overrides, so a later node Save or Detect keeps them
    overrides = {"type": ctype, **({"settings": settings} if settings else {}), **({} if required else {"optional": True})}
    return {
        "id": uid("input", node, name),
        "variable_name": name,
        "variable_instructions": description,
        "variable_type": "string",
        "variable_format_instructions": "",
        "variable_enum_values": [],
        "configure_data_format": False,
        "collection": {
            "type": ctype,
            "options": options,
            "choices": choices,
            "choices_from_call": False,
            "num_digits": num_digits,
            "spell_back": None,
            "fresh_question": False,
            "required": required,
            "instructions": instructions,
            "version": None,
            "stale": True,  # the first node Save lets the runner refresh `instructions`; overrides survive it
            "overrides": overrides,
        },
    }


def intent(node: str, name: str, instructions: str) -> dict:
    return {"id": uid("intent", node, name), "intent_name": name, "intent_instructions": instructions,
            "intent_speech": {"intent_speech_text": "", "speech_enabled": False}}


def agent_node(name: str, description: str, instructions: str, inputs: list, intents: list) -> dict:
    return {
        "id": uid("node", name),
        "type": "ai_agent_v29",
        "data": {
            "meta": {"name": "AI conversation v2.9"},
            "_meta": None,
            "config": {
                "name": name,
                "description": description,
                "channel": "call",
                "instructions": instructions,
                "instruction_attachments": None,
                "allow_greeting_interruption": True,
                "intents": intents,
                "extract_variables": inputs,
                "actions": [],
                "screening_name": "Hi, this is HomeFix Services calling",
                "screening_reason": "I'm calling about your home service request.",
                "initial_wait_time": 0,
            },
        },
    }


CALLER_CHECK = "Caller Check"
SERVICE = "Service Request"
CONFIRM = "Booking Confirmation"
S = "{{Start.http.params.%s}}"

caller_check = agent_node(
    CALLER_CHECK,
    "Confirms the caller is the account holder before the service request.",
    f"""## Goal
Confirm you are speaking with the account holder before taking a home service request.

## Context
- The account holder on file is {S % 'customer_name'}.
- Their city on file is {S % 'city'}.

## Task
1. Say you are calling from HomeFix Services about their home service request.
2. Collect caller_name: the caller's full name. The name on file is {S % 'customer_name'}; pass it as the known value so the collector confirms it instead of asking from scratch.
3. When caller_name is collected, select Caller Confirmed.
4. If the caller says they are not {S % 'customer_name'} and nobody else on the line can make the request, select Wrong Person.

## Rules
- Ask one question at a time.
- Never read out account details other than the name on file.""",
    [field(CALLER_CHECK, "caller_name", "name", "The caller's full name, confirmed against the name on file.",
           "Confirm the caller's full name against the name on file.",
           options={"first_name": True, "last_name": True})],
    [intent(CALLER_CHECK, "Caller Confirmed", "Select once caller_name has been collected and the caller has confirmed they are the account holder."),
     intent(CALLER_CHECK, "Wrong Person", "Select when the caller says they are not the account holder and nobody else on the line can make the service request.")],
)

service = agent_node(
    SERVICE,
    "Takes the service request and collects one value of every Input type.",
    f"""## Goal
Take a home service request from {{{{{CALLER_CHECK}.caller_name}}}} and collect every detail the technician needs.

## Context
- Address the caller as {{{{{CALLER_CHECK}.caller_name}}}}. Do not ask for their name again.
- Their city on file is {S % 'city'}.

## Task
Collect these in order, one question at a time:
1. service_type: which service they need.
2. issue_description: a short description of the problem.
3. rooms_affected: how many rooms are affected, as a whole number.
4. preferred_visit_date: the date they would like the technician to visit. It must be a future date and not today.
5. max_budget: the most they want to spend on this visit.
6. service_address: the street address and city where the work is needed.
7. gate_code: the 4-digit gate or building entry code, if there is one. It is optional.
8. onsite_contact_name: the full name of the person who will be at the property during the visit.
9. contact_email: an email address for the booking confirmation.
10. alternate_phone: another phone number to reach them on the day of the visit. It is optional.
11. pets_at_home: whether there are pets at home.
12. date_of_birth: the account holder's date of birth, for identity verification.
When every required value is collected, select Request Captured.
If the caller no longer wants the service, select Caller Declines.
If the caller asks to speak to a person, select Human Requested.

## Rules
- Ask one question at a time and never bundle two questions.
- If an optional value is not available, move on without pressing.""",
    [
        field(SERVICE, "service_type", "choice", "The kind of service the caller needs.",
              "Ask which service they need: Plumbing, Electrical or Cleaning.",
              options={"present_options": True}, choices=["Plumbing", "Electrical", "Cleaning"]),
        field(SERVICE, "issue_description", "text", "A short description of the problem.",
              "Ask for a short description of the problem."),
        field(SERVICE, "rooms_affected", "number", "How many rooms are affected, as a whole number.",
              "Ask how many rooms are affected; a whole number, never negative.",
              options={"allow_decimal": False, "allow_negative": False}),
        field(SERVICE, "preferred_visit_date", "date", "The date the caller wants the technician to visit.",
              "Ask for the date they would like the visit; it must be a future date and not today.",
              options={"accept_past": False, "accept_today": False, "require_time": False}),
        field(SERVICE, "max_budget", "currency", "The most the caller wants to spend on this visit.",
              "Ask for the most they want to spend on this visit."),
        field(SERVICE, "service_address", "address", "The street address and city where the work is needed.",
              "Ask for the street address and city where the work is needed.",
              options={"required_fields": ["street_address", "city"]}),
        field(SERVICE, "gate_code", "dtmf", "The 4-digit gate or building entry code, if there is one.",
              "Ask for the 4-digit gate or building entry code; the caller may key it in or say it. Optional.",
              required=False, num_digits=4),
        field(SERVICE, "onsite_contact_name", "name", "The full name of the person at the property during the visit.",
              "Ask for the full name of the person who will be at the property during the visit.",
              options={"first_name": True, "last_name": True}),
        field(SERVICE, "contact_email", "email", "An email address for the booking confirmation.",
              "Ask for an email address for the booking confirmation."),
        field(SERVICE, "alternate_phone", "phone", "Another phone number for the day of the visit.",
              "Ask for another phone number to reach them on the day of the visit. Optional.",
              required=False),
        field(SERVICE, "pets_at_home", "boolean", "Whether there are pets at home.",
              "Ask whether there are pets at home."),
        field(SERVICE, "date_of_birth", "dob", "The account holder's date of birth, for identity verification.",
              "Ask for the account holder's date of birth, for identity verification.",
              options={"require_time": False}),
    ],
    [intent(SERVICE, "Request Captured", "Select once every required value in the Task has been collected."),
     intent(SERVICE, "Caller Declines", "Select when the caller says they no longer want the service."),
     intent(SERVICE, "Human Requested", "Select when the caller asks to speak to a person.")],
)

R = "{{%s.%%s}}" % SERVICE
confirm = agent_node(
    CONFIRM,
    "Reads the booking back and gets the caller's confirmation.",
    f"""## Goal
Read the booking back and get the caller's confirmation.

## Context
- Service: {R % 'service_type'}
- Visit date: {R % 'preferred_visit_date'}
- Address: {R % 'service_address'}
- On-site contact: {R % 'onsite_contact_name'}
- Confirmation email: {R % 'contact_email'}

## Task
1. Read back the service, the visit date, the address and the on-site contact in one short summary.
2. Collect booking_confirmed: whether everything is correct and they want to book the visit.
3. If booking_confirmed is yes, collect reminder_preference: how they would like a reminder the day before. It is optional.
4. If booking_confirmed is yes, select Booking Confirmed. If it is no, select Booking Not Confirmed.

## Rules
- Use only the values above; never invent a detail.""",
    [field(CONFIRM, "booking_confirmed", "boolean", "Whether the caller confirms the booking as read back.",
           "Ask whether everything read back is correct and they want to book the visit."),
     field(CONFIRM, "reminder_preference", "choice", "How the caller wants a reminder the day before.",
           "Ask how they would like a reminder the day before: SMS, Email or No reminder. Optional.",
           required=False, options={"present_options": True}, choices=["SMS", "Email", "No reminder"])],
    [intent(CONFIRM, "Booking Confirmed", "Select once booking_confirmed is yes and reminder_preference has been asked."),
     intent(CONFIRM, "Booking Not Confirmed", "Select when booking_confirmed is no.")],
)

ENDS = {
    "Booking Complete End": "Thank the caller, say the booking is confirmed and a confirmation email will follow, then say goodbye.",
    "Not Confirmed End": "Tell the caller the booking was not made and they can call back any time, then say goodbye.",
    "Declined End": "Acknowledge the caller's decision, thank them for their time and say goodbye.",
    "Human Followup End": "Tell the caller a team member will call them back shortly, thank them and say goodbye.",
    "Wrong Person End": "Apologise for the mix-up, thank them and say goodbye.",
    "Try Later End": "Thank them, say HomeFix will call back at a better time, and say goodbye.",
    "Not Reached End": "Say goodbye.",
}

DIAL_VARS = ["uuid", "to", "from", "direction", "from_iso2", "leg", "bill_rate", "from_country",
             "voicemail_detected", "call_status", "conversation_id"]
SCREEN_VARS = ["screening_disposition", "screening_status", "screening_answered_by",
               "screening_relationship", "screening_callback_time"]


def node_vars(node: dict, handle: str) -> list[str]:
    t, cfg = node["type"], node["data"]["config"]
    if t == "start":
        return ["{{Start.request_type}}", "{{Start.flow_run_id}}", "{{Start.http.params}}"] + [
            "{{Start.http.params.%s}}" % k for k in cfg["payload_format"]]
    if t == "outbound_screening":
        if handle in ("no_answer", "busy_rejected", "failed"):
            return ["{{%s · Dial.%s}}" % (cfg["name"], v) for v in DIAL_VARS]
        return ["{{%s.%s}}" % (cfg["name"], v) for v in SCREEN_VARS]
    return ["{{%s.%s}}" % (cfg["name"], v["variable_name"]) for v in cfg["extract_variables"]]


def build() -> dict:
    start, screen = start_node(), screening_node()
    ends = {name: end_node(name, msg) for name, msg in ENDS.items()}
    nodes = [start, screen, caller_check, service, confirm, *ends.values()]
    byname = {n["data"]["config"]["name"]: n for n in nodes}

    def handle_of(src: dict, label: str) -> str:
        if src["type"] != "ai_agent_v29":
            return label
        return next(i["id"] for i in src["data"]["config"]["intents"] if i["intent_name"] == label)

    wiring = [
        ("Start", "http", "Screening Contact"),
        ("Screening Contact", "reached", CALLER_CHECK),
        *[("Screening Contact", h, "Not Reached End") for h in ("no_answer", "busy_rejected", "failed", "Voicemail Detected")],
        *[("Screening Contact", h, "Try Later End") for h in ("callback", "unavailable")],
        ("Screening Contact", "wrong_contact", "Wrong Person End"),
        *[("Screening Contact", h, "Declined End") for h in ("declined", "do_not_call")],
        (CALLER_CHECK, "Caller Confirmed", SERVICE),
        (CALLER_CHECK, "Wrong Person", "Wrong Person End"),
        (SERVICE, "Request Captured", CONFIRM),
        (SERVICE, "Caller Declines", "Declined End"),
        (SERVICE, "Human Requested", "Human Followup End"),
        (CONFIRM, "Booking Confirmed", "Booking Complete End"),
        (CONFIRM, "Booking Not Confirmed", "Not Confirmed End"),
    ]
    edges = []
    for src_name, label, dst_name in wiring:
        src, dst = byname[src_name], byname[dst_name]
        handle = handle_of(src, label)
        edges.append({"id": uid("edge", src_name, label), "source": src["id"], "target": dst["id"],
                      "sourceHandle": handle, "data": {"nodeVars": node_vars(src, handle)}})
    return {"name": "V2.9 Hunter Example", "nodes": nodes, "edges": edges}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clipboard", action="store_true")
    a = ap.parse_args()
    flow = build()
    OUT.write_text(json.dumps(flow, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(flow['nodes'])} nodes, {len(flow['edges'])} edges")
    if a.clipboard:
        subprocess.run(["pbcopy"], input=OUT.read_bytes(), check=True)
        print("on the clipboard")
