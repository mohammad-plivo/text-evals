"""Everything the agent said in one practice call, from the verbose sim log. usage: said.py <log> <scenario>-<run>"""
import json, re, sys
log, call = sys.argv[1], "sim-cli-" + sys.argv[2]
for line in open(log, errors="replace"):
    if call not in line or '"LLM response"' not in line:
        continue
    d = json.loads(line)
    if d.get("call_uuid") != call:
        continue
    text = " ".join(str(d.get("text") or "").split())
    tools = re.findall(r"'name': '([a-z_0-9]+)'", str(d.get("tool_calls") or ""))
    print(f"  SAID: {text[:400]!r}" + (f"  TOOLS: {tools}" if tools else ""))
