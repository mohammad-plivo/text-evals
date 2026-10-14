#!/usr/bin/env python3
"""Try a wording on Jev before it goes into the engine. Nothing is dialled and nothing in git changes.

    engine(name, commit)             a scratch copy of the engine in the container at /tmp/engine-<name>, which keeps every Jev request
    capture(name, letters, times)    the scripted text callers of text_evals.py on that copy; each run's requests land beside its log
    kept(folder)                     those requests: the call so far, the questions, Jev's answer, the kind of question that was open
    reworded(request, wording, ...)  one request with a wording in place, and optionally another caller line or agent line
    ask(jobs, times)                 the requests put to Jev again, several times each, inside the container

A wording is {"library": [{"kind", "intent" or "template", "new"}], "texts": [{"old", "new"}]}: the first rebuilds the reading
question from the approved library, the second replaces text in the other questions (a tool's description, the correction question).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import text_evals  # noqa: E402

ENGINE = HERE.parent.parent / "agent-runner-lang"
BOX = text_evals.BOX
ASKED = "        shares = await ask_jev(render_state(llm.ChatContext([*chat_ctx.items, *policy])), questions) if questions else {}\n"
KEEPS = """        state = render_state(llm.ChatContext([*chat_ctx.items, *policy]))
        shares = await ask_jev(state, questions) if questions else {}
        if questions and __import__("sys").argv[1:2] == ["run"]:
            with open(__import__("sys").argv[2] + "/jev.jsonl", "a") as kept:
                kept.write(json.dumps({"kind": kind, "values": values, "caller_line": caller_line, "fresh": bool(fresh), "state": state,
                                       "questions": questions, "shares": shares}, ensure_ascii=False) + "\\n")
"""
IN_BOX = r'''
import asyncio, json, os, sys
sys.path.insert(0, "/app")
for line in open("/app/.env"):
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.strip().split("=", 1)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))
from src.system_one import ask_jev

async def main():
    plan, gate, out = json.load(open(sys.argv[1])), asyncio.Semaphore(4), {}
    async def one(name, job):
        async with gate:
            try:
                out.setdefault(name, []).append(await ask_jev(job["state"], job["questions"], (4, 6)))
            except Exception as error:
                out.setdefault(name, []).append({"fault": type(error).__name__})
    await asyncio.gather(*(one(name, job) for name, job in plan["jobs"].items() for _ in range(plan["times"])))
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False)

asyncio.run(main())
'''


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ENGINE), *args], capture_output=True, check=True).stdout


def engine(name: str, commit: str = "917ceca79", patch: str = "", overlay: str = "") -> str:
    """A scratch engine at /tmp/engine-<name> in the container: the commit's source, then a unified diff (git apply) and a folder of whole
    files laid over it (overlay/src/... replaces src/...), then the line that keeps every Jev request."""
    place = f"/tmp/engine-{name}"
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(["tar", "-x", "-C", scratch], input=git("archive", commit, "src", "pyproject.toml"), check=True)
        if patch:
            subprocess.run(["git", "apply", "--whitespace=nowarn", str(Path(patch).resolve())], cwd=scratch, check=True)
        if overlay:
            subprocess.run(["cp", "-R", f"{Path(overlay).resolve()}/.", scratch], check=True)
        source = Path(scratch) / "src/system_one.py"
        text = source.read_text()
        assert text.count(ASKED) == 1, "the line that asks Jev has moved"
        source.write_text(text.replace(ASKED, KEEPS))
        text_evals.box(f"rm -rf {place} && mkdir -p {place}")
        subprocess.run(["docker", "cp", f"{scratch}/.", f"{BOX}:{place}"], check=True, capture_output=True)
    return place


def capture(name: str, letters: list[str], times: int = 1) -> Path:
    """The scripted callers (letters of text_evals.EVALS) on the scratch engine <name>; returns the folder with each run's log and requests."""
    text_evals.ENGINES[name] = f"/tmp/engine-{name}"
    text_evals.AT_ONCE = 3   # several of these may be going at once
    return text_evals.run(letters, times, name) / name


def scripted(name: str, calls: dict[str, tuple[str, str, str, list]], times: int = 1) -> Path:
    """Scripted text calls on the scratch engine <name>. calls: {label: (suite folder, start of the caller's folder name, step to start on,
    the caller's lines)}; a line that is None is a silence up to the check-in. Returns the folder: <label>-<n>.log and <label>-<n>.jev.jsonl."""
    for label, (suite, caller, node, lines) in calls.items():
        text_evals.EVALS[label] = (suite, caller, node, lines, label, lambda run: None)
    return capture(name, list(calls), times)


def kept(folder: Path, letter: str = "") -> list[dict]:
    rows = []
    for path in sorted(folder.glob(f"{letter}*.jev.jsonl")):
        rows += [{**json.loads(line), "run": path.name.split(".")[0]} for line in path.read_text().splitlines() if line.strip()]
    return rows


