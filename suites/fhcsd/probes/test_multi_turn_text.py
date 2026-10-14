from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import multi_turn_text as M
from src.units.tasks.collectors import REGISTRY


BOOK_CONFIG = {
    "intents": [
        {"intent_name": "book"},
        {"intent_name": "Patient Declines"},
    ]
}
FOLLOWUP_CONFIG = {"intents": [{"intent_name": "Done"}]}


@pytest.fixture(autouse=True)
def isolate_base_oracle(monkeypatch):
    monkeypatch.setattr(M.baseline, "evaluate_probe", lambda *_args: {"base": True})


def _owned_store(trace, name, task_type, value, enter_turn, store_turn):
    owner = {"name": name, "task_type": task_type}
    call_id = f"update-{name}-{len(trace.stores)}"
    enter = {"kind": "collector_enter", "caller_turn": enter_turn, **owner}
    emitted = {
        "kind": "emitted", "call_id": call_id,
        "name": "update_choice" if task_type == "choice" else "update_boolean_answer",
        "caller_turn": store_turn, "collector": owner,
        "effective_arguments": (
            {"choice": value}
            if task_type == "choice"
            else {"value": M.baseline._is_true(value)}
        ),
    }
    emitted["arguments"] = json.dumps(emitted["effective_arguments"])
    executed = {
        "kind": "executed", "call_id": call_id, "name": emitted["name"],
        "arguments": emitted["arguments"], "is_error": False,
    }
    store = {
        "kind": "store", "name": name, "value": value,
        "caller_turn": store_turn, "collector": owner,
    }
    exit_ = {"kind": "collector_exit", "caller_turn": store_turn, **owner}
    trace.emitted.append(emitted)
    trace.executed.append(executed)
    trace.stores.append(store)
    trace.events.extend((enter, emitted, executed, store, exit_))
    return store


def _corrected_choice_store(trace, value):
    owner = {"name": "selected_slot", "task_type": "choice"}
    update = {
        "kind": "emitted", "call_id": "update-selected_slot-corrected",
        "name": "update_choice", "caller_turn": 2, "collector": owner,
        "effective_arguments": {"choice": value},
        "arguments": json.dumps({"choice": value}),
    }
    update_done = {
        "kind": "executed", "call_id": update["call_id"], "name": update["name"],
        "arguments": update["arguments"], "is_error": False,
    }
    trace.events.extend(({"kind": "collector_enter", "caller_turn": 2, **owner}, update, update_done))
    trace.emitted.append(update)
    trace.executed.append(update_done)
    trace.events.append({
        "kind": "caller_delivery", "caller_turn": 3, "stage": "confirm_selection_only",
        "text": "Yes, option 2 is my choice.",
    })
    confirm = {
        "kind": "emitted", "call_id": "confirm-selected-slot-corrected",
        "name": "confirm_choice", "caller_turn": 3, "collector": owner,
        "effective_arguments": {}, "arguments": "{}",
    }
    confirm_done = {
        "kind": "executed", "call_id": confirm["call_id"], "name": confirm["name"],
        "arguments": "{}", "is_error": False,
    }
    store = {
        "kind": "store", "name": "selected_slot", "value": value,
        "caller_turn": 3, "collector": owner,
    }
    trace.emitted.append(confirm)
    trace.executed.append(confirm_done)
    trace.stores.append(store)
    trace.events.extend((confirm, confirm_done, store, {
        "kind": "collector_exit", "caller_turn": 3, **owner,
    }))


