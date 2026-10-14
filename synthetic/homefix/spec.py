"""The v2.10 logic test flow: ONE synthetic flow with every collector type, actions, hops between AI nodes and handoffs.

This file is the single source. build.py turns it into the simulator's flow.json, the flow stored on the local stack and
the 30 Hunter callers. Nothing here is customer data: HomeFix Services and every person are made up.

    Start -> Call Customer -> Screen Customer -> Account Check -> Book Visit | Site Details | Contact Details | Payment -> End

Adapted from V29-Hunter-Example (24 Sep 2026): same business, but stamped v2.10, with actions, a transfer and exits that
are chosen from action results. Each caller walks one branch, because a call must end inside Hunter's 290 seconds.
"""
from __future__ import annotations

import datetime
import json
import uuid
import zoneinfo

NS = uuid.uuid5(uuid.NAMESPACE_URL, "v210-logic-flow")
ORG, CITY, FLOW_NAME = "HomeFix Services", "Pune", "v2.10 logic flow"
IST = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(IST).date()
P = "{{Start.http.params.%s}}"
PAYLOAD = ["customer_name", "phone_number", "city"]


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def _next(weekday: int, after: int) -> datetime.date:
    """The first given weekday at least `after` days from today."""
    day = TODAY + datetime.timedelta(days=after)
    return day + datetime.timedelta(days=(weekday - day.weekday()) % 7)


def spoken(day: datetime.date) -> str:
    n = day.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{day:%A} the {n}{suffix} of {day:%B}"


def slot_day(day: datetime.date) -> str:
    return f"{day:%A} {day.day} {day:%B}"


VISIT = _next(1, 3)                               # a Tuesday: two open times
VISIT_2 = VISIT + datetime.timedelta(days=7)      # the Tuesday after, for the second search
SUNDAY = _next(6, 2)                              # no open times at a weekend
SLOTS = ("9:30 AM", "2:00 PM")

# ---------------------------------------------------------------------------------------------------------------- actions
# Custom code runs in the E2B sandbox with no network call of its own. Each body carries the accounts it needs, so a
# caller's record decides what the action answers. `main` is the entry point; a failure is returned as data.
_HELPERS = '''
import datetime
import re


def _key(name):
    return " ".join(str(name or "").lower().split())


def _account(name):
    key = _key(name)
    if key in ACCOUNTS:
        return ACCOUNTS[key]
    # the model may pass a first name only, or the name with a title
    return next((row for known, row in ACCOUNTS.items() if set(known.split()) & set(key.split())), None)


def _day(value):
    text = str(value or "").strip()
    found = re.match(r"^(\\d{4})-(\\d{1,2})-(\\d{1,2})", text)
    if found:
        year, month, day = (int(part) for part in found.groups())
    else:
        found = re.match(r"^(\\d{1,2})[/-](\\d{1,2})[/-](\\d{4})$", text)
        if not found:
            return None
        month, day, year = (int(part) for part in found.groups())
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _label(day):
    return "%s %d %s" % (day.strftime("%A"), day.day, day.strftime("%B"))
'''

_LOOKUP = '''
def main(customer_name=None, date_of_birth=None, **_):
    account = _account(customer_name)
    if account is None:
        return {"verified": False, "reason": "no_account_for_that_name"}
    if account.get("lookup") == "error":
        raise RuntimeError("the account service is not answering")
    given = _day(date_of_birth)
    if given is None or given.isoformat() != account["dob"]:
        return {"verified": False, "reason": "date_of_birth_does_not_match"}
    return {"verified": True, "open_item": account["open_item"] or "none"}
'''

_FIND = '''
def main(visit_date=None, **_):
    day = _day(visit_date)
    if day is None:
        return {"slots": [], "reason": "date_not_understood"}
    if day.weekday() >= 5:
        return {"date": day.isoformat(), "slots": [], "reason": "no_visits_at_the_weekend"}
    return {"date": day.isoformat(), "slots": [_label(day) + ", " + time for time in SLOTS]}
'''