def library(commit: str = "917ceca79") -> tuple[dict, str]:
    steps = {step["kind"]: step for step in json.loads(git("show", f"{commit}:src/prompts/jev/steps.json"))}
    heads = json.loads(git("show", f"{commit}:src/prompts/jev/core-decide.json"))["heads"]
    return steps, next(head["instructions"] for head in heads if head["name"] == "step_intent")


def reading(kind: str, values: dict, heard: str, changes: list[dict], commit: str = "917ceca79") -> dict:
    """The reading question as the engine composes it (step_question), with a wording's library changes in place."""
    steps, head = library(commit)
    new = {(change["kind"], change.get("intent", "template")): change["new"] for change in changes}
    template = new.get((kind, "template"), steps[kind]["question_template"])
    return {"type": "choice", "instructions": f"{head}\n{template.format_map({**values, 'caller_turn': heard})}",
            "criteria": {intent["id"]: new.get((kind, intent["id"]), intent["criterion"]) for intent in steps[kind]["intents"]}}


def heard(request: dict) -> str:
    """The caller's words as Jev was shown them: the last caller line of the call so far."""
    return next(line[len("caller: "):] for line in reversed(request["state"].splitlines()) if line.startswith("caller: "))


def last(state: str, speaker: str, new: str, before: int | None = None) -> tuple[str, int]:
    lines = state.splitlines()
    at = max(index for index, line in enumerate(lines[:before]) if line.startswith(f"{speaker}: "))
    lines[at] = f"{speaker}: {new}"
    return "\n".join(lines), at


def reworded(request: dict, wording: dict, caller: str | None = None, agent: str | None = None) -> dict:
    state, questions, values, said = request["state"], json.loads(json.dumps(request["questions"])), dict(request["values"]), heard(request)
    swaps = [(pair["old"], pair["new"]) for pair in wording.get("texts", [])]
    if caller is not None:
        (state, at), swaps = last(state, "caller", caller), [*swaps, (said, caller)]
        if agent is not None:
            state, _ = last(state, "agent", agent, at)
            for key in ("delivered_question", "readback_text", "last_agent_line"):
                if key in values:
                    swaps, values[key] = [*swaps, (values[key], agent)], agent
    for name, question in questions.items():
        if name == "step_intent":
            continue
        for old, new in swaps:
            question["instructions"] = question["instructions"].replace(old, new)
            question["criteria"] = {option: text.replace(old, new) for option, text in question["criteria"].items()}
    if "step_intent" in questions:
        questions["step_intent"] = reading(request["kind"], values, said if caller is None else caller, wording.get("library", []))
    return {"state": state, "questions": questions}


def ask(jobs: dict[str, dict], times: int = 5) -> dict[str, list[dict]]:
    """Each job {"state", "questions"} put to Jev <times> times; returns {job name: [one {question: {option: share}} per run]}."""
    with tempfile.TemporaryDirectory() as scratch:
        spot = f"/tmp/jev-lab/{Path(scratch).name}"   # its own folder: several of these may be going at once
        (Path(scratch) / "plan.json").write_text(json.dumps({"jobs": jobs, "times": times}, ensure_ascii=False))
        (Path(scratch) / "ask.py").write_text(IN_BOX)
        text_evals.box(f"mkdir -p {spot}")
        subprocess.run(["docker", "cp", f"{scratch}/.", f"{BOX}:{spot}"], check=True, capture_output=True)
        text_evals.box(f"cd /app && python {spot}/ask.py {spot}/plan.json {spot}/out.json > {spot}/log.txt 2>&1")
        out = json.loads(text_evals.box(f"cat {spot}/out.json") or "{}")
        text_evals.box(f"rm -rf {spot}")
        return out


def mean(runs: list[dict], question: str) -> dict[str, float]:
    """Jev's average answer to one question over the runs, largest first; a run with no usable answer is left out."""
    good = [run[question] for run in runs if question in run]
    options = {option for run in good for option in run}
    shares = {option: sum(run.get(option, 0) for run in good) / len(good) for option in options} if good else {}
    return dict(sorted(shares.items(), key=lambda item: -item[1]))


def sure(runs: list[dict], question: str, floor: float, margin: float) -> dict[str, int]:
    """How many runs were sure of each option, by the bar the engine uses; "" counts the runs that were not sure."""
    counts: dict[str, int] = {}
    for run in runs:
        ordered = sorted(run.get(question, {}).items(), key=lambda item: -item[1]) + [("", 0.0), ("", 0.0)]
        pick = ordered[0][0] if ordered[0][1] >= floor and ordered[0][1] - ordered[1][1] >= margin else ""
        counts[pick] = counts.get(pick, 0) + 1
    return counts