def _trace(
    *,
    selected=("option 1",),
    booking="yes",
    intent="book",
    consent_for="option 1",
    readback_option="option 1",
    delivery_stages=("booking_consent",),
):
    trace = SimpleNamespace(
        emitted=[], executed=[], stores=[], events=[], model_calls=[], turns=[], states=[],
        observation_failures=[], cleanup_failures=[], messages=[], collector_stack=[],
    )
    trace.events.append({
        "kind": "caller_delivery", "caller_turn": 1, "stage": "initial",
        "text": "I choose option 1.",
    })
    _owned_store(trace, "selected_slot", "choice", selected[0], 1, 1)
    question_turn = 1
    if len(selected) > 1:
        trace.events.append({
            "kind": "caller_delivery", "caller_turn": 2, "stage": "change_selection",
            "text": "Actually, change my selection to option 2.",
        })
        _corrected_choice_store(trace, selected[-1])
        question_turn = 3

    boolean_owner = {"name": "booking_confirmed", "task_type": "boolean"}
    collect = {
        "kind": "emitted", "call_id": "collect-booking", "name": "collect_input",
        "caller_turn": question_turn, "collector": None,
        "effective_arguments": {
            "name": "booking_confirmed", "task_type": "boolean", "known_value": None,
            "options": {"ask_before_update": True, "require_confirmation": False},
            "unrelated_default": "allowed",
        },
    }
    collect["arguments"] = json.dumps(collect["effective_arguments"])
    trace.emitted.append(collect)
    trace.events.append(collect)
    trace.events.append({"kind": "collector_enter", "caller_turn": question_turn, **boolean_owner})
    speech = "Confirm September 15 2026 at nine AM with Dr Casey at Harbor Clinic."
    if readback_option == "option 2":
        speech = "Confirm September 16 2026 at two thirty PM with Dr Morgan at Cedar Clinic."
    trace.events.append({
        "kind": "message", "role": "assistant", "caller_turn": question_turn, "content": speech,
    })
    request = len(trace.model_calls)
    trace.model_calls.append({
        "caller_turn": question_turn, "collector": boolean_owner, "speech": speech,
    })
    trace.events.append({
        "kind": "model_speech", "caller_turn": question_turn,
        "collector": boolean_owner, "content": speech, "request": request,
    })
    consent_turn = question_turn
    for stage in delivery_stages:
        consent_turn += 1
        delivery = {
            "kind": "caller_delivery", "caller_turn": consent_turn,
            "stage": stage, "text": "Yes, book it.",
        }
        if consent_for is not None and stage == delivery_stages[-1]:
            delivery.update({"consent_for": consent_for, "owed_consent_ordinal": consent_turn})
        trace.events.append(delivery)
    if booking is not None:
        emitted_update = {
            "kind": "emitted", "call_id": "update-booking", "name": "update_boolean_answer",
            "caller_turn": consent_turn, "collector": boolean_owner,
            "effective_arguments": {"value": M.baseline._is_true(booking)},
        }
        emitted_update["arguments"] = json.dumps(emitted_update["effective_arguments"])
        executed_update = {
            "kind": "executed", "call_id": "update-booking",
            "name": "update_boolean_answer", "arguments": emitted_update["arguments"],
            "is_error": False,
        }
        store = {
            "kind": "store", "name": "booking_confirmed", "value": booking,
            "caller_turn": consent_turn, "collector": boolean_owner,
        }
        exit_ = {"kind": "collector_exit", "caller_turn": consent_turn, **boolean_owner}
        trace.emitted.append(emitted_update)
        trace.executed.append(executed_update)
        trace.stores.append(store)
        trace.events.extend((emitted_update, executed_update, store, exit_))
    handoff_name = f"handoff_{M.baseline._sanitize_tool_name(intent)}"
    emitted_handoff = {
        "kind": "emitted", "call_id": "terminal", "name": handoff_name,
        "caller_turn": consent_turn, "arguments": "{}",
    }
    executed_handoff = {
        "kind": "executed", "call_id": "terminal", "name": handoff_name,
        "caller_turn": consent_turn, "arguments": "{}", "is_error": False,
    }
    trace.emitted.append(emitted_handoff)
    trace.executed.append(executed_handoff)
    trace.events.extend((emitted_handoff, executed_handoff))
    return trace


def _case(case_id="choose_fresh_yes"):
    return M.CASES_BY_ID[case_id]


def _split_booking_readback(trace, speech):
    original_index, original = next(
        (index, event) for index, event in enumerate(trace.events)
        if event.get("kind") == "model_speech"
        and event.get("collector") == {"name": "booking_confirmed", "task_type": "boolean"}
    )
    words = speech.split(" ")
    chunks = [part for word in words for part in (word, " ")][:-1]
    trace.events[original_index:original_index + 1] = [
        {**original, "content": chunk} for chunk in chunks
    ]


