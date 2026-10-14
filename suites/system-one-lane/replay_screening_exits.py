"""Ask Jev the step question again on saved screening turns, with each exception the flow lists as its own option.

  cd <product tree> && python <this file> [ordinary turns per step] [--lines]

The saved turns come with the old fixed answers, which only label them here: a person asked for, an emergency, an end or
never-call, an ordinary reply. Each wording of the exit options is tried on the same turns. No call is simulated; Jev's
spend goes through the shared meter and ledger.
"""
import asyncio
import glob
import json
import os
import random
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

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
EXITS = {"exit Emergency Mentioned": "The person describes a medical emergency.",
         "exit Screening Exit": os.environ.get("SCREENING_EXIT_TEXT") or "The person asks to speak to a person or a staff member. This call cannot "
                                "connect them, so it ends here."}
STATUS = {"identity": "update_identify_contact", "permission": "complete_permission_to_continue"}


def top(shares: dict | None, floor: float, margin: float) -> str | None:
    ordered = sorted((shares or {}).items(), key=lambda pair: -pair[1]) + [(None, 0.0)]
    return ordered[0][0] if ordered[0][1] >= floor and ordered[0][1] - ordered[1][1] >= margin else None


def last(state: str) -> str:
    return next((line for line in reversed(state.splitlines()) if line.startswith("caller: ")), "")


def saved() -> dict[str, list[dict]]:
    found: dict[str, dict[str, dict]] = {}
    for path in sorted(glob.glob(str(AUDIT.parent / "text-evals" / "text-lane" / "runs" / "s1-*" / "*" / "trace.json"))
                       + glob.glob(str(AUDIT / "lane" / "runs" / "s1-fx-*" / "*" / "trace.json"))):
        try:
            events = json.load(open(path))["events"]
        except (OSError, ValueError):
            continue
        for ask in events:
            criteria = (ask.get("questions", {}).get("step") or {}).get("criteria", {}) if ask.get("kind") == "jev" and "state" in ask else {}
            phase = next((name for name, tool in STATUS.items() if tool in criteria), None)
            if not phase or "human_request" not in ask["probs"]:
                continue
            probs = ask["probs"]
            human, closure, urgency = (top(probs.get(head), 0.6, 0.15) for head in ("human_request", "closure_request", "urgency"))
            group = ("a person asked for" if human == "transfer_to_human" else "an emergency" if urgency == "emergency_right_now"
                     else "end or never call" if closure in ("wants_to_end_the_call", "do_not_call_again")
                     else "ordinary" if human == "no_transfer" and closure == "neither" else None)
            if group:
                found.setdefault(f"{group}, {phase}", {}).setdefault(last(ask["state"]), {**ask, "phase": phase})
    random.seed(9)
    return {name: random.sample(list(asks.values()), min(LIMIT if name.startswith("ordinary") else 60, len(asks))) for name, asks in sorted(found.items())}


LISTED = "\n".join(f"- {name.removeprefix('exit ')}: {text}" for name, text in EXITS.items())
NOTES = {  # a note put with the instructions Jev reads, before the call so far
    "note": "Exceptions this flow lists. When the caller's words fit one, the call leaves screening for it at once, before identity or permission "
            "is settled:\n" + LISTED,
}
MARK = "\n\nCALL SO FAR"


def question(ask: dict) -> dict:
    step = ask["questions"]["step"]
    criteria = {name: rubric for name, rubric in step["criteria"].items() if name not in ("exit_collection", "only speak")}
    return {**step, "criteria": {**criteria, **EXITS, "only speak": step["criteria"]["only speak"]}}


def state(ask: dict, note: str) -> str:
    assert ask["state"].count(MARK) == 1
    return ask["state"].replace(MARK, f"\n{note}{MARK}") if note else ask["state"]


SAID = {  # typed lines put in place of the caller's last line of ordinary saved turns: what must and must not leave screening
    "typed: asks for a person": ["Can I talk to a real person?", "kisi insaan se baat karao", "Just transfer me to your staff please.",
                                 "I'm not doing this with a computer. Put someone on.", "Mujhe kisi agent se baat karni hai.", "Operator."],
    "typed: yes, and a person": ["Yes, now's fine, but I'd rather speak to a real person.", "Yes this is me. Can I talk to someone from your team though?",
                                 "Sure, go ahead, but I'd like a human for this.", "Haan theek hai, par kisi insaan se baat karao."],
    "typed: asks about the agent": ["Are you a robot?", "Is this a real person or a machine?", "Who is this?", "Why are you calling me?",
                                    "What is this about?", "Is this a recording?", "kya aap robot ho?"],
    "typed: mentions a person": ["My wife usually takes these calls.", "The nurse told me to expect a call.", "Sam's at work, try him after six.",
                                 "I spoke to someone there last week already."],
    "typed: an emergency": ["I can't talk, I think I'm having a heart attack.", "My chest hurts and I can't breathe."],
}


async def read(name: str, asks: list[dict]) -> None:
    rows = {}
    for label, note in NOTES.items():
        answers = await asyncio.gather(*(system_one.ask_jev(state(ask, note), {"step": question(ask)}) for ask in asks))
        picks = [str(top(answer.get("step"), 0.5, 0.15)) for answer in answers]
        rows[label] = picks
        print(f"{name:32} {label:6} n={len(asks):3} step { {pick: picks.count(pick) for pick in sorted(set(picks))} }")
    if "--lines" in sys.argv:
        for ask, *per in zip(asks, *rows.values()):
            print("     " + " | ".join(f"{pick[:28]:28}" for pick in per) + f" | {ask['phase']:10} | {last(ask['state'])[8:100]}")


async def main() -> None:
    groups = saved()
    if "--typed" not in sys.argv:
        for name, asks in groups.items():
            await read(name, asks)
    base = groups["ordinary, identity"][:2] + groups["ordinary, permission"][:2]
    for name, lines in SAID.items():
        await read(name, [{**ask, "state": ask["state"][:ask["state"].rindex(last(ask["state"]))] + "caller: " + line} for line in lines for ask in base])


out = AUDIT / "evals" / "replay-screening-exits.wire.jsonl"
out.parent.mkdir(exist_ok=True)
entry = meter.reserve("s1-thin-evals", "replay-screening-exits", 2.0, campaign_cap=20.0)
meter.install(str(out), 2.0)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f}")
