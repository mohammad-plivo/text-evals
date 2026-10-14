"""Negative controls for the text gate: the harness must FAIL these, with no model calls.

Each case is one false-pass path the auditor reproduced on 2026-09-21 (wrong exit, skipped screening
coverage counted as satisfied, a judge reply that repeats criterion 1 and omits 2), plus simulator
failures, an elicited turn, which can never prove the agent spoke unprompted, and agent speech that
carries a tag or a snake_case token (planning or tool syntax that TTS would read aloud).
Run: python3 test_gate_negative.py
"""
import asyncio
import json
import sys
import types

sys.dont_write_bytecode = True
import judge

PROMPT = "Evaluate these criteria:\n1. The agent verifies the date of birth.\n2. The agent books a slot.\n"


def stub_azure(criteria):
    """Replace the CLI's azure client with one that returns a fixed judge reply."""
    mod = types.ModuleType("azure_chat")
    mod.DEFAULT_DEPLOYMENT = "stub"

    class Resp:
        def __init__(self, text): self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=text))]

    class Completions:
        async def create(self, **kw):
            system = kw["messages"][0]["content"]
            if system.startswith("You check one callback variable"):
                return Resp(json.dumps({"match": False, "why": "stub: different value"}))
            if system.startswith("You check one verdict"):
                return Resp(json.dumps({"verdict": "NOT MET", "why": "stub"}))
            return Resp(json.dumps({"criteria": criteria}))

    mod._get_client = lambda: types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    pkg = types.ModuleType("src.simulation.cli"); pkg.azure_chat = mod
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src.simulation"] = types.ModuleType("src.simulation")
    sys.modules["src.simulation.cli"] = pkg


def run(turns=None, failures=(), ecv=None, expect="", criteria=None, variables=None):
    stub_azure(criteria or [{"n": 1, "met": True, "accuracy": 1.0}, {"n": 2, "met": True, "accuracy": 1.0}])
    r = {"scenario": "T", "run": 1, "failures": list(failures),
         "nodes_visited": ["Missed Visit Rescheduler"],
         "variables": variables if variables is not None else {"dob_confirmed": "1977-02-18"},
         "turns": turns or [{"user": "hi", "agent": "hello", "intent": "Rescheduled"}]}
    return asyncio.run(judge.judge_run(r, PROMPT, 0.8, "stub", verify=False, ecv=ecv or {}, expect_intent=expect))


ok = run()
assert ok["verdict"] == "PASS", ok           # positive control: a clean run still passes

wrong_exit = run(turns=[{"user": "hi", "agent": "bye", "intent": "Declined"}], expect="Rescheduled")
assert wrong_exit["verdict"] == "FAIL" and not wrong_exit["evidence"]["intent_ok"], wrong_exit["evidence"]

skipped = run(ecv={"dob_confirmed": "1977-02-18", "screening_status": "permission_granted"})
assert skipped["verdict"] == "PARTIAL", skipped["evidence"]
assert skipped["evidence"]["not_covered"] == ["screening_status"], skipped["evidence"]

dup = run(criteria=[{"n": 1, "met": True, "accuracy": 1.0}, {"n": 1, "met": True, "accuracy": 1.0}])
assert dup["verdict"] == "FAIL" and not dup["evidence"]["numbering_ok"], dup["evidence"]

simfail = run(failures=["expected intent Rescheduled, got Declined"])
assert simfail["verdict"] == "FAIL" and simfail["evidence"]["sim_failures"] == 1, simfail["evidence"]

elicited = run(turns=[{"user": "", "elicited": True, "agent": "hello", "intent": "Rescheduled"}])
assert elicited["verdict"] == "FAIL" and elicited["evidence"]["elicited_turns"] == 1, elicited["evidence"]

missing_var = run(ecv={"booking_confirmed": "yes"}, variables={})
assert missing_var["verdict"] == "FAIL", missing_var["variables"]


spoken = run(turns=[{"user": "sixty days", "agent": "Sixty days, got it.\n<instructions>\nNext: collect `currently_serving_notice`.\n</instructions>", "intent": "Rescheduled"}])
assert spoken["verdict"] == "FAIL" and spoken["evidence"]["non_speech"], spoken["evidence"]   # a tag or snake_case token in agent speech fails the run

print("gate negative controls: 8/8 behave as required (1 positive, 7 must-fail)")
