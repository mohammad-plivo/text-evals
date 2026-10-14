"""Put one saved Jev request to Jev three ways: as recorded, with one FLOW POLICY note removed, and with that note moved
into CALL SO FAR as a history line just before a given transcript line. A text repro, no call simulated.
  cd s1-note-scope && python ../s1-thin-audit/lane/replay_note_as_history.py <trace.json> <seconds> "<start of the note>" "<start of the line it precedes>" [repeats]
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

trace, at, note, before = json.load(open(sys.argv[1]))["events"], float(sys.argv[2]), sys.argv[3], sys.argv[4]
repeats = int(sys.argv[5]) if len(sys.argv) > 5 else 4
ask = min((e for e in trace if e["kind"] == "jev" and "state" in e), key=lambda e: abs(float(e["t"]) - at))
policy, sep, rest = ask["state"].partition("CALL SO FAR")
text = next(line for line in policy.split("\n") if line.startswith(note))
kept = "\n".join(line for line in policy.split("\n") if line != text)
lines = rest.split("\n")
spot = next(i for i, line in enumerate(lines) if line.startswith(before))
history = kept + sep + "\n".join([*lines[:spot], " ".join(f"note: {text}".split()), *lines[spot:]])
questions = {"step": ask["questions"]["step"], **({"step_intent": ask["questions"]["step_intent"]} if "step_intent" in ask["questions"] else {})}


async def main() -> None:
    entry = meter.reserve("s1-thin-audit", "replay-note-history", 0.05)
    try:
        for name, state in (("as recorded", ask["state"]), ("note removed", kept + sep + rest), ("note as history", history)):
            for _ in range(repeats):
                shares = await system_one.ask_jev(state, questions)
                print(f"{name:16} step={ {k: round(v, 2) for k, v in shares.get('step', {}).items() if v >= 0.01} }", flush=True)
    finally:
        meter.settle(entry, 0.0, {"run": "replay-note-history"})


print(f"ask at {ask['t']}s, options {sorted(ask['questions']['step']['criteria'])}")
asyncio.run(main())
