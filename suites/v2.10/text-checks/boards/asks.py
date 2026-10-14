#!/usr/bin/env python3
"""How often each question was put to the caller in each call of a board, from the merged timelines.

    python3 asks.py <folder of call folders> [least number of agent questions to show, default 3]

The talk between two results of a collect tool belongs to the question the second result names. Every agent line with a
question mark in it counts, so a read-back counts too; the caller's lines in between are printed with them.
"""
import re, sys
from pathlib import Path

least = int(sys.argv[2]) if len(sys.argv) > 2 else 3
total = shown = 0
for folder in sorted(Path(sys.argv[1]).iterdir()):
    said, counts = [], []
    for line in (folder / "timeline.txt").read_text().splitlines():
        text = line[12:]
        closed = re.search(r'engine: Tool call tool=collect_\w+ arguments=.*?"name": "(\w+)".*? output=(.{0,70})', text)
        if closed:
            counts.append((closed.group(1), said, closed.group(2)))
            said = []
        elif text.startswith("NODE"):
            counts.append(("(talk at the step itself)", said, "moved to another step"))
            said = []
        elif text.startswith("AGENT") and "?" in text:
            said.append("A: " + text[9:])
        elif text.startswith("CALLER"):
            said.append("C: " + text.split("   ", 1)[1])
    counts.append(("(open when the call ended)", said, "the call ended"))
    for name, lines, end in counts:
        asked = sum(line.startswith("A: ") for line in lines)
        total += bool(asked)
        if asked >= least:
            shown += 1
            print(f"\n{folder.name}  {name}: {asked} agent questions, ended: {end.strip()}")
            for line in lines:
                print("    " + line[:170])
print(f"\n{shown} of {total} stretches had {least} or more agent questions")
