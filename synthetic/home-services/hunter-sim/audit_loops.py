#!/usr/bin/env python3
"""Per sim run: the longest run of refused declines inside one caller turn, and where the walk ended.

    python3 V29-Hunter-Example/hunter-sim/audit_loops.py <sim --verbose log> [<more logs>...]

A refusal is a 'ToolError while executing tool: REJECTED' row; one generation (speech_id) answers one
caller turn, so the count per (speech_id, function) is the number of times the model repeated a refused
decline without the caller speaking.
"""
from __future__ import annotations

import collections
import json
import re
import sys

EXIT = re.compile(r"Tool call tool=(handoff_[a-z0-9_]+)")
SETTLED = re.compile(r"collect: (\w+) \(\w+\) (declined by the caller|not provided|handed back|collected)")


def audit(paths: list[str]) -> dict[str, dict]:
    runs: dict[str, dict] = collections.defaultdict(lambda: {"refusals": collections.Counter(), "exit": None, "settled": []})
    for path in paths:
        for line in open(path, errors="replace"):
            if not line.startswith("{"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            run, message = runs[row.get("call_uuid") or "?"], row.get("message", "")
            if "ToolError while executing tool: REJECTED" in message:
                run["refusals"][(row.get("speech_id"), row.get("function"))] += 1
            if match := EXIT.search(message):
                run["exit"] = match.group(1)
            if match := SETTLED.search(message):
                run["settled"].append(f"{match.group(1)}:{match.group(2)}")
    return runs


def main() -> None:
    runs = audit(sys.argv[1:])
    worst = []
    print(f"{'run':34s} {'max in one turn':>15s} {'total':>6s}  exit / settled optional fields")
    for name, run in sorted(runs.items()):
        top = max(run["refusals"].values(), default=0)
        worst.append(top)
        fields = [s for s in run["settled"] if s.split(":")[0] in ("gate_code", "alternate_phone")]
        print(f"{name:34s} {top:15d} {sum(run['refusals'].values()):6d}  {run['exit']} | {', '.join(fields)}")
    looped = sum(1 for w in worst if w >= 2)
    print(f"\n{len(worst)} runs; {looped} with a refused decline repeated in one turn; "
          f"median worst {sorted(worst)[len(worst) // 2] if worst else 0}, max {max(worst, default=0)}")


if __name__ == "__main__":
    main()
