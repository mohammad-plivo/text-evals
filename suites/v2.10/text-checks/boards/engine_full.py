#!/usr/bin/env python3
"""The engine's whole log for chosen calls of a saved board, one file per call beside its timeline (long lines cut at 5000 letters).

    python3 engine_full.py <stack> <out folder> <suite name> <board json> <caller number> [<caller number> ...]
"""
import json, re, subprocess, sys
from pathlib import Path

stack, out, suite, board = sys.argv[1], Path(sys.argv[2]), sys.argv[3], json.load(open(sys.argv[4]))
wanted = {re.search(r"(\d\d)-", call["caller"]).group(1): call["flow_run"] for call in board["calls"]}
logs = subprocess.run(["docker", "logs", f"{stack}-agent-runner"], capture_output=True, text=True)
lines = [line for line in (logs.stdout + logs.stderr).splitlines() if line.startswith("{")]
for number in sys.argv[5:]:
    run, kept = wanted[number], []
    for line in lines:
        if run in line:
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if "timestamp" in doc:   # a line of another shape is not the engine's own
                kept.append(f"{doc['timestamp'][11:22]} {doc.get('level', ''):7s} {' '.join(str(doc.get('message', '')).split())[:5000]}")
    (out / f"{suite}-{number}" / "engine-full.txt").write_text("\n".join(kept) + "\n")
    print(number, len(kept), "lines")
