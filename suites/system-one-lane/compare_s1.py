"""Side by side: the same scenarios on several finished campaigns. Runs nothing, pays nothing.

  python compare_s1.py --off <campaign> --on NAME=<campaign> [--on NAME=<campaign> ...] [--engine <campaign>] [--out FILE]

One row per scenario, one column per campaign, with the by-turn verdict of board_s1.py. A cell that is not PASS says why in
a few words. The engine's column is its own lane verdict over its repeats, on its own flow.
"""
import argparse
import collections
import glob
import json
import os
import statistics

import board_s1

SHORT = {"no dead air over 15s": "dead air", "expected exit fired": "wrong ending", "call reached an exit": "no ending",
         board_s1.ACK_TURN: "only an acknowledgement"}


def why(row: dict) -> str:
    if row["verdict_by_turn"] == "PASS":
        return "pass"
    if row["verdict_by_turn"] == "INVALID":
        return "not valid"
    checks = sorted({SHORT.get(check, "a tool did not run" if check.startswith("tool ") else check) for check in row["failed_by_turn"]})
    rules = [f"judge rule {n}" for n in row.get("not_met") or []]
    reasons = checks + rules or ["the judge's overall verdict"]
    return "FAIL: " + ", ".join(reasons)


def summary(rows: list[dict]) -> str:
    gaps = sorted(gap for row in rows for gap in row["gaps"])
    cost = sum(row.get("cost_usd") or 0 for row in rows)
    return (f"{sum(row['verdict_by_turn'] == 'PASS' for row in rows)} of {len(rows)} pass by turn, {sum(row['verdict'] == 'PASS' for row in rows)} strict; "
            f"reply median {statistics.median(gaps):.1f} s, 9 in 10 under {gaps[int(len(gaps) * 0.9)]:.1f} s; ${cost:.2f} (${cost / len(rows):.2f} a call)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--off", required=True)
    parser.add_argument("--on", action="append", required=True)
    parser.add_argument("--engine")
    parser.add_argument("--out")
    args = parser.parse_args()
    columns = {"main alone": {row["scenario"]: row for row in board_s1.load(args.off, switch_off=True)}}
    for spec in args.on:
        name, _, campaign = spec.partition("=")
        columns[name] = {row["scenario"]: row for row in board_s1.load(campaign)}
    engine = collections.defaultdict(list)
    for path in glob.glob(os.path.join(args.engine, "*", "row.json")) if args.engine else ():
        row = json.load(open(path))
        engine[row["scenario"]].append(row["verdict"])
    names = list(columns)
    text = [f"- {name}: {summary(list(rows.values()))}" for name, rows in columns.items()]
    if engine:
        runs = [verdict for verdicts in engine.values() for verdict in verdicts]
        text.append(f"- big engine, its own flow and its own lane rules: {runs.count('PASS')} of {len(runs)} runs pass, "
                    f"{sum(all(v == 'PASS' for v in verdicts) for verdicts in engine.values())} of {len(engine)} scenarios every time")
    text += ["", "| Scenario | " + " | ".join(names) + (" | big engine |" if engine else " |"), "|---|" + "---|" * (len(names) + bool(engine))]
    for scenario in sorted(next(iter(columns.values()))):
        cells = [why(columns[name][scenario]) if scenario in columns[name] else "not run" for name in names]
        if engine:
            cells.append(f"{engine[scenario].count('PASS')} of {len(engine[scenario])}" if engine.get(scenario) else "-")
        text.append(f"| {scenario} | " + " | ".join(cells) + " |")
    print("\n".join(text))
    if args.out:
        open(args.out, "w").write("\n".join(text) + "\n")


if __name__ == "__main__":
    main()
