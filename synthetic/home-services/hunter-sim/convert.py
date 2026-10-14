#!/usr/bin/env python3
"""Turn the V2.9 example Hunter scenarios into sim workspaces, one per scenario (adapted from Sigma/hunter-sim).

    python3 V29-Hunter-Example/hunter-sim/convert.py <worktree> [--only <slug-substring>]

Writes <worktree>/eval_tests/v29ex_hunter/<slug>/{flow.json,params.yaml,scenarios/<slug>.yaml,hunter.json}.
The flow is the scenario's own payload.agentConfig (the builder paste); the sim resolves {{Node Name.x}} refs
by node name, so nothing is pre-rendered. Every run enters at Caller Check: the screening step is Hunter's,
and one CX span walks all three V2.9 nodes, so upstream values are real collections, never seeds.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
SRC = HERE.parent / "hunter" / "scenarios"
FLOW = json.loads((HERE.parent / "v29-hunter-example-flow.json").read_text())
ENTRY = next(n["id"] for n in FLOW["nodes"] if n["data"]["config"]["name"] == "Caller Check")
TIMEZONE = "Asia/Kolkata"
TARGET = re.compile(r"(TARGET is achieved.*)", re.S)


def params_for(payload: dict) -> dict:
    variables = payload.get("initiationVariables") or {}
    body = json.loads(payload["initiationRequest"]["bodyTemplate"])
    out = {}
    for key, value in body.items():
        ref = value.strip("{}").strip() if isinstance(value, str) and value.startswith("{{") else None
        out[key] = "+15550100" if ref == "INBOUND_NUMBER" else str(variables.get(ref, "") if ref else value)
    return out


def flow_for(payload: dict) -> dict:
    flow = json.loads(json.dumps(payload["agentConfig"]))
    flow.setdefault("agent_settings", {}).setdefault("schedule", {})["timezone"] = TIMEZONE  # the sim clock is UTC otherwise
    return flow


def scenario_for(slug: str, doc: dict) -> dict:
    prompt = doc["payload"]["conversationPrompt"].strip()
    match = TARGET.search(prompt)
    return {
        "name": slug,
        "description": doc["name"],
        "initial_variables": {"http": {"params": params_for(doc["payload"])}},
        "simulated_user": {
            "persona": prompt[: match.start()].strip() if match else prompt,
            "goal": (match.group(1).strip() if match else "Stay on the call until the agent ends it.")
            + " The screening step already confirmed who you are and that now is a good time.",
            "opening": "Yes, go ahead.",
            "max_turns": 60,
        },
        "expect": {"ended": True},
    }


def main() -> None:
    worktree = Path(sys.argv[1])
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    root = worktree / "eval_tests" / "v29ex_hunter"
    made = []
    for path in sorted(SRC.glob("*.json")):
        slug = path.stem.replace("-", "_")
        if only and not any(o in slug for o in only.split(",")):
            continue
        doc = json.loads(path.read_text())
        ws = root / slug
        (ws / "scenarios").mkdir(parents=True, exist_ok=True)
        (ws / "reports").mkdir(exist_ok=True)
        (ws / "flow.json").write_text(json.dumps(flow_for(doc["payload"]), indent=1))
        (ws / "params.yaml").write_text(yaml.safe_dump({"params": params_for(doc["payload"]), "substitutions": {}}, sort_keys=False))
        (ws / "scenarios" / f"{slug}.yaml").write_text(
            yaml.safe_dump(scenario_for(slug, doc), sort_keys=False, allow_unicode=True, width=1000))
        (ws / "hunter.json").write_text(json.dumps({
            "name": doc["name"], "entry_node": ENTRY, "timezone": TIMEZONE,
            "evaluationPrompt": doc["payload"]["evaluationPrompt"], "expected": doc.get("_expected_variables"),
            "built_ist": doc.get("_built_ist"), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }, indent=1))
        made.append(slug)
    print(f"{len(made)} workspaces under {root}; entry node {ENTRY}")
    for slug in made:
        print("  ", slug)


if __name__ == "__main__":
    main()
