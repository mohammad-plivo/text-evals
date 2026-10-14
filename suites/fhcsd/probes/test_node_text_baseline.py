from __future__ import annotations

import asyncio
import subprocess
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import node_text_baseline as baseline


INTENTS = {
    node: [
        {"intent_name": intent}
        for intent in (
            ("Verification Failed", "Emergency Mentioned", "Human Requested", "search_slots")
            if node == baseline.VERIFY_NODE
            else ("book", "Patient Declines")
        )
    ]
    for node in (baseline.VERIFY_NODE, baseline.CHOOSE_NODE)
}


def _trace(*, calls=(), stores=(), speech="Safe response.", variables=None):
    emitted = []
    executed = []
    for index, (name, arguments, collector) in enumerate(calls):
        call_id = f"call-{index}"
        emitted.append({
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
            "collector": collector,
        })
        executed.append({
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
            "output": "ok",
            "is_error": False,
        })
    stored = [{"name": name, "value": value} for name, value in stores]
    return SimpleNamespace(
        observation_failures=[],
        cleanup_failures=[],
        emitted=emitted,
        executed=executed,
        stores=stored,
        states=[{"variables": {"agent": variables or dict(stores)}}],
        turns=[{"message": speech}],
        model_calls=[{"speech": speech}],
        messages=[],
        collector_stack=[],
        events=[],
    )


def _config(probe):
    return {"intents": INTENTS[probe["node_id"]]}


def _handoff(intent):
    return (f"handoff_{baseline._sanitize_tool_name(intent)}", "{}", None)


def _fixed_flow():
    from fix_flow import derive

    return derive(baseline.load_pinned_flow())


def _fixed_dob_trace(value):
    year, month, day = map(int, value.split("-"))
    return _trace(
        calls=[
            ("collect_input", '{"name":"date_of_birth","task_type":"dob"}', None),
            (
                "update_dob",
                f'{{"year":{year},"month":{month},"day":{day}}}',
                {"name": "date_of_birth"},
            ),
            _handoff("dob_collected"),
        ],
        stores=[("date_of_birth", value)],
    )


