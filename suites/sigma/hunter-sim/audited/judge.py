"""Strict, manifest-driven grading helpers for audited simulator reports."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

CRITERION = re.compile(r"(?m)^(\d+)\.\s+")
STAMP = re.compile(r"(\d{8})-(\d{6})")
NOT_GRADABLE = ("N/A", "UNGRADED")
CONTRADICTION = re.compile(r"(?m)^\s*(\d+)\s*:\s*(CONSISTENT|CONTRADICTS)\s*$")
CONTRADICTION_INSTRUCTION = (
    "You are checking one grader's own output for self-contradiction. You are NOT regrading, and you "
    "cannot see the transcript. For each item you get the authored criteria and the grader's evidence "
    "for a criterion it marked NOT MET. Answer CONTRADICTS when that evidence, read on its own, states "
    "that the criterion's required behaviour did happen or that its forbidden behaviour did not happen. "
    "Answer CONSISTENT for everything else, including evidence you cannot judge.\n"
    "Return exactly one line per item, unchanged order: <id>: CONSISTENT or <id>: CONTRADICTS. No other text."
)
VERDICT = re.compile(
    r"^\s*(\d+)\s*[:.]\s*"          # the id, with a colon or a full stop
    r"(?:[^:\[]{0,80}:\s*)?"          # the model sometimes echoes the criterion title first
    r"\[?(MET|NOT MET|N/A)\]?\s+"     # brackets optional
    r"accuracy=(100|[1-9]?\d)\s+[-:]\s+(.+?)\s*$"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rubric_ids(rubric: str) -> list[int]:
    ids = [int(value) for value in CRITERION.findall(rubric)]
    if not ids or len(ids) != len(set(ids)) or ids != list(range(1, len(ids) + 1)):
        raise ValueError("rubric criteria must have unique contiguous numbering from 1")
    return ids


def na_allowed_ids(rubric: str) -> set[int]:
    matches = list(CRITERION.finditer(rubric))
    allowed = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(rubric)
        block = rubric[match.start():end]
        mentions_na = re.search(r"\bN/A\b", block)
        # a criterion that states its own precondition is not applicable when that precondition did
        # not occur; counting it against the agent grades a path the scenario never took
        conditional = re.search(r"(?i)\bthis criterion applies only\b|\bapplies only (?:once|if|when)\b", block)
        forbids_na = re.search(r"\b(?:never|not)\s+(?:be\s+|mark(?:ed)?\s+)?N/A\b", block, re.I)
        if (mentions_na or conditional) and not forbids_na:
            allowed.add(int(match.group(1)))
    return allowed


def run_clocks(report: Path) -> dict[int, dt.datetime]:
    """When each run in the batch ran, from the recorder's sidecar jsonl, keyed by run index.

    The report stamp is the SUITE start, shared by every run of a --repeat batch, so run N is graded
    against a clock N run-lengths stale and a batch launched before midnight dates its later runs a
    day early. The sidecar carries one event per run.

    ponytail: a run's events are buffered and flushed when it ends (cli/engine.py _EventBuffer), so
    this is late by the run's own duration, minutes rather than the batch's hours.
    """
    path = report.with_suffix(".jsonl")
    clocks: dict[int, dt.datetime] = {}
    if not path.exists():
        return clocks
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "scenario_started" and event.get("run") is not None and event.get("ts"):
            clocks.setdefault(int(event["run"]), dt.datetime.fromtimestamp(float(event["ts"])))
    return clocks


def call_clock(report: Path, timezone: str, when: dt.datetime | None = None) -> str:
    """The call's date, weekday and local time (H-5): a weekday criterion is ungradable without it.

    ponytail: both the sidecar ts and the report stamp are the machine clock, so this is the call
    clock only while the machine runs in the workspace timezone.
    """
    if when is None:
        match = STAMP.search(report.name)
        if not match:
            return ""
        when = dt.datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    return f"{when:%A, %d %B %Y, %H:%M} {timezone}"


def gradable(verdicts: list[dict]) -> list[dict]:
    """The criteria that count: neither N/A nor a verdict that contradicted its own evidence."""
    return [v for v in verdicts if v["status"] not in NOT_GRADABLE]


async def contradicting_ids(rubric: str, verdicts: list[dict], chat, deployment: str) -> set[int]:
    """H-7: the ids whose NOT MET evidence says the criterion was met; they are ungraded, not failures."""
    # a coerced N/A reads as "it did not happen", so passing it here would hand back the N/A the
    # rubric author forbade; only a verdict the judge itself chose to fail may be ungraded
    failed = [v for v in verdicts if v["status"] == "NOT MET" and not v.get("coerced_na")]
    if not failed:
        return set()
    body = ("AUTHORED CRITERIA:\n" + rubric + "\n\nGRADER EVIDENCE, one line per criterion it marked NOT MET:\n"
            + "\n".join(f"{v['id']}: {v['evidence']}" for v in failed))
    raw = await chat(CONTRADICTION_INSTRUCTION, body, deployment=deployment)
    flagged = {int(i) for i, answer in CONTRADICTION.findall(raw) if answer == "CONTRADICTS"}
    return flagged & {v["id"] for v in failed}


def transcript_evidence(run: dict) -> tuple[str, bool]:
    lines: list[str] = []
    turns = run.get("turns") or []
    for turn in turns:
        if turn.get("user") is not None:
            lines.append(f"CALLER: {turn['user']}")
        if turn.get("agent") is not None:
            # On the routing turn the end node speaks last, in words the flow authored. Labelling that
            # line AGENT convicted the agent of the flow's own closing (Retry Later, 2026-09-21).
            spoken = str(turn["agent"]).split("\n")
            if turn.get("intent") and turn.get("ended") and spoken[-1].strip():
                for line in spoken[:-1]:
                    if line.strip():
                        lines.append(f"AGENT: {line}")
                lines.append(f"END NODE ({turn['intent']}): {spoken[-1]}")
            else:
                lines.append(f"AGENT: {turn['agent']}")
        for transition in turn.get("transitions") or []:
            lines.append("TRANSITION: " + json.dumps(transition, sort_keys=True))
    return "\n".join(lines), bool(turns and turns[-1].get("ended"))


def parse_verdict(text: str, expected_ids: list[int], allowed_na: set[int]) -> list[dict]:
    lines = [line for line in text.splitlines() if line.strip()]
    parsed = []
    for line in lines:
        match = VERDICT.fullmatch(line)
        if not match:
            raise ValueError(f"malformed judge output line: {line!r}")
        number, status, accuracy, evidence = match.groups()
        criterion_id = int(number)
        coerced = status == "N/A" and criterion_id not in allowed_na
        if coerced:
            status, evidence = "NOT MET", f"[unauthorised N/A counted against the agent] {evidence}"  # conservative, never a pass
        parsed.append({"id": criterion_id, "status": status, "accuracy": int(accuracy), "evidence": evidence,
                       "coerced_na": coerced})
    if [item["id"] for item in parsed] != expected_ids:
        raise ValueError("judge output does not exactly cover authored criterion IDs in order")
    return parsed


def load_manifest(path: Path, root: Path) -> list[tuple[Path, Path]]:
    data = json.loads(path.read_text())
    entries = data.get("reports") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest must contain a non-empty reports list")
    result = []
    for entry in entries:
        workspace = (root / entry["workspace"]).resolve()
        report = (root / entry["report"]).resolve()
        if root.resolve() not in workspace.parents or workspace not in report.parents:
            raise ValueError("manifest report must be inside its named workspace")
        result.append((workspace, report))
    return result


async def grade_report(workspace: Path, report: Path, chat, deployment: str) -> dict:
    hunter_path = workspace / "hunter.json"
    hunter = json.loads(hunter_path.read_text())
    ids = rubric_ids(hunter["evaluationPrompt"])
    allowed_na = na_allowed_ids(hunter["evaluationPrompt"])
    runs = json.loads(report.read_text())
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"{report}: expected a non-empty run list")
    clocks = run_clocks(report)
    graded = []
    for run in runs:
        clock = call_clock(report, hunter.get("timezone") or "UTC", clocks.get(run.get("run")))
        transcript, ended = transcript_evidence(run)
        instruction = hunter["evaluationPrompt"] + f"\nN/A is permitted only for these criterion IDs when their authored condition applies: {sorted(allowed_na)}."
        instruction += "\nReturn exactly one line per numbered criterion, unchanged order: <id>: [MET|NOT MET|N/A] accuracy=<0-100> - <observed evidence>. No summary."
        clock_line = f"CALL CLOCK, a fact the transcript does not carry: {clock}.\n" if clock else ""
        speakers = ("SPEAKERS: CALLER is the simulated candidate. AGENT is the node under test. "
                    "END NODE is a closing the FLOW authored, not the agent's own words: never judge "
                    "the agent for its content, only for whether routing there was right.\n")
        prompt = f"{clock_line}{speakers}OBSERVED TRANSCRIPT ONLY:\n{transcript}\n\nDerived ended from final turn: {ended}. Harness failures: {run.get('failures') or 'none'}."
        raw = await chat(instruction, prompt, deployment=deployment)
        try:
            verdicts = parse_verdict(raw, ids, allowed_na)
        except ValueError as error:  # one malformed verdict must not abort the batch; the run is reported ungraded
            graded.append({"scenario": run.get("scenario"), "run": run.get("run"), "ended": ended, "criteria": [],
                           "all_criteria_met": False, "minimum_accuracy": None, "judge_raw": raw, "ungraded": str(error)})
            continue
        ungraded = await contradicting_ids(hunter["evaluationPrompt"], verdicts, chat, deployment)
        for verdict in verdicts:
            if verdict["id"] in ungraded:
                verdict["contradicts_own_evidence"] = True  # flagged for a human, still counted as failed
                verdict["evidence"] = f"[flagged: verdict may contradict its own evidence, still counted] {verdict['evidence']}"
        applicable = gradable(verdicts)
        graded.append({
            "scenario": run.get("scenario"), "run": run.get("run"), "ended": ended,
            "criteria": verdicts, "all_criteria_met": bool(applicable) and all(v["status"] == "MET" for v in applicable),
            "minimum_accuracy": min((v["accuracy"] for v in applicable), default=None),
            "ungraded_ids": sorted(ungraded), "call_clock": clock, "judge_raw": raw,
        })
    return {
        "workspace": workspace.name, "report": str(report),
        "report_sha256": sha256(report), "hunter_sha256": sha256(hunter_path),
        "source_sha256": hunter.get("source_sha256"), "flow_sha256": hunter.get("flow_sha256"),
        "runs": graded,
    }


async def async_main(args) -> int:
    import sys
    sys.path.insert(0, str(args.worktree))
    from src.simulation.cli import azure_chat
    items = load_manifest(args.manifest, args.root)
    output = [await grade_report(ws, report, azure_chat.chat, args.deployment) for ws, report in items]
    destination = args.output
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.write_text(json.dumps({"manifest_sha256": sha256(args.manifest), "reports": output}, indent=2) + "\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audited simulator judge; not Hunter-equivalent scoring")
    parser.add_argument("worktree", type=Path)
    parser.add_argument("root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--deployment", default="gpt-4.1")
    return asyncio.run(async_main(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
