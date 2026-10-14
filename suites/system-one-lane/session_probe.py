"""Main's own multi-turn V2.9 session cases, with System One Thinking on: real Jev and the node's real model.

Run from the s1-thin worktree:
  python ../s1-thin-audit/session_probe.py --cases mt_name_spelled_confirmation [--off] [--label L] [--budget 1.0]

The case's authored caller speaks, main's router and collectors run, tools are mocked by the case, and main's own
oracle (assert_session_case) grades the result. --off runs the same case with no profile, which is main as it is.
Spend goes through the text lane's shared meter and ledger.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[1]
LANE = AUDIT.parent / "text-evals" / "text-lane"
LIVEKIT_ENV = ROOT / "repos" / "cx-dev-dockerized-v291-jev" / "services" / "plivo-cx-livekit" / ".env"
PROFILE = {"version": 1, "engine": "jev", "fault_policy": "safe_close", "scribe_close_permit": True, "amd": "off"}

parser = argparse.ArgumentParser()
parser.add_argument("--cases", required=True, help="comma-separated session case ids, or 'all'")
parser.add_argument("--off", action="store_true", help="no profile: the case runs as on main")
parser.add_argument("--label", default="session-probe")
parser.add_argument("--budget", type=float, default=1.0)
parser.add_argument("--campaign", default="s1-thin-audit")
parser.add_argument("--campaign-cap", type=float, default=12.0)
parser.add_argument("--auto", action="store_true", help="experiment: a picked step keeps main's tool_choice, so the model may speak and call")
parser.add_argument("--repeat", type=int, default=1)
parser.add_argument("--prompts", help="JSON file whose keys replace entries of the shipped prompt file")
args = parser.parse_args()

# the stack's settings and keys must be in the environment before any src import; a later line wins, as in the stack
for line in LIVEKIT_ENV.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
os.environ["TYPESAFE_API_KEY"] = (AUDIT.parent / ".jev-env").read_text().split("TYPESAFE_API_KEY=", 1)[1].split("\n")[0].strip().strip('"')
os.environ.update({"REDIS_URL": "redis://127.0.0.1:1/0", "REDIS_IS_CLUSTER": "false"})

sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(LANE))
import meter  # noqa: E402

from src import system_one  # noqa: E402
from src.agent_factory import _build_llm  # noqa: E402
from src.models.ai_config import ActionConfig, ActionType, ModelConfig  # noqa: E402
from tests.v29_model_eval.live import _add_lookup_action  # noqa: E402
from tests.v29_model_eval.session_cases import DAY_ONLY_DATE_CASES, MULTI_TURN_CASES, MULTI_TURN_EXTRA_CASES  # noqa: E402
from tests.v29_model_eval.session_runner import (  # noqa: E402
    AuthoredCaller,
    SessionCase,
    assert_session_case,
    build_session_node_config,
    run_session,
    session_action_mocks,
)

from dataclasses import replace  # noqa: E402

from livekit.agents import llm  # noqa: E402

from src.cx_agent import CXAgent  # noqa: E402
from src.language_hint import LanguageHintTask  # noqa: E402


def _chunks_only(node):
    """Main's llm_node may yield plain text (its speech cut does); LiveKit accepts that, the lane's observer does not."""
    async def llm_node(agent, chat_ctx, tools, model_settings):
        async for chunk in node(agent, chat_ctx, tools, model_settings):
            yield llm.ChatChunk(id="text", delta=llm.ChoiceDelta(role="assistant", content=chunk)) if isinstance(chunk, str) else chunk
    return llm_node


CXAgent.llm_node = _chunks_only(CXAgent.llm_node)
LanguageHintTask.llm_node = _chunks_only(LanguageHintTask.llm_node)

if args.auto:
    forced_lead = system_one.SystemOneLLM.lead

    async def lead(self, chat_ctx, tools, tool_choice):
        result = await forced_lead(self, chat_ctx, tools, tool_choice)
        picked_a_step = result.tool_choice == "required" and tool_choice != "required" and not result.fire
        return replace(result, tool_choice=tool_choice) if picked_a_step else result

    system_one.SystemOneLLM.lead = lead

if args.prompts:
    system_one.PROMPTS.update(json.loads(Path(args.prompts).read_text()))

ASKS: list[dict] = []
real_ask = system_one.ask_jev


async def recorded_ask(state: str, questions: dict) -> dict:
    started = time.perf_counter()
    answers = await real_ask(state, questions)
    step = answers.get("step", {})
    ASKS.append({"seconds": round(time.perf_counter() - started, 3),
                 "pick": system_one.sure_pick(step, system_one.STEP_FLOOR) or "speak (or unsure)",
                 "top": dict(sorted(step.items(), key=lambda item: -item[1])[:3]),
                 "about_agent": system_one.sure_pick(answers.get("about_agent") or answers.get("sensitive_question") or {}, system_one.SURE_FLOOR),
                 "turn": {head: max(shares, key=shares.get) for head, shares in answers.items() if head != "step" and shares}})
    return answers


system_one.ask_jev = recorded_ask


async def one(case: dict) -> dict:
    node_config = build_session_node_config(
        case["id"], case["instructions"], case["fields"], required_fields=list(case["submit_arguments"]),
        action_execution_policy=case.get("action_execution_policy"), configurations=None, extra_actions=case.get("extra_actions"))
    node_config["llm_model_config"] = ModelConfig(provider="openai", model="gpt-4.1").model_dump(mode="json")
    _add_lookup_action(node_config, case, (ActionConfig, ActionType))
    if not args.off:
        node_config["leader_profile"] = PROFILE
    session = SessionCase(
        id=case["id"], node_config=node_config, caller_driver=AuthoredCaller(case), action_mocks=session_action_mocks(case),
        required_values=case["expected_values"], frozen_time=case.get("frozen_time", "2026-09-09T10:00:00+05:30"),
        flow_session=case.get("flow_session", False))
    first, started, row, trace = len(ASKS), time.perf_counter(), {"id": case["id"], "switch": "off" if args.off else "on"}, None
    try:
        trace = await run_session(session, model_factory=_build_llm)
        assert_session_case(case, trace, None)
        row["verdict"] = "pass"
    except BaseException as error:  # noqa: BLE001 - a failed case is a result
        trace = trace or getattr(error, "trace", None)
        row["verdict"] = f"fail: {type(error).__name__}: {str(error)[:400]}"
    row["seconds"] = round(time.perf_counter() - started, 1)
    row["jev"] = ASKS[first:]
    if trace is not None:
        row["model_requests"] = len(getattr(trace, "requests", []) or [])
        row["executed"] = [{"name": call["name"], "arguments": call["arguments"][:160], "output": str(call["output"])[:160],
                            "error": call["is_error"]} for call in trace.executed]
        row["lines"] = [f"{message['role']}: {message['content']}" for message in trace.messages if message.get("content")]
    return row


async def main() -> None:
    catalog = {case["id"]: case for case in (*MULTI_TURN_CASES, *MULTI_TURN_EXTRA_CASES, *DAY_ONLY_DATE_CASES)}
    wanted = (list(catalog) if args.cases == "all" else args.cases.split(",")) * args.repeat
    rows = []
    for case_id in wanted:
        rows.append(await one(catalog[case_id]))
        print("ROW " + json.dumps(rows[-1], ensure_ascii=False), flush=True)
    passed = sum(row["verdict"] == "pass" for row in rows)
    print(f"SUMMARY switch={'off' if args.off else 'on'}: {passed} of {len(rows)} session cases passed main's own checks")


out = AUDIT / f"{args.label}.wire.jsonl"
entry = meter.reserve(args.campaign, args.label, args.budget, campaign_cap=args.campaign_cap)
meter.install(str(out), args.budget)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f} {json.dumps(detail)}")
