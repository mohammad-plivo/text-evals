#!/usr/bin/env python3
"""Put the logic flow on the local v210 stack through config-service, stamp it v2.10, publish it and check what was stored.

    python3 stack.py push      # create or update the flow from out/flow.json
    python3 stack.py show      # what the database holds for it

Nothing is clicked in the console and no row is written by hand. cfg_call.py runs inside the v210-config container with
the service's own token, so no secret leaves it. Do not save this flow from the console: it drops the screening exits.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FLOW = json.loads((HERE / "out/flow.json").read_text())
UUID = FLOW["flowId"]


def call(method: str, path: str, kind: str = "console", body: dict | None = None) -> tuple[int, dict]:
    done = subprocess.run(["docker", "exec", "-i", "v210-config", "sh", "-c", f"cd /app && python /tmp/cfg_call.py {method} {path} {kind}"],
                          input=json.dumps(body) if body is not None else None, capture_output=True, text=True, check=True)
    status, _, text = done.stdout.partition("\n")
    return int(status), json.loads(text or "{}")


def sql(query: str) -> str:
    return subprocess.run(["docker", "exec", "v210-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", query],
                          capture_output=True, text=True, check=True).stdout.strip()


def push() -> None:
    subprocess.run(["docker", "cp", str(HERE / "cfg_call.py"), "v210-config:/tmp/cfg_call.py"], check=True)
    settings, start = FLOW["agentSettings"], FLOW["nodes"][0]
    exists = sql(f"select state from phlo where uuid = '{UUID}'")
    if not exists:
        # the canvas endpoint cannot set the voice settings of a new flow, so the flow is first saved as a draft with its Start node
        status, reply = call("POST", f"/v1/config/phlo/{UUID}", body={
            "phlo": {"name": FLOW["name"], "description": "Synthetic test flow: every collector type, actions, hops and handoffs.",
                     "enabled": False, "state": "DRAFT", "changed": True, "redact": False, "phlo_type": "api_request",
                     "voice_ai_config": settings["voice_ai_config"], "schedule": settings["schedule"]},
            "nodes": [{"id": start["id"], "name": "Start", "type": "start", "top": 0, "left": 0, "changed": True, "description": "",
                       "config": {"model": {key: value for key, value in start["data"]["config"].items() if key not in ("name", "description")}}}],
            "connections": [], "notes": {"notes": []},
            "global_meta": {"system_prompt": None, "stt_guidance": None, "agent_name": None, "agent_persona": None, "livekit_ready": True},
            "is_playground": False, "editor_metadata": {"last_editor_type": "user"}})
        print("draft:", status, json.dumps(reply.get("validation_errors"))[:300])
        assert status in (200, 201), reply
    status, reply = call("POST", f"/v1/config/phlo/{UUID}/canvas", body={
        "flow_name": FLOW["name"], "workflow": {"nodes": FLOW["nodes"], "edges": FLOW["edges"]}, "global_meta": {"livekit_ready": True}})
    print("canvas:", status, json.dumps(reply.get("validation_errors") or reply)[:900])
    assert status in (200, 201), reply
    status, reply = call("POST", "/v1/internal/phlo/engine-version", "admin", {"phlo_uuids": [UUID], "engine_version": "v2.10"})
    print("stamp:", status, json.dumps(reply)[:200])
    if exists != "ACTIVE":
        status, reply = call("GET", f"/v1/config/phlo/{UUID}/publish_phlo")
        print("publish:", status, json.dumps(reply)[:200])
    show()


def show() -> None:
    row = sql(f"select id || '|' || state || '|' || enabled || '|' || coalesce(attributes::text, '') || '|' || active_version_id from phlo where uuid = '{UUID}'")
    print("flow row (id|state|enabled|attributes|version):", row)
    flow_id, version = row.split("|")[0], row.split("|")[-1]
    print("version:", sql(f"select 'edges ' || jsonb_array_length(connections::jsonb) || ', global_meta ' || global_meta::text || ', errors ' || coalesce(validation_errors::text, 'none') from phlo_connections where id = {version}"))
    print(sql(f"""select c.type || ' | ' || n.name || ' | inputs ' || coalesce(jsonb_array_length(n.config::jsonb->'model'->'extract_variables'), 0)
                  || ' | exits ' || coalesce(jsonb_array_length(n.config::jsonb->'model'->'intents'), 0)
                  || ' | actions ' || coalesce(jsonb_array_length(n.config::jsonb->'model'->'actions'), 0)
                  || ' | refs ' || coalesce((n.config::jsonb->'template_vars')::text, '-')
                  from node n join component c on c.id = n.component_id where n.phlo_id = {flow_id} and not n.deleted
                  and (c.type <> 'end_conversation' or n.config::jsonb->'template_vars' <> '{{}}'::jsonb) order by n.id"""))
    print("screening:", sql(f"""select (n.config::jsonb->'model'->'screening_task')::text || ' | exits ' || (n.config::jsonb->'model'->'intents')::text
                               from node n join component c on c.id = n.component_id where n.phlo_id = {flow_id} and c.type = 'contact_screening'""")[:700])


if __name__ == "__main__":
    {"push": push, "show": show}[sys.argv[1]]()