_BOOK = '''
MONTHS = [datetime.date(2000, month, 1).strftime("%B") for month in range(1, 13)]


def main(customer_name=None, visit_date=None, slot=None, **_):
    account, day, text = _account(customer_name), _day(visit_date), str(slot or "")
    if account is None:
        return {"booked": False, "reason": "no_account_for_that_name"}
    time = next((known for known in SLOTS if known.split()[0] in text), None)
    if day is None or day.weekday() >= 5 or time is None:
        return {"booked": False, "reason": "not_one_of_the_open_times"}
    # a slot label names its own day, so a label taken from another day's list is a stale choice
    named = re.search(r"(\\d{1,2}) (%s)" % "|".join(MONTHS), text)
    if named and (int(named.group(1)), named.group(2)) != (day.day, day.strftime("%B")):
        return {"booked": False, "reason": "slot_is_from_another_day"}
    if account.get("book") == "slot_taken":
        return {"booked": False, "reason": "slot_taken"}
    return {"booked": True, "date": day.isoformat(), "time": time, "reference": "HF-%02d%02d" % (day.month, day.day)}
'''

_PAY = '''
def main(customer_name=None, amount=None, pin=None, **_):
    account = _account(customer_name)
    if account is None:
        return {"paid": False, "reason": "no_account_for_that_name"}
    digits = "".join(character for character in str(pin or "") if character.isdigit())
    if digits != account["pin"]:
        return {"paid": False, "reason": "wrong_pin"}
    return {"paid": True, "amount": str(amount), "receipt": "RC-" + digits[::-1]}
'''

_SAVE = '''
def main(customer_name=None, **details):
    account = _account(customer_name)
    if account is None:
        return {"saved": False, "reason": "no_account_for_that_name"}
    if account.get("save") == "error":
        return {"saved": False, "reason": "could_not_be_saved"}
    return {"saved": True, "fields": sorted(name for name, value in details.items() if value)}
'''


def _code(body: str, accounts: dict | None) -> str:
    head = f"SLOTS = {list(SLOTS)!r}\nACCOUNTS = {accounts or {}!r}\n"   # a Python literal: JSON would write null
    code = head + _HELPERS + body
    assert "{{" not in code, "a hop renders {{...}} inside code too"
    return code


def _action(name: str, when: str, code: str, **arguments: str) -> dict:
    optional = {key for key, text in arguments.items() if text.startswith("Optional")}
    return {"action_type": "CUSTOM_CODE", "code_name": name, "code_description": when, "code_body": code,
            "code_function_schema": {"name": name, "description": when, "strict": True, "parameters": {
                "type": "object", "additionalProperties": False, "required": [key for key in arguments if key not in optional],
                "properties": {key: {"type": "string", "description": text} for key, text in arguments.items()}}}}


NAME_ARG = f"The account holder's full name, exactly as given in the call context ({P % 'customer_name'})."


