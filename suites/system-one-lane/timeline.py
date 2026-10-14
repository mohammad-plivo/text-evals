"""One run's timeline: caller and agent lines, Jev's step pick, steps and tools, with gaps over 15 s marked.

  python3 timeline.py RUN_DIR [--all-logs]
"""
import json
import os
import sys

run = sys.argv[1]
events = json.load(open(os.path.join(run, "trace.json")))["events"]
last_caller = None
for e in events:
    t = float(e.get("t") or 0)
    kind = e["kind"]
    if kind == "line":
        gap = f"  <-- {t - last_caller:.1f}s after the caller" if e["role"] == "agent" and last_caller and t - last_caller > 15 else ""
        print(f"{t:7.1f} {e['role'].upper():6} {' '.join(e['text'].split())[:230]}{gap}")
        last_caller = t if e["role"] == "caller" else None
    elif kind == "log" and ("s1." in e.get("msg", "") or "--all-logs" in sys.argv):
        print(f"{t:7.1f}   log  {e['msg'][:260]}")
    elif kind in ("step", "tool", "span", "end"):
        bits = {k: v for k, v in e.items() if k not in ("t", "kind", "result", "arguments")}
        print(f"{t:7.1f}   {kind:5} {json.dumps(bits)[:200]}")
