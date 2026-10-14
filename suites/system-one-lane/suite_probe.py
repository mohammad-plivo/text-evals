"""Main's own V2.9 tool-calling cases, the single-turn half of its extended suite, run live: real Jev picks, real Gemma fills.

Run from the s1-thin worktree:
  python ../s1-thin-audit/suite_probe.py [--off] [--limit N] [--cases a,b] [--label L] [--budget 2.0]

Each case is one request to the node's model, built by the production factory and checked by main's own assert_trace.
--off runs the same case with no profile, which is main as it is. Spend goes through the text lane's shared meter and ledger.
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
CAMPAIGN, CAMPAIGN_CAP = "s1-thin-evals", 20.0

parser = argparse.ArgumentParser()
parser.add_argument("--off", action="store_true", help="no profile: the case runs as on main")
parser.add_argument("--limit", type=int, default=0)
parser.add_argument("--cases", default="", help="comma-separated case ids; default is the whole extended selection")
parser.add_argument("--label", default="suite")
parser.add_argument("--budget", type=float, default=2.0)
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
from src.agent_factory import build_node_llm  # noqa: E402
from src.models.ai_config import LeaderProfile, ModelConfig  # noqa: E402
from tests.v29_model_eval.cases import CASES  # noqa: E402
from tests.v29_model_eval.runner import _config, assert_trace, run_case  # noqa: E402
from tests.v29_model_eval.selection import select_benchmark_suite  # noqa: E402
from tests.v29_model_eval.session_cases import MULTI_TURN_CASES  # noqa: E402

ASKS: list[dict] = []
real_ask = system_one.ask_jev


async def recorded_ask(state: str, questions: dict) -> dict:
    started = time.perf_counter()
    answers = await real_ask(state, questions)
    step = answers.get("step", {})
    ASKS.append({"seconds": round(time.perf_counter() - started, 3),
                 "pick": system_one.sure_pick(step, system_one.STEP_FLOOR) or system_one.SPEAK,
                 "top": dict(sorted(step.items(), key=lambda item: -item[1])[:3])})
    return answers


system_one.ask_jev = recorded_ask


async def one(case: dict) -> dict:
    model_config = ModelConfig(provider="openai", model="gpt-4.1")
    config = _config(case, model_config)
    inner = build_node_llm(config)  # the production factory: Gemma on the gateway, with main's own failover legs
    model = inner
    if not args.off:
        config.agent_config.leader_profile = LeaderProfile(**PROFILE)
        model = system_one.SystemOneLLM(inner, config.agent_config)
    first, started, row = len(ASKS), time.perf_counter(), {"id": case["id"], "switch": "off" if args.off else "on"}
    wanted = (case.get("expected") or [{}])[0]
    row["expected"] = wanted.get("name") or "speech"
    try:
        trace = await run_case(case, llm_model=model, model_config=model_config)
        row["called"], row["said"] = [call.get("name") for call in trace.get("calls") or []], (trace.get("speech") or "")[:160]
        assert_trace(case, trace, None)
        row["verdict"] = "pass"
    except Exception as error:  # noqa: BLE001 - a failed case is a result
        row["verdict"] = f"fail: {type(error).__name__}: {str(error)[:300]}"
    finally:
        await inner.aclose()
    row["seconds"], row["jev"] = round(time.perf_counter() - started, 1), ASKS[first:]
    return row


async def main() -> None:
    chosen = list(select_benchmark_suite(list(CASES), list(MULTI_TURN_CASES), "extended").snapshots)
    if args.cases:
        chosen = [case for case in chosen if case["id"] in set(args.cases.split(","))]
    rows = []
    for case in chosen[: args.limit or None]:
        rows.append(await one(case))
        print("ROW " + json.dumps(rows[-1], ensure_ascii=False), flush=True)
    passed = sum(row["verdict"] == "pass" for row in rows)
    print(f"SUMMARY switch={'off' if args.off else 'on'}: {passed} of {len(rows)} single-turn cases passed main's own checks")


out = AUDIT / "evals" / f"{args.label}.wire.jsonl"
out.parent.mkdir(exist_ok=True)
entry = meter.reserve(CAMPAIGN, args.label, args.budget, campaign_cap=CAMPAIGN_CAP)
meter.install(str(out), args.budget)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f} {json.dumps(detail)}")
