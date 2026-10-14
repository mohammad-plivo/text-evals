#!/usr/bin/env python3
"""Text checks for the fixes of 11 October 2026: one scripted caller per fix, saying the words the voice callers said.

    python3 text_evals.py run [letter ...] [--times N] [--only before|now]
    python3 text_evals.py read <stamp>          # the table again, from the saved runs

Each run is the engine's own text simulator inside v210-agent-runner, started on the step where the fault happened.
"before" is the engine at 24755e55a, unpacked in the container at /tmp/engine-old. "now" is /app, the engine the stack
runs. Nothing is dialled. Jev's answers move a little from run to run, so every check is run several times and read as
a count. A run where the scripted words no longer fit what the agent asked is "off script" and is not counted.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
BOX = "v210-agent-runner"
ENGINES = {"before": "/tmp/engine-old", "now": "/app"}
ENGINES_OWN = tuple(ENGINES)   # a scratch engine of wording/lab.py is added beside these
IDLE = None   # the caller says nothing until the check-in
AT_ONCE = 6   # text runs going at the same time in the container
SLOTS = 8     # the same, over every runner on this laptop: the container has room for about that many


def calls(run: str) -> list[tuple[str, str]]:
    """Every step that reached the engine, in order, as the simulator printed it: its name and what it was sent."""
    return re.findall(r"(?m)^  TOOL : (\w+)\((.*)\)\s*$", run)


def turns(run: str) -> list[list[str]]:
    """What the agent said and did after each caller line, as the simulator printed it."""
    out: list[list[str]] = []
    for line in run.splitlines():
        if line.startswith("  USER :"):
            out.append([])
        elif out and line.startswith(("  AGENT:", "  TOOL :", "  INTENT:")):
            out[-1].append(line.strip())
    return out


def said(run: str, turn: int) -> str:
    """The agent's words after one caller line (1 is the first)."""
    rows = turns(run)
    return " ".join(line[6:].strip() for line in rows[turn - 1] if line.startswith("AGENT:")) if len(rows) >= turn else ""


def ran(run: str, tool: str, holds: str = "") -> int:
    return sum(name == tool and holds in sent for name, sent in calls(run))


def dropped(run: str) -> list[str]:
    return re.findall(r"system_one: dropped (\[.*?\]), outside", run)


# each check returns True (the fix holds), False (the fault), or None (the run went off script and says nothing)
def check_b(run):
    if "the caller has not declined" in run:
        return False   # the collector rejected a decline Jev had read as a refusal
    return True if ran(run, "decline_text_capture") else None   # None: Jev chose to ask once more, so no decline was tried


def check_a_text(run):
    return ran(run, "update_text") >= 1 and not dropped(run)


def check_a_name(run):
    asked = [turn for turn in range(1, 12) if re.search(r"(?i)spell the first name", said(run, turn))]   # the last name is another question
    if not asked:
        return None   # the agent never asked for the spelling, so the fault had no chance
    return len(asked) == 1


def check_f(run):
    return ran(run, "change_earlier_value") >= 1


def check_m(run):
    if not ran(run, "change_earlier_value"):
        return None   # the day was never changed, so nothing is known about the second search
    return ran(run, "find_slots", "2026-10-27") >= 1 and not any("find_slots" in drop for drop in dropped(run))


def check_booked(run):
    return ran(run, "book_visit", "2026-10-27") >= 1 and ran(run, "handoff_booked") >= 1


def check_c(run):
    rows = turns(run)
    return bool(rows) and len(rows) >= 2 and any("update_identify_contact" in line for line in rows[1])


def check_d(run):
    reply = said(run, 3)
    return None if not reply else reply.rstrip().endswith("?")


def check_e(run):
    return not ran(run, "exit_collection")


def check_g(run):
    if ran(run, "take_payment") < 1:
        return None
    return ran(run, "take_payment", '"4321"') >= 1


def check_h(run):
    words = " ".join(said(run, turn) for turn in range(1, 6))
    if not re.search(r"(?i)part.?time", words):
        return None
    return "part_time" not in words and "full_time" not in words


def check_j(run):
    return "Hello, are you still there?" in said(run, 2)


