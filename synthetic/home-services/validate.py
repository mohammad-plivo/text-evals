#!/usr/bin/env python3
"""Validate the example flow against the wiring rules and the prod runtime's own collection resolver.

    PYTHONPATH=repos/agent-runner-main repos/agent-runner/.venv/bin/python V29-Hunter-Example/validate.py
Exit 1 on any problem.
"""
import json
import re
import sys
from pathlib import Path

from src.units.collection_configuration import ConfigurationError, _parse_and_resolve

FLOW = Path(__file__).parent / "v29-hunter-example-flow.json"
TYPES = {"text", "name", "email", "phone", "choice", "date", "currency", "boolean", "address", "number", "dob", "dtmf"}
SCREEN_PORTS = {"reached", "no_answer", "busy_rejected", "failed", "callback", "wrong_contact", "unavailable",
                "declined", "do_not_call", "Voicemail Detected"}


def main() -> int:
    flow = json.loads(FLOW.read_text())
    nodes, edges = flow["nodes"], flow["edges"]
    ids = {n["id"]: n for n in nodes}
    names = {n["data"]["config"]["name"]: n for n in nodes}
    problems: list[str] = []

    if len(ids) != len(nodes) or len(names) != len(nodes):
        problems.append("duplicate node id or name")
    for e in edges:
        if e["source"] not in ids or e["target"] not in ids:
            problems.append(f"dangling edge {e['id']}")
            continue
        src = ids[e["source"]]
        if src["type"] == "ai_agent_v29":
            if e["sourceHandle"] not in {i["id"] for i in src["data"]["config"]["intents"]}:
                problems.append(f"edge {e['id']}: handle is not an intent id of {src['data']['config']['name']}")
        elif src["type"] == "outbound_screening" and e["sourceHandle"] not in SCREEN_PORTS:
            problems.append(f"edge {e['id']}: unknown screening port {e['sourceHandle']!r}")
    for n in nodes:
        cfg = n["data"]["config"]
        if n["type"] == "ai_agent_v29":
            wired = {e["sourceHandle"] for e in edges if e["source"] == n["id"]}
            for i in cfg["intents"]:
                if i["id"] not in wired:
                    problems.append(f"{cfg['name']}: intent {i['intent_name']!r} has no edge")
        if n["type"] == "outbound_screening":
            missing = SCREEN_PORTS - {e["sourceHandle"] for e in edges if e["source"] == n["id"]}
            if missing:
                problems.append(f"screening ports not wired: {sorted(missing)}")

    # every {{Node.path}} reference resolves to a node and, for an AI node, to one of its Inputs
    params = set(names["Start"]["data"]["config"]["payload_format"])
    for ref in sorted(set(re.findall(r"\{\{([^}]+)\}\}", json.dumps([n["data"]["config"] for n in nodes], ensure_ascii=False)))):
        node, _, path = ref.partition(".")
        if node == "Start":
            if path.startswith("http.params.") and path.split(".", 2)[2] not in params:
                problems.append(f"ref {{{{{ref}}}}}: no such Start param")
        elif node not in names:
            problems.append(f"ref {{{{{ref}}}}}: no such node")
        elif names[node]["type"] == "ai_agent_v29":
            if path not in {v["variable_name"] for v in names[node]["data"]["config"]["extract_variables"]}:
                problems.append(f"ref {{{{{ref}}}}}: {node} has no Input {path!r}")

    # every Input resolves under the prod runtime's resolver; the main node covers all twelve types
    for n in nodes:
        if n["type"] != "ai_agent_v29":
            continue
        cfg = n["data"]["config"]
        for v in cfg["extract_variables"]:
            r = _parse_and_resolve(v["variable_name"], v["collection"], v["variable_instructions"], cfg["instructions"])
            if isinstance(r, ConfigurationError):
                problems.append(f"{cfg['name']}.{v['variable_name']}: runtime rejects the configuration: {r.reason}")
    main_types = {v["collection"]["type"] for v in names["Service Request"]["data"]["config"]["extract_variables"]}
    if main_types != TYPES:
        problems.append(f"Service Request types: missing {sorted(TYPES - main_types)}, extra {sorted(main_types - TYPES)}")

    n_inputs = sum(len(n["data"]["config"].get("extract_variables") or []) for n in nodes if n["type"] == "ai_agent_v29")
    print(f"{len(nodes)} nodes, {len(edges)} edges, {n_inputs} Inputs; Service Request types: {len(main_types)}/12")
    for p in problems:
        print("PROBLEM", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
