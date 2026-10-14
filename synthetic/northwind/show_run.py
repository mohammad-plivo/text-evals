"""Print one run's spoken lines with the leader's settled commands, exits and faults: python3 show_run.py RUN_DIR [t0 t1]"""
import json
import re
import sys

t = json.load(open(sys.argv[1] + "/trace.json"))
lo, hi = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (0, 1e9)
keypad = {}  # keypad candidate -> keys; a key press adds no caller line, so show the leader's candidate and its grounding
for e in t["events"]:
    if not lo <= e["t"] <= hi:
        continue
    if e["kind"] == "line":
        print(f"{e['t']:6.0f} {e['role'].upper():6} {e['text'][:220]}")
    elif e["kind"] == "tool":
        print(f"{e['t']:6.0f} TOOL   {e['action']} {e['status']} {json.dumps(e.get('arguments'))[:160]}")
    elif e["kind"] == "log":
        m = e["msg"]
        if m.startswith("jev.request") and "actual keypad ingress" in m:
            for cid, value in re.findall(r'For candidate (\w+) on field .*?canonical_value\\?": \\?"([0-9*#]+)', m):
                if cid not in keypad:
                    keypad[cid] = value
                    print(f"{e['t']:6.0f} KEYS   {value} (keypad candidate {cid[:8]})")
        if "stage=settled" in m and m.startswith("jev.decision"):
            f = dict(re.findall(r"(command|step|intent|reason)=(\S+)", m))
            for cid, choice in re.findall(r'"grounding_(\w+)": \{"choice": "(\w+)"', m):
                if cid in keypad:
                    print(f"{e['t']:6.0f}   jev  keypad {cid[:8]} grounding={choice} command={f['command']}")
            if not f["command"].startswith(("EXTRACT", "WAIT")):
                print(f"{e['t']:6.0f}   jev  {f['command']} step={f['step']} intent={f['intent']} reason={f['reason']}")
        elif m.startswith(("jev.fault", "jev.exit", "jev.handoff", "jev.route", "jev.veto", "jev.close", "jev.tool_note", "jev.sensitive entry")):
            print(f"{e['t']:6.0f}   log  {m[:260]}")
