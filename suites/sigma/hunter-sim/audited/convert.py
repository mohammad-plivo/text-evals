"""Create isolated simulator workspaces from Hunter scenario snapshots."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import yaml

TARGET = re.compile(r"(TARGET is achieved[^\n]*)", re.S)
EXTERNAL_REF = re.compile(r"\{\{([0-9a-f-]+)\.http\.params\.([A-Za-z0-9_]+)\}\}")
REQUEST_REF = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def slug(name: str) -> str:
    value = re.sub(r"^sigma v2\.9\s*-\s*", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:70]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def start_nodes(flow: dict) -> list[dict]:
    return [node for node in flow.get("nodes", []) if node.get("type") == "start"]


def runtime_string(value) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def request_params(payload: dict, inbound_number: str) -> dict[str, str]:
    variables = dict(payload.get("initiationVariables") or {})
    variables["INBOUND_NUMBER"] = inbound_number
    template = json.loads(payload["initiationRequest"]["bodyTemplate"])
    if not isinstance(template, dict):
        raise ValueError("initiation request bodyTemplate must be a JSON object")
    rendered = {}
    for key, value in template.items():
        if not isinstance(value, str):
            rendered[key] = runtime_string(value)
            continue
        exact = REQUEST_REF.fullmatch(value)
        if exact:
            name = exact.group(1)
            if name not in variables:
                raise ValueError(f"initiation request variable is undefined: {name}")
            rendered[key] = runtime_string(variables[name])
            continue
        def replace(match):
            name = match.group(1)
            if name not in variables:
                raise ValueError(f"initiation request variable is undefined: {name}")
            return runtime_string(variables[name])
        rendered[key] = REQUEST_REF.sub(replace, value)
    return rendered


def build_bindings(payload: dict, flow: dict, inbound_number: str) -> tuple[dict, dict]:
    """Bind only UUID Start references, retaining empty authored values."""
    starts = start_nodes(flow)
    if not starts:
        raise ValueError("agentConfig has no Start node")
    start_ids = {node["id"] for node in starts}
    defined = request_params(payload, inbound_number)
    refs = set(EXTERNAL_REF.findall(json.dumps(flow)))
    start_refs = {(node_id, key) for node_id, key in refs if node_id in start_ids}
    missing = sorted({key for _, key in start_refs if key not in defined})
    if missing:
        raise ValueError(f"required external Start parameters are undefined: {missing}")
    substitutions = {
        "{{" + node_id + ".http.params." + key + "}}": str(defined[key])
        for node_id, key in sorted(start_refs)
    }
    return defined, substitutions


def select_entry(name: str, flow: dict) -> dict:
    """Snapshot the existing entry policy and the concrete matching node."""
    wanted = "contact_screening" if ("screening -" in name.lower() or "wrong person guard" in name.lower()) else "ai_agent_v29"
    matches = [node for node in flow.get("nodes", []) if node.get("type") == wanted]
    if len(matches) != 1:
        raise ValueError(f"entry policy expected exactly one {wanted} node, found {len(matches)}")
    return {"node_id": matches[0]["id"], "node_type": wanted, "policy": "legacy_name_policy_v1"}


def scenario_for(name: str, payload: dict) -> dict:
    prompt = payload["conversationPrompt"].strip()
    match = TARGET.search(prompt)
    goal = match.group(1).strip() if match else "Take part in the screening call as this person would until it ends."
    persona = prompt[:match.start()].strip() if match else prompt
    return {
        "name": slug(name), "description": name,
        "simulated_user": {
            "persona": persona,
            "goal": goal + " You are the CALLED party: you answered your own phone. Never hang up before the agent ends the call.",
            "opening": "Hello?" if select_entry(name, payload["agentConfig"])["node_type"] == "contact_screening" else "Yes, go ahead.",
            "max_turns": min(int(payload.get("maxTurns") or 40), 60),
        },
        "expect": {"ended": True},
    }


def convert_one(source: Path, output_root: Path, inbound_number: str) -> Path:
    raw = source.read_bytes()
    document = json.loads(raw)
    payload = document["payload"]
    if payload.get("testType") != "outbound-agent":
        raise ValueError(f"{source}: unsupported testType")
    flow = payload["agentConfig"]
    params, substitutions = build_bindings(payload, flow, inbound_number)
    entry = select_entry(document["name"], flow)
    workspace = output_root / slug(document["name"])
    if workspace.exists():
        raise FileExistsError(f"refusing to overwrite existing workspace: {workspace}")
    (workspace / "scenarios").mkdir(parents=True)
    (workspace / "reports").mkdir()
    flow_bytes = (json.dumps(flow, indent=2, ensure_ascii=False) + "\n").encode()
    (workspace / "flow.json").write_bytes(flow_bytes)
    (workspace / "params.yaml").write_text(yaml.safe_dump({"params": params, "substitutions": substitutions}, sort_keys=False, allow_unicode=True))
    scenario = scenario_for(document["name"], payload)
    (workspace / "scenarios" / f"{slug(document['name'])}.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=1000))
    metadata = {
        "id": document.get("id"), "name": document["name"], "entry": entry,
        "evaluationPrompt": payload["evaluationPrompt"],
        "evaluationThreshold": payload.get("evaluationThreshold", 0.8),
        "source": source.name, "source_sha256": sha256_bytes(raw),
        "flow_sha256": sha256_bytes(flow_bytes),
    }
    (workspace / "hunter.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--inbound-number", required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output must be a new path; historical workspaces are never overwritten")
    args.output.mkdir(parents=True)
    made = [convert_one(path, args.output, args.inbound_number) for path in sorted(args.source.glob("*.json"))]
    artifact_hashes = {}
    for workspace in made:
        artifact_hashes[workspace.name] = {
            name: sha256_bytes((workspace / name).read_bytes())
            for name in ("flow.json", "params.yaml", "hunter.json")
        }
        scenario_path = next((workspace / "scenarios").glob("*.yaml"))
        artifact_hashes[workspace.name]["scenario.yaml"] = sha256_bytes(scenario_path.read_bytes())
    manifest = {
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "converter_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "workspaces": [str(path.resolve()) for path in made],
        "artifact_sha256": artifact_hashes,
        "execution_ready": False,
    }
    (args.output / "conversion-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"created {len(made)} isolated workspaces under {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