def actions(accounts: dict) -> dict[str, dict]:
    return {
        "lookup_account": _action(
            "lookup_account", "Checks the caller's date of birth against the account and returns verified and the open item. "
            "Due when date_of_birth has just been collected, or collected again, and no lookup has run since that collection.",
            _code(_LOOKUP, accounts), customer_name=NAME_ARG, date_of_birth="The collected date of birth, as YYYY-MM-DD."),
        "find_slots": _action(
            "find_slots", "Returns the open visit times on one day. Due when visit_date has just been collected, or collected "
            "again, and no search has run for that day.",
            _code(_FIND, None), visit_date="The collected visit date, as YYYY-MM-DD."),
        "book_visit": _action(
            "book_visit", "Books the visit. Due only when visit_slot has been collected and confirmed by the caller, and no "
            "booking result exists for it.",
            _code(_BOOK, accounts), customer_name=NAME_ARG, visit_date="The collected visit date, as YYYY-MM-DD.",
            slot="The collected visit_slot, word for word."),
        "save_site_details": _action(
            "save_site_details", "Saves the visit address and the on-site contact. Due when service_address and "
            "onsite_contact_name are collected and access_note was asked.",
            _code(_SAVE, accounts), customer_name=NAME_ARG, service_address="The collected service_address.",
            onsite_contact_name="The collected onsite_contact_name.", access_note="Optional. The collected access_note."),
        "save_contact_details": _action(
            "save_contact_details", "Saves the caller's contact details. Due when contact_email and contact_method are "
            "collected and alternate_phone was asked.",
            _code(_SAVE, accounts), customer_name=NAME_ARG, contact_email="The collected contact_email.",
            contact_method="The collected contact_method.", alternate_phone="Optional. The collected alternate_phone."),
        "take_payment": _action(
            "take_payment", "Charges the caller. Due only when payment_authorised has been collected as yes, and no payment "
            "result exists for this PIN.",
            _code(_PAY, accounts), customer_name=NAME_ARG, amount="The collected amount_to_pay.",
            pin="The collected payment_pin, four digits."),
    }


# ------------------------------------------------------------------------------------------------------------------ nodes
def inp(name: str, kind: str, text: str, *, required: bool = True, **settings) -> dict:
    """One Input row. `text` is the whole brief its collector reads; nothing else reaches it."""
    options = settings.pop("options", {})
    return {"variable_name": name, "variable_instructions": text, "variable_type": "string", "variable_format_instructions": "",
            "variable_enum_values": [], "configure_data_format": False,
            "collection": {"type": kind, "options": options, "required": required, **settings}}


def exit_(node: str, name: str, when: str, speech: str = "") -> dict:
    return {"id": uid("intent", node, name), "intent_name": name, "intent_instructions": when,
            "intent_speech": {"speech_enabled": bool(speech), "intent_speech_text": speech}}


RULES = """## Rules
- One question at a time. Keep every turn to one or two short sentences.
- Never ask for a value in your own words: call its collect tool and let it ask.
- Never say an account detail, a time or a result that an action on this call did not return."""
PERSON = "Let me get someone from our team on the line for you."
VERIFIED = "Only after lookup_account returned verified true: "

CHECK, BOOK, SITE, CONTACT, PAY = "Account Check", "Book Visit", "Site Details", "Contact Details", "Payment"
TRANSFER = "Transfer to Staff"

