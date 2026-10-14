"""Put one saved Jev request to Jev again with other option texts. A text repro for a wrong pick: no call is simulated.

  cd s1-thin && python ../s1-thin-audit/lane/replay_ask.py <trace.json> <ask index> [<ask index> ...]

The trace must come from a run with S1_DUMP_ASKS=1 (run_one_s1.py then stores each request whole). Every variant below is
asked once per ask; Jev's spend goes through the shared meter and ledger (a fraction of a cent per ask).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1]
ROOT = AUDIT.parents[1]
LIVEKIT_ENV = ROOT / "repos" / "cx-dev-dockerized-v291-jev" / "services" / "plivo-cx-livekit" / ".env"

for line in LIVEKIT_ENV.read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
os.environ["TYPESAFE_API_KEY"] = (AUDIT.parent / ".jev-env").read_text().split("TYPESAFE_API_KEY=", 1)[1].split("\n")[0].strip().strip('"')
os.environ.update({"REDIS_URL": "redis://127.0.0.1:1/0", "REDIS_IS_CLUSTER": "false"})
sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(AUDIT.parent / "text-evals" / "text-lane"))
import meter  # noqa: E402

from src import system_one  # noqa: E402

EXIT_FIRST = (" Due only once everything the policy puts before this exit has happened. If the policy says to ask again or "
              "to try once more first, that comes before the exit.")
RETRY_FIRST = (" When the policy says to ask again or to try once more before giving up, that retry is the step that is "
               "due, not the exit that would follow it.")


def exits(questions: dict) -> dict:
    step = questions["step"]
    criteria = {name: text + (EXIT_FIRST if name.startswith("handoff_") else "") for name, text in step["criteria"].items()}
    return {**questions, "step": {**step, "criteria": criteria}}


def instruction(questions: dict) -> dict:
    step = questions["step"]
    return {**questions, "step": {**step, "instructions": step["instructions"] + RETRY_FIRST}}


VARIANTS = {"as sent": lambda q: q, "exit text": exits, "step instruction": instruction, "both": lambda q: instruction(exits(q))}


async def main() -> None:
    events = [e for e in json.load(open(sys.argv[1]))["events"] if e["kind"] == "jev" and "state" in e]
    for index in map(int, sys.argv[2:]):
        ask = events[index]
        print(f"ask {index} (t={ask['t']}), {len(ask['questions']['step']['criteria'])} options")
        for name, change in VARIANTS.items():
            questions = {"step": change(ask["questions"])["step"]}
            shares = (await system_one.ask_jev(ask["state"], questions)).get("step", {})
            top = sorted(shares.items(), key=lambda item: -item[1])[:4]
            print(f"  {name:17} {[(option, round(share, 2)) for option, share in top]}")


out = AUDIT / "evals" / "replay-ask.wire.jsonl"
entry = meter.reserve("s1-thin-evals", "replay-ask", 0.5, campaign_cap=20.0)
meter.install(str(out), 0.5)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f}")
