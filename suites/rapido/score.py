"""Score the 'why do you need this?' A/B. usage: score.py <report.jsonl> [--show]"""
import json
import re
import sys
from collections import defaultdict

DEV = re.compile(r"[ऀ-ॿ]")
LAT = re.compile(r"[A-Za-z]")
WHY_TURN = {"why-platform": 1, "why-callback": 5, "refuse-twice": 1}
ANSWER_TOOL = {"why-platform": (2, "update_text"), "why-callback": (6, "update_date"), "answer-direct": (1, "update_text")}  # prefixes


def hindi(text):
    d, l = len(DEV.findall(text)), len(LAT.findall(text))
    return d > 0 and d >= l


runs, cur = [], None
for line in open(sys.argv[1]):
    d = json.loads(line)
    if d.get("type") == "scenario_started":
        cur = {"name": d["name"], "run": d.get("run"), "turns": []}
        runs.append(cur)
    elif d.get("type") == "turn" and cur is not None:
        cur["turns"].append((d.get("user"), " ".join(str(d.get("agent") or "").split()), [c["name"] for c in d.get("tool_calls") or []]))

table = defaultdict(lambda: defaultdict(int))
for r in runs:
    row, t = table[r["name"]], r["turns"]
    row["runs"] += 1
    if r["name"] in WHY_TURN and len(t) > WHY_TURN[r["name"]]:
        reply = t[WHY_TURN[r["name"]]][1]
        row["reply asks again"] += "?" in reply
        row["reply in Hindi"] += hindi(reply)
        if "--show" in sys.argv:
            print(f"{r['name']:14s} run {r['run']:>2}: {reply[:170]}")
    if r["name"] in ANSWER_TOOL:
        i, tool = ANSWER_TOOL[r["name"]]
        row["answer recorded"] += len(t) > i and any(n.startswith(tool) for n in t[i][2])
    if r["name"] == "refuse-twice" and len(t) > 2:
        row["second refusal accepted"] += any(n.startswith("decline_") for n in t[2][2])
        row["moves on after it"] += "पार्ट" in t[2][1] or "फुल" in t[2][1] or "part" in t[2][1].lower()
        row["next answer misfiled"] += len(t) > 3 and "update_text" in t[3][2]

cols = ["runs", "reply asks again", "reply in Hindi", "answer recorded", "second refusal accepted", "moves on after it", "next answer misfiled"]
print("\n" + " | ".join(["scenario".ljust(14)] + cols))
for name in ["why-platform", "why-callback", "answer-direct", "refuse-twice"]:
    row = table[name]
    print(" | ".join([name.ljust(14)] + [(str(row[c]) if (c in row or c == "runs") else "-").ljust(len(c)) for c in cols]))
