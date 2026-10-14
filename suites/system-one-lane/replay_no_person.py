"""Ask Jev the fixed-answers question again on saved caller turns, with the "asks for a person" option added.

  cd <product tree> && python ../../v2.9.1-jev/s1-thin-audit/lane/replay_no_person.py [max turns per group]

Three groups of saved turns: a person was asked for, the agent's nature was asked about, and ordinary turns. Two wordings:
the library's own "none of these" line, and that line without "a person" among the requests the flow itself handles.
No call is simulated; Jev's spend goes through the shared meter and ledger.
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
from src.system_one_intents import CATALOGUE, NO_TRANSFER, sure  # noqa: E402

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 40
RUNS = AUDIT.parent / "text-evals" / "text-lane" / "runs"
OPTION = os.environ.get("NO_PERSON_TEXT") or system_one.PROMPTS["no_person"]  # a wording under trial


def groups() -> dict[str, list[dict]]:
    found: dict[str, dict[str, dict]] = {"a person asked for": {}, "asks what the agent is": {}, "ordinary": {}}
    for path in sorted(glob.glob(str(RUNS / "s1-*" / "*" / "trace.json"))):
        for ask in json.load(open(path))["events"]:
            if ask.get("kind") != "jev" or "state" not in ask or CATALOGUE not in ask.get("questions", {}) or "human_request" not in ask["probs"]:
                continue
            said = next((line for line in reversed(ask["state"].splitlines()) if line.startswith("caller: ")), "")
            human, about = sure(ask["probs"]["human_request"], "human_request"), sure(ask["probs"].get(CATALOGUE), CATALOGUE)
            group = ("a person asked for" if human == "transfer_to_human" else "asks what the agent is" if about in ("bot_or_human", "why_ai_calling")
                     else "ordinary" if human == "no_transfer" and about == "not_one_of_these" else None)
            if group:
                found[group].setdefault(said, ask)
    random.seed(9)
    return {name: random.sample(list(asks.values()), min(LIMIT, len(asks))) for name, asks in found.items()}


def variants(question: dict) -> dict[str, dict]:
    criteria = question["criteria"]
    plain = {**criteria, NO_TRANSFER: OPTION}
    narrowed = {**plain, "not_one_of_these": criteria["not_one_of_these"].replace("(a person, a callback, stop calling)", "(a callback, stop calling)")}
    assert narrowed["not_one_of_these"] != criteria["not_one_of_these"]
    return {"library none line": {**question, "criteria": plain}, "none line without a person": {**question, "criteria": narrowed}}


SAID = {  # typed lines put in place of the caller's last line of an ordinary saved turn: what must and must not pick the option
    "asks for a person": ["Can I talk to a real person?", "Is there a human I can speak to?", "I don't want to talk to a machine, get me someone.",
                          "Just transfer me to your staff please.", "kisi insaan se baat karao", "Mujhe kisi agent se baat karni hai.",
                          "Yes, now's fine, but I'd rather speak to a real person.", "Actually, forget the appointment, I want to speak to a real person.",
                          "Put me through to the front desk.", "Operator."],
    "asks what the agent is": ["Wait, am I talking to a robot?", "Is this an AI?", "Are you a real person or a machine?", "kya aap robot ho?",
                               "Are you a real person?"],
    "mentions a person only": ["My husband usually handles this, but go ahead.", "The person I spoke with last time said Tuesday.",
                               "I already spoke to someone from your team yesterday.", "A nurse told me to come in before noon.",
                               "Can you call me back later?", "Take me off your list.", "I'm having chest pain right now."],
}


def last(state: str) -> str:
    return next((line for line in reversed(state.splitlines()) if line.startswith("caller: ")), "")


async def read(name: str, asks: list[dict]) -> None:
    rows = {}
    for label in ("library none line", "none line without a person"):
        answers = await asyncio.gather(*(system_one.ask_jev(ask["state"], {CATALOGUE: variants(ask["questions"][CATALOGUE])[label]}) for ask in asks))
        picks = [str(sure(answer.get(CATALOGUE), CATALOGUE)) for answer in answers]
        rows[label] = [(pick, round((answer.get(CATALOGUE) or {}).get(NO_TRANSFER, 0), 2)) for pick, answer in zip(picks, answers)]
        print(f"{name:24} {label:28} n={len(asks):3} sure picks { {pick: picks.count(pick) for pick in sorted(set(picks))} }")
    if "--lines" in sys.argv:
        for ask, one, two in zip(asks, *rows.values()):
            print(f"     {one[0][:18]:18} {one[1]:4} | {two[0][:18]:18} {two[1]:4} | {last(ask['state'])[8:118]}")


async def main() -> None:
    saved = groups()
    for name in ("a person asked for", "ordinary"):
        await read(name, saved[name])
    for name, lines in SAID.items():
        await read(name, [{**ask, "state": ask["state"][:ask["state"].rindex(last(ask["state"]))] + "caller: " + line}
                          for line in lines for ask in saved["ordinary"][:3]])


out = AUDIT / "evals" / "replay-no-person.wire.jsonl"
out.parent.mkdir(exist_ok=True)
entry = meter.reserve("s1-thin-evals", "replay-no-person", 1.0, campaign_cap=20.0)
meter.install(str(out), 1.0)
try:
    asyncio.run(main())
finally:
    actual, detail = meter.settle_from_meter(str(out))
    meter.settle(entry, actual, detail)
    print(f"SPEND ${actual:.4f}")