NODES = {
    CHECK: {
        "description": "Verifies the caller and sends them to the right step.",
        "instructions": f"""## Goal
Verify the caller, then send them to the right step.

## Context
- You are calling from {ORG}. The account holder is {P % 'customer_name'}, in {P % 'city'}.

## Task
1. Collect date_of_birth.
2. Run lookup_account with the account holder's name above and the date of birth.
3. If verified is false, tell the caller the date does not match the account, collect date_of_birth one more time and run lookup_account again. If verified is false a second time, select Verification Failed.
4. If lookup_account fails with an error, select Lookup Failed.
5. If verified is true and open_item is not none, do not ask what they need. Select the exit for it: book_visit is Book Visit, site_details is Site Details, contact_details is Contact Details, payment is Payment.
6. If verified is true and open_item is none, collect request_summary, then select the one exit that fits what they said.

{RULES}
- Until verified is true, say nothing from the account: no balance, no booking, no address, no date of birth on file.
- If the caller asks to speak to a person, select Human Requested. If they do not want to continue, select Caller Declines.""",
        "inputs": [
            inp("date_of_birth", "dob", "Ask for the caller's date of birth, to verify the account. It needs the day, the month and the year."),
            # optional: a required Input holds every exit back until it is collected, and this one is asked only for an account with no open item
            inp("request_summary", "text", "Ask what the caller needs help with today, in a few words: booking a technician visit, "
                "changing the visit address or the person on site, changing their own contact details, or paying their invoice.",
                required=False),
        ],
        "actions": ["lookup_account"],
        "exits": [
            ("Book Visit", VERIFIED + "its open_item is book_visit, or the caller said they want to book a technician visit.", "", BOOK),
            ("Site Details", VERIFIED + "its open_item is site_details, or the caller wants to change the visit address or the person on site.", "", SITE),
            ("Contact Details", VERIFIED + "its open_item is contact_details, or the caller wants to change their own email, phone or how they are contacted.", "", CONTACT),
            ("Payment", VERIFIED + "its open_item is payment, or the caller wants to pay their invoice.", "", PAY),
            ("Verification Failed", "lookup_account returned verified false for the second time.", "", "End Verification Failed"),
            ("Lookup Failed", "lookup_account failed with an error.", "", "End Callback"),
            ("Human Requested", "The caller asks to speak to a person.", PERSON, TRANSFER),
            ("Caller Declines", "The caller does not want to continue with the call.", "", "End Declined"),
        ],
    },
    BOOK: {
        "description": "Books a technician visit from the open times.",
        "instructions": f"""## Goal
Book a technician visit.

## Task
1. Collect visit_date.
2. Run find_slots with that date.
3. If slots is empty, tell the caller there is nothing on that day and collect visit_date again for another day. If the caller has no other day, select No Availability.
4. Collect visit_slot. Pass the slots of the latest find_slots result as its choices, word for word.
5. Run book_visit with the visit date and the chosen slot.
6. If booked is true, select Booked. The closing message tells the caller what was booked.
7. If booked is false, never say it is booked. Select Booking Failed. The closing message tells the caller.

## Facts you may share
- A visit takes about one hour. The call-out fee is 300 rupees, paid after the visit.

{RULES}
- If the caller asks to speak to a person, select Human Requested. If they no longer want a visit, select Caller Declines.""",
        "inputs": [
            inp("visit_date", "date", "Ask which day the caller wants the technician to visit. It must be a coming day, not today "
                "and not a day that has passed.", options={"accept_past": False, "accept_today": False}),
            inp("visit_slot", "choice", "Ask which of the open times the caller wants.", choices_from_call=True,
                options={"confirm_before_complete": True}),
        ],
        "actions": ["find_slots", "book_visit"],
        "exits": [
            ("Booked", "book_visit returned booked true.", "", "End Booked"),
            ("No Availability", "find_slots returned no slots and the caller has no other day.", "", "End No Availability"),
            ("Booking Failed", "book_visit returned booked false.", "", "End Booking Failed"),
            ("Human Requested", "The caller asks to speak to a person.", PERSON, TRANSFER),
            ("Caller Declines", "The caller no longer wants to book a visit.", "", "End Declined"),
        ],
    },
    SITE: {
        "description": "Takes the visit address and the person on site.",
        "instructions": f"""## Goal
Take the address for the visit and who will be there.

## Task
1. Collect service_address.
2. Collect onsite_contact_name.
3. Collect access_note. It is optional: if the caller has none, move on.
4. Run save_site_details with the values collected.
5. If saved is true, select Details Saved. The closing message tells the caller.
6. If saved is false, select Save Failed. The closing message tells the caller.

{RULES}
- If the caller asks to speak to a person, select Human Requested. If they do not want to continue, select Caller Declines.""",
        "inputs": [
            inp("service_address", "address", "Ask for the street address and city where the work is needed.",
                options={"required_fields": ["street_address", "city"]}),
            inp("onsite_contact_name", "name", "Ask for the full name of the person who will be at the property during the visit. "
                "The technician needs it to know who to ask for."),
            inp("access_note", "text", "Ask whether there is any note for the technician, such as parking or a gate. Optional.",
                required=False),
        ],
        "actions": ["save_site_details"],
        "exits": [
            ("Details Saved", "save_site_details returned saved true.", "", "End Site Saved"),
            ("Save Failed", "save_site_details returned saved false.", "", "End Callback"),
            ("Human Requested", "The caller asks to speak to a person.", "", "End Human Followup"),
            ("Caller Declines", "The caller does not want to continue.", "", "End Declined"),
        ],
    },
    CONTACT: {
        "description": "Takes the caller's own contact details.",
        "instructions": f"""## Goal
Update how {ORG} reaches the caller.

## Task
1. Collect contact_email.
2. Collect alternate_phone. It is optional: if the caller has none, move on.
3. Collect contact_method.
4. Run save_contact_details with the values collected.
5. If saved is true, select Contact Saved. The closing message tells the caller.
6. If saved is false, select Save Failed. The closing message tells the caller.

{RULES}
- If the caller asks to speak to a person, select Human Requested. If they do not want to continue, select Caller Declines.""",
        "inputs": [
            inp("contact_email", "email", "Ask for an email address for booking confirmations."),
            inp("alternate_phone", "phone", "Ask for another phone number to reach them on the day of a visit. Optional.", required=False),
            inp("contact_method", "choice", "Ask how they would like to be contacted about bookings.", choices=["Phone call", "SMS", "Email"]),
        ],
        "actions": ["save_contact_details"],
        "exits": [
            ("Contact Saved", "save_contact_details returned saved true.", "", "End Contact Saved"),
            ("Save Failed", "save_contact_details returned saved false.", "", "End Callback"),
            ("Human Requested", "The caller asks to speak to a person.", "", "End Human Followup"),
            ("Caller Declines", "The caller does not want to continue.", "", "End Declined"),
        ],
    },
    PAY: {
        "description": "Takes a payment on the open invoice.",
        "instructions": f"""## Goal
Take a payment on the caller's open invoice.

## Task
1. Collect amount_to_pay.
2. Collect installments.
3. Collect payment_pin.
4. Collect payment_authorised.
5. Only when payment_authorised is yes, run take_payment with the amount and the PIN. When it is no, never run it: select Caller Declines.
6. If paid is true, select Payment Done. The closing message tells the caller what was paid.
7. If the reason is wrong_pin, say the PIN did not match, collect payment_pin once more and run take_payment again. If it fails again, or for any other reason, select Payment Failed.

## Facts you may share
- The PIN is the four digit code the caller chose when the account was opened. It proves the payment is theirs.

{RULES}
- If the caller says they would rather book a technician visit than pay now, select Book Visit Instead.
- If the caller does not want to pay or to continue, select Caller Declines.""",
        "inputs": [
            inp("amount_to_pay", "currency", "Ask how much the caller wants to pay today, in rupees."),
            inp("installments", "number", "Ask in how many monthly installments they want to pay the rest. A whole number from 1 to 6.",
                options={"allow_decimal": False}),
            inp("payment_pin", "dtmf", "Ask for the four digit payment PIN. The caller may key it in or say the digits.", num_digits=4),
            inp("payment_authorised", "boolean", "Say the amount to be charged and ask for a clear yes or no to charge it now."),
        ],
        "actions": ["take_payment"],
        "exits": [
            ("Payment Done", "take_payment returned paid true.", "", "End Paid"),
            ("Payment Failed", "take_payment returned paid false after the PIN was asked a second time, or failed for another reason.", "", "End Payment Failed"),
            ("Book Visit Instead", "The caller says they would rather book a technician visit than pay now.", "", BOOK),
            ("Caller Declines", "The caller does not want to pay, says no to the charge, or does not want to continue.", "", "End Declined"),
        ],
    },
}