def _main_speech(trace, ordinal, speech):
    trace.states.append({
        "collector": None, "ordinal": ordinal, "agent": "src.cx_agent.CXAgent",
    })
    request = len(trace.model_calls)
    trace.model_calls.append({
        "caller_turn": ordinal, "collector": None, "speech": speech,
    })
    trace.events.append({
        "kind": "model_speech", "caller_turn": ordinal, "collector": None,
        "content": speech, "request": request,
    })


def _terminal(trace, intent, ordinal):
    name = f"handoff_{M.baseline._sanitize_tool_name(intent)}"
    emitted = {
        "kind": "emitted", "call_id": "terminal", "name": name,
        "caller_turn": ordinal, "arguments": "{}",
    }
    executed = {**emitted, "kind": "executed", "is_error": False}
    trace.emitted.append(emitted)
    trace.executed.append(executed)
    trace.events.extend((emitted, executed))


def _driver_trace():
    return SimpleNamespace(
        emitted=[], executed=[], stores=[], events=[], model_calls=[], turns=[], states=[],
        observation_failures=[], cleanup_failures=[], messages=[], collector_stack=[],
    )


def _activate(trace, field, task_type, ordinal, speech):
    owner = {"name": field, "task_type": task_type}
    trace.events.append({"kind": "collector_enter", "caller_turn": ordinal, **owner})
    request = len(trace.model_calls)
    trace.model_calls.append({"caller_turn": ordinal, "collector": owner, "speech": speech})
    trace.events.append({
        "kind": "model_speech", "caller_turn": ordinal, "collector": owner,
        "content": speech, "request": request,
    })
    trace.events.append({
        "kind": "message", "role": "assistant", "caller_turn": ordinal, "content": speech,
    })
    trace.states.append({
        "collector": owner, "ordinal": ordinal,
        "agent": f"{REGISTRY[task_type].cls.__module__}.{REGISTRY[task_type].cls.__qualname__}",
    })
    if task_type == "boolean":
        call = {
            "call_id": f"collect-{field}-{ordinal}", "name": "collect_input",
            "effective_arguments": {
                "name": field, "task_type": task_type, "known_value": None,
                "options": {"ask_before_update": True},
            },
        }
        call["arguments"] = json.dumps(call["effective_arguments"])
        trace.emitted.append(call)


def test_change_driver_runs_four_deliveries_before_terminal_snapshot():
    caller = M.EventGatedCaller(_case("choose_change_before_consent"))
    trace = _driver_trace()
    assert "option 1" in caller(trace).casefold()
    caller.record_delivery(trace, 1)
    trace.stores.append({"name": "selected_slot", "value": "option 1"})

    _activate(
        trace, "booking_confirmed", "boolean", 1,
        "September 15 2026 at nine AM with Dr Casey at Harbor Clinic.",
    )
    assert "option 2" in caller(trace).casefold()
    caller.record_delivery(trace, 2)

    _activate(trace, "selected_slot", "choice", 2, "You selected option 2.")
    assert "option 2 is my choice" in caller(trace).casefold()
    caller.record_delivery(trace, 3)
    trace.stores.append({"name": "selected_slot", "value": "option 2"})

    _activate(
        trace, "booking_confirmed", "boolean", 3,
        "September 16 2026 at two thirty PM with Dr Morgan at Cedar Clinic.",
    )
    assert "book that appointment" in caller(trace).casefold()
    caller.record_delivery(trace, 4)
    trace.executed.append({"name": "handoff_book"})
    assert caller(trace) is None
    assert caller.snapshot is not None

    deliveries = [event for event in trace.events if event.get("kind") == "caller_delivery"]
    assert [event["stage"] for event in deliveries] == [
        "initial", "change_selection", "confirm_selection_only", "booking_consent",
    ]
    assert [event.get("consent_for") for event in deliveries] == [None, None, None, "option 2"]


