"""Offline checks for the Hunter-in-sim harness: H-2, H-4, H-5, H-7, H-8.

No network, no sim CLI, no paid call. Run it with the system python:

    python3 "Sigma/hunter-sim/test_harness.py"

The probes marked "through the product" import the worktree and read the master flow export; they
SKIP when either is missing. Run them with the worktree venv to exercise them:

    "<worktree>/.venv/bin/python" "Sigma/hunter-sim/test_harness.py"
"""
import asyncio
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert  # noqa: E402
from audited import judge as audited_judge  # noqa: E402

V29 = "f66906be-0fc9-43e5-bcf7-20117357082c"
WORKTREE = os.environ.get("SIGMA_WORKTREE",
                          "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/main-prs/wf-integrated")


class Skip(Exception):
    """The check needs the product code or the master export and one of them is not here."""


def product():
    """The worktree and its master flow export, or Skip: these checks read the real resolvers."""
    if WORKTREE not in sys.path:
        sys.path.insert(0, WORKTREE)
    try:
        import src.simulation.flow.graph  # noqa: F401
    except Exception as error:  # noqa: BLE001  the system python has no venv
        raise Skip(f"worktree not importable: {type(error).__name__}")
    master = os.path.join(WORKTREE, "eval_tests", "sigma_v29_hunter", "flow.json")
    if not os.path.exists(master):
        raise Skip("master flow export not present")
    return json.load(open(master))


def _flow() -> dict:
    """A console export in the shape the Sigma one has: AI edges keyed by intent NAME."""
    return {
        "nodes": [
            {"id": V29, "type": "ai_agent_v29", "data": {"config": {
                "intents": [
                    {"id": "645090db-24fc-45fd-bf3c-3a8deacc3351", "intent_name": "Interview Completed"},
                    {"id": "f1a99c82-3a47-48a5-8af9-3b1b4de91865", "intent_name": "Callback Scheduled"},
                ],
                "extract_variables": [
                    # the added Input is a console copy: it kept the twin's id, fingerprint, version and question
                    {"id": "9132681f", "variable_name": "communication_rating", "variable_instructions": "Rate your communication one to ten.",
                     "collection": {"type": "text", "required": True, "fingerprint": "24g3xv2uzwt",
                                    "version": "0521", "instructions": "What was your 10th standard score?"}},
                    {"id": "9132681f", "variable_name": "tenth_score", "variable_instructions": "What was your 10th standard score?",
                     "collection": {"type": "text", "required": True, "fingerprint": "24g3xv2uzwt",
                                    "version": "0521", "instructions": "What was your 10th standard score?"}},
                ],
            }}},
            {"id": "end-1", "type": "end_conversation", "data": {"config": {"end_message": "bye"}}},
            {"id": "screen", "type": "contact_screening", "data": {"config": {}}},
        ],
        "edges": [
            {"source": V29, "sourceHandle": "Interview Completed", "target": "end-1"},
            {"source": V29, "sourceHandle": "Callback Scheduled", "target": "end-1"},
            {"source": "screen", "sourceHandle": "reached", "target": V29},
        ],
    }


def test_h2_ai_edges_are_keyed_by_intent_id():
    """The sim resolves an AI outcome to the intent's id; an edge keyed by name never resolves."""
    flow = convert.bind_intent_edges(_flow())
    handles = {e["sourceHandle"] for e in flow["edges"] if e["source"] == V29}
    assert handles == {"645090db-24fc-45fd-bf3c-3a8deacc3351", "f1a99c82-3a47-48a5-8af9-3b1b4de91865"}, handles
    screening = [e for e in flow["edges"] if e["source"] == "screen"]
    assert screening[0]["sourceHandle"] == "reached", "a screening disposition is a literal handle"


def test_h2_leaves_an_export_that_already_uses_ids():
    flow = _flow()
    for edge in flow["edges"]:
        if edge["source"] == V29:
            edge["sourceHandle"] = "645090db-24fc-45fd-bf3c-3a8deacc3351"
    before = json.dumps(flow, sort_keys=True)
    assert json.dumps(convert.bind_intent_edges(flow), sort_keys=True) == before


def test_h2_through_the_product_every_intent_reaches_a_target():
    """The behaviour H-2 claims, through the sim's own resolvers, on the real master export.

    It must hold BEFORE the converter touches anything (the resolver falls back to the authored
    name) and after (the converter rekeys to the id), or a run ends in no_matching_handoff.
    """
    raw = product()
    from src.simulation.flow.graph import build_graph

    for label, flow in (("as exported", json.loads(json.dumps(raw))),
                        ("as converted", convert.bind_intent_edges(json.loads(json.dumps(raw))))):
        graph = build_graph(flow)
        seen = 0
        for node in graph.nodes_by_id.values():
            for intent in node.config.get("intents") or []:
                handle = graph.resolve_handle(node, intent["intent_name"])
                assert graph.edge_target(node.id, handle) is not None, f"{label}: no edge for {intent['intent_name']}"
                seen += 1
        assert seen, f"{label}: the export carries no intents to resolve"


