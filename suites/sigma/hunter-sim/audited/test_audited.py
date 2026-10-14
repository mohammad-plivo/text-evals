from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


convert = load("convert")
judge = load("judge")


START_ID = "11111111-1111-1111-1111-111111111111"


def flow_with_refs(start_id=START_ID):
    return {
        "nodes": [
            {"id": start_id, "type": "start", "data": {"config": {"payload_format": {"empty": "string", "candidate_phone": "string"}}}},
            {"id": "agent", "type": "ai_agent_v29", "data": {"config": {"prompt": f"{{{{{start_id}.http.params.empty}}}} {{{{{start_id}.http.params.candidate_phone}}}}"}}},
        ],
        "edges": [],
    }


def test_bindings_preserve_empty_and_bind_only_actual_start_uuid():
    params, substitutions = convert.build_bindings(
        {"initiationVariables": {"source_empty": "", "unused": "kept"},
         "initiationRequest": {"bodyTemplate": json.dumps({"empty": "{{source_empty}}", "candidate_phone": "{{INBOUND_NUMBER}}"})}},
        flow_with_refs(), "+15550100000"
    )
    assert params == {"empty": "", "candidate_phone": "+15550100000"}
    assert substitutions == {
        f"{{{{{START_ID}.http.params.candidate_phone}}}}": "+15550100000",
        f"{{{{{START_ID}.http.params.empty}}}}": "",
    }


def test_bindings_reject_unresolved_required_ref():
    flow = flow_with_refs()
    flow["nodes"][1]["data"]["config"]["prompt"] += f" {{{{{START_ID}.http.params.missing}}}}"
    with pytest.raises(ValueError, match="undefined"):
        convert.build_bindings({"initiationVariables": {"empty": ""}, "initiationRequest": {
            "bodyTemplate": json.dumps({"empty": "{{empty}}", "candidate_phone": "{{INBOUND_NUMBER}}"})}},
            flow, "+15550100000")


def test_request_template_controls_names_literals_and_runtime_serialization():
    payload = {"initiationVariables": {"old_name": True, "nothing": None, "items": [1, 2]}, "initiationRequest": {
        "bodyTemplate": json.dumps({"renamed": "{{old_name}}", "literal": "fixed", "nothing": "{{nothing}}", "items": "{{items}}"})}}
    assert convert.request_params(payload, "+15550100000") == {
        "renamed": "true", "literal": "fixed", "nothing": "", "items": "[1,2]"
    }


def test_convert_uses_scenario_agent_config_and_refuses_overwrite(tmp_path):
    source = tmp_path / "case.json"
    flow = flow_with_refs()
    document = {
        "id": 1, "name": "Sigma v2.9 - ordinary", "payload": {
            "testType": "outbound-agent", "agentConfig": flow,
            "initiationVariables": {"empty": ""},
            "initiationRequest": {"bodyTemplate": json.dumps({"empty": "{{empty}}", "candidate_phone": "{{INBOUND_NUMBER}}"})},
            "conversationPrompt": "Persona\nTARGET is achieved when done.",
            "evaluationPrompt": "Evaluate:\n1. ONE", "maxTurns": 3,
        },
    }
    source.write_text(json.dumps(document))
    workspace = convert.convert_one(source, tmp_path / "new-root", "+15550100000")
    assert json.loads((workspace / "flow.json").read_text()) == flow
    assert json.loads((workspace / "hunter.json").read_text())["entry"]["node_id"] == "agent"
    with pytest.raises(FileExistsError):
        convert.convert_one(source, tmp_path / "new-root", "+15550100000")


def test_transcript_never_fabricates_closing_and_ended_comes_from_last_turn():
    run = {"ended": True, "turns": [
        {"user": "hello", "agent": "question", "ended": False, "transitions": []},
        {"user": "answer", "agent": "thanks", "ended": True, "transitions": [{"target": "end"}]},
    ]}
    text, ended = judge.transcript_evidence(run)
    assert ended is True
    assert "thanks" in text and "end node speaks" not in text
    assert "TRANSITION:" in text


def test_verdict_requires_exact_complete_unique_criteria():
    parsed = judge.parse_verdict("1: [MET] accuracy=91 - observed\n2: [NOT MET] accuracy=20 - absent", [1, 2], set())
    assert [item["id"] for item in parsed] == [1, 2]
    with pytest.raises(ValueError, match="exactly cover"):
        judge.parse_verdict("1: [MET] accuracy=91 - observed", [1, 2], set())


def test_an_unauthorised_na_is_counted_against_the_agent_and_tagged():
    parsed = judge.parse_verdict("1: [N/A] accuracy=0 - absent", [1], set())
    assert parsed[0]["status"] == "NOT MET" and parsed[0]["coerced_na"] is True
    assert parsed[0]["evidence"].startswith("[unauthorised N/A")


def test_na_permission_is_criterion_specific():
    rubric = "Evaluate:\n1. MUST HAPPEN: never N/A when absent.\n2. CUTOFF: if cut off mark N/A.\n3. REQUIRED: fail if absent."
    assert judge.na_allowed_ids(rubric) == {2}
    # Authored text controls permission: an N/A on an unlisted criterion is failed, not honoured.
    parsed = judge.parse_verdict("1: [MET] accuracy=90 - seen\n2: [MET] accuracy=90 - seen\n3: [N/A] accuracy=0 - absent", [1, 2, 3], {2})
    assert parsed[2]["status"] == "NOT MET" and parsed[2]["coerced_na"] is True
    assert [item["coerced_na"] for item in parsed[:2]] == [False, False]


def test_manifest_selects_explicit_report_not_latest(tmp_path):
    root = tmp_path / "root"; workspace = root / "case"; reports = workspace / "reports"
    reports.mkdir(parents=True)
    chosen = reports / "old.json"; chosen.write_text("[]")
    (reports / "new.json").write_text("[]")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"reports": [{"workspace": "case", "report": "case/reports/old.json"}]}))
    assert judge.load_manifest(manifest, root) == [(workspace.resolve(), chosen.resolve())]
