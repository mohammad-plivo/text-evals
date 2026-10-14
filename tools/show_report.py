"""Print the transcript and tool calls of each run in a sim report (.jsonl). usage: show.py <report.jsonl> [--short]"""
import json, sys
short = "--short" in sys.argv
for l in open(sys.argv[1]):
    d = json.loads(l); t = d.get("type")
    if t == "scenario_started": print(f"\n===== {d['name']} run {d.get('run')}")
    elif t == "turn":
        print(f"  PATIENT: {d.get('user')}")
        for c in d.get("tool_calls") or []:
            args = c.get("arguments") or ""
            if c["name"].startswith("collect_"):
                try: a = json.loads(args); args = json.dumps({k: (v if k != "instructions" else "…") for k, v in a.items()})
                except ValueError: pass
            out = str(c.get("output") or "")
            print(f"     TOOL {c['name']}{' (mock)' if c.get('mocked') else ''} {args[:330]}" + ("" if short else f"\n          -> {out[:260]}"))
        print(f"  AGENT:   {d.get('agent')}")
        if d.get("intent"): print(f"     intent: {d['intent']}")
    elif t == "scenario_finished": print("  failures:", d.get("failures"))
