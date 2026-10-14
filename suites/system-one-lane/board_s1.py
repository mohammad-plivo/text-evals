"""One table for a small-version lane campaign, read from its stored runs. Nothing is run and nothing is paid.

  python board_s1.py <campaign dir> [--engine <engine campaign dir>] [--switch-off] [--set-aside CHECK ...] [--out board-s1.md]

Two verdicts per run. "strict" is the lane's own verdict, the rules the engine board was judged by. "by turn" differs in
one rule: an acknowledgement on its own line ("Alright.") counts as a fault only when it is all the agent said before
the caller spoke again. Main's collectors say the receipt and the next question as two lines of one turn.

--switch-off reads a campaign run with the switch off (main alone): no Jev request is the point there, not a fault.
--set-aside adds a third count that leaves out the named checks (a check name's start is enough), for a check the
flow leaves to the engine's code, such as the Northwind call note.
"""
import argparse
import collections
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "text-evals", "text-lane"))
import judge_lane  # noqa: E402

ACK_LINE = "no ack-only spoken line"
ACK_TURN = "an agent turn was only an acknowledgement"


def by_turn(judge: dict) -> list[str]:
    """The failed checks with the acknowledgement rule read per caller turn."""
    failed = [check for check in judge.get("checks_failed") or [] if check != ACK_LINE]
    only_ack = [turn["agent"] for turn in judge.get("transcript") or []
                if turn["agent"].strip() and judge_lane.ACK.match(" ".join(turn["agent"].split()))]
    return failed + ([ACK_TURN] if only_ack else [])


def reply_gaps(trace: dict) -> list[float]:
    """Seconds from each caller line to the agent's next line."""
    lines = [event for event in trace["events"] if event["kind"] == "line"]
    return [after["t"] - line["t"] for line, after in zip(lines, lines[1:])
            if line["role"] == "caller" and after["role"] == "agent"]


NO_JEV = "no Jev request answered 200"


def load(campaign: str, switch_off: bool = False) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(campaign, "*", "row.json"))):
        out = os.path.dirname(path)
        row = json.load(open(path))
        if row["verdict"] == "NOT RUN":  # the campaign cap stopped it before it started
            continue
        judge = json.load(open(os.path.join(out, "judge.json"))) if os.path.exists(os.path.join(out, "judge.json")) else {}
        trace = json.load(open(os.path.join(out, "trace.json"))) if os.path.exists(os.path.join(out, "trace.json")) else {"events": []}
        failed = by_turn(judge)
        rubric_pass = judge.get("rubric_verdict") == "PASS"
        invalid = [reason for reason in row.get("invalid_reasons") or [] if not (switch_off and reason == NO_JEV)]
        strict = "INVALID" if invalid else "PASS" if rubric_pass and not judge.get("checks_failed") else "FAIL"
        rows.append({**row, "verdict": strict, "invalid_reasons": invalid, "judge": judge, "gaps": reply_gaps(trace),
                     "failed_by_turn": failed,
                     "verdict_by_turn": "INVALID" if invalid else "PASS" if rubric_pass and not failed else "FAIL"})
    return rows


def passes(rows: list[dict], key: str) -> dict[str, list[str]]:
    found = collections.defaultdict(list)
    for row in rows:
        found[row["scenario"]].append(row[key])
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign")
    parser.add_argument("--engine", help="the engine's campaign on the same pack, for a side column")
    parser.add_argument("--switch-off", action="store_true")
    parser.add_argument("--set-aside", nargs="*", default=[])
    parser.add_argument("--out", default="board-s1.md")
    args = parser.parse_args()
    rows = load(args.campaign, args.switch_off)
    engine = passes([json.load(open(p)) for p in glob.glob(os.path.join(args.engine, "*", "row.json"))], "verdict") if args.engine else {}
    for row in rows:
        kept = [check for check in row["failed_by_turn"] if not check.startswith(tuple(args.set_aside))] if args.set_aside else row["failed_by_turn"]
        rubric_pass = row["judge"].get("rubric_verdict") == "PASS"
        row["verdict_set_aside"] = "INVALID" if row["verdict_by_turn"] == "INVALID" else "PASS" if rubric_pass and not kept else "FAIL"
    count = lambda key, verdict: sum(row[key] == verdict for row in rows)  # noqa: E731
    gaps = sorted(gap for row in rows for gap in row["gaps"])
    checks = collections.Counter(check for row in rows for check in row["failed_by_turn"])
    unmet = collections.Counter(f"criterion {n}" for row in rows for n in row.get("not_met") or [])
    text = [f"# {os.path.basename(args.campaign)}: {len(rows)} runs", "",
            f"- Strict (the engine board's rules): {count('verdict', 'PASS')} pass, {count('verdict', 'FAIL')} fail, {count('verdict', 'INVALID')} not valid.",
            f"- By turn (an acknowledgement before the next question is not a fault): {count('verdict_by_turn', 'PASS')} pass, "
            f"{count('verdict_by_turn', 'FAIL')} fail, {count('verdict_by_turn', 'INVALID')} not valid.",
            *([f"- By turn, with {', '.join(repr(name) for name in args.set_aside)} set aside: {count('verdict_set_aside', 'PASS')} pass, "
               f"{count('verdict_set_aside', 'FAIL')} fail."] if args.set_aside else []),
            f"- Rubric alone (the Hunter judge): {sum(row['judge'].get('rubric_verdict') == 'PASS' for row in rows)} of {len(rows)} pass.",
            f"- Cost ${sum(row.get('cost_usd') or 0 for row in rows):.2f}. Jev faults in {sum(bool((row.get('proof') or {}).get('jev_faults')) for row in rows)} runs.",
            f"- Seconds from the caller's line to the agent's next line, text only: median {statistics.median(gaps):.1f}, "
            f"9 in 10 under {gaps[int(len(gaps) * 0.9)]:.1f}." if gaps else "- No replies timed.", "",
            "Failed checks, by turn: " + (", ".join(f"{name} x{n}" for name, n in checks.most_common()) or "none") + ".",
            "Rubric criteria not met: " + (", ".join(f"{name} x{n}" for name, n in unmet.most_common()) or "none") + ".", "",
            "| Scenario | Strict | By turn | Rubric score | Failed checks (by turn) | Criteria not met | Cost | Engine board |",
            "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        theirs = engine.get(row["scenario"])
        engine_cell = f"{theirs.count('PASS')} of {len(theirs)}" if theirs else "-"
        text.append(f"| {row['scenario']} | {row['verdict']} | {row['verdict_by_turn']} | {row.get('score')} | "
                    f"{', '.join(row['failed_by_turn']) or '-'} | {', '.join(map(str, row.get('not_met') or [])) or '-'} | "
                    f"${(row.get('cost_usd') or 0):.2f} | {engine_cell} |")
    for row in rows:
        if row["verdict"] == "INVALID":
            text.append(f"\n{row['scenario']} is not valid: {'; '.join(row.get('invalid_reasons') or [])}")
    open(os.path.join(args.campaign, args.out), "w").write("\n".join(text) + "\n")
    print("\n".join(text))


if __name__ == "__main__":
    main()