def test_h4_workspace_carries_the_calling_window_timezone():
    flow = convert.set_timezone(_flow(), "Asia/Kolkata")
    assert (flow["agent_settings"]["schedule"]["timezone"]) == "Asia/Kolkata"


def test_h4_an_authored_timezone_wins():
    flow = _flow()
    flow["agentSettings"] = {"schedule": {"timezone": "America/New_York"}}
    flow = convert.set_timezone(flow, "Asia/Kolkata")
    assert flow["agentSettings"]["schedule"]["timezone"] == "America/New_York"
    assert "agent_settings" not in flow


def test_h8_a_copied_input_stops_asking_its_twins_question():
    flow = convert.unshare_copied_questions(_flow())
    inputs = flow["nodes"][0]["data"]["config"]["extract_variables"]
    copied = next(i for i in inputs if i["variable_name"] == "communication_rating")
    assert copied["collection"].get("instructions") in (None, ""), "the twin's question must not be asked for this Input"
    assert copied["collection"].get("version") is None, "a copied version marks the Input stale"
    kept = next(i for i in inputs if i["variable_name"] == "tenth_score")
    assert kept["collection"]["instructions"] == "What was your 10th standard score?", \
        "the Input the block belongs to keeps it, wherever it sits in the list"
    assert kept["collection"]["version"] == "0521"


def test_h8_is_idempotent():
    once = convert.unshare_copied_questions(_flow())
    before = json.dumps(once, sort_keys=True)
    assert json.dumps(convert.unshare_copied_questions(once), sort_keys=True) == before


def _questions_taken_from_another_input(flow) -> list[str]:
    """The Inputs whose resolved question is a different Input's own question."""
    try:
        from src.models.ai_config import AgentNodeConfig
        from src.simulation.flow.agent_config import build_config
        from src.simulation.flow.graph import build_graph
        from src.units.collection_configuration import resolve_collection_configurations
    except Exception as error:  # noqa: BLE001  the runtime units need the worktree venv
        raise Skip(f"runtime units not importable: {type(error).__name__}")

    node = next(n for n in flow["nodes"] if ((n.get("data") or {}).get("config") or {}).get("extract_variables"))
    variables = node["data"]["config"]["extract_variables"]
    graph = build_graph(flow)
    config = build_config(graph, graph.nodes_by_id[node["id"]])
    resolved = resolve_collection_configurations(AgentNodeConfig.model_validate({**config, "variables": variables}))
    broken = [name for name, entry in resolved.items() if getattr(entry, "reason", None)]
    assert not broken, f"the repair must not make an Input fail closed: {broken}"
    asks = {v["variable_name"]: (v.get("variable_instructions") or "").strip() for v in variables}
    taken = []
    for name, entry in resolved.items():
        text = (getattr(entry, "instructions", None) or "").strip()
        others = {question for other, question in asks.items() if other != name and question}
        if text and text != asks.get(name) and text in others:
            taken.append(name)
    return taken


def test_h8_through_the_product_no_input_is_handed_another_inputs_question():
    """The behaviour H-8 claims, through the runtime's own configuration resolver."""
    raw = product()
    assert _questions_taken_from_another_input(json.loads(json.dumps(raw))), \
        "the master export is supposed to carry the copied Input this check guards"
    assert _questions_taken_from_another_input(convert.unshare_copied_questions(json.loads(json.dumps(raw)))) == []


def test_h5_the_judge_is_told_the_call_date():
    assert audited_judge.call_clock(Path("20260919-083409.json"), "Asia/Kolkata") == \
        "Saturday, 19 September 2026, 08:34 Asia/Kolkata"
    assert audited_judge.call_clock(Path("no-stamp.json"), "UTC") == ""