ENDS = {
    # four closings say values saved in an earlier step, so the caller hears what was stored and Hunter's judge can check it
    "End Booked": "Thank the caller, say the visit is booked for {{%s.visit_slot}} and a confirmation message will follow, then "
                  "say goodbye. Say both the day and the time." % BOOK,
    "End Site Saved": "Thank the caller and say the details are saved: the visit address is {{%s.service_address}} and the person "
                      "on site is {{%s.onsite_contact_name}}. Say the address the way a person would, with the flat or house "
                      "number, the street and the city, and leave out the state and the country. Then say goodbye." % (SITE, SITE),
    "End Contact Saved": "Thank the caller and say the details are saved: booking confirmations go to {{%s.contact_email}} and "
                         "they will be contacted by {{%s.contact_method}}. Then say goodbye." % (CONTACT, CONTACT),
    "End Paid": "Thank the caller, say the payment of {{%s.amount_to_pay}} went through, that the rest is set for "
                "{{%s.installments}} monthly installments, and that a receipt will follow, then say goodbye. Say the amount in "
                "rupees, in plain words." % (PAY, PAY),
    "End Payment Failed": "Say the payment could not be taken and nothing was charged, and that the team will call back. Then say goodbye.",
    "End Booking Failed": "Say that time could not be held, so the visit is not booked, and that the team will call back within one working day. Then say goodbye.",
    "End No Availability": "Say no visit was booked because there are no times free on the days they can do, and that they can call again any time. Then say goodbye.",
    "End Verification Failed": f"Say you could not verify the account on this call, so you cannot go further, and that they can call {ORG} support. Then say goodbye.",
    "End Callback": "Say there is a problem on our side and the team will call back. Then say goodbye.",
    "End Declined": "Acknowledge the caller's decision in one short sentence, promise nothing about future calls, thank them, then say goodbye.",
    "End Human Followup": "Say a team member will call them back shortly, thank them, then say goodbye.",
    "End Wrong Person": "Apologise for the mix-up, thank them, then say goodbye.",
    "End Try Later": f"Thank them, say {ORG} will call back at a better time, then say goodbye.",
    "End Not Reached": "Say goodbye.",
    "End Emergency": f"Tell them to get to safety and call the local emergency number now, and that {ORG} will call back later. Then say goodbye.",
    "End Transfer Done": "",
    "End Transfer Failed": "",
}
SCREEN, DIAL = "Screen Customer", "Call Customer"
EMERGENCY = "Emergency Reported"
SCREEN_CONTEXT = (f"Calling {P % 'customer_name'} from {ORG} about their home service account. Confirm you are speaking with them, "
                  "then confirm now is a good time, before anything about the account is said.")