def test_change_driver_skips_reconfirming_selection_when_option_two_is_already_stored():
    caller = M.EventGatedCaller(_case("choose_change_before_consent"))
    trace = _driver_trace()
    caller(trace)
    caller.record_delivery(trace, 1)
    trace.stores.append({"name": "selected_slot", "value": "option 1"})
    _activate(
        trace, "booking_confirmed", "boolean", 1,
        "September 15 2026 at nine AM with Dr Casey at Harbor Clinic.",
    )
    caller(trace)
    caller.record_delivery(trace, 2)
    trace.stores.append({"name": "selected_slot", "value": "option 2"})
    _activate(
        trace, "booking_confirmed", "boolean", 2,
        "September 16 2026 at two thirty PM with Dr Morgan at Cedar Clinic.",
    )

    assert "book that appointment" in caller(trace).casefold()
    assert caller.stage == "booking_consent"


def test_valid_booking_requires_cross_turn_boolean_owner_and_canonical_yes():
    result = M.evaluate_case(_case(), _trace(), BOOK_CONFIG)
    assert result["final_selected_slot"] == "option 1"
    assert result["booking_store_count"] == 1


def test_split_stream_booking_readback_preserves_word_boundaries():
    trace = _trace()
    _split_booking_readback(
        trace,
        "Confirm September 15 2026 at nine AM with Dr Casey at Harbor Clinic.",
    )

    result = M.evaluate_case(_case(), trace, BOOK_CONFIG)

    assert result["final_selected_slot"] == "option 1"
    assert result["booking_store_count"] == 1


@pytest.mark.parametrize(
    "speech",
    (
        "Confirm September 17 2026 at nine AM with Dr Casey at Harbor Clinic.",
        "Confirm September 15 2026 at nine AM with Dr Morgan at Harbor Clinic.",
    ),
)
def test_split_stream_booking_readback_still_rejects_wrong_facts(speech):
    trace = _trace()
    _split_booking_readback(trace, speech)

    with pytest.raises(M.CallerWordingReview):
        M.evaluate_case(_case(), trace, BOOK_CONFIG)


async def _sim_turn_completed_with(error):
    from livekit.agents import RunResult
    from src.simulation import runner as simulation_runner
    from src.simulation.schema import SimTurnRequest
    from tests.test_simulation_runner import _ai_node, _graph, _make_session_mock

    sim = simulation_runner.SimSession(
        phlo_run_uuid="phlo-1", auth_id="auth-1", node_uuid="A",
        node_run_uuid="run-A", graph=_graph([_ai_node("A", "NodeA", [])], []),
    )
    sim.session = _make_session_mock(active_agent=object())
    run = RunResult(user_input="scripted turn", output_type=None, session=sim.session)
    run._done_fut.set_exception(error)
    sim.session.run.return_value = run
    original_signals = simulation_runner._WALK_CONTROL_SIGNALS
    try:
        with patch("src.services.aci_rollout.use_aci_for_org", new=AsyncMock(return_value=False)):
            return await sim.turn(SimTurnRequest(phlo_run_uuid="phlo-1", user_message="continue"))
    finally:
        assert simulation_runner._WALK_CONTROL_SIGNALS is original_signals


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_name", ("change", "hand_back"))
async def test_sim_turn_treats_collector_control_transfer_as_continuation(signal_name):
    from src.simulation import runner as simulation_runner
    from src.units.collect_input import ChangeRequest, HandBack

    signal = (
        ChangeRequest("selected_slot", "option 2")
        if signal_name == "change"
        else HandBack("caller requested a person")
    )
    assert type(signal) in simulation_runner._WALK_CONTROL_SIGNALS
    response = await _sim_turn_completed_with(signal)

    assert response.message == ""
    assert response.ended is False


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", ("tool", "other"))
async def test_sim_turn_non_control_errors_remain_surfaced(error_kind):
    from livekit.agents import ToolError
    from src.simulation import runner as simulation_runner

    error = ToolError("unrelated tool failure") if error_kind == "tool" else ValueError("other failure")
    assert type(error) not in simulation_runner._WALK_CONTROL_SIGNALS
    with pytest.raises(type(error), match="failure"):
        await _sim_turn_completed_with(error)


def test_corrected_selection_requires_later_full_readback_and_fresh_booking_yes():
    trace = _trace(
        selected=("option 1", "option 2"),
        consent_for="option 2",
        readback_option="option 2",
    )
    result = M.evaluate_case(_case("choose_change_before_consent"), trace, BOOK_CONFIG)
    assert result["final_selected_slot"] == "option 2"
    assert result["booking_store_count"] == 1


