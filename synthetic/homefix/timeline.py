#!/usr/bin/env python3
"""One voice call on the local stack as a readable timeline: the stack's log rows merged with the engine's System One lines.

    python3 timeline.py <flow run uuid> [--no-engine]     # the uuid is in out/voice/<run id>.json, key "flow_run"
"""
import datetime, json, re, subprocess, sys

run = sys.argv[1]
rows = json.loads(subprocess.run(["docker", "exec", "v210-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c",
    f"SELECT json_agg(log_data ORDER BY id) FROM conversation_run_logs WHERE flow_run_uuid = '{run}'"], capture_output=True, text=True, check=True).stdout or "[]")
at = lambda text: datetime.datetime.fromisoformat(text[:26]).replace(tzinfo=None).timestamp()
events = []
for r in rows:
    t, kind, ty = at(r["timestamp"]), r.get("event_name"), r.get("type")
    if kind == "NODE_EXECUTED":
        events.append((t, f"NODE     {r.get('previous_node')} -> {r.get('current_node')}  (way out: {r.get('chosen_path')})"))
    elif ty in ("USER_STARTED_SPEAKING", "USER_STOPPED_SPEAKING", "BOT_STARTED_SPEAKING", "BOT_STOPPED_SPEAKING"):
        events.append((t, "  " + ty.lower().replace("_", " ")))
    elif ty == "TOOL_CALL_EVENT":
        events.append((t, f"TOOL     {r.get('tool_name')} {json.dumps(r.get('tool_input'))[:200]} -> {str(r.get('tool_response'))[:200]}"))
    elif ty == "text" and (r.get("text") or "").strip():
        events.append((t, ("CALLER   " if r.get("sender") == "user" else "AGENT    ") + " ".join(r["text"].split())))
    elif ty == "text" and (r.get("node_config") or {}).get("variables"):
        events.append((t, "saved    " + json.dumps(r["node_config"]["variables"])[:200]))
if "--no-engine" not in sys.argv:
    out = subprocess.run(["docker", "logs", "v210-agent-runner"], capture_output=True, text=True)
    keep = re.compile(r"system_one|Jev did not lead|Tool call tool=|handoff|Handoff|fixed answer|collect_|ERROR|Traceback|exception", re.I)
    for line in (out.stdout + out.stderr).splitlines():
        if run in line and line.startswith("{"):
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            message = doc.get("message", "")
            if keep.search(message) and not message.startswith(("Agent system prompt", "LLM HTTP timing", "created citadel log")):
                events.append((at(doc["timestamp"].replace("+00:00", "")), "    engine: " + " ".join(message.split())[:520]))
events.sort(key=lambda item: item[0])
start = events[0][0] if events else 0
for t, text in events:
    print(f"{t - start:6.1f} {text}")
