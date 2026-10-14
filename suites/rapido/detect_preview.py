"""Run the runner's own Detect-from-instructions code (propose + configure) on a node's Task. Prints no secrets.
usage: <tree>/.venv/bin/python detect_preview.py <flow.json> [node name]"""
import asyncio, json, os, re, sys

ENV_FILE = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized-v291-jev/services/plivo-cx-livekit/.env"
for line in open(ENV_FILE, errors="replace"):
    m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
    if m and m.group(2).strip().strip('"').strip("'") and m.group(1) not in os.environ:
        os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")

from src.collection_configuration_suggest import SuggestRequest, suggest_configurations  # noqa: E402

flow = json.load(open(sys.argv[1]))
node = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")
task = node["data"]["config"]["instructions"]
result = asyncio.run(suggest_configurations(SuggestRequest(auth_id="local-detect-preview", instructions=task, inputs=[], propose_inputs=True)))
print("errors:", result["errors"])
for p in result["proposed"]:
    c = p.get("collection") or {}
    print(f"- {p['variable_name']:24s} type={c.get('type')!s:8s} required={c.get('required')!s:5s} "
          f"choices={c.get('choices')} options={c.get('options')} fresh={c.get('fresh_question')}")
    print(f"    asks: {p['variable_instructions'][:160]}")
json.dump(result, open(sys.argv[1].replace(".json", "-detect-preview.json"), "w"), ensure_ascii=False, indent=1)