def test_booking_question_requires_live_boolean_owner_and_current_full_readback():
    caller = M.EventGatedCaller(_case())
    caller.last_ordinal = 1
    trace = _trace(booking=None, intent="Patient Declines", consent_for=None)
    trace.stores = [item for item in trace.stores if item["name"] == "selected_slot"]
    trace.states = [{
        "collector": {"name": "booking_confirmed", "task_type": "boolean"},
        "ordinal": 1,
        "agent": f"{REGISTRY['boolean'].cls.__module__}.{REGISTRY['boolean'].cls.__qualname__}",
    }]
    assert M._facts_present(caller._booking_question(trace, "option 1"), "option 1")

    trace.states[-1]["collector"] = {"name": "selected_slot", "task_type": "choice"}
    with pytest.raises(M.CallerWordingReview):
        caller._booking_question(trace, "option 1")


def test_fresh_parent_help_question_delivers_reply_but_remains_sticky_failure():
    caller = M.EventGatedCaller(_case("followup_no_more_help"))
    trace = _driver_trace()
    assert caller(trace) == "I am still here."
    caller.record_delivery(trace, 1)
    _main_speech(trace, 1, "Is there anything else I can help you with?")

    assert caller(trace) == "No, that is all. Thank you."
    caller.record_delivery(trace, 2)
    _terminal(trace, "Done", 2)

    with pytest.raises(M.MultiTurnOracleError) as excinfo:
        M.evaluate_case(_case("followup_no_more_help"), trace, FOLLOWUP_CONFIG)
    assert excinfo.value.checks["policy_deviations"] == [{
        "kind": "policy_deviation", "caller_turn": 2, "stage": "help_reply",
        "policy": "needs_more_help_collector_required",
    }]


@pytest.mark.parametrize("parent_speech", (
    "Is there anything else I can help you with?",
    "Your confirmed appointment is with Dr Casey at Harbor Clinic.",
))
def test_parent_question_before_child_question_is_sticky_but_fact_statement_is_allowed(
    parent_speech,
):
    caller = M.EventGatedCaller(_case("followup_no_more_help"))
    trace = _driver_trace()
    caller(trace)
    caller.record_delivery(trace, 1)
    _main_speech(trace, 1, parent_speech)
    _activate(
        trace, "needs_more_help", "boolean", 1,
        "Your appointment is September 15 2026 at nine AM with Dr Casey at Harbor Clinic. "
        "Do you need any more help?",
    )

    assert caller(trace) == "No, that is all. Thank you."
    caller.record_delivery(trace, 2)

    deviations = [event for event in trace.events if event.get("kind") == "policy_deviation"]
    assert bool(deviations) is parent_speech.endswith("?")


@pytest.mark.parametrize(
    ("ordinal", "speech"),
    (
        (0, "Is there anything else I can help you with?"),
        (1, "Your appointment is confirmed."),
    ),
)
def test_stale_or_nonquestion_parent_speech_cannot_deliver_help_reply(ordinal, speech):
    caller = M.EventGatedCaller(_case("followup_no_more_help"))
    trace = _driver_trace()
    caller(trace)
    caller.record_delivery(trace, 1)
    _main_speech(trace, ordinal, speech)

    with pytest.raises(M.CallerWordingReview):
        caller(trace)


def test_initial_receipt_cannot_satisfy_later_factual_answer_check():
    trace = _driver_trace()
    trace.events.extend((
        {"kind": "caller_delivery", "caller_turn": 1, "stage": "initial", "text": "I am still here."},
        {
            "kind": "model_speech", "caller_turn": 1,
            "content": "Your appointment is with Dr Casey at Harbor Clinic.",
        },
        {"kind": "caller_delivery", "caller_turn": 2, "stage": "help_reply", "text": "Yes."},
        {
            "kind": "caller_delivery", "caller_turn": 3, "stage": "factual_question",
            "text": "Which provider and clinic is it with?",
        },
        {
            "kind": "model_speech", "caller_turn": 3,
            "content": "I can help. Is there anything else?",
        },
        {
            "kind": "caller_delivery", "caller_turn": 4, "stage": "final_no_help",
            "text": "No, that is all.",
        },
    ))
    _owned_store(trace, "needs_more_help", "boolean", "no", 4, 4)
    _terminal(trace, "Done", 4)

    with pytest.raises(M.MultiTurnOracleError, match="factual answer omitted"):
        M.evaluate_case(_case("followup_factual_help"), trace, FOLLOWUP_CONFIG)