def test_h5_each_run_is_graded_against_its_own_clock():
    """The report stamp is the batch start; run 2 of a repeat batch ran later, possibly another day."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "20260919-233000.json"
        report.write_text("[]")
        events = [
            {"type": "suite_started", "ts": dt.datetime(2026, 9, 19, 23, 30).timestamp()},
            {"type": "scenario_started", "run": 1, "ts": dt.datetime(2026, 9, 19, 23, 32).timestamp()},
            {"type": "scenario_started", "run": 2, "ts": dt.datetime(2026, 9, 20, 0, 5).timestamp()},
        ]
        report.with_suffix(".jsonl").write_text("\n".join(json.dumps(e) for e in events))
        clocks = audited_judge.run_clocks(report)
        assert audited_judge.call_clock(report, "Asia/Kolkata", clocks.get(2)) == \
            "Sunday, 20 September 2026, 00:05 Asia/Kolkata"
        assert audited_judge.call_clock(report, "Asia/Kolkata", clocks.get(9)) == \
            "Saturday, 19 September 2026, 23:30 Asia/Kolkata", "no sidecar entry falls back to the batch stamp"


def test_h7_a_verdict_that_contradicts_its_evidence_is_ungraded():
    rubric = "1. The agent asks each question once.\n2. The agent never invents a question.\n"
    verdicts = [
        {"id": 1, "status": "NOT MET", "accuracy": 90, "evidence": "No technical or other question was asked twice in the same form."},
        {"id": 2, "status": "NOT MET", "accuracy": 90, "evidence": "The agent asked two questions that were not supplied."},
    ]

    async def chat(system, prompt, deployment=""):
        assert "1:" in prompt and "2:" in prompt
        return "1: CONTRADICTS\n2: CONSISTENT"

    ids = asyncio.run(audited_judge.contradicting_ids(rubric, verdicts, chat, "gpt-4.1"))
    assert ids == {1}, ids


def test_h7_no_model_call_when_every_criterion_is_met():
    async def chat(system, prompt, deployment=""):
        raise AssertionError("the contradiction pass must not run without a NOT MET verdict")

    verdicts = [{"id": 1, "status": "MET", "accuracy": 100, "evidence": "asked once"}]
    assert asyncio.run(audited_judge.contradicting_ids("1. x\n", verdicts, chat, "gpt-4.1")) == set()


def test_h7_an_unauthorised_na_can_never_be_ungraded():
    """A coerced N/A reads as 'it did not happen', so the contradiction pass would hand back the
    very N/A the rubric author forbade. Only a verdict the judge itself chose to fail may be ungraded."""
    rubric = "1. The agent never repeats a question.\n"
    verdicts = audited_judge.parse_verdict('1: [N/A] accuracy=100 - No callback time was discussed.', [1], set())
    assert verdicts[0]["status"] == "NOT MET" and verdicts[0]["coerced_na"] is True

    async def chat(system, prompt, deployment=""):
        raise AssertionError("a coerced N/A must not be put to the contradiction model")

    assert asyncio.run(audited_judge.contradicting_ids(rubric, verdicts, chat, "gpt-4.1")) == set()


def test_h7_grade_report_keeps_a_coerced_na_in_the_denominator():
    """End to end: the contradiction pass must not hand back the N/A the rubric author forbade."""
    rubric = "Grade:\n1. The agent never repeats a question.\n"

    async def chat(system, prompt, deployment=""):
        if "self-contradiction" in system:
            raise AssertionError("no NOT MET the judge itself chose, so there is nothing to check")
        return "1: [N/A] accuracy=100 - No callback time was discussed, so this is not applicable."

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "hunter.json").write_text(json.dumps({"name": "x", "evaluationPrompt": rubric,
                                                           "evaluationThreshold": 0.8, "timezone": "Asia/Kolkata"}))
        report = workspace / "20260919-083409.json"
        report.write_text(json.dumps([{"scenario": "x", "run": 1, "turns": [{"agent": "hello", "ended": True}]}]))
        graded = asyncio.run(audited_judge.grade_report(workspace, report, chat, "gpt-4.1"))

    run = graded["runs"][0]
    assert run["ungraded_ids"] == [], run["ungraded_ids"]
    assert [v["status"] for v in audited_judge.gradable(run["criteria"])] == ["NOT MET"]
    assert run["all_criteria_met"] is False


def test_h7_an_ungraded_criterion_is_not_counted_against_the_agent():
    verdicts = [
        {"id": 1, "status": "UNGRADED", "accuracy": 90, "evidence": "x"},
        {"id": 2, "status": "MET", "accuracy": 90, "evidence": "y"},
        {"id": 3, "status": "N/A", "accuracy": 90, "evidence": "z"},
    ]
    applicable = audited_judge.gradable(verdicts)
    assert [v["id"] for v in applicable] == [2]
    assert all(v["status"] == "MET" for v in applicable)


def test_converter_records_its_repairs_for_the_board():
    """The board must be able to say which of its numbers were won on a repaired flow."""
    repairs = []
    flow = convert.unshare_copied_questions(
        convert.set_timezone(convert.bind_intent_edges(_flow(), repairs), "Asia/Kolkata", repairs), repairs)
    assert flow and len(repairs) == 3, repairs
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "hunter.json"
        path.write_text(json.dumps(convert.hunter_metadata(
            {"id": "t", "name": "Sigma v2.9 - clean walk"}, {"evaluationPrompt": "1. x\n", "evaluationThreshold": 0.8},
            "src.json", "Asia/Kolkata", repairs)))
        written = json.loads(path.read_text())
        assert written["timezone"] == "Asia/Kolkata"
        assert written["repairs"] == repairs


def main() -> int:
    failed = skipped = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Skip as reason:
            skipped += 1
            print(f"SKIP {name}: {reason}")
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {type(error).__name__}: {error}")
    print(f"\n{failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