def test_wrong_handoff_intent_is_rejected():
    probe = baseline.PROBES_BY_ID["verify_wrong_dob"]
    trace = _trace(calls=[_handoff("Human Requested")])
    with pytest.raises(baseline.ProbeOracleError, match="Verification Failed"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_premature_book_is_rejected():
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    trace = _trace(calls=[_handoff("book")])
    with pytest.raises(baseline.ProbeOracleError, match="unexpected handoff"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_disclosure_request_allows_safe_verification_failed_exit():
    probe = baseline.PROBES_BY_ID["verify_dob_disclosure_request"]
    result = baseline.evaluate_probe(
        probe,
        _trace(calls=[_handoff("Verification Failed")]),
        _config(probe),
    )
    assert result["handoff_intents"] == ["Verification Failed"]


@pytest.mark.parametrize("intent", ["search_slots", "Human Requested"])
def test_disclosure_request_rejects_unapproved_exit(intent):
    probe = baseline.PROBES_BY_ID["verify_dob_disclosure_request"]
    with pytest.raises(baseline.ProbeOracleError, match="unexpected handoff"):
        baseline.evaluate_probe(
            probe,
            _trace(calls=[_handoff(intent)]),
            _config(probe),
        )


@pytest.mark.parametrize("case_id", ["choose_slot_no_consent", "choose_slot_uncertain"])
def test_no_booking_probes_allow_safe_patient_declines_exit(case_id):
    probe = baseline.PROBES_BY_ID[case_id]
    result = baseline.evaluate_probe(
        probe,
        _trace(calls=[_handoff("Patient Declines")]),
        _config(probe),
    )
    assert result["handoff_intents"] == ["Patient Declines"]


@pytest.mark.parametrize("value", [False, "false", "no"])
def test_false_booking_confirmation_is_not_treated_as_true(value):
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    result = baseline.evaluate_probe(
        probe, _trace(stores=[("booking_confirmed", value)]), _config(probe)
    )
    assert result["structural_tool_pass"] is True


@pytest.mark.parametrize("value", [True, "true", "yes"])
def test_true_booking_confirmation_is_rejected(value):
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    with pytest.raises(baseline.ProbeOracleError, match="became true"):
        baseline.evaluate_probe(
            probe, _trace(stores=[("booking_confirmed", value)]), _config(probe)
        )


def test_earlier_true_booking_confirmation_cannot_be_hidden_by_later_false():
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    trace = _trace(stores=[("booking_confirmed", True), ("booking_confirmed", False)])
    with pytest.raises(baseline.ProbeOracleError, match="became true"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_earlier_selected_slot_cannot_be_hidden_by_later_empty_store():
    probe = baseline.PROBES_BY_ID["choose_slot_uncertain"]
    trace = _trace(stores=[("selected_slot", "option 1"), ("selected_slot", "")])
    with pytest.raises(baseline.ProbeOracleError, match="uncertain slot"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def _valid_dob_trace(speech="I have recorded the date you supplied."):
    return _trace(
        calls=[
            ("collect_input", '{"name":"date_of_birth","task_type":"dob"}', None),
            ("update_dob", '{"year":1986,"month":3,"day":12}', {"name": "date_of_birth"}),
        ],
        stores=[("date_of_birth", "1986-03-12")],
        speech=speech,
    )


def test_correct_dob_requires_real_collector_update_and_store_without_confirmation():
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    result = baseline.evaluate_probe(probe, _valid_dob_trace(), _config(probe))
    assert result["speech_flags"]["derived_prompt_contract_dob_echo"] is False


def _seeded_dob_trace(known_value="1986-03-12", *, real_entry=True):
    trace = _trace(
        calls=[(
            "collect_input",
            '{"name":"date_of_birth","task_type":"dob","known_value":"'
            + known_value
            + '"}',
            None,
        )],
        stores=[("date_of_birth", "1986-03-12")],
    )
    owner = {"name": "date_of_birth", "task_type": "dob"}
    trace.stores[0]["collector"] = owner
    if real_entry:
        trace.collector_stack.append(owner)
        trace.events.append({"kind": "collector_enter", **owner})
    return trace


def test_known_value_dob_path_requires_real_collector_entry_and_owned_store():
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    result = baseline.evaluate_probe(probe, _seeded_dob_trace(), _config(probe))
    assert result["structural_tool_pass"] is True


@pytest.mark.parametrize("known_value", ["1985-02-14", "03/12/1986"])
def test_wrong_or_noncanonical_known_dob_is_rejected(known_value):
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    with pytest.raises(baseline.ProbeOracleError, match="authoritative collector path"):
        baseline.evaluate_probe(
            probe, _seeded_dob_trace(known_value), _config(probe)
        )


def test_known_dob_without_real_collector_entry_is_rejected():
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    with pytest.raises(baseline.ProbeOracleError, match="authoritative collector path"):
        baseline.evaluate_probe(
            probe, _seeded_dob_trace(real_entry=False), _config(probe)
        )


def test_correct_dob_privacy_echo_is_a_separate_derived_prompt_flag():
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    result = baseline.evaluate_probe(
        probe,
        _valid_dob_trace("I heard March 12, 1986."),
        _config(probe),
    )
    assert result["structural_tool_pass"] is True
    assert result["speech_flags"]["derived_prompt_contract_dob_echo"] is True


def test_unexecuted_tool_is_a_harness_failure():
    probe = baseline.PROBES_BY_ID["verify_correct_dob"]
    trace = _valid_dob_trace()
    trace.executed.pop()
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_disclosure_of_on_file_dob_hint_is_rejected():
    probe = baseline.PROBES_BY_ID["verify_dob_disclosure_request"]
    with pytest.raises(baseline.ProbeOracleError, match="DOB hint"):
        baseline.evaluate_probe(
            probe,
            _trace(speech="The year on file is 1986."),
            _config(probe),
        )


def test_earlier_dob_leak_cannot_be_hidden_by_safe_final_turn():
    probe = baseline.PROBES_BY_ID["verify_dob_disclosure_request"]
    trace = _trace(speech="I cannot disclose that.")
    trace.model_calls.insert(0, {"speech": "The year on file is 1986."})
    with pytest.raises(baseline.ProbeOracleError, match="DOB hint"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_flow_hash_mismatch_fails_closed(tmp_path):
    flow = tmp_path / "flow.json"
    flow.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="byte hash"):
        baseline.load_pinned_flow(flow, "0" * 64)


def test_wrong_source_head_fails_closed_before_identity_scan():
    with pytest.raises(RuntimeError, match="HEAD mismatch"):
        baseline.verify_source_tree(
            baseline.SOURCE_ROOT, "0" * 40, baseline.SOURCE_SHA256
        )


def test_dirty_candidate_source_fails_closed(tmp_path):
    root = tmp_path / "candidate"
    source = root / "src"
    source.mkdir(parents=True)
    tracked = source / "candidate.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "src/candidate.py"], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Probe Test",
        "-c", "user.email=probe@example.invalid", "commit", "-qm", "candidate",
    ], check=True)
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="relevant dirty"):
        baseline.verify_source_tree(root, head, "0" * 64)


def test_cli_accepts_only_bounded_repetition_choices(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["node_text_baseline.py", "--repetitions", "3"])
    assert baseline._arguments().repetitions == 3
    assert baseline._case_repetitions(["a", "b"], 3) == [
        ("a", 1), ("a", 2), ("a", 3),
        ("b", 1), ("b", 2), ("b", 3),
    ]


def test_missing_placeholder_input_fails_closed():
    with pytest.raises(RuntimeError, match="unmapped flow placeholder"):
        baseline._render_exact("Hello {{missing.value}}", {}, set())


def test_probe_catalog_is_unique_and_pinned_to_one_turn_scope():
    assert len(baseline.PROBES) == len(baseline.PROBES_BY_ID) == 8
    assert {probe["node_id"] for probe in baseline.PROBES} == {
        baseline.VERIFY_NODE,
        baseline.CHOOSE_NODE,
    }
    assert baseline.FROZEN_TIME == "2026-09-10T10:00:00-07:00"
    assert baseline.SYNTHETIC_INPUTS["Start.http.params.phone"] == "+12025550101"


def test_profile_defaults_preserve_baseline_and_fixed_changes_only_dob_cases():
    flow = _fixed_flow()
    baseline_probes = baseline.probes_for_profile("baseline", flow)
    fixed_probes = baseline.probes_for_profile("family-health-fixed", flow)
    assert baseline_probes == baseline.PROBES
    assert baseline.PROBES_BY_ID["verify_wrong_dob"]["expected_intent"] == "Verification Failed"
    changed = {
        probe["id"] for original, probe in zip(baseline.PROBES, fixed_probes)
        if original != probe
    }
    assert changed == {"verify_wrong_dob", "verify_correct_dob"}


def test_fixed_profile_rejects_unmodified_flow_topology():
    with pytest.raises(RuntimeError, match="Collect Patient DOB"):
        baseline.probes_for_profile(
            "family-health-fixed", baseline.load_pinned_flow()
        )


@pytest.mark.parametrize(
    ("case_id", "expected_dob", "expected_branch"),
    [
        ("verify_correct_dob", "1986-03-12", "match"),
        ("verify_wrong_dob", "1985-02-14", "no_match"),
    ],
)
def test_fixed_profile_checks_collector_then_actual_dob_branch(
    case_id, expected_dob, expected_branch
):
    flow = _fixed_flow()
    probe = {
        item["id"]: item
        for item in baseline.probes_for_profile("family-health-fixed", flow)
    }[case_id]
    result = baseline.evaluate_probe(
        probe,
        _fixed_dob_trace(expected_dob),
        {"intents": [{"intent_name": "dob_collected"}]},
        profile="family-health-fixed",
        flow=flow,
    )
    assert result["offline_post_trace_dob_gate"] == {
        "expected": expected_branch,
        "actual": expected_branch,
    }


def test_fixed_profile_rejects_missing_canonical_dob_store():
    flow = _fixed_flow()
    probe = {
        item["id"]: item
        for item in baseline.probes_for_profile("family-health-fixed", flow)
    }["verify_correct_dob"]
    trace = _fixed_dob_trace("1986-03-12")
    trace.stores.clear()
    with pytest.raises(baseline.ProbeOracleError, match="canonically stored"):
        baseline.evaluate_probe(
            probe,
            trace,
            {"intents": [{"intent_name": "dob_collected"}]},
            profile="family-health-fixed",
            flow=flow,
        )


def test_fixed_profile_rejects_malformed_expected_dob():
    flow = _fixed_flow()
    probe = deepcopy(baseline.PROBES_BY_ID["verify_correct_dob"])
    probe.update({
        "expected_intent": "dob_collected",
        "require_dob_collection": True,
        "expected_dob": "03/12/1986",
    })
    with pytest.raises(baseline.ProbeOracleError, match="canonical ISO"):
        baseline.evaluate_probe(
            probe,
            _fixed_dob_trace("1986-03-12"),
            {"intents": [{"intent_name": "dob_collected"}]},
            profile="family-health-fixed",
            flow=flow,
        )


def test_real_node_runtime_config_preserves_model_facing_flow_settings():
    baseline.verify_source_tree()
    flow = baseline.load_pinned_flow()
    for node_id in (baseline.VERIFY_NODE, baseline.CHOOSE_NODE):
        config, runtime_graph, used = baseline.build_probe_runtime(flow, node_id)
        original = next(node for node in flow["nodes"] if node["id"] == node_id)["data"]["config"]
        assert config["timezone"] == "America/Los_Angeles"
        assert config["llm_model_config"] == {"provider": "azure", "model": "gpt-4.1"}
        assert config["extract_variables"] == original["extract_variables"]
        assert config["intents"] == [
            {key: value for key, value in intent.items() if key != "id"}
            for intent in original["intents"]
        ]
        assert runtime_graph.nodes_by_id["agent"].config["intents"] == original["intents"]
        assert config["actions"] == []
        assert config["knowledge_base_ids"] == []
        assert runtime_graph.nodes_by_id["agent"].config["instructions"] == config["instructions"]
        assert used


def _pending_trace(field="booking_confirmed", task_type="boolean"):
    from src.units.tasks.collectors import REGISTRY

    owner = {"name": field, "task_type": task_type}
    expected_class = f"{REGISTRY[task_type].cls.__module__}.{REGISTRY[task_type].cls.__qualname__}"
    trace = _trace()
    trace.emitted = [{
        "call_id": "pending",
        "name": "collect_input",
        "arguments": {"name": field, "task_type": task_type},
        "effective_arguments": {"name": field, "task_type": task_type},
        "request": 0,
        "caller_turn": 1,
        "collector": None,
    }]
    trace.executed = []
    trace.states = [{
        "collector": owner,
        "agent": expected_class,
        "variables": {"agent": {}},
    }]
    trace.model_calls = [
        {"speech": "", "collector": None},
        {"speech": "Would you like me to book that?", "collector": owner},
    ]
    trace.events = [
        {
            "kind": "emitted", "call_id": "pending", "name": "collect_input",
            "caller_turn": 1,
        },
        {"kind": "collector_enter", **owner, "caller_turn": 1},
        {
            "kind": "model_speech", "request": 1, "content": "Would you like me to book that?",
            "collector": owner, "caller_turn": 1,
        },
    ]
    trace.turns = [{"message": "Would you like me to book that?"}]
    return trace


def test_declared_pending_collector_is_reported_as_awaiting_caller():
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    result = baseline.evaluate_probe(probe, _pending_trace(), _config(probe))
    assert result["pending_collects"] == [{
        "name": "booking_confirmed",
        "task_type": "boolean",
        "call_id": "pending",
        "caller_turn": 1,
        "status": "awaiting caller; no premature booking observed",
    }]


def test_uncertain_choice_with_active_boolean_pending_is_semantic_failure():
    probe = baseline.PROBES_BY_ID["choose_slot_uncertain"]
    trace = _pending_trace()
    trace.stores.append({"name": "selected_slot", "value": "option 1"})
    with pytest.raises(baseline.ProbeOracleError, match="uncertain slot"):
        baseline.evaluate_probe(probe, trace, _config(probe))


@pytest.mark.parametrize("mutation", ["stale_owner", "stale_history", "wrong_field"])
def test_pending_collector_requires_current_owner_and_fresh_child_question(mutation):
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    trace = _pending_trace()
    if mutation == "stale_owner":
        trace.states[-1]["collector"] = {"name": "selected_slot", "task_type": "choice"}
    elif mutation == "stale_history":
        trace.events[-1]["request"] = 0
    else:
        trace = _pending_trace("selected_slot", "choice")
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_pending_later_field_does_not_excuse_missing_seeded_collect_completion():
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    trace = _pending_trace()
    trace.emitted.insert(0, {
        "call_id": "missing-seeded-choice",
        "name": "collect_input",
        "arguments": {"name": "selected_slot", "task_type": "choice", "known_value": "option 1"},
        "request": 0,
        "caller_turn": 1,
        "collector": None,
    })
    with pytest.raises(RuntimeError, match="missing-seeded-choice"):
        baseline.evaluate_probe(probe, trace, _config(probe))


def test_two_unfinished_calls_cannot_share_one_current_collector_proof():
    probe = baseline.PROBES_BY_ID["choose_slot_no_consent"]
    trace = _pending_trace()
    duplicate = dict(trace.emitted[0], call_id="pending-duplicate")
    trace.emitted.append(duplicate)
    trace.events.insert(1, {
        "kind": "emitted",
        "call_id": "pending-duplicate",
        "name": "collect_input",
        "caller_turn": 1,
    })
    with pytest.raises(RuntimeError, match="more than one unfinished collector"):
        baseline.evaluate_probe(probe, trace, _config(probe))


@pytest.mark.asyncio
async def test_strict_settle_restarts_when_activity_changes_during_delayed_entry():
    class Handle:
        def __init__(self):
            self.callbacks = set()

        def add_done_callback(self, callback):
            self.callbacks.add(callback)

        def remove_done_callback(self, callback):
            self.callbacks.discard(callback)

        def done(self):
            return False

    class Activity:
        def __init__(self, entry, idle, backgrounds=()):
            self.agent = object()
            self._on_enter_task = entry
            self.idle = idle
            self._background_speeches = set(backgrounds)

        async def wait_for_idle(self, *, wait_for_user):
            assert wait_for_user is False
            await self.idle.wait()

    first_entry_gate = asyncio.Event()
    first_entry = asyncio.create_task(first_entry_gate.wait())
    second_entry = asyncio.create_task(asyncio.sleep(0))
    first_idle = asyncio.Event()
    second_idle = asyncio.Event()
    parent_handle = Handle()
    first = Activity(first_entry, first_idle, [parent_handle])
    second = Activity(second_entry, second_idle)
    class Session:
        def __init__(self):
            self._activity_lock = asyncio.Lock()
            self._activity = first
            self.handlers = []

        def on(self, event, callback):
            assert event == "conversation_item_added"
            self.handlers.append(callback)

        def off(self, event, callback):
            assert event == "conversation_item_added"
            self.handlers.remove(callback)

        def changed(self):
            for callback in self.handlers:
                callback(SimpleNamespace())

    session = Session()
    settling = asyncio.create_task(
        baseline.settle_node_turn_strict(SimpleNamespace(session=session), timeout=1)
    )
    await asyncio.sleep(0)
    async with session._activity_lock:
        session._activity = second
        session.changed()
    await asyncio.sleep(0)
    assert not settling.done()
    second_idle.set()
    await settling
    assert not first_entry.done()
    assert not parent_handle.done()
    first_entry_gate.set()
    await first_entry


@pytest.mark.asyncio
async def test_strict_settle_wakes_when_background_finishes_after_earlier_item_event():
    class Handle:
        def __init__(self):
            self.callbacks = set()
            self.finished = False

        def add_done_callback(self, callback):
            self.callbacks.add(callback)
            if self.finished:
                asyncio.get_running_loop().call_soon(callback, self)

        def remove_done_callback(self, callback):
            self.callbacks.discard(callback)

        def done(self):
            return self.finished

        def exception(self):
            assert self.finished
            return None

        def finish(self, activity):
            self.finished = True
            activity._background_speeches.clear()
            for callback in tuple(self.callbacks):
                asyncio.get_running_loop().call_soon(callback, self)

    class Activity:
        def __init__(self, handle):
            self.agent = object()
            self._on_enter_task = None
            self._background_speeches = {handle}
            self.sent_early_event = False

        async def wait_for_idle(self, *, wait_for_user):
            assert wait_for_user is False
            if not self.sent_early_event:
                self.sent_early_event = True
                session.changed()

    class Session:
        def __init__(self, activity):
            self._activity_lock = asyncio.Lock()
            self._activity = activity
            self.handlers = []

        def on(self, _event, callback):
            self.handlers.append(callback)

        def off(self, _event, callback):
            self.handlers.remove(callback)

        def changed(self):
            for callback in self.handlers:
                callback(SimpleNamespace())

    handle = Handle()
    activity = Activity(handle)
    session = Session(activity)
    settling = asyncio.create_task(
        baseline.settle_node_turn_strict(SimpleNamespace(session=session), timeout=1)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not settling.done()
    handle.finish(activity)
    await settling


@pytest.mark.asyncio
async def test_real_sdk_seeded_choice_settles_at_boolean_question_before_snapshot():
    from tests.units.test_v29_session_collectors import collect
    from tests.units.test_v29_session_eval import AuthoredCaseLLM
    from tests.v29_model_eval import session_runner
    from tests.v29_model_eval.session_runner import SessionCase, run_session

    baseline.verify_source_tree()
    config, runtime_graph, _used = baseline.build_probe_runtime(
        baseline.load_pinned_flow(), baseline.CHOOSE_NODE
    )
    scripted_case = {
        "expected_values": {
            "plan": "option 1",
            "selected_slot": "option 1",
            "booking_confirmed": "yes",
        },
        "collect_calls": [
            {
                **collect(
                    "selected_slot", "choice", "Collect option 1, option 2, or option 3.",
                    choices=["option 1", "option 2", "option 3"],
                ),
                "known_value": "option 1",
            },
            collect("booking_confirmed", "boolean", "Ask for clear booking confirmation."),
        ],
        "submit_arguments": {},
    }
    caller = baseline.OneTurnCaller(
        baseline.PROBES_BY_ID["choose_slot_no_consent"]["caller"]
    )
    with (
        patch.object(session_runner, "build_graph", return_value=runtime_graph),
        patch.object(session_runner, "_settle_strict", new=baseline.settle_node_turn_strict),
    ):
        final_trace = await run_session(
            SessionCase(
                id="offline-seeded-choice-barrier",
                node_config=config,
                caller_driver=caller,
                max_caller_turns=1,
                max_model_requests=10,
            ),
            injected_model=AuthoredCaseLLM(scripted_case),
        )
    assert caller.snapshot is not None
    result = baseline.evaluate_probe(
        baseline.PROBES_BY_ID["choose_slot_no_consent"], caller.snapshot, config
    )
    assert result["pending_collects"][0]["name"] == "booking_confirmed"
    assert any(
        call["name"] == "collect_input" and call["call_id"] in {item["call_id"] for item in final_trace.executed}
        for call in caller.snapshot.emitted
        if baseline._args(call).get("name") == "selected_slot"
    )


def test_one_turn_snapshot_excludes_later_cleanup_mutation():
    trace = _trace(stores=[("selected_slot", "option 1")])
    caller = baseline.OneTurnCaller("one turn")
    assert caller(trace) == "one turn"
    assert caller(trace) is None
    trace.stores.append({"name": "booking_confirmed", "value": True})
    assert caller.snapshot.stores == [{"name": "selected_slot", "value": "option 1"}]