EVALS = {
    "B": ("rapido-flow", "30-", "Captain Reactivation", ["Hello?", "I don't wanna say."],
          "a refusal on the two-language flow is recorded on that turn", check_b),
    "A1": ("rapido-flow", "14-", "Captain Reactivation", ["Hello?", "Nowhere steady."],
           "\"Nowhere steady\" is recorded on that turn, nothing dropped", check_a_text),
    "A2": ("logic-flow", "28-", "Site Details",
           ["Hello?", "Flat 12, Lakeview Residency, Station Road, Pune.", "Yes, that's right.", "Maria D'Souza.", "No. Maria D'Souza.",
            "M a r I a.", "M a r I a.", "M a r I a."],
           "the spelling of the name is asked for once, not again and again", check_a_name),
    "F0": ("logic-flow", "05-", "Account Check",
           ["Hello?", "The twenty-second of May, nineteen eighty-two.", "Okay.", "Tuesday, the 20th of October.",
            "Neither works for me. What about Tuesday, the 27th of October instead?", "Yes.", "The 2 o'clock in the afternoon.",
            "Yes, that's right."],
           "the same call from the account check on, where Jev reads the line as on voice", check_f),
    "F": ("logic-flow", "05-", "Book Visit",
          ["Hello?", "Tuesday, the 20th of October.", "Neither works for me. What about Tuesday, the 27th of October instead?", "Yes.",
           "The 2 o'clock in the afternoon.", "Yes, that's right."],
          "\"What about the 27th instead?\" changes the day", check_f),
    "M": ("logic-flow", "05-", "Book Visit",
          ["Hello?", "Tuesday, the 20th of October.", "Neither works for me. What about Tuesday, the 27th of October instead?", "Yes.",
           "The 2 o'clock in the afternoon.", "Yes, that's right."],
          "after the day changes, the times are searched again", check_m),
    "F3": ("logic-flow", "05-", "Book Visit",
           ["Hello?", "Tuesday, the 20th of October.", "Neither works for me. What about Tuesday, the 27th of October instead?", "Yes.",
            "The 2 o'clock in the afternoon.", "Yes, that's right."],
           "the visit is booked for the new day at the time the caller chose", check_booked),
    "C": ("rapido-flow", "10-", "Screen Captain", ["Hello?", "हां बोल रहा हूं."],
          "a Hindi \"yes, speaking\" is taken on the first reply", check_c),
    "D": ("rapido-flow", "29-", "Screen Captain", ["Hello?", IDLE, "हां, मैं line पर हूं."],
          "a reply Jev is not sure of ends on a question", check_d),
    "E": ("logic-flow", "19-", "Screen Customer", ["Hello?", IDLE, "Yes. I'm here."],
          "\"Yes, I'm here\" after the check-in does not take the emergency way out", check_e),
    "G": ("logic-flow", "16-", "Payment", ["Hello?", "1250 rupees.", "4", "1 2 3 4", "Yes. Go ahead.", "4 3", "2 1", "Yes. Go ahead."],
          "a PIN said in two halves is one PIN", check_g),
    "H": ("rapido-flow", "07-", "Captain Reactivation", ["Hello?", "I drive for Uber now."],
          "the options are said as words, not as stored names", check_h),
    "J": ("rapido-flow", "07-", "Screen Captain", ["Hello?", IDLE],
          "the check-in is said in both languages", check_j),
}


def box(script: str, detach: bool = False) -> str:
    return subprocess.run(["docker", "exec", *(["-d"] if detach else []), BOX, "sh", "-c", script], capture_output=True, text=True).stdout


def slot() -> str:
    """A free place for one text run, taken; "" when all are in use. A place held over six minutes was left behind and is freed."""
    return box("mkdir -p /tmp/sim-slots; find /tmp/sim-slots -mindepth 1 -maxdepth 1 -mmin +6 -exec rmdir {} + 2>/dev/null; "
               f"for n in $(seq 1 {SLOTS}); do mkdir /tmp/sim-slots/$n 2>/dev/null && echo $n && break; done").strip()