SCREEN_EXITS = [(EMERGENCY, "The person says there is an emergency at the property right now, such as flooding, a gas smell, "
                 "sparks or a fire.", "End Emergency")]
SCREEN_PORTS = {"reached": CHECK, "wrong_contact": "End Wrong Person", "unavailable": "End Try Later", "callback": "End Try Later",
                "declined": "End Declined", "do_not_call": "End Declined", "Voicemail Detected": "End Not Reached"}
DIAL_PORTS = {"answered": SCREEN, "no_answer": "End Not Reached", "busy_rejected": "End Not Reached", "failed": "End Not Reached"}
TRANSFER_PORTS = {"completed": "End Transfer Done", "no_answer": "End Transfer Failed", "busy_rejected": "End Transfer Failed",
                  "failed": "End Transfer Failed"}
# left and top of each step on the canvas; the console draws the dial and the screening as one step, at the dial's place
PLACE = {
    "Start": (1202, 0), DIAL: (1202, 230), SCREEN: (1202, 390),
    "End Emergency": (0, 670), "End Try Later": (360, 670), "End Wrong Person": (720, 670), "End Not Reached": (1080, 670), CHECK: (1600, 670),
    PAY: (620, 971), "End Verification Failed": (1410, 971), SITE: (1940, 971), CONTACT: (2960, 971),
    "End Payment Failed": (410, 1370), "End Paid": (830, 1370), "End Callback": (1770, 1370), "End Site Saved": (2110, 1370),
    "End Human Followup": (2450, 1370), "End Contact Saved": (2790, 1370), BOOK: (620, 1590), TRANSFER: (1600, 1830),
    "End No Availability": (110, 1930), "End Booking Failed": (450, 1930), "End Booked": (790, 1930), "End Declined": (1260, 1930),
    "End Transfer Failed": (1430, 2201), "End Transfer Done": (1770, 2201),
}