def test_latest_speech_never_falls_back_to_stale_sim_turn_message():
    trace = SimpleNamespace(
        events=[], model_calls=[],
        turns=[{"message": "September 15 2026 at nine AM with Dr Casey at Harbor Clinic."}],
    )
    assert M._latest_speech(trace, 1) == ""


@pytest.mark.parametrize(
    ("selected", "readback"),
    (("option 2", "option 1"), ("option 1", "option 2")),
)
def test_stale_or_foreign_option_facts_cannot_authorize_booking(selected, readback):
    trace = _trace(
        selected=("option 1", selected) if selected == "option 2" else (selected,),
        consent_for=selected,
        readback_option=readback,
    )
    case = deepcopy(_case("choose_change_before_consent" if selected == "option 2" else "choose_fresh_yes"))
    with pytest.raises((M.MultiTurnOracleError, M.CallerWordingReview)):
        M.evaluate_case(case, trace, BOOK_CONFIG)


def test_selection_correction_yes_is_not_booking_consent():
    trace = _trace(selected=("option 1", "option 2"), consent_for=None, readback_option="option 2")
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case("choose_change_before_consent"), trace, BOOK_CONFIG)


@pytest.mark.parametrize("case_id", ("choose_decline", "choose_tentative_consent", "choose_conditional_consent"))
def test_nonconsent_paths_reject_affirmative_store_or_book(case_id):
    stages = {
        "choose_decline": ("booking_decline",),
        "choose_tentative_consent": ("tentative_reply", "final_decline"),
        "choose_conditional_consent": ("conditional_reply", "final_decline"),
    }[case_id]
    trace = _trace(intent="Patient Declines", consent_for=None, delivery_stages=stages)
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case(case_id), trace, BOOK_CONFIG)


def test_consent_producer_store_and_handoff_must_follow_delivery_in_order():
    trace = _trace()
    handoff = next(event for event in trace.events if event.get("name") == "handoff_book")
    trace.events.remove(handoff)
    store_index = next(i for i, event in enumerate(trace.events) if event.get("name") == "booking_confirmed")
    trace.events.insert(store_index, handoff)
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case(), trace, BOOK_CONFIG)


def test_early_consent_before_full_readback_is_rejected():
    trace = _trace()
    delivery = next(event for event in trace.events if event.get("consent_for"))
    trace.events.remove(delivery)
    message_index = next(i for i, event in enumerate(trace.events) if event.get("kind") == "message")
    trace.events.insert(message_index, delivery)
    with pytest.raises((M.MultiTurnOracleError, M.CallerWordingReview)):
        M.evaluate_case(_case(), trace, BOOK_CONFIG)


@pytest.mark.parametrize("value", (True, "true", 1))
def test_only_canonical_yes_is_affirmative(value):
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case(), _trace(booking=value), BOOK_CONFIG)


@pytest.mark.parametrize("value", (False, "false", 0))
def test_only_canonical_no_is_negative(value):
    trace = _trace(booking=value, intent="Patient Declines", consent_for=None)
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case("choose_decline"), trace, BOOK_CONFIG)


def test_canonical_no_is_accepted_for_decline():
    result = M.evaluate_case(
        _case("choose_decline"),
        _trace(
            booking="no", intent="Patient Declines", consent_for=None,
            delivery_stages=("booking_decline",),
        ),
        BOOK_CONFIG,
    )
    assert result["booking_store_count"] == 1


