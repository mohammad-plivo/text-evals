"""One run's timeline with the lead and model rows S1_DUMP_ASKS records: what each request offered, kept, and got back.

  python3 dumpline.py RUN_DIR [FROM_SECONDS]
"""
import json
import os
import sys

events = json.load(open(os.path.join(sys.argv[1], "trace.json")))["events"]
start = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
for e in events:
    t, kind = float(e.get("t") or 0), e["kind"]
    if t < start:
        continue
    if kind == "line":
        print(f"{t:6.1f} {e['role'].upper():6} {' '.join(e['text'].split())[:220]}")
    elif kind == "log" and "s1." in e.get("msg", ""):
        print(f"{t:6.1f}   log   {e['msg'][:300]}")
    elif kind == "lead":
        kept = e["kept"] if len(e["kept"]) < 6 else f"{len(e['kept'])} tools"
        print(f"{t:6.1f}   lead  offered={len(e['offered'])} kept={kept} choice={e['kept_choice']} insist={e['insist']} "
              f"notes={[n[:70] for n in e['notes'] if not n.startswith('#')]}")
    elif kind == "model":
        print(f"{t:6.1f}   model choice={e['choice']} text={e['text'][:140]!r} calls={[c[:90] for c in e['calls']]}")
    elif kind in ("step", "end"):
        print(f"{t:6.1f}   {kind:5} {e.get('name', '')} error={e.get('error')} {str(e.get('result', ''))[:120]!r}")
