"""Put the screening permission step to Jev again with other option texts and other call texts. No call is simulated.

  cd s1-thin && python ../s1-thin-audit/lane/replay_screening.py

It takes one saved request of the permission step (a run with S1_DUMP_ASKS=1), swaps the call text for each case below,
and asks Jev once per case and option-text variant. Spend goes through the shared meter and ledger (a fraction of a cent).
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

TRACE = AUDIT.parent / "text-evals" / "text-lane" / "runs" / "s1-thin-fhcsd-dump" / "L-dob-refused-r1" / "trace.json"
OPENING = ["agent: Hi, is this Desmond Whitaker?", "caller: yes, this is Desmond",
           "agent: I'm calling about your recent appointment. Is now a good time to continue?"]
CASES = {
    "emergency, first report": ["caller: actually I can't breathe properly right now, my chest is really tight."],
    "emergency, after the 911 line": ["caller: actually I can't breathe properly right now, my chest is really tight.",
                                      "agent: Please hang up and call 9 1 1 right now.", "caller: okay, I will"],
    "yes with a question": ["caller: Yeah, that's fine. What's this about exactly?"],
    "a question only": ["caller: What's this about exactly?"],
    "a plain yes": ["caller: Yeah, now's fine."],
    "a conditional question": ["caller: Yeah, that's fine. What's this about exactly?",
                               "agent: It's a quick follow-up about your recent appointment.",
                               "caller: Alright, I see. Can we just do this without me giving out any personal info?"],
    "a plain no": ["caller: No, not now."],
    "asks to wait": ["caller: hold on one second"],
}
STATUS = ("status: One of permission_granted, permission_denied, callback_requested, refused, do_not_call. permission_denied is a "
          "plain, non-hostile decline made WITHOUT having just heard the call's reason; a decline on the turn right after you "
          "explained what the call is about is an informed decline — refused. refused also covers not-interested, hostility, or "
          "ending the call. do_not_call only for an explicit future-contact removal, or for declining the one-time callback offer.")


def with_arguments(criteria: dict) -> dict:
    return {name: text.rstrip() + ("\n" + STATUS if name == "complete_permission_to_continue" else "") for name, text in criteria.items()}


ENDING = (" When the call is ending, because the caller is leaving or the agent has just told them to hang up, the step "
          "that closes this part of the call is due.")
VARIANTS = {"as sent": lambda criteria: criteria, "with the argument text": with_arguments}
INSTRUCTIONS = {"as sent": "", "call is ending": ENDING}


async def main() -> None:
    events = [e for e in json.load(open(TRACE))["events"] if e["kind"] == "jev" and "state" in e]
    ask = next(e for e in events if "complete_permission_to_continue" in e["questions"]["step"]["criteria"])
    head = ask["state"][: ask["state"].index("CALL SO FAR")]
    heading = ask["state"][ask["state"].index("CALL SO FAR"):].split("\n", 1)[0]
    only = sys.argv[1:]
    for case, lines in CASES.items():
        if only and not any(word in case for word in only):
            continue
        state = head + "\n".join([heading, *OPENING, *lines])
        print(case)
        for name, change in VARIANTS.items():
            for label, extra in INSTRUCTIONS.items():
                step = {**ask["questions"]["step"], "criteria": change(ask["questions"]["step"]["criteria"])}
                step["instructions"] = step["instructions"] + extra
                shares = (await system_one.ask_jev(state, {"step": step})).get("step", {})
                top = sorted(shares.items(), key=lambda item: -item[1])[:3]
                print(f"  options {name:24} instruction {label:15} {[(option, round(share, 2)) for option, share in top]}")


out = AUDIT / "evals" / "replay-screening.wire.jsonl"
entry = meter.reserve("s1-thin-evals", "replay-screening", 0.5, campaign_cap=20.0)
meter.install(str(out), 0.5)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f}")