@pytest.mark.parametrize("damage", ("foreign_owner", "missing_producer", "exited_before_store"))
def test_foreign_fabricated_or_stale_booking_store_is_rejected(damage):
    trace = _trace()
    store = next(item for item in trace.stores if item["name"] == "booking_confirmed")
    if damage == "foreign_owner":
        store["collector"] = {"name": "other", "task_type": "boolean"}
    elif damage == "missing_producer":
        trace.executed = [call for call in trace.executed if call.get("name") != "update_boolean_answer"]
        trace.events = [event for event in trace.events if event.get("name") != "update_boolean_answer"]
    else:
        enter = next(event for event in trace.events if event.get("kind") == "collector_enter" and event.get("name") == "booking_confirmed")
        trace.events.insert(trace.events.index(enter) + 1, {
            "kind": "collector_exit", "caller_turn": enter["caller_turn"],
            "name": "booking_confirmed", "task_type": "boolean",
        })
    with pytest.raises((RuntimeError, M.MultiTurnOracleError)):
        M.evaluate_case(_case(), trace, BOOK_CONFIG)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda args: args.update(known_value="yes"),
        lambda args: args["options"].update(ask_before_update=False),
    ),
)
def test_boolean_policy_rejects_seed_or_missing_specific_gate(mutate):
    trace = _trace()
    args = next(
        call["effective_arguments"]
        for call in trace.emitted
        if call.get("name") == "collect_input"
    )
    mutate(args)
    with pytest.raises(M.MultiTurnOracleError):
        M._assert_boolean_policy(trace, "booking_confirmed")


def test_boolean_policy_allows_unrelated_defaults_and_extra_options():
    trace = _trace()
    M._assert_boolean_policy(trace, "booking_confirmed")


def test_boolean_policy_checks_every_collect_attempt_not_only_latest():
    trace = _trace()
    original = next(call for call in trace.emitted if call.get("name") == "collect_input")
    invalid = deepcopy(original)
    invalid["call_id"] = "collect-booking-invalid-earlier"
    invalid["effective_arguments"]["known_value"] = "yes"
    invalid["arguments"] = json.dumps(invalid["effective_arguments"])
    trace.emitted.insert(0, invalid)

    with pytest.raises(M.MultiTurnOracleError, match="implicitly seeded"):
        M._assert_boolean_policy(trace, "booking_confirmed")


@pytest.mark.parametrize("terminal_count", (0, 2))
def test_exactly_one_expected_terminal_is_mandatory(terminal_count):
    trace = _trace()
    emitted = next(
        event for event in trace.events
        if event.get("kind") == "emitted" and event.get("name") == "handoff_book"
    )
    terminal = next(
        event for event in trace.events
        if event.get("kind") == "executed" and event.get("name") == "handoff_book"
    )
    terminal_call = next(call for call in trace.executed if call.get("name") == "handoff_book")
    if terminal_count == 0:
        trace.events.remove(emitted)
        trace.events.remove(terminal)
        trace.emitted.remove(next(call for call in trace.emitted if call.get("name") == "handoff_book"))
        trace.executed.remove(terminal_call)
    else:
        trace.events.append(dict(emitted, call_id="terminal-2"))
        trace.events.append(dict(terminal, call_id="terminal-2"))
        trace.emitted.append(dict(emitted, call_id="terminal-2"))
        trace.executed.append(dict(terminal_call, call_id="terminal-2"))
    with pytest.raises(M.MultiTurnOracleError):
        M.evaluate_case(_case(), trace, BOOK_CONFIG)


def test_source_flow_pins_and_output_exclusivity_preflight(tmp_path):
    assert M.SOURCE_HEAD == "415aa7d5fcb1e42a6e79bb7f245ddebfed295c00"
    assert M.SOURCE_SHA256 == "8df972b2b4834a2e8ac4fcf006866730bd78410a9876a424d892cc86256bee5b"
    assert hashlib.sha256(M.FLOW_PATH.read_bytes()).hexdigest() == M.FLOW_SHA256

    env_file = tmp_path / "env"
    ledger = tmp_path / "ledger.json"
    output = tmp_path / "output.jsonl"
    for path in (env_file, ledger, output):
        path.write_text("{}")
    with pytest.raises(SystemExit):
        M._arguments([
            "--execute", "--case", "choose_fresh_yes", "--env-file", str(env_file),
            "--ledger", str(ledger), "--campaign-id", "test", "--output", str(output),
        ])
