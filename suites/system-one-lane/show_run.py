"""One saved text run, turn by turn: lines, steps, tools and Jev's top answers. Reads only.

  python3 show_run.py <run dir> [first event] [last event]
"""
import json
import sys

ev = json.load(open(sys.argv[1].rstrip("/") + "/trace.json"))["events"]
lo, hi = (int(sys.argv[2]) if len(sys.argv) > 2 else 0), (int(sys.argv[3]) if len(sys.argv) > 3 else len(ev))
for at, e in enumerate(ev[lo:hi], lo):
    kind = e["kind"]
    if kind == "line":
        print(f"{at:3} {(e.get('role') or e.get('who')):6}: {str(e.get('text'))[:260]}")
    elif kind == "step":
        print(f"{at:3}     step {e.get('name')} -> {str(e.get('result'))[:120]}{' ERR ' + str(e.get('error'))[:80] if e.get('error') else ''}")
    elif kind == "tool":
        print(f"{at:3}     tool {e.get('action')}: {e.get('status')}")
    elif kind == "jev":
        probs = e.get("probs", {})
        top = sorted(probs.get("step", {}).items(), key=lambda pair: -pair[1])[:3]
        rest = {head: f"{max(v, key=v.get)} {max(v.values()):.2f}" for head, v in probs.items() if head != "step" and v}
        print(f"{at:3}     jev step={[(name, round(share, 2)) for name, share in top]} {rest}")
    else:
        print(f"{at:3}     {kind} {str({k: v for k, v in e.items() if k != 'kind'})[:160]}")