def workspace(letter: str, stamp: str = "") -> tuple[Path, str]:
    """A simulator workspace for one check: the caller's flow and settings, and one scripted scenario."""
    suite, caller, node, lines, _, _ = EVALS[letter]
    source = next((ROOT / suite / "out/sim").glob(f"{caller}*"))
    flow = json.loads((source / "flow.json").read_text())
    entry = next(item["id"] for item in flow["nodes"] if item["data"]["config"]["name"] == node)
    made = HERE / "text" / "workspaces" / stamp / letter   # its own folder per run: two runs at once never share one
    (made / "scenarios").mkdir(parents=True, exist_ok=True)
    for name in ("flow.json", "params.yaml"):
        (made / name).write_bytes((source / name).read_bytes())
    old = json.loads(next((source / "scenarios").glob("*.yaml")).read_text())
    scenario = {"description": EVALS[letter][4], "turns": [{"idle": True} if line is IDLE else {"user": line} for line in lines],
                "real_actions": old.get("real_actions", [])}
    (made / "scenarios" / f"{letter}.yaml").write_text(json.dumps(scenario, ensure_ascii=False, indent=1))
    return made, entry


def run(letters: list[str], times: int, only: str | None) -> Path:
    stamp = time.strftime("%m%d-%H%M%S") + (f"-{os.getpid()}" if only not in (None, *ENGINES_OWN) else "")
    base, saved = f"/tmp/fix-evals/{stamp}", HERE / "text" / stamp
    jobs = []
    for letter in letters:
        made, entry = workspace(letter, stamp)
        for engine in ([only] if only else list(ENGINES)):
            for number in range(1, times + 1):
                jobs.append((letter, engine, number, made, entry))
    waiting, running = list(jobs), []
    while waiting or running:
        while waiting and len(running) < AT_ONCE and (taken := slot()):
            letter, engine, number, made, entry = job = waiting.pop(0)
            place = f"{base}/{engine}/{letter}-{number}"
            box(f"mkdir -p {base}/{engine}")
            subprocess.run(["docker", "cp", str(made), f"{BOX}:{place}"], check=True)
            # a run that hangs is stopped after five minutes and read as far as it got
            box(f"cd {ENGINES[engine]} && timeout 300 python -m src.simulation.cli run {place} --node {entry} --env-file /app/.env --no-open --verbose "
                f"> {place}/run.log 2>&1; echo $? > {place}/done.flag; rmdir /tmp/sim-slots/{taken}", detach=True)
            running.append(job)
        time.sleep(4)
        for job in list(running):
            letter, engine, number, _, _ = job
            place = f"{base}/{engine}/{letter}-{number}"
            if box(f"cat {place}/done.flag 2>/dev/null").strip():
                running.remove(job)
                (saved / engine).mkdir(parents=True, exist_ok=True)
                (saved / engine / f"{letter}-{number}.log").write_text(box(f"cat {place}/run.log"))
                if requests := box(f"cat {place}/jev.jsonl 2>/dev/null"):   # only a scratch engine of wording/lab.py keeps them
                    (saved / engine / f"{letter}-{number}.jev.jsonl").write_text(requests)
                print(f"  done {engine:6s} {letter}-{number}", flush=True)
    return saved


def read(saved: Path, letters: list[str] | None = None) -> None:
    print(f"{'':3s} {'what the check looks for':66s} {'before':>10s} {'now':>10s}")
    for letter, (_, _, _, _, what, check) in EVALS.items():
        if letters and letter not in letters:
            continue
        cells = []
        for engine in ENGINES:
            results = [check(path.read_text()) for path in sorted((saved / engine).glob(f"{'F' if letter in ('M', 'F3') else letter}-*.log"))]
            counted = [result for result in results if result is not None]
            off = len(results) - len(counted)
            cells.append("-" if not results else f"{sum(counted)} of {len(counted)}" + (f" ({off} off)" if off else ""))
        print(f"{letter:3s} {what:66s} {cells[0]:>10s} {cells[1]:>10s}")
    print(f"saved in {saved}")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["read"]:
        return read(HERE / "text" / args[1], args[2:] or None)
    times = int(args[args.index("--times") + 1]) if "--times" in args else 5
    only = args[args.index("--only") + 1] if "--only" in args else None
    letters = [arg for arg in args[1:] if arg in EVALS] or list(EVALS)
    read(run([letter for letter in letters if letter not in ("M", "F3")], times, only), letters)   # M and F3 read the runs of F: the same call


if __name__ == "__main__":
    main()
