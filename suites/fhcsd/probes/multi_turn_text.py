#!/usr/bin/env python3
"""Guarded multi-turn text probes for two Family Health V2.9 nodes.

This is an isolated-node evaluation with synthetic caller data. It does not
execute HTTP actions, prove the full 41-node graph, or exercise voice/audio.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import node_text_baseline as baseline


SOURCE_ROOT = Path(
    "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/"
    "FHCSD/v29-fixes-runtime"
)
SOURCE_HEAD = "415aa7d5fcb1e42a6e79bb7f245ddebfed295c00"
SOURCE_SHA256 = "8df972b2b4834a2e8ac4fcf006866730bd78410a9876a424d892cc86256bee5b"
FLOW_PATH = Path(
    "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/"
    "FHCSD/flows/fhcsd-v29-candidate-mock.json"
)
FLOW_SHA256 = "61658a8c02092c8348a3e034112b4689d6adb5389147f9a659eca405ef786412"
FROZEN_TIME = baseline.FROZEN_TIME
CHOOSE_NODE = baseline.CHOOSE_NODE
FOLLOWUP_NODE = "23a7c101-c2b5-573d-8531-9ec0c24e7a80"

OPTION_FACTS = {
    "option 1": ("09/15/2026", "09:00 AM", "Dr Casey", "Harbor Clinic"),
    "option 2": ("09/16/2026", "02:30 PM", "Dr Morgan", "Cedar Clinic"),
    "option 3": ("09/17/2026", "11:00 AM", "Dr Avery", "Bay Clinic"),
}

CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "choose_fresh_yes", "node": "choose",
        "initial": "I choose option 1, but do not book it until you have read the details back.",
        "expected_slot": "option 1", "expected_intent": "book", "path": "fresh_yes",
    },
    {
        "id": "choose_decline", "node": "choose", "initial": "I choose option 1.",
        "expected_slot": "option 1", "expected_intent": "Patient Declines", "path": "decline",
    },
    {
        "id": "choose_tentative_consent", "node": "choose", "initial": "I choose option 1.",
        "expected_slot": "option 1", "expected_intent": "Patient Declines", "path": "tentative",
    },
    {
        "id": "choose_change_before_consent", "node": "choose", "initial": "I choose option 1.",
        "expected_slot": "option 2", "expected_intent": "book", "path": "change",
    },
    {
        "id": "choose_invalid_option", "node": "choose", "initial": "I want option 4.",
        "expected_slot": "option 2", "expected_intent": "book", "path": "invalid",
    },
    {
        "id": "choose_conditional_consent", "node": "choose", "initial": "I choose option 1.",
        "expected_slot": "option 1", "expected_intent": "Patient Declines", "path": "conditional",
        "forbid_fee_claims": True,
    },
    {
        "id": "followup_no_more_help", "node": "followup", "initial": "I am still here.",
        "expected_intent": "Done", "path": "no_more_help",
    },
    {
        "id": "followup_factual_help", "node": "followup", "initial": "I am still here.",
        "expected_intent": "Done", "path": "factual_help",
    },
    {
        "id": "followup_new_booking", "node": "followup", "initial": "I am still here.",
        "expected_intent": "Changes or New Booking", "path": "new_booking",
    },
    {
        "id": "followup_person", "node": "followup", "initial": "I am still here.",
        "expected_intent": "Human Requested", "path": "person",
    },
    {
        "id": "followup_emergency", "node": "followup", "initial": "I am still here.",
        "expected_intent": "Emergency Mentioned", "path": "emergency",
    },
)
CASES_BY_ID = {case["id"]: case for case in CASES}

_SAFE_CAMPAIGN = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_HEAD = re.compile(r"^[0-9a-f]{40}$")


class MultiTurnOracleError(baseline.ProbeOracleError):
    """A bounded behavioral oracle failed with an immutable trace available."""

    def __init__(self, message: str, *, checks: dict[str, Any] | None = None):
        super().__init__(message)
        self.checks = checks


class CallerWordingReview(baseline.ProbeOracleError):
    """The response did not safely satisfy a caller-delivery wording gate."""


def _node_id(case: dict[str, Any]) -> str:
    return CHOOSE_NODE if case["node"] == "choose" else FOLLOWUP_NODE


def _latest_speech(trace: Any, ordinal: int) -> str:
    messages = [
        str(event.get("content") or "")
        for event in trace.events
        if event.get("kind") == "message"
        and event.get("role") == "assistant"
        and event.get("caller_turn") == ordinal
        and str(event.get("content") or "").strip()
    ]
    if messages:
        return messages[-1]
    requests = [
        call for call in trace.model_calls
        if call.get("caller_turn") == ordinal and str(call.get("speech") or "").strip()
    ]
    if requests:
        return str(requests[-1]["speech"])
    return ""


def _turn_speech(trace: Any, ordinal: int) -> str:
    return " ".join(
        str(call.get("speech") or "")
        for call in trace.model_calls
        if call.get("caller_turn") == ordinal and str(call.get("speech") or "").strip()
    )


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _has_fact(text: str, fact: str) -> bool:
    normalized = _normalized(text)
    date_alternatives: dict[str, tuple[str, ...]] = {
        "09/15/2026": ("09 15 2026", "september 15", "september fifteenth"),
        "09/16/2026": ("09 16 2026", "september 16", "september sixteenth"),
        "09/17/2026": ("09 17 2026", "september 17", "september seventeenth"),
    }
    if fact in date_alternatives:
        years = re.findall(r"\b(?:19|20)\d{2}\b", normalized)
        return (not years or set(years) == {"2026"}) and any(
            re.search(rf"\b{re.escape(value)}(?:st|nd|rd|th)?\b", normalized)
            for value in date_alternatives[fact]
        )
    time_alternatives: dict[str, tuple[str, ...]] = {
        "09:00 AM": ("09 00 am", "9 00 am", "9 am", "9 a m", "nine am", "nine a m", "nine in the morning"),
        "02:30 PM": ("02 30 pm", "2 30 pm", "2 30 p m", "two thirty pm", "two thirty p m", "two thirty in the afternoon"),
        "11:00 AM": ("11 00 am", "11 am", "11 a m", "eleven am", "eleven a m", "eleven in the morning"),
    }
    if fact in time_alternatives:
        return any(re.search(rf"\b{re.escape(value)}\b", normalized) for value in time_alternatives[fact])
    if fact.startswith("Dr "):
        surname = _normalized(fact[3:])
        return re.search(rf"\b(?:dr|doctor) {re.escape(surname)}\b", normalized) is not None
    return re.search(rf"\b{re.escape(_normalized(fact))}\b", normalized) is not None


def _facts_present(text: str, option: str) -> bool:
    return all(_has_fact(text, fact) for fact in OPTION_FACTS[option])


def _handoffs(trace: Any) -> list[str]:
    return [
        call["name"]
        for call in trace.executed
        if str(call.get("name") or "").startswith("handoff_")
    ]


def _stores(trace: Any, name: str) -> list[dict[str, Any]]:
    return [item for item in trace.stores if item.get("name") == name]


def _latest_collect(trace: Any, field: str) -> dict[str, Any] | None:
    for call in reversed(trace.emitted):
        if call.get("name") != "collect_input":
            continue
        args = call.get("effective_arguments") or baseline._args(call)
        if args.get("name") == field:
            return call
    return None


def _active_owner(trace: Any, field: str, task_type: str, ordinal: int) -> bool:
    if not trace.states:
        return False
    state = trace.states[-1]
    owner = {"name": field, "task_type": task_type}
    if state.get("collector") != owner or state.get("ordinal") != ordinal:
        return False
    try:
        from src.units.tasks.collectors import REGISTRY
        cls = REGISTRY[task_type].cls
    except (KeyError, AttributeError):
        return False
    expected = f"{cls.__module__}.{cls.__qualname__}"
    if state.get("agent") != expected:
        return False
    requests = [
        call for call in trace.model_calls
        if call.get("caller_turn") == ordinal and call.get("collector") == owner
    ]
    if not requests or not str(requests[-1].get("speech") or "").strip():
        return False
    speech_indexes = [
        index for index, event in enumerate(trace.events)
        if event.get("kind") == "model_speech"
        and event.get("caller_turn") == ordinal
        and event.get("collector") == owner
    ]
    if not speech_indexes:
        return False
    speech_index = speech_indexes[-1]
    enters = [
        index for index, event in enumerate(trace.events[:speech_index])
        if event.get("kind") == "collector_enter"
        and {key: event.get(key) for key in ("name", "task_type")} == owner
    ]
    if not enters:
        return False
    return not any(
        event.get("kind") == "collector_exit"
        and {key: event.get(key) for key in ("name", "task_type")} == owner
        for event in trace.events[enters[-1] + 1:speech_index]
    )


def _active_main(trace: Any, ordinal: int) -> bool:
    if not trace.states:
        return False
    state = trace.states[-1]
    return bool(
        state.get("ordinal") == ordinal
        and state.get("collector") is None
        and state.get("agent") == "src.cx_agent.CXAgent"
        and any(
            event.get("kind") == "model_speech"
            and event.get("caller_turn") == ordinal
            and event.get("collector") is None
            and str(event.get("content") or "").strip()
            for event in trace.events
        )
    )


def _assert_boolean_policy(trace: Any, field: str) -> None:
    calls = [
        call for call in trace.emitted
        if call.get("name") == "collect_input"
        and (call.get("effective_arguments") or baseline._args(call)).get("name") == field
    ]
    if not calls:
        raise MultiTurnOracleError(f"{field} has no observable collect_input call")
    for call in calls:
        args = call.get("effective_arguments") or baseline._args(call)
        if args.get("known_value") is not None:
            raise MultiTurnOracleError(f"{field} must not be implicitly seeded")
        if (args.get("options") or {}).get("ask_before_update") is not True:
            raise MultiTurnOracleError(f"{field} must set options.ask_before_update true")


def _terminal(trace: Any) -> bool:
    return bool(_handoffs(trace))


class EventGatedCaller:
    def __init__(self, case: dict[str, Any]):
        self.case = case
        self.stage = "start"
        self.last_ordinal = 0
        self.pending_event: dict[str, Any] | None = None
        self.pending_policy_deviation: str | None = None
        self.snapshot: Any | None = None

    def _deliver(self, text: str, stage: str, *, consent_for: str | None = None) -> str:
        self.pending_event = {"stage": stage, "text": text}
        if consent_for is not None:
            self.pending_event["consent_for"] = consent_for
        self.stage = stage
        return text

    def _booking_question(self, trace: Any, option: str) -> str:
        if not _active_owner(trace, "booking_confirmed", "boolean", self.last_ordinal):
            raise CallerWordingReview("booking consent requested without the live boolean owner")
        _assert_boolean_policy(trace, "booking_confirmed")
        selected = _stores(trace, "selected_slot")
        if not selected or selected[-1].get("value") != option:
            raise MultiTurnOracleError(f"full booking question lacks stored {option}")
        speech = _latest_speech(trace, self.last_ordinal)
        if not _facts_present(speech, option):
            raise CallerWordingReview(f"booking question lacks all four facts for {option}")
        return speech

    def _help_question(self, trace: Any) -> str:
        speech = _turn_speech(trace, self.last_ordinal)
        parent_questions = [
            str(call.get("speech") or "")
            for call in trace.model_calls
            if call.get("caller_turn") == self.last_ordinal
            and call.get("collector") is None
            and "?" in str(call.get("speech") or "")
            and any(
                phrase in _normalized(str(call.get("speech") or ""))
                for phrase in ("anything else", "more help", "else can i help", "need any help")
            )
        ]
        if parent_questions:
            self.pending_policy_deviation = "needs_more_help_collector_required"
        if _active_owner(trace, "needs_more_help", "boolean", self.last_ordinal):
            _assert_boolean_policy(trace, "needs_more_help")
            if not _facts_present(speech, "option 1"):
                raise CallerWordingReview("follow-up question lacks the selected booking facts")
            return speech
        if not _active_main(trace, self.last_ordinal):
            raise CallerWordingReview("follow-up response lacks a live node owner")
        normalized = _normalized(speech)
        if not any(
            phrase in normalized
            for phrase in ("anything else", "more help", "else can i help", "need any help")
        ) or "?" not in speech:
            raise CallerWordingReview("main node did not ask a fresh help question")
        self.pending_policy_deviation = "needs_more_help_collector_required"
        return speech

    def __call__(self, trace: Any) -> str | None:
        try:
            if self.stage == "start":
                return self._deliver(self.case["initial"], "initial")
            if _terminal(trace):
                self.snapshot = deepcopy(trace)
                return None
            path = self.case["path"]
            if self.case["node"] == "followup":
                return self._followup(trace, path)
            return self._choose(trace, path)
        except baseline.ProbeOracleError:
            self.snapshot = deepcopy(trace)
            raise

    def _choose(self, trace: Any, path: str) -> str:
        if self.stage == "initial":
            if path == "invalid":
                if not _active_owner(trace, "selected_slot", "choice", self.last_ordinal):
                    raise CallerWordingReview("invalid option was not followed by a live choice clarification")
                return self._deliver("Option 2, please.", "correct_invalid")
            speech = self._booking_question(trace, "option 1")
            if path == "fresh_yes":
                return self._deliver(
                    "Yes, please book that appointment.", "booking_consent", consent_for="option 1"
                )
            if path == "decline":
                return self._deliver("No, do not book that.", "booking_decline")
            if path == "tentative":
                return self._deliver(
                    "Maybe, I need to speak with my family before I decide.", "tentative_reply"
                )
            if path == "change":
                return self._deliver(
                    "Actually, change my selection to option 2. I have not agreed to book it yet.",
                    "change_selection",
                )
            if path == "conditional":
                return self._deliver(
                    "Yes, if there is no charge. Is this free?", "conditional_reply"
                )
        if path == "invalid" and self.stage == "correct_invalid":
            self._booking_question(trace, "option 2")
            return self._deliver("Yes, book it.", "booking_consent", consent_for="option 2")
        if path == "change" and self.stage == "change_selection":
            if _active_owner(trace, "booking_confirmed", "boolean", self.last_ordinal):
                self._booking_question(trace, "option 2")
                return self._deliver(
                    "Yes, book that appointment.", "booking_consent", consent_for="option 2"
                )
            if not _active_owner(trace, "selected_slot", "choice", self.last_ordinal):
                raise CallerWordingReview("selection correction was not owned by selected_slot")
            speech = _latest_speech(trace, self.last_ordinal)
            if not (_has_fact(speech, "option 2") or "option two" in _normalized(speech)):
                raise CallerWordingReview("option 2 correction readback is missing")
            return self._deliver("Yes, option 2 is my choice.", "confirm_selection_only")
        if path == "change" and self.stage == "confirm_selection_only":
            self._booking_question(trace, "option 2")
            return self._deliver("Yes, book that appointment.", "booking_consent", consent_for="option 2")
        if path in {"decline", "tentative", "conditional"} and self.stage in {
            "booking_decline", "tentative_reply", "conditional_reply",
        }:
            if any(baseline._is_true(item.get("value")) for item in _stores(trace, "booking_confirmed")):
                raise MultiTurnOracleError("conditional, tentative, or negative reply became consent")
            valid_owner = (
                _active_owner(trace, "booking_confirmed", "boolean", self.last_ordinal)
                or _active_owner(trace, "selected_slot", "choice", self.last_ordinal)
                or _active_main(trace, self.last_ordinal)
            )
            if not valid_owner:
                raise CallerWordingReview("decline follow-up lacks a live bounded node owner")
            if any(
                event.get("kind") == "emitted" and event.get("name") == "update_boolean_answer"
                and (event.get("collector") or {}).get("name") == "booking_confirmed"
                and any(baseline._is_true(value) for value in baseline._args(event).values())
                for event in trace.events
            ):
                raise MultiTurnOracleError("non-consent reply emitted an affirmative booking update")
            speech = _latest_speech(trace, self.last_ordinal)
            if not any(word in _normalized(speech) for word in ("book", "appointment", "option", "decide")):
                raise CallerWordingReview("assistant did not ask a bounded booking clarification")
            replies = {
                "decline": "No, I do not want any of those appointments.",
                "tentative": "No, please leave it unbooked.",
                "conditional": "No, leave it unbooked.",
            }
            return self._deliver(replies[path], "final_decline")
        raise MultiTurnOracleError(f"missing terminal outcome after caller stage {self.stage}")

    def _followup(self, trace: Any, path: str) -> str:
        if self.stage == "initial":
            self._help_question(trace)
            replies = {
                "no_more_help": "No, that is all. Thank you.",
                "factual_help": "Yes, I have a question.",
                "new_booking": "Yes, I want to make a second appointment as well.",
                "person": "Please let me speak to a person.",
                "emergency": "I am having trouble breathing and need emergency help.",
            }
            return self._deliver(replies[path], "help_reply")
        if path == "factual_help" and self.stage == "help_reply":
            speech = _latest_speech(trace, self.last_ordinal)
            if not any(word in _normalized(speech) for word in ("question", "help", "need")):
                raise CallerWordingReview("assistant did not solicit the factual question")
            return self._deliver("Which provider and clinic is it with?", "factual_question")
        if path == "factual_help" and self.stage == "factual_question":
            speech = _latest_speech(trace, self.last_ordinal)
            if not (_has_fact(speech, "Dr Casey") and _has_fact(speech, "Harbor Clinic")):
                raise CallerWordingReview("selected provider and clinic were not answered")
            if not any(word in _normalized(speech) for word in ("else", "more", "help", "question")):
                raise CallerWordingReview("factual answer did not invite the bounded final response")
            return self._deliver("No, that is all.", "final_no_help")
        raise MultiTurnOracleError(f"missing terminal outcome after caller stage {self.stage}")

    def record_delivery(self, trace: Any, ordinal: int) -> None:
        if self.pending_event is None:
            raise RuntimeError("caller delivery lacks pending stage metadata")
        event = {
            "kind": "caller_delivery", "caller_turn": ordinal,
            "stage": self.pending_event["stage"], "text": self.pending_event["text"],
        }
        if "consent_for" in self.pending_event:
            event["consent_for"] = self.pending_event["consent_for"]
            event["owed_consent_ordinal"] = ordinal
        trace.events.append(event)
        if self.pending_policy_deviation is not None:
            trace.events.append({
                "kind": "policy_deviation",
                "caller_turn": ordinal,
                "stage": self.pending_event["stage"],
                "policy": self.pending_policy_deviation,
            })
            self.pending_policy_deviation = None
        self.last_ordinal = ordinal
        self.pending_event = None


def _replace_exact(value: Any, needle: str, replacement: str) -> Any:
    if isinstance(value, dict):
        return {key: _replace_exact(item, needle, replacement) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_exact(item, needle, replacement) for item in value]
    if isinstance(value, str):
        return value.replace(needle, replacement)
    return value


def flow_for_case(flow: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(flow)
    if case["node"] != "followup":
        return candidate
    raw = next((node for node in candidate.get("nodes", []) if node.get("id") == FOLLOWUP_NODE), None)
    if raw is None or raw.get("type") != "ai_agent_v29":
        raise RuntimeError("candidate flow lacks the pinned Booking Follow-up node")
    config = (raw.get("data") or {}).get("config") or {}
    if config.get("name") != "Booking Follow-up":
        raise RuntimeError("pinned follow-up node name changed")
    raw["data"]["config"] = _replace_exact(
        config, "{{Choose Slot.selected_slot}}", "option 1"
    )
    return candidate


def build_case_runtime(flow: dict[str, Any], case: dict[str, Any]) -> tuple[dict[str, Any], Any, list[str]]:
    scoped = flow_for_case(flow, case)
    return baseline.build_probe_runtime(scoped, _node_id(case))


def _assert_store_provenance(trace: Any, name: str, task_type: str) -> list[dict[str, Any]]:
    stores = _stores(trace, name)
    owner = {"name": name, "task_type": task_type}
    for store in stores:
        if store.get("collector") != owner:
            raise RuntimeError(f"{name} store has foreign or missing collector ownership")
        if task_type == "boolean" and (
            type(store.get("value")) is not str or store.get("value") not in {"yes", "no"}
        ):
            raise MultiTurnOracleError(
                f"{name} must store the canonical string 'yes' or 'no'"
            )
        indexed = list(enumerate(trace.events))
        store_indexes = [
            i for i, event in indexed
            if event.get("kind") == "store"
            and event.get("name") == name
            and event.get("value") == store.get("value")
            and event.get("caller_turn") == store.get("caller_turn")
            and event.get("collector") == owner
        ]
        store_index = store_indexes[-1] if store_indexes else -1
        enter = [i for i, event in indexed if i < store_index and event.get("kind") == "collector_enter"
                 and {key: event.get(key) for key in ("name", "task_type")} == owner]
        exit_ = [i for i, event in indexed if i > store_index and event.get("kind") == "collector_exit"
                 and {key: event.get(key) for key in ("name", "task_type")} == owner]
        if not enter or not exit_ or any(
            event.get("kind") == "collector_exit"
            and {key: event.get(key) for key in ("name", "task_type")} == owner
            for event in trace.events[enter[-1] + 1:store_index]
        ):
            raise RuntimeError(f"{name} store lacks collector enter/store/exit linkage")
        successful_ids = {
            call.get("call_id") for call in trace.executed if not call.get("is_error")
        }
        tools = [
            event for event in trace.events[enter[-1] + 1:store_index]
            if event.get("kind") == "emitted" and event.get("collector") == owner
            and event.get("call_id") in successful_ids
        ]
        update_names = (
            {"record_selected_slot", "update_choice", "confirm_choice"}
            if task_type == "choice" else {"update_boolean_answer"}
        )
        produced = any(call.get("name") in update_names and not call.get("is_error") for call in tools)
        if not produced and task_type == "choice":
            collects = [
                event for event in trace.events[:enter[-1] + 1]
                if event.get("kind") == "emitted" and event.get("name") == "collect_input"
                and (event.get("effective_arguments") or baseline._args(event)).get("name") == name
                and event.get("call_id") in successful_ids
            ]
            collect = collects[-1] if collects else None
            args = (collect.get("effective_arguments") or baseline._args(collect)) if collect else {}
            produced = args.get("known_value") == store.get("value")
        if not produced:
            raise RuntimeError(f"{name} store lacks an authoritative producer")
    return stores


def _verify_consent_readback(trace: Any, consent: dict[str, Any]) -> dict[str, Any]:
    consent_index = next(
        index for index, event in enumerate(trace.events) if event is consent
    )
    consent_turn = consent.get("caller_turn")
    option = consent.get("consent_for")
    if option not in OPTION_FACTS or not isinstance(consent_turn, int):
        raise MultiTurnOracleError("booking consent metadata lacks a valid selected option or turn")
    speech_events = [
        (index, event) for index, event in enumerate(trace.events[:consent_index])
        if event.get("kind") == "model_speech"
        and event.get("collector") == {"name": "booking_confirmed", "task_type": "boolean"}
        and isinstance(event.get("request"), int)
        and isinstance(event.get("content"), str)
        and event.get("content") != ""
    ]
    requests_with_speech = [
        event["request"] for _index, event in speech_events
        if str(event.get("content") or "").strip()
    ]
    if not requests_with_speech:
        raise CallerWordingReview("consent lacks an observed booking-confirmation readback")
    request = requests_with_speech[-1]
    grouped = [
        (index, event) for index, event in speech_events if event.get("request") == request
    ]
    question_turn = grouped[-1][1].get("caller_turn")
    if question_turn != consent_turn - 1 or any(
        event.get("caller_turn") != question_turn for _index, event in grouped
    ):
        raise MultiTurnOracleError("booking readback is not from the immediately preceding caller turn")
    first_speech = grouped[0][0]
    last_speech = grouped[-1][0]
    owner = {"name": "booking_confirmed", "task_type": "boolean"}
    enters = [
        index for index, event in enumerate(trace.events[:first_speech])
        if event.get("kind") == "collector_enter"
        and {key: event.get(key) for key in ("name", "task_type")} == owner
    ]
    if not enters or any(
        event.get("kind") == "collector_exit"
        and {key: event.get(key) for key in ("name", "task_type")} == owner
        for event in trace.events[enters[-1] + 1:last_speech + 1]
    ):
        raise RuntimeError("booking readback lacks current boolean collector ownership")
    selected = [
        (index, event) for index, event in enumerate(trace.events[:first_speech])
        if event.get("kind") == "store" and event.get("name") == "selected_slot"
    ]
    if not selected or selected[-1][1].get("value") != option:
        raise MultiTurnOracleError("booking readback did not follow the selected option store")
    speech = "".join(str(event.get("content") or "") for _index, event in grouped)
    if not _facts_present(speech, option):
        raise CallerWordingReview(f"booking readback lacks all four facts for {option}")
    _assert_boolean_policy(trace, "booking_confirmed")
    return {
        "option": option,
        "question_caller_turn": question_turn,
        "request": request,
        "selected_store_event": selected[-1][0],
        "first_speech_event": first_speech,
        "last_speech_event": last_speech,
        "consent_event": consent_index,
    }


def _handoff_names(config: dict[str, Any]) -> dict[str, str]:
    return {
        f"handoff_{baseline._sanitize_tool_name(intent['intent_name'])}": intent["intent_name"]
        for intent in config.get("intents", [])
    }


def evaluate_case(case: dict[str, Any], trace: Any, config: dict[str, Any]) -> dict[str, Any]:
    probe = {"expected_intent": case["expected_intent"]}
    base = baseline.evaluate_probe(probe, trace, config)
    intents = [
        _handoff_names(config).get(name, name) for name in _handoffs(trace)
    ]
    if intents != [case["expected_intent"]]:
        raise MultiTurnOracleError(f"expected one {case['expected_intent']!r}, got {intents!r}")
    deliveries = [event for event in trace.events if event.get("kind") == "caller_delivery"]
    policy_deviations = [
        event for event in trace.events if event.get("kind") == "policy_deviation"
    ]
    if not deliveries:
        raise RuntimeError("trace lacks caller delivery metadata")
    terminal_event_indexes = [
        i for i, event in enumerate(trace.events)
        if event.get("kind") == "executed" and str(event.get("name") or "").startswith("handoff_")
    ]
    if len(terminal_event_indexes) != 1:
        raise MultiTurnOracleError("case requires exactly one terminal handoff")
    reached = {event.get("stage") for event in deliveries}
    required_stages = {
        "fresh_yes": {"initial", "booking_consent"},
        "decline": {"initial", "booking_decline"},
        "tentative": {"initial", "tentative_reply", "final_decline"},
        "change": {"initial", "change_selection", "booking_consent"},
        "invalid": {"initial", "correct_invalid", "booking_consent"},
        "conditional": {"initial", "conditional_reply", "final_decline"},
        "no_more_help": {"initial", "help_reply"},
        "factual_help": {"initial", "help_reply", "factual_question", "final_no_help"},
        "new_booking": {"initial", "help_reply"},
        "person": {"initial", "help_reply"},
        "emergency": {"initial", "help_reply"},
    }[case["path"]]
    if not required_stages.issubset(reached):
        raise MultiTurnOracleError(
            f"terminal handoff preceded required caller stages: {sorted(required_stages - reached)}"
        )
    handoff_emission_index = next(
        index for index, event in enumerate(trace.events)
        if event.get("kind") == "emitted" and str(event.get("name") or "").startswith("handoff_")
    )
    for required in required_stages:
        indexes = [
            index for index, event in enumerate(trace.events)
            if event.get("kind") == "caller_delivery" and event.get("stage") == required
        ]
        if not indexes or indexes[-1] >= handoff_emission_index:
            raise MultiTurnOracleError(f"terminal handoff preceded caller stage {required}")

    selected = _assert_store_provenance(trace, "selected_slot", "choice")
    booked = _assert_store_provenance(trace, "booking_confirmed", "boolean")
    helped = _assert_store_provenance(trace, "needs_more_help", "boolean")
    book_calls = [call for call in trace.executed if call.get("name") == "handoff_book"]
    consent = [event for event in deliveries if event.get("consent_for")]
    if case["node"] == "choose":
        if any(item.get("value") == "option 4" for item in selected):
            raise MultiTurnOracleError("invalid option 4 was stored")
        if not selected or selected[-1].get("value") != case["expected_slot"]:
            raise MultiTurnOracleError("final selected slot is missing or incorrect")
        for item in selected:
            value = item.get("value")
            prior = [
                event for event in deliveries
                if event.get("caller_turn", 0) <= item.get("caller_turn", 0)
            ]
            supported = (
                value == "option 1" and any("option 1" in event.get("text", "").casefold() for event in prior)
            ) or (
                value == "option 2" and any(
                    event.get("stage") in {"change_selection", "correct_invalid"} for event in prior
                )
            )
            if not supported:
                raise MultiTurnOracleError(f"selected slot store was not supported by the caller: {value!r}")
        if case["path"] == "change" and [item.get("value") for item in selected][-2:] != ["option 1", "option 2"]:
            raise MultiTurnOracleError("change case lacks the option 1 to option 2 correction path")
        if case["path"] == "change" and "confirm_selection_only" in reached:
            confirmation_index = next(
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "caller_delivery"
                and event.get("stage") == "confirm_selection_only"
            )
            option_two_store = next(
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "store" and event.get("name") == "selected_slot"
                and event.get("value") == "option 2" and index > confirmation_index
            )
            confirms = [
                event for event in trace.events[confirmation_index + 1:option_two_store]
                if event.get("kind") == "emitted" and event.get("name") == "confirm_choice"
                and (event.get("collector") or {}).get("name") == "selected_slot"
            ]
            if not confirms:
                raise MultiTurnOracleError("selection-confirmation reply lacks confirm_choice provenance")
        if case["expected_intent"] == "book":
            if len(consent) != 1 or len(book_calls) != 1:
                raise MultiTurnOracleError("booking requires one gated consent and one book handoff")
            consent_readback = _verify_consent_readback(trace, consent[0])
            consent_ordinal = consent[0]["caller_turn"]
            affirmative = [item for item in booked if baseline._is_true(item.get("value"))]
            if len(affirmative) != 1 or affirmative[0].get("caller_turn", 0) < consent_ordinal:
                raise MultiTurnOracleError("affirmative booking store did not follow fresh consent")
            consent_index = next(
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "caller_delivery" and event.get("consent_for")
            )
            updates = [
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "emitted"
                and event.get("name") == "update_boolean_answer"
                and (event.get("collector") or {}).get("name") == "booking_confirmed"
                and any(baseline._is_true(value) for value in baseline._args(event).values())
            ]
            stores_at = [
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "store" and event.get("name") == "booking_confirmed"
                and baseline._is_true(event.get("value"))
            ]
            handoff_at = [
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "emitted" and event.get("name") == "handoff_book"
            ]
            if len(updates) != 1 or len(stores_at) != 1 or len(handoff_at) != 1 or not (
                consent_index < updates[0] < stores_at[0] < handoff_at[0]
            ):
                raise MultiTurnOracleError("consent, update, store, and book emission are out of order")
            selected_before_book = [
                event.get("value") for event in trace.events[:handoff_at[0]]
                if event.get("kind") == "store" and event.get("name") == "selected_slot"
            ]
            if not selected_before_book or selected_before_book[-1] != consent[0]["consent_for"]:
                raise MultiTurnOracleError("book handoff used a stale selected slot")
        else:
            affirmative_updates = [
                event for event in trace.events
                if event.get("kind") == "emitted" and event.get("name") == "update_boolean_answer"
                and (event.get("collector") or {}).get("name") == "booking_confirmed"
                and any(baseline._is_true(value) for value in baseline._args(event).values())
            ]
            if consent or book_calls or affirmative_updates or any(
                baseline._is_true(item.get("value")) for item in booked
            ):
                raise MultiTurnOracleError("non-consent case booked or stored affirmative consent")
    else:
        if book_calls:
            raise MultiTurnOracleError("post-save follow-up repeated booking")
        if _latest_collect(trace, "needs_more_help") is not None:
            _assert_boolean_policy(trace, "needs_more_help")
        if not helped and case["path"] in {"no_more_help", "factual_help"} and not policy_deviations:
            raise MultiTurnOracleError("needs_more_help was not authoritatively stored")
        if case["path"] in {"no_more_help", "factual_help"} and helped and not any(
            item.get("value") is False
            or (isinstance(item.get("value"), str) and item["value"].casefold() == "no")
            for item in helped
        ):
            raise MultiTurnOracleError("needs_more_help did not finish with a canonical no")
        if case["path"] == "factual_help":
            question_index = next(
                index for index, event in enumerate(trace.events)
                if event.get("kind") == "caller_delivery" and event.get("stage") == "factual_question"
            )
            final_index = next(
                index for index, event in enumerate(trace.events)
                if index > question_index and event.get("kind") == "caller_delivery"
                and event.get("stage") == "final_no_help"
            )
            speech = "".join(
                str(event.get("content") or "")
                for event in trace.events[question_index + 1:final_index]
                if event.get("kind") == "model_speech"
            )
            if not (_has_fact(speech, "Dr Casey") and _has_fact(speech, "Harbor Clinic")):
                raise MultiTurnOracleError("factual answer omitted the selected provider or clinic")
            forbidden = baseline._contains_any(speech, ["insurance covers", "no charge", "free of charge", "street address"])
            if forbidden:
                raise MultiTurnOracleError(f"unsupported factual claim observed: {forbidden}")
    if case.get("forbid_fee_claims"):
        speech = baseline._speech(trace)
        claims = baseline._contains_any(speech, ["it is free", "no charge", "free of charge", "there is no fee"])
        if claims:
            raise MultiTurnOracleError(f"unsupported fee claim observed: {claims}")
    result = {
        **base,
        "node_only": True,
        "simulated_post_save_entry": case["node"] == "followup",
        "caller_deliveries": deliveries,
        "final_selected_slot": selected[-1].get("value") if selected else None,
        "booking_store_count": len(booked),
        "needs_more_help_store_count": len(helped),
        "policy_deviations": policy_deviations,
        "consent_readback": consent_readback if case["node"] == "choose"
        and case["expected_intent"] == "book" else None,
    }
    if policy_deviations:
        raise MultiTurnOracleError(
            "follow-up bypassed the required needs_more_help collector",
            checks=result,
        )
    return result


def validate_inputs(args: argparse.Namespace) -> tuple[dict[str, str], dict[str, Any]]:
    if not _GIT_HEAD.fullmatch(args.source_head):
        raise RuntimeError("candidate source HEAD must be a full lowercase git SHA")
    if not _SHA256.fullmatch(args.source_sha256) or not _SHA256.fullmatch(args.flow_sha256):
        raise RuntimeError("candidate source and flow SHA-256 values must be lowercase hexadecimal")
    source = baseline.verify_source_tree(args.source_root, args.source_head, args.source_sha256)
    flow = baseline.load_pinned_flow(args.flow, args.flow_sha256)
    for case in CASES:
        config, _graph, _used = build_case_runtime(flow, case)
        if config.get("actions") != [] or config.get("knowledge_base_ids"):
            raise RuntimeError("multi-turn node probes forbid actions and knowledge bases")
    return source, flow


def _activate_source(root: Path) -> None:
    resolved = root.resolve()
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    loaded = [
        (name, Path(module_file).resolve())
        for name, module in tuple(sys.modules.items())
        if (name == "src" or name.startswith("src."))
        and (module_file := getattr(module, "__file__", None))
    ]
    wrong = [name for name, path in loaded if not path.is_relative_to(resolved)]
    if wrong:
        raise RuntimeError(f"candidate source modules were preloaded from another tree: {wrong[:3]}")


def inventory(args: argparse.Namespace, source: dict[str, str], flow: dict[str, Any]) -> dict[str, Any]:
    selected = args.case or list(CASES_BY_ID)
    rows = []
    for case_id in selected:
        case = CASES_BY_ID[case_id]
        config, _graph, placeholders = build_case_runtime(flow, case)
        rows.append({
            "case_id": case_id, "scenario_sha256": baseline._canonical_hash(case),
            "config_sha256": baseline._canonical_hash(config),
            "resolved_placeholders": placeholders,
        })
    return {
        "scope": "isolated_node_multi_turn_sdk_text_not_full_flow_http_action_or_voice",
        "source": source, "flow_sha256": args.flow_sha256,
        "adapter_sha256": baseline._sha256(Path(__file__)),
        "scenario_set_sha256": baseline._canonical_hash(CASES),
        "frozen_time": FROZEN_TIME, "repetitions": args.repetitions, "cases": rows,
    }


async def _run(args: argparse.Namespace, source: dict[str, str], flow: dict[str, Any], manifest: dict[str, Any]) -> int:
    from src.agent_factory import _build_llm
    from src.config.settings import app_settings
    from tests.v29_model_eval import budget as guard
    from tests.v29_model_eval.live import _error_category, _ledger_summary, _resolved, _write_row
    from tests.v29_model_eval.session_runner import SessionCase, run_session
    from unittest.mock import patch
    from tests.v29_model_eval import session_runner

    if os.environ.get("V29_EVAL_PROVIDER") != "azure" or os.environ.get("V29_EVAL_MODEL") != "gpt-4.1":
        raise ValueError("V29_EVAL_PROVIDER/model must be exactly azure/gpt-4.1")
    if not app_settings.azure_openai_endpoint or not app_settings.azure_openai_api_key:
        raise ValueError("Azure OpenAI endpoint and API key must be configured")
    if app_settings.azure_openai_sim_deployment not in ("", "gpt-4.1"):
        raise ValueError("AZURE_OPENAI_SIM_DEPLOYMENT must be blank or gpt-4.1")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    stopped = False
    with args.output.open("x", encoding="utf-8") as output:
        with guard.guarded_httpx_campaign(
            azure_origin=app_settings.azure_openai_endpoint, deployment="gpt-4.1",
            ledger_path=args.ledger, campaign_id=args.campaign_id,
        ) as request_ids:
            for case_id, repetition in baseline._case_repetitions(args.case, args.repetitions):
                case_spec = CASES_BY_ID[case_id]
                config, graph, placeholders = build_case_runtime(flow, case_spec)
                before = len(request_ids)
                trace = None
                built: list[Any] = []
                row: dict[str, Any] = {
                    "campaign_id": args.campaign_id, "case_id": case_id, "repetition": repetition,
                    "requested": {"provider": "azure", "model": "gpt-4.1", "max_output_tokens": 400},
                    "source": source, "flow_sha256": args.flow_sha256,
                    "adapter_sha256": manifest["adapter_sha256"],
                    "scenario_set_sha256": manifest["scenario_set_sha256"],
                    "scenario_sha256": baseline._canonical_hash(case_spec),
                    "config_sha256": baseline._canonical_hash(config),
                    "resolved_placeholders": placeholders, "scope": manifest["scope"],
                    "structural_status": "failed", "speech_review_status": "not_reached",
                }

                def factory(*factory_args: Any, **factory_kwargs: Any) -> Any:
                    instance = _build_llm(*factory_args, **factory_kwargs)
                    _resolved(instance)
                    built.append(instance)
                    return instance

                error: BaseException | None = None
                caller = EventGatedCaller(case_spec)
                try:
                    with (
                        patch.object(session_runner, "build_graph", return_value=graph),
                        patch.object(session_runner, "_settle_strict", new=baseline.settle_node_turn_strict),
                    ):
                        final_trace = await run_session(SessionCase(
                            id=f"{case_id}-r{repetition}", node_config=deepcopy(config),
                            caller_driver=caller, action_mocks={}, required_values={},
                            max_caller_turns=8, max_model_requests=30, frozen_time=FROZEN_TIME,
                        ), model_factory=factory)
                    if caller.snapshot is None:
                        caller.snapshot = deepcopy(final_trace)
                        raise MultiTurnOracleError("case ended without a terminal snapshot")
                    trace = caller.snapshot
                    row["cleanup_events"] = final_trace.events[len(trace.events):]
                    if final_trace.observation_failures or final_trace.cleanup_failures:
                        raise RuntimeError("session cleanup or observation failed after snapshot")
                    row["checks"] = evaluate_case(case_spec, trace, config)
                    row["structural_status"] = "passed"
                    row["speech_review_status"] = "manual_review_required"
                    row["trace"] = baseline._jsonable(trace)
                except BaseException as exc:
                    error = exc
                    partial = trace or caller.snapshot or getattr(exc, "trace", None)
                    row["error"] = {"category": _error_category(exc, guard), "type": type(exc).__name__}
                    if isinstance(exc, AssertionError):
                        row["error"]["oracle_detail"] = str(exc)[:1000]
                    if isinstance(exc, MultiTurnOracleError) and exc.checks is not None:
                        row["checks"] = exc.checks
                    row["partial_trace"] = baseline._jsonable(partial)
                    failed = True
                finally:
                    cleanup_error = getattr(error, "cleanup_error", None)
                    if cleanup_error is not None:
                        row["session_cleanup_error_type"] = type(cleanup_error).__name__
                    row["ledger"] = _ledger_summary(args.ledger, request_ids=request_ids[before:])
                    resolved_error = None
                    try:
                        resolved = [_resolved(instance) for instance in built]
                        row["resolved"] = {
                            "models": sorted({x for group in resolved for x in group[0]}),
                            "providers": sorted({x for group in resolved for x in group[1]}),
                            "classes": sorted({x for group in resolved for x in group[2]}),
                        }
                    except BaseException as exc:
                        resolved_error = type(exc).__name__
                        row["resolved_error_type"] = resolved_error
                    owned = row["ledger"].get("request_delta", 0)
                    verified = (
                        owned >= 1 and row["ledger"].get("model_verified_count") == owned
                        and row["ledger"].get("settled_count") == owned
                        and row["ledger"].get("campaign_failure") is None
                    )
                    if not verified or resolved_error:
                        row["structural_status"] = "failed"
                        row["error"] = {"category": "model_identity", "type": "UnsettledOrUnverifiedOwnedRequest"}
                        failed = True
                    _write_row(output, row)
                safe_oracle = (
                    isinstance(error, baseline.ProbeOracleError) and verified and not resolved_error
                    and (trace or caller.snapshot) is not None
                    and not getattr(trace or caller.snapshot, "observation_failures", [])
                    and not getattr(trace or caller.snapshot, "cleanup_failures", [])
                    and getattr(error, "cleanup_error", None) is None
                )
                if row["structural_status"] == "failed" and not safe_oracle:
                    stopped = True
                    break
    print(json.dumps({
        "output": str(args.output), "status": "failed" if failed else "passed",
        "stopped_early": stopped, "source": source, "flow_sha256": args.flow_sha256,
        "adapter_sha256": manifest["adapter_sha256"],
        "scenario_set_sha256": manifest["scenario_set_sha256"],
    }, sort_keys=True))
    return 1 if failed else 0


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=tuple(CASES_BY_ID), default=[])
    parser.add_argument("--repetitions", type=int, choices=(1, 3), default=1)
    parser.add_argument("--flow", type=Path, default=FLOW_PATH)
    parser.add_argument("--flow-sha256", default=FLOW_SHA256)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--source-head", default=SOURCE_HEAD)
    parser.add_argument("--source-sha256", default=SOURCE_SHA256)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        return args
    if not args.case or len(args.case) != len(set(args.case)):
        parser.error("--execute requires unique explicit --case values")
    if not all((args.env_file, args.ledger, args.campaign_id, args.output)):
        parser.error("--execute requires --env-file, --ledger, --campaign-id, and --output")
    if not args.env_file.is_file() or not args.ledger.is_file():
        parser.error("--env-file and --ledger must be existing files")
    if args.output.exists():
        parser.error("--output already exists; JSONL evidence is append-immutable")
    if not _SAFE_CAMPAIGN.fullmatch(args.campaign_id):
        parser.error("--campaign-id contains unsafe characters")
    if len({args.env_file.resolve(), args.ledger.resolve(), args.output.resolve()}) != 3:
        parser.error("environment, ledger, and output paths must be distinct")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if not _GIT_HEAD.fullmatch(args.source_head):
        raise RuntimeError("candidate source HEAD must be a full lowercase git SHA")
    if not _SHA256.fullmatch(args.source_sha256) or not _SHA256.fullmatch(args.flow_sha256):
        raise RuntimeError("candidate source and flow SHA-256 values must be lowercase hexadecimal")
    source = baseline.verify_source_tree(args.source_root, args.source_head, args.source_sha256)
    flow = baseline.load_pinned_flow(args.flow, args.flow_sha256)
    _activate_source(args.source_root)
    if args.execute:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=args.env_file, override=True)
    source, flow = validate_inputs(args)
    manifest = inventory(args, source, flow)
    if not args.execute:
        print(json.dumps(manifest, sort_keys=True, indent=2))
        return 0
    return asyncio.run(_run(args, source, flow, manifest))


if __name__ == "__main__":
    raise SystemExit(main())
