#!/usr/bin/env python3
"""Guarded two-case FHCSD receipt/consent probe using the production session harness.

This is an isolated AI-node text probe, not a 16-node end-to-end, HTTP, audio, or phone test.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


CASES = ("happy_booking", "decline_booking")
FROZEN_TIME = "2026-09-10T10:00:00-07:00"
PARAMS = {
    "Start.http.params.first_name": "Maya",
    "Start.http.params.last_name": "Rao",
    "Start.http.params.date_of_birth": "1980-04-12",
    "Start.http.params.phone_number": "+12025550101",
}
ACTION_NAMES = (
    "fhcsd_match_patient_fresh_auth",
    "fhcsd_get_patient_appointments_fresh_auth",
    "fhcsd_search_available_appointments_fresh_auth",
    "fhcsd_reschedule_appointment_fresh_auth",
)
MOCKS = {
    ACTION_NAMES[0]: {"operation": "patient_matching", "success": True, "status_code": 200,
                      "data": [{"MasterId": 101, "FirstName": "Maya", "LastName": "Rao",
                                "DOB": "04/12/1980", "Phone": "+12025550101"}],
                      "error": None, "patients_found": 1},
    ACTION_NAMES[1]: {"operation": "existing_appointment_retrieval", "success": True,
                      "status_code": 200, "error": None, "appointments_found": 1,
                      "data": [{"AppointmentId": 201, "AppointmentDate": "09/10/2026",
                                "AppointmentTime": "09:00 AM", "FacilityId": 301,
                                "FacilityName": "Harbor Clinic", "DepartmentId": 401,
                                "ProviderId": 501, "ProviderName": "Dr Casey", "AttributeId": 601}]},
    ACTION_NAMES[2]: {"operation": "available_appointment_search", "success": True,
                      "status_code": 200, "error": None, "slots_available": 1,
                      "window": {"start": "09-10-2026", "end": "10-10-2026"},
                      "first_available": "09-15-2026",
                      "data": [{"option": 1, "ProvScheduleId": 701,
                                "ApptDate": "09-15-2026", "FromSlotId": 801,
                                "TimeSlot": "09:00 AM", "FacilityId": 301,
                                "FacilityName": "Harbor Clinic", "DepartmentId": 401,
                                "ProviderId": 501, "ProviderName": "Dr Casey"}]},
    ACTION_NAMES[3]: {"operation": "appointment_reschedule", "success": True,
                      "status_code": 200, "data": {"Error": 0, "Id": 201},
                      "error": None, "error_code": None, "id": 201},
}
EXPECTED_SAVE = {"appointment_id": 201, "appointment_date": "09-15-2026",
                 "department_id": 401, "facility_id": 301, "from_slot_id": 801,
                 "master_id": 101, "prov_schedule_id": 701, "attribute_id": 601}
PLACEHOLDER = re.compile(r"{{\s*([^{}]+?)\s*}}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_HEAD_RE = re.compile(r"[0-9a-f]{40}")
CAMPAIGN_ID = "v29-gpt41-20260909"


class ManualReviewRequired(AssertionError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value if isinstance(value, (str, int, float, bool)) or value is None else repr(value)


def load_inputs(args: argparse.Namespace) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    if sha256(args.flow) != args.flow_sha256:
        raise RuntimeError("flow hash mismatch")
    head = subprocess.check_output(["git", "-C", str(args.source_root), "rev-parse", "HEAD"], text=True).strip()
    if head != args.source_head:
        raise RuntimeError("source head mismatch")
    from node_text_baseline import _source_identity
    source = _source_identity(args.source_root)
    if source["source_sha256"] != args.source_sha256:
        raise RuntimeError("source content hash mismatch")
    flow = json.loads(args.flow.read_text())
    nodes = [n for n in flow.get("nodes", []) if n.get("type") == "ai_agent_v29"]
    if len(nodes) != 1 or len(flow.get("nodes", [])) != 16:
        raise RuntimeError("candidate must contain 16 nodes and exactly one ai_agent_v29")
    config = deepcopy(nodes[0]["data"]["config"])
    used: set[str] = set()

    def render(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: render(v) for k, v in value.items()}
        if isinstance(value, list):
            return [render(v) for v in value]
        if not isinstance(value, str):
            return value
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in PARAMS:
                raise RuntimeError(f"unresolved placeholder {key}")
            used.add(key)
            return PARAMS[key]
        return PLACEHOLDER.sub(replace, value)

    config = render(config)
    if used != set(PARAMS) or PLACEHOLDER.search(json.dumps(config)):
        raise RuntimeError("placeholder resolution was not exact")
    if {a.get("code_name") for a in config.get("actions", [])} != set(ACTION_NAMES):
        raise RuntimeError("candidate action set mismatch")
    config["llm_model_config"] = {"provider": "azure", "model": "gpt-4.1"}
    return source, flow, config


def arguments(call: dict[str, Any]) -> dict[str, Any]:
    value = call.get("arguments", {})
    return json.loads(value) if isinstance(value, str) else value


def output_value(call: dict[str, Any]) -> Any:
    value = call.get("output")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def contains_pinned_slot(speech: str) -> bool:
    return all(re.search(pattern, speech, re.I) for pattern in (
        r"09[/ -]15[/ -]2026|september\s+(?:15|fifteenth)",
        r"9(?::00)?\s*a\.?m\.?|nine.*morning", r"casey", r"harbor\s+clinic"))


class GatedCaller:
    def __init__(self, booking: bool):
        self.booking = booking
        self.opened = False
        self.replied: set[str] = set()
        self.pending_delivery: tuple[str, str] | None = None
        self.post_save_replied = False

    def __call__(self, trace: Any) -> str | None:
        if not self.opened:
            self.opened = True
            return "Please go ahead."
        state = trace.states[-1] if trace.states else {}
        collector = (state.get("collector") or {}).get("name")
        ordinal = state.get("ordinal")
        requests = [r for r in trace.model_calls if (r.get("collector") or {}).get("name") == collector
                    and r.get("caller_turn") == ordinal]
        speech = str(requests[-1].get("speech", "")).lower() if requests else ""
        replies = {
            "dob_confirmed": "My date of birth is April 12, 1980.",
            "wants_to_reschedule": "Yes.",
            "selected_slot": "Option 1.",
            "booking_confirmed": "Yes." if self.booking else "No.",
        }
        if collector in replies and collector not in self.replied:
            if not requests:
                raise ManualReviewRequired(f"{collector} active without current collector speech")
            if collector == "booking_confirmed":
                requirements = (r"september\s+(?:15|fifteenth)", r"(?:9|nine).*(?:a\.?m\.?|morning)",
                                r"casey", r"harbor\s+clinic")
                if any(re.search(pattern, speech) is None for pattern in requirements):
                    raise ManualReviewRequired("booking question did not contain the whole chosen booking")
            self.replied.add(collector)
            reply = replies[collector]
            self.pending_delivery = (collector, "yes" if reply == "Yes." else
                                      "no" if reply == "No." else reply)
            return reply
        if self.booking and ACTION_NAMES[3] in [c.get("name") for c in trace.executed]:
            if self.post_save_replied:
                if intent_seen(trace, "rescheduled"):
                    return None
                raise ManualReviewRequired("expected Rescheduled handoff after the final reply")
            main_requests = [r for r in trace.model_calls if r.get("collector") is None]
            speech = str(main_requests[-1].get("speech", "")).lower() if main_requests else ""
            if "anything else" not in speech:
                raise ManualReviewRequired("save completed without observed anything-else question")
            self.post_save_replied = True
            self.pending_delivery = ("post_save_anything_else", "no thanks")
            return "No thanks."
        if not self.booking and "booking_confirmed" in self.replied:
            if intent_seen(trace, "declined"):
                return None
            raise ManualReviewRequired("expected Declined handoff after booking no")
        raise ManualReviewRequired("no authorized caller reply for the observed state")

    def record_delivery(self, trace: Any, ordinal: int) -> None:
        if self.pending_delivery is not None:
            field, value = self.pending_delivery
            trace.events.append({"kind": "probe_reply", "field": field, "value": value,
                                 "caller_turn": ordinal})
            self.pending_delivery = None


def intent_seen(trace: Any, fragment: str) -> bool:
    return any(fragment in str(call.get("name", "")).lower()
               for call in [*trace.emitted, *trace.executed])


def evaluate(case_id: str, trace: Any) -> dict[str, Any]:
    if trace.observation_failures or trace.cleanup_failures:
        raise AssertionError(f"trace failures: {trace.observation_failures + trace.cleanup_failures}")
    calls = [c for c in trace.executed if c.get("name")]
    names = [c["name"] for c in calls]
    action_calls = [c for c in calls if c["name"] in ACTION_NAMES]
    action_names = [c["name"] for c in action_calls]
    expected = list(ACTION_NAMES if case_id == "happy_booking" else ACTION_NAMES[:3])
    if action_names != expected:
        raise AssertionError(f"action order mismatch: {action_names}")
    for call in action_calls:
        if output_value(call) != MOCKS[call["name"]]:
            raise AssertionError(f"action did not return its pinned mock: {call['name']}")
    lookup_args = {call["name"]: arguments(call) for call in action_calls}
    required_sources = {
        ACTION_NAMES[0]: {"first_name": "Maya", "last_name": "Rao", "phone_number": "+12025550101"},
        ACTION_NAMES[1]: {"master_id": "101"},
        ACTION_NAMES[2]: {"master_id": "101", "facility_id": "301", "department_id": "401",
                          "provider_id": "501", "attribute_id": "601", "appointment_id": "201"},
    }
    for name, required in required_sources.items():
        actual = lookup_args.get(name, {})
        for key, value in required.items():
            if str(actual.get(key)) != value:
                raise AssertionError(f"{name}.{key} did not come from the pinned inputs/mocks")
    if lookup_args[ACTION_NAMES[0]].get("date_of_birth") != "04/12/1980":
        raise AssertionError("patient match DOB was not the patient's normalized answer")
    search_args = lookup_args[ACTION_NAMES[2]]
    if search_args.get("start_date") is not None or search_args.get("end_date") is not None or search_args.get("appt_type_id") != "0":
        raise AssertionError("initial search did not use null dates and appt_type_id 0")
    events = trace.events
    match_emissions = [(i, e) for i, e in enumerate(events)
                       if e.get("kind") == "emitted" and e.get("name") == ACTION_NAMES[0]]
    if len(match_emissions) != 1:
        raise AssertionError("patient match emission missing or repeated")
    match_index = match_emissions[0][0]
    dob_stores = [(i, e) for i, e in enumerate(events[:match_index])
                  if e.get("kind") == "store" and e.get("name") == "dob_confirmed"]
    dob_replies = [(i, e) for i, e in enumerate(events[:match_index])
                   if e.get("kind") == "probe_reply" and e.get("field") == "dob_confirmed"]
    stored_dob = str(dob_stores[-1][1].get("value", "")) if dob_stores else ""
    if (not dob_stores or stored_dob not in ("1980-04-12", "04/12/1980")
            or not dob_replies or dob_replies[-1][0] >= dob_stores[-1][0]):
        raise AssertionError("patient match occurred before patient DOB collector store")
    first_dob = next((arguments(c) for c in calls if c["name"] == "collect_input"
                      and arguments(c).get("name") == "dob_confirmed"), None)
    if first_dob is None or first_dob.get("known_value") is not None:
        raise AssertionError("DOB was seeded before the patient supplied it")
    selected = next((arguments(c) for c in calls if c["name"] == "collect_input"
                     and arguments(c).get("name") == "selected_slot"), None)
    if selected is None:
        raise AssertionError("selected_slot collector missing")
    options = {k: v for k, v in (selected.get("options") or {}).items() if v is not None}
    if options != {"present_options": False, "confirm_before_complete": False,
                   "receipt_shape": "acknowledge"}:
        raise AssertionError(f"selected_slot options mismatch: {options}")
    selected_emissions = [e for e in trace.emitted if e.get("name") == "collect_input"
                          and arguments(e).get("name") == "selected_slot"
                          and e.get("request") is not None]
    if len(selected_emissions) != 1:
        raise AssertionError("selected_slot collector emission missing or repeated")
    selected_parent_speech = str(trace.model_calls[selected_emissions[0]["request"]].get("speech", ""))
    if "?" in selected_parent_speech or "？" in selected_parent_speech:
        raise AssertionError("selected_slot question was asked by the parent")
    selected_replies = [e for e in trace.events if e.get("kind") == "probe_reply"
                        and e.get("field") == "selected_slot"]
    selected_collectors = [r for r in trace.model_calls
                           if (r.get("collector") or {}).get("name") == "selected_slot"]
    if not selected_replies or not selected_collectors:
        raise AssertionError("selected_slot collector speech/reply evidence missing")
    selected_collector_speech = str(selected_collectors[0].get("speech", ""))
    if (selected_collectors[0].get("caller_turn", -1) >= selected_replies[0].get("caller_turn", -1)
            or contains_pinned_slot(selected_collector_speech)):
        raise AssertionError("selected_slot collector repeated the pinned slot before the reply")
    if any(n == "confirm_choice" for n in names):
        raise AssertionError("choice collector added a confirmation")
    save_events = [(i, e) for i, e in enumerate(events)
                   if e.get("kind") == "emitted" and e.get("name") == ACTION_NAMES[3]]
    saves = [(i, arguments(c)) for i, c in enumerate(calls) if c["name"] == ACTION_NAMES[3]]
    if case_id == "happy_booking":
        if len(saves) != 1 or len(save_events) != 1:
            raise AssertionError("save must be emitted and executed exactly once")
        save_event_index = save_events[0][0]
        prior_stores = [(i, e) for i, e in enumerate(events[:save_event_index])
                        if e.get("kind") == "store" and e.get("name") == "booking_confirmed"]
        if not prior_stores or str(prior_stores[-1][1].get("value", "")).lower() != "yes":
            raise AssertionError("save lacks latest booking_confirmed=yes store")
        prior_replies = [(i, e) for i, e in enumerate(events[:save_event_index])
                         if e.get("kind") == "probe_reply" and e.get("field") == "booking_confirmed"]
        if not prior_replies or prior_replies[-1][1].get("value") != "yes" or prior_replies[-1][0] >= prior_stores[-1][0]:
            raise AssertionError("save lacks patient booking yes delivered before its store")
        if saves[0][1] != EXPECTED_SAVE:
            raise AssertionError(f"save IDs did not come from mocks: {saves[0][1]}")
        save_executions = [i for i, e in enumerate(events)
                           if e.get("kind") == "executed" and e.get("name") == ACTION_NAMES[3]]
        final_replies = [i for i, e in enumerate(events)
                         if e.get("kind") == "probe_reply"
                         and e.get("field") == "post_save_anything_else"]
        handoffs = [i for i, e in enumerate(events)
                    if e.get("kind") == "emitted" and "rescheduled" in str(e.get("name", "")).lower()]
        if (len(save_executions) != 1 or len(final_replies) != 1 or len(handoffs) != 1
                or not save_executions[0] < final_replies[0] < handoffs[0]):
            raise AssertionError("Rescheduled handoff must follow the single post-save caller reply")
    elif saves:
        raise AssertionError("decline case called save")
    collect_wants = [e for e in trace.emitted if e.get("name") == "collect_input"
                     and arguments(e).get("name") == "wants_to_reschedule" and e.get("request") is not None]
    if len(collect_wants) != 1:
        raise AssertionError("wants_to_reschedule collector emission missing or repeated")
    emission = collect_wants[0]
    emission_index = next(i for i, e in enumerate(events) if e.get("kind") == "emitted"
                          and e.get("call_id") == emission.get("call_id"))
    appt_exec = [i for i, e in enumerate(events[:emission_index]) if e.get("kind") == "executed"
                 and e.get("name") == ACTION_NAMES[1]]
    speech = str(trace.model_calls[emission["request"]].get("speech", ""))
    factual = all(re.search(p, speech, re.I) for p in (r"09[/ -]10[/ -]2026|september\s+(?:10|tenth)",
                  r"9(?::00)?\s*a\.?m\.?|nine.*morning", r"casey", r"harbor\s+clinic"))
    if not appt_exec or not factual or "?" in speech or "？" in speech or re.search(r"reschedul.*\?", speech, re.I):
        raise AssertionError("appointment disclosure and reschedule collector ownership mismatch")
    if case_id == "decline_booking":
        booking_collects = [c for c in calls if c["name"] == "collect_input"
                            and arguments(c).get("name") == "booking_confirmed"]
        if len(booking_collects) != 1:
            raise AssertionError("booking decline caused repeated confirmation")
    if case_id == "happy_booking":
        save_event_index = save_events[0][0]
        later = " ".join(str(e.get("content", "")) for e in events[save_event_index + 1:]
                         if e.get("kind") in ("model_speech", "message")).lower()
        if all(piece in later for piece in ("september", "nine", "casey", "harbor")):
            raise AssertionError("success response repeated the full booking")
        if not intent_seen(trace, "rescheduled"):
            raise AssertionError("happy case did not emit or execute Rescheduled handoff")
    elif not intent_seen(trace, "declined"):
        raise AssertionError("decline case did not emit or execute Declined handoff")
    return {"action_order": action_names, "save_count": len(saves),
            "selected_options": options, "manual_review": True}


def self_check(config: dict[str, Any]) -> None:
    if set(MOCKS) != set(ACTION_NAMES) or any(not isinstance(MOCKS[n], dict) for n in ACTION_NAMES):
        raise AssertionError("all four custom actions require complete mocks")
    if len(config.get("actions", [])) != 4:
        raise AssertionError("node config lost action schemas")
    def call(name, args, output=None):
        return {"call_id": name, "name": name, "arguments": json.dumps(args), "output": output}
    executed = [
        call("collect_input", {"name": "dob_confirmed", "known_value": None}),
        call(ACTION_NAMES[0], {"first_name": "Maya", "last_name": "Rao", "date_of_birth": "04/12/1980",
                               "phone_number": "+12025550101"}, MOCKS[ACTION_NAMES[0]]),
        call(ACTION_NAMES[1], {"master_id": "101"}, MOCKS[ACTION_NAMES[1]]),
        call(ACTION_NAMES[2], {"master_id": "101", "facility_id": "301", "department_id": "401",
                               "provider_id": "501", "start_date": None, "end_date": None,
                               "attribute_id": "601", "appt_type_id": "0", "appointment_id": "201"},
             MOCKS[ACTION_NAMES[2]]),
        call("collect_input", {"name": "selected_slot", "options": {"present_options": False,
             "confirm_before_complete": False, "receipt_shape": "acknowledge"}}),
        call("collect_input", {"name": "booking_confirmed"}),
        call(ACTION_NAMES[3], EXPECTED_SAVE, MOCKS[ACTION_NAMES[3]]),
        call("handoff_rescheduled", {}),
    ]
    events = [
        {"kind": "probe_reply", "field": "dob_confirmed", "value": "My date of birth is April 12, 1980."},
        {"kind": "store", "name": "dob_confirmed", "value": "1980-04-12"},
        {"kind": "emitted", "name": ACTION_NAMES[0], "call_id": "match", "request": 0},
        {"kind": "executed", "name": ACTION_NAMES[1]},
        {"kind": "emitted", "name": "collect_input", "call_id": "wants", "request": 1,
         "arguments": json.dumps({"name": "wants_to_reschedule"})},
        {"kind": "emitted", "name": "collect_input", "call_id": "selected", "request": 2,
         "arguments": json.dumps({"name": "selected_slot"})},
        {"kind": "probe_reply", "field": "selected_slot", "value": "Option 1.", "caller_turn": 4},
        {"kind": "probe_reply", "field": "booking_confirmed", "value": "yes"},
        {"kind": "store", "name": "booking_confirmed", "value": "yes"},
        {"kind": "emitted", "name": ACTION_NAMES[3], "call_id": "save", "request": 4},
        {"kind": "executed", "name": ACTION_NAMES[3]},
        {"kind": "model_speech", "content": "Your appointment was rescheduled. Anything else?"},
        {"kind": "probe_reply", "field": "post_save_anything_else", "value": "no thanks"},
        {"kind": "emitted", "name": "handoff_rescheduled", "call_id": "handoff", "request": 5},
    ]
    emitted = [events[2], events[4], events[5], events[9], events[13]]
    fake = SimpleNamespace(executed=executed, emitted=emitted, events=events, messages=[], turns=[],
        stores=[], states=[], observation_failures=[], cleanup_failures=[], model_calls=[
            {"speech": ""},
            {"speech": "You missed your September 10 2026 appointment at 9 AM with Dr Casey at Harbor Clinic."},
            {"caller_turn": 3, "collector": None, "speech": "One available slot follows."},
            {"caller_turn": 3, "collector": {"name": "selected_slot"}, "speech": "Which option would you like?"},
            {"speech": "Your appointment was rescheduled. Anything else?"},
        ])
    evaluate("happy_booking", fake)
    for mutation in ("false", "remove", "after"):
        broken = deepcopy(fake)
        store = next(e for e in broken.events if e.get("kind") == "store"
                     and e.get("name") == "booking_confirmed")
        if mutation == "false": store["value"] = "no"
        elif mutation == "remove": broken.events.remove(store)
        else:
            broken.events.remove(store); broken.events.append(store)
        try: evaluate("happy_booking", broken)
        except AssertionError as exc:
            if "booking_confirmed=yes store" not in str(exc): raise
        else: raise AssertionError(f"consent mutation {mutation} passed")
    questioned = deepcopy(fake)
    wants_request = next(e["request"] for e in questioned.emitted
                         if e.get("name") == "collect_input"
                         and arguments(e).get("name") == "wants_to_reschedule")
    questioned.model_calls[wants_request]["speech"] += " Would you like to reschedule?"
    try: evaluate("happy_booking", questioned)
    except AssertionError as exc:
        if "ownership mismatch" not in str(exc): raise
    else: raise AssertionError("parent-question mutation passed")
    parent_choice = deepcopy(fake)
    parent_choice.model_calls[2]["speech"] += " Which option would you like?"
    try: evaluate("happy_booking", parent_choice)
    except AssertionError as exc:
        if "asked by the parent" not in str(exc): raise
    else: raise AssertionError("selected parent-question mutation passed")
    repeated_choice = deepcopy(fake)
    repeated_choice.model_calls[3]["speech"] = (
        "September fifteenth 2026 at nine in the morning with Dr Casey at Harbor Clinic. Which option?")
    try: evaluate("happy_booking", repeated_choice)
    except AssertionError as exc:
        if "repeated the pinned slot" not in str(exc): raise
    else: raise AssertionError("selected repeated-slot mutation passed")
    seeded = deepcopy(fake); seeded.executed[0]["arguments"] = json.dumps({"name": "dob_confirmed", "known_value": "1980-04-12"})
    try: evaluate("happy_booking", seeded)
    except AssertionError as exc:
        if "DOB was seeded" not in str(exc): raise
    else: raise AssertionError("DOB seed mutation passed")
    bypassed = deepcopy(fake)
    bypassed.events = [e for e in bypassed.events if e.get("name") != "dob_confirmed" and e.get("field") != "dob_confirmed"]
    try: evaluate("happy_booking", bypassed)
    except AssertionError as exc:
        if "DOB collector store" not in str(exc): raise
    else: raise AssertionError("DOB bypass mutation passed")
    reordered = deepcopy(fake)
    match = next(e for e in reordered.events if e.get("name") == ACTION_NAMES[0])
    reordered.events.remove(match); reordered.events.insert(0, match)
    try: evaluate("happy_booking", reordered)
    except AssertionError as exc:
        if "DOB collector store" not in str(exc): raise
    else: raise AssertionError("early patient match mutation passed")
    missing_reply = deepcopy(fake)
    missing_reply.events = [e for e in missing_reply.events
                            if e.get("field") != "post_save_anything_else"]
    try: evaluate("happy_booking", missing_reply)
    except AssertionError as exc:
        if "post-save caller reply" not in str(exc): raise
    else: raise AssertionError("missing final reply mutation passed")
    early_handoff = deepcopy(fake)
    handoff = next(e for e in early_handoff.events
                   if e.get("kind") == "emitted" and e.get("name") == "handoff_rescheduled")
    early_handoff.events.remove(handoff); early_handoff.events.insert(9, handoff)
    try: evaluate("happy_booking", early_handoff)
    except AssertionError as exc:
        if "post-save caller reply" not in str(exc): raise
    else: raise AssertionError("early Rescheduled handoff mutation passed")
    decline_executed = deepcopy(executed[:-2]) + [call("handoff_declined", {})]
    decline_events = deepcopy(events[:9])
    next(e for e in decline_events if e.get("field") == "booking_confirmed")["value"] = "no"
    next(e for e in decline_events if e.get("name") == "booking_confirmed")["value"] = "no"
    decline_emitted = [decline_events[2], decline_events[4], decline_events[5],
                       {"name": "handoff_declined", "arguments": "{}"}]
    decline = SimpleNamespace(executed=decline_executed, emitted=decline_emitted,
        events=decline_events, messages=[], turns=[], stores=[], states=[],
        observation_failures=[], cleanup_failures=[], model_calls=deepcopy(fake.model_calls[:4]))
    evaluate("decline_booking", decline)
    caller = GatedCaller(True); caller.opened = True; caller.replied = set()
    caller.replied.update({"dob_confirmed", "wants_to_reschedule", "selected_slot", "booking_confirmed"})
    caller_trace = deepcopy(fake)
    caller_trace.emitted = [e for e in caller_trace.emitted if "rescheduled" not in str(e.get("name", "")).lower()]
    caller_trace.executed = [e for e in caller_trace.executed if "rescheduled" not in str(e.get("name", "")).lower()]
    caller_trace.model_calls.append({"collector": None, "speech": "Anything else?"})
    assert caller(caller_trace) == "No thanks."
    try: caller(caller_trace)
    except ManualReviewRequired: pass
    else: raise AssertionError("caller repeated No thanks without a handoff")


async def execute(args: argparse.Namespace, source: dict[str, str], config: dict[str, Any]) -> int:
    from src.agent_factory import _build_llm
    from src.config.settings import app_settings
    from tests.v29_model_eval import budget as guard
    from tests.v29_model_eval.live import _error_category, _ledger_summary, _resolved, _write_row
    from tests.v29_model_eval.session_runner import SessionCase, run_session
    if os.environ.get("V29_EVAL_PROVIDER") != "azure" or os.environ.get("V29_EVAL_MODEL") != "gpt-4.1":
        raise RuntimeError("V29_EVAL_PROVIDER/model must be azure/gpt-4.1")
    if not app_settings.azure_openai_endpoint or not app_settings.azure_openai_api_key:
        raise RuntimeError("Azure app environment is not configured")
    failed = False
    stopped = False
    with args.output.open("x") as output:
        with guard.guarded_httpx_campaign(azure_origin=app_settings.azure_openai_endpoint,
                                          deployment="gpt-4.1", ledger_path=args.ledger,
                                          campaign_id=args.campaign_id) as request_ids:
            for case_id in args.case:
                before = len(request_ids); caller = GatedCaller(case_id == "happy_booking"); built = []
                row = {"case_id": case_id, "source": source, "flow_sha256": args.flow_sha256,
                       "adapter_sha256": sha256(Path(__file__)), "scope": "isolated_ai_node_text_not_16_node_e2e",
                       "structural_status": "failed", "speech_review_status": "manual_review_required"}
                trace = None
                error: BaseException | None = None
                try:
                    def factory(*a: Any, **kw: Any) -> Any:
                        model = _build_llm(*a, **kw); _resolved(model); built.append(model); return model
                    trace = await run_session(SessionCase(id=case_id, node_config=deepcopy(config),
                        caller_driver=caller, action_mocks=deepcopy(MOCKS), required_values={},
                        max_caller_turns=12, max_model_requests=30, frozen_time=FROZEN_TIME), model_factory=factory)
                    row["trace"] = jsonable(trace)
                    row["checks"] = evaluate(case_id, trace)
                    row["structural_status"] = "passed"
                except BaseException as exc:
                    error = exc; failed = True
                    row["error"] = {"category": _error_category(exc, guard), "type": type(exc).__name__}
                    if isinstance(exc, AssertionError):
                        row["error"]["oracle_detail"] = str(exc)[:1000]
                    trace = trace or getattr(exc, "trace", None)
                    if trace is not None:
                        row["trace"] = jsonable(trace)
                finally:
                    row["ledger"] = _ledger_summary(args.ledger, request_ids=request_ids[before:])
                    resolved_error = None
                    try:
                        resolved = [_resolved(instance) for instance in built]
                        row["resolved"] = {
                            "models": sorted({item for group in resolved for item in group[0]}),
                            "providers": sorted({item for group in resolved for item in group[1]}),
                            "classes": sorted({item for group in resolved for item in group[2]}),
                        }
                    except BaseException as exc:
                        resolved_error = type(exc).__name__
                        row["resolved_error_type"] = resolved_error
                    owned = row["ledger"].get("request_delta", 0)
                    verified = (owned >= 1 and row["ledger"].get("model_verified_count") == owned
                                and row["ledger"].get("settled_count") == owned
                                and row["ledger"].get("campaign_failure") is None and not resolved_error)
                    if not verified:
                        failed = True; row["structural_status"] = "failed"
                        row["error"] = {"category": "model_identity",
                                        "type": "UnsettledOrUnverifiedOwnedRequest"}
                    _write_row(output, row)
                safe_oracle = (isinstance(error, AssertionError) and verified and trace is not None
                               and not trace.observation_failures and not trace.cleanup_failures
                               and getattr(error, "cleanup_error", None) is None)
                if row["structural_status"] == "failed" and not safe_oracle:
                    stopped = True
                    break
    print(json.dumps({"output": str(args.output), "status": "failed" if failed else "passed",
                      "stopped_early": stopped}, sort_keys=True))
    return int(failed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--flow", required=True, type=Path)
    parser.add_argument("--flow-sha256", required=True)
    parser.add_argument("--case", action="append", choices=CASES, default=[])
    parser.add_argument("--env-file", type=Path); parser.add_argument("--ledger", type=Path)
    parser.add_argument("--campaign-id"); parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute and (not args.case or len(args.case) != len(set(args.case))):
        parser.error("--execute requires a nonempty unique case selection")
    if args.execute and not all((args.env_file, args.ledger, args.campaign_id, args.output)):
        parser.error("--execute requires env-file, ledger, campaign-id, and output")
    if args.execute and (not args.env_file.is_file() or not args.ledger.is_file()):
        parser.error("env-file and ledger must already exist")
    if args.execute and args.output.exists():
        parser.error("output exists; JSONL is exclusive and immutable")
    if args.execute and len({args.env_file.resolve(), args.ledger.resolve(), args.output.resolve()}) != 3:
        parser.error("env-file, ledger, and output paths must be distinct")
    if (not GIT_HEAD_RE.fullmatch(args.source_head)
            or not SHA256_RE.fullmatch(args.source_sha256)
            or not SHA256_RE.fullmatch(args.flow_sha256)):
        parser.error("source HEAD and SHA-256 pins must be full lowercase hexadecimal")
    if args.execute:
        ledger = json.loads(args.ledger.read_text())
        if args.campaign_id != CAMPAIGN_ID or ledger.get("campaign_id") != CAMPAIGN_ID:
            parser.error("campaign must use the existing canonical ledger")
        if str(ledger.get("conservative_ceiling_usd")) != "200.000000000":
            parser.error("canonical campaign ceiling must remain 200 USD")
        if int(ledger.get("request_count", 0)) <= 0 or float(ledger.get("conservative_spent_usd", 0)) <= 0:
            parser.error("canonical campaign ledger must retain prior spend")
    return args


def main() -> int:
    args = parse_args()
    while str(args.source_root) in sys.path:
        sys.path.remove(str(args.source_root))
    sys.path.insert(0, str(args.source_root))
    source, _flow, config = load_inputs(args)
    self_check(config)
    if not args.execute:
        print(json.dumps({"source": source, "flow_sha256": args.flow_sha256,
                          "adapter_sha256": sha256(Path(__file__)), "cases": CASES,
                          "actions_mocked": ACTION_NAMES, "scope": "isolated_ai_node_text_not_16_node_e2e"}, indent=2))
        return 0
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=True)
    return asyncio.run(execute(args, source, config))


if __name__ == "__main__":
    raise SystemExit(main())
