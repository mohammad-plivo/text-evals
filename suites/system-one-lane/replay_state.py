"""Put one saved Jev request to Jev again with one note taken out of the FLOW POLICY block. A text repro, no call simulated.
  cd s1-approved && python ../s1-thin-audit/lane/replay_state.py <trace.json> <seconds> "<start of the note>" [repeats]
The trace must come from a run with S1_DUMP_ASKS=1. Jev's spend goes through the shared meter (a fraction of a cent per ask).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1]
ROOT = AUDIT.parents[1]
for line in (ROOT / "repos" / "cx-dev-dockerized-v291-jev" / "services" / "plivo-cx-livekit" / ".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")
os.environ["TYPESAFE_API_KEY"] = (AUDIT.parent / ".jev-env").read_text().split("TYPESAFE_API_KEY=", 1)[1].split("\n")[0].strip().strip('"')
os.environ.update({"REDIS_URL": "redis://127.0.0.1:1/0", "REDIS_IS_CLUSTER": "false"})
sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(AUDIT.parent / "text-evals" / "text-lane"))
import meter  # noqa: E402
from src import system_one  # noqa: E402

trace, at, note = json.load(open(sys.argv[1]))["events"], float(sys.argv[2]), sys.argv[3]
repeats = int(sys.argv[4]) if len(sys.argv) > 4 else 3
ask = min((e for e in trace if e["kind"] == "jev" and "state" in e), key=lambda e: abs(float(e["t"]) - at))
policy, sep, rest = ask["state"].partition("CALL SO FAR")
kept = "\n".join(line for line in policy.split("\n") if not line.startswith(note))
assert kept != policy, "the note is not in the policy block"
questions = {"step": ask["questions"]["step"], **({"step_intent": ask["questions"]["step_intent"]} if "step_intent" in ask["questions"] else {})}


async def main() -> None:
    entry = meter.reserve("s1-thin-audit", "replay-state", 0.05)
    try:
        for name, state in (("as recorded", ask["state"]), ("note out of policy", kept + sep + rest)):
            for _ in range(repeats):
                shares = await system_one.ask_jev(state, questions)
                print(f"{name:20} step={ {k: round(v, 2) for k, v in shares.get('step', {}).items() if v >= 0.01} }")
    finally:
        meter.settle(entry, 0.0, {"run": "replay-state"})


print(f"ask at {ask['t']}s, options {sorted(ask['questions']['step']['criteria'])}")
asyncio.run(main())
