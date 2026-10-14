#!/usr/bin/env python3
"""Drive the V2.9 text-eval lane over a list of session cases and report one row per case.

Row keys come from tests/v29_model_eval/live.py (_run) and session_runner.SessionTrace.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__import__("os").environ.get("STRESS_REPO") or "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/repo")  # STRESS_REPO pins a test tree
MAX_PER_INVOCATION = 25  # live.py:47
PASSED = "passed"


def ledger_figures(path: Path) -> tuple[float, str]:
    """Conservative spend and a printable line. A missing/unreadable ledger reads as zero spend."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0, f"ledger {path.name}: absent or unreadable (conservative spend 0)"
    spent = data.get("conservative_spent_usd", "0")
    standard = data.get("standard_estimated_usd", "0")
    ceiling = data.get("conservative_ceiling_usd", "?")
    requests = data.get("request_count", 0)
    failure = data.get("campaign_failure")
    line = (
        f"ledger {path.name}: conservative ${float(spent):.4f} / ceiling {ceiling}, "
        f"standard estimate ${float(standard):.4f}, {requests} request(s)"
        + (f", campaign_failure={failure!r}" if failure else "")
    )
    return float(spent), line


def load_rows(output: Path, campaign_id: str | None) -> tuple[list[dict], str | None]:
    """Rows for this campaign, or a note saying why there are none."""
    if not output.exists():
        return [], f"no output file at {output}"
    rows = []
    for number, line in enumerate(output.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            return rows, f"line {number} of {output.name} is not JSON"
    if not rows:
        return [], f"{output} is empty"
    if campaign_id:
        wanted = {campaign_id, campaign_id + "-configured"}  # live.py:19,26
        rows = [row for row in rows if row.get("campaign_id") in wanted]
        if not rows:
            return [], f"no rows in {output.name} for campaign {campaign_id}"
    return rows, None


def row_trace(row: dict) -> dict:
    """A pass carries `trace`, a failure `partial_trace` (live.py:404,416); either may be absent."""
    trace = row.get("partial_trace") or row.get("trace") or {}
    return trace if isinstance(trace, dict) else {}


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def table(rows: list[dict]) -> list[str]:
    header = [
        "| case | rep | structural | oracle_detail | speech | dimensions not passed | tool calls |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    body = []
    for row in rows:
        detail = (row.get("error") or {}).get("oracle_detail") or ""
        dims = row.get("dimensions") or {}
        bad = ",".join(
            f"{name}={score.get('status')}"
            for name, score in sorted(dims.items())
            if isinstance(score, dict) and score.get("status") != PASSED
        )
        events = row_trace(row).get("events") or []
        executed = sum(1 for event in events if event.get("kind") == "executed")
        body.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                cell(str(row.get("case_id"))),
                row.get("repetition"),
                cell(str(row.get("structural_status"))),
                cell(detail[:90]),
                cell(str(row.get("speech_review_status"))),
                cell(bad),
                executed,
            )
        )
    return header + body


def summary(rows: list[dict], ledger_line: str) -> list[str]:
    per_case: dict[str, list[str]] = {}
    for row in rows:
        per_case.setdefault(str(row.get("case_id")), []).append(str(row.get("structural_status")))
    lines = [""]
    for case_id, statuses in sorted(per_case.items()):
        good = sum(status == PASSED for status in statuses)
        lines.append(f"- {case_id}: {good} passed / {len(statuses) - good} not passed of {len(statuses)}")
    lines.append(f"- total rows: {len(rows)}")
    lines.append(f"- {ledger_line}")
    return lines


def trace_view(rows: list[dict], case_id: str, rep: int | None) -> list[str]:
    picked = [
        row for row in rows
        if str(row.get("case_id")) == case_id and (rep is None or row.get("repetition") == rep)
    ]
    if not picked:
        return [f"no row for case {case_id}" + (f" repetition {rep}" if rep else "")]
    lines = []
    for row in picked:
        events = row_trace(row).get("events") or []
        lines.append(f"## {case_id} rep {row.get('repetition')} — {row.get('structural_status')}, {len(events)} event(s)")
        if not events:
            lines.append("(no trace events on this row)")
        for index, event in enumerate(events):
            kind = event.get("kind")
            collector = event.get("collector")
            suffix = f"  [collector {collector.get('name')}/{collector.get('task_type')}]" if isinstance(collector, dict) else ""
            turn = event.get("caller_turn")
            if kind == "message":
                role = event.get("role")
                content = str(event.get("content") or "")
                lines.append(f"{index:>3} t{turn} {role}: {content[:400]}")
            elif kind in ("emitted", "executed"):
                arguments = str(event.get("arguments") or "")[:160]
                tail = ""
                if kind == "executed":
                    tail = f" -> {str(event.get('output') or '')[:160]}" + (" [ERROR]" if event.get("is_error") else "")
                lines.append(f"{index:>3} t{turn} {kind} {event.get('name')}({arguments}){tail}{suffix}")
            elif kind == "store":
                lines.append(f"{index:>3} t{turn} store {event.get('name')}={event.get('value')!r}{suffix}")
            elif kind in ("collector_enter", "collector_exit"):
                lines.append(f"{index:>3} t{turn} {kind} {event.get('name')}/{event.get('task_type')}")
            else:
                lines.append(f"{index:>3} t{turn} {kind} {json.dumps(event, default=str)[:200]}")
        lines.append("")
    return lines