def flow(accounts: dict, dial: dict, transfer: dict, settings: dict) -> dict:
    """The flow in the simulator's shape. The canvas endpoint of config-service takes the same nodes and edges.

    dial and transfer are the saved settings of a working local flow (caller id, transfer number), read at build time
    so that no number is written in this file.
    """
    tools = actions(accounts)

    def node(name: str, kind: str, config: dict) -> dict:
        return {"id": uid("node", name), "type": kind, "position": dict(zip("xy", PLACE[name])),
                "data": {"config": {"name": name, "description": "", **config}}}

    nodes = [
        node("Start", "start", {"triggers": ["http"], "payload_format": dict.fromkeys(PAYLOAD, "string"), "require_http_auth": True}),
        node(DIAL, "initiate_call", {**dial, "to": P % "phone_number", "description": "Dials the customer."}),
        node(SCREEN, "contact_screening", {
            "channel": "call", "context": SCREEN_CONTEXT, "ask_permission": True, "initial_wait_time": 2,
            "description": "Confirms the right person answered and that now is a good time.",
            "intents": [{"intent_name": name, "intent_instructions": when,
                         "intent_speech": {"speech_enabled": False, "intent_speech_text": ""}} for name, when, _ in SCREEN_EXITS],
            # the simulator reads the list at the top level, the stored node under screening_task
            "exception_intents": [name for name, _, _ in SCREEN_EXITS],
            "screening_task": {"target_name": P % "customer_name", "organization": ORG, "reason": "their home service account",
                               "extra_instructions": SCREEN_CONTEXT, "ask_permission": True,
                               "exception_intents": [name for name, _, _ in SCREEN_EXITS]}}),
        *[node(name, "ai_agent_v2", {
            "description": spec["description"], "channel": "call", "instructions": spec["instructions"], "initial_wait_time": 0,
            "allow_greeting_interruption": True, "screening_name": None, "screening_reason": None,
            "intents": [exit_(name, exit_name, when, speech) for exit_name, when, speech, _ in spec["exits"]],
            "extract_variables": spec["inputs"], "actions": [tools[tool] for tool in spec["actions"]]})
          for name, spec in NODES.items()],
        node(TRANSFER, "call_forward", {**transfer, "description": "Puts the caller through to a person."}),
        *[node(name, "end_conversation", {"end_message": message}) for name, message in ENDS.items()],
    ]
    ids = {entry["data"]["config"]["name"]: entry["id"] for entry in nodes}
    wiring = [("Start", "http", DIAL), *[(DIAL, port, target) for port, target in DIAL_PORTS.items()],
              *[(SCREEN, port, target) for port, target in SCREEN_PORTS.items()],
              *[(SCREEN, name, target) for name, _, target in SCREEN_EXITS],
              # an AI node's edge leaves by the exit's id; the server stores it under the exit's name
              *[(name, uid("intent", name, exit_name), target) for name, spec in NODES.items() for exit_name, _, _, target in spec["exits"]],
              *[(TRANSFER, port, target) for port, target in TRANSFER_PORTS.items()]]
    edges = [{"id": uid("edge", source, handle), "source": ids[source], "sourceHandle": handle, "target": ids[target]}
             for source, handle, target in wiring]
    assert len({(edge["source"], edge["sourceHandle"]) for edge in edges}) == len(edges), "one port wired twice"
    return {"name": FLOW_NAME, "flowId": uid("flow"), "attributes": {"agent_engine_version": "v2.10"},
            "agentSettings": settings, "nodes": nodes, "edges": edges}