def run_batch(args: argparse.Namespace, batch: list[str]) -> tuple[bool, int]:
    """Launch one lane invocation. Returns (launched, returncode)."""
    command = [
        ".venv/bin/python", "-m", "tests.v29_model_eval.live",
        "--env-file", str(args.env_file),
        "--ledger", str(args.ledger),
        "--campaign-id", args.campaign_id,
        "--output", str(args.output),
        "--repetitions", str(args.repetitions),
        "--continue-on-oracle-failure",
    ]
    if args.configured:
        command.append("--configured")
    for case_id in batch:
        command += ["--session-case", case_id]
    print("$ " + " ".join(command))
    if args.dry_run:
        return True, 0
    log = args.output.with_suffix(args.output.suffix + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n=== {args.campaign_id} :: {' '.join(batch)} ===\n")
        handle.flush()
        try:
            completed = subprocess.run(command, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT)
        except OSError as exc:
            print(f"failed to launch: {exc}")
            return False, 1
    print(f"lane exit={completed.returncode}; log: {log}")
    # rc 0/1 is the lane's own pass/fail verdict (live.py:459); anything else never got going
    return completed.returncode in (0, 1), completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", default=[])
    parser.add_argument("--cases-from", type=Path)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--campaign-id")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--configured", action="store_true")
    parser.add_argument("--cap-usd", type=float, default=100.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--trace")
    parser.add_argument("--rep", type=int)
    args = parser.parse_args()

    cases = list(args.cases)
    if args.cases_from:
        cases += [line.strip() for line in args.cases_from.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen: dict[str, None] = dict.fromkeys(cases)  # live.py:49 rejects duplicates
    cases = list(seen)

    if args.trace:
        rows, note = load_rows(args.output, args.campaign_id)
        print(note or "")
        print("\n".join(trace_view(rows, args.trace, args.rep)))
        return 0 if rows else 1

    failed = False
    if cases:
        for missing in ("campaign_id", "env_file", "ledger"):
            if getattr(args, missing) is None:
                parser.error(f"--{missing.replace('_', '-')} is required to run cases")
        for start in range(0, len(cases), MAX_PER_INVOCATION):
            batch = cases[start:start + MAX_PER_INVOCATION]
            if not args.dry_run:
                spent, line = ledger_figures(args.ledger)
                print(f"before batch: {line}")
                if spent >= args.cap_usd:
                    print(f"STOPPED: conservative spend ${spent:.4f} is at or above the ${args.cap_usd:.2f} cap")
                    return 2
            launched, _ = run_batch(args, batch)
            failed = failed or not launched
            if not args.dry_run:
                spent, line = ledger_figures(args.ledger)
                print(f"after batch:  {line}")
                if spent >= args.cap_usd:
                    print(f"STOPPED: conservative spend ${spent:.4f} is at or above the ${args.cap_usd:.2f} cap")
                    return 2
    elif not args.report:
        parser.error("give --cases/--cases-from, --report, or --trace")

    if args.dry_run:
        return 1 if failed else 0

    rows, note = load_rows(args.output, args.campaign_id)
    if note:
        print(note)
        return 1 if failed else 0
    ledger_line = ledger_figures(args.ledger)[1] if args.ledger else "no --ledger given"
    report = table(rows) + summary(rows, ledger_line)
    print("\n".join(report))
    args.output.with_suffix(args.output.suffix + ".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 1 if failed else 0


def _self_check() -> None:
    """Row-shape check: the table and trace view must survive a pass row, a fail row, and no rows."""
    fail = {
        "campaign_id": "c1", "case_id": "mt_x", "repetition": 1, "structural_status": "failed",
        "speech_review_status": "not_reached",
        "error": {"category": "oracle", "oracle_detail": "wrong stored email: a|b"},
        "dimensions": {"wire": {"status": "failed", "detail": "d"}, "effects": {"status": "passed"}},
        "partial_trace": {"events": [
            {"kind": "message", "role": "assistant", "content": "Hi", "caller_turn": 0},
            {"kind": "emitted", "name": "collect_input", "arguments": "{}", "caller_turn": 1,
             "collector": {"name": "email", "task_type": "collect_email"}},
            {"kind": "executed", "name": "collect_input", "arguments": "{}", "output": "Collected email", "caller_turn": 1},
        ]},
    }
    ok = {"campaign_id": "c1", "case_id": "mt_y", "repetition": 1, "structural_status": "passed",
          "speech_review_status": "passed", "dimensions": {"wire": {"status": "passed"}},
          "trace": {"events": [{"kind": "executed", "name": "submit_details", "caller_turn": 2}]}}
    lines = table([fail, ok])
    assert lines[2].startswith("| mt_x |") and "a\\|b" in lines[2], lines[2]
    assert lines[2].endswith("| 1 |") and lines[3].endswith("| 1 |"), lines[-2:]
    assert "wire=failed" in lines[2] and "effects" not in lines[2]
    assert "mt_x: 0 passed / 1 not passed of 1" in summary([fail, ok], "x")[1]
    assert any("collector email" in line for line in trace_view([fail], "mt_x", 1))
    assert trace_view([ok], "nope", None) == ["no row for case nope"]
    assert load_rows(Path("/nonexistent/out.jsonl"), None)[0] == []
    print("self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
