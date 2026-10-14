"""Turn the 38 Hunter Sigma scenarios into sim workspaces: one per scenario, because the Start
params live in the workspace's params.yaml and every scenario carries its own initiationVariables.

The frozen source for a workspace is that scenario's own payload.agentConfig, which is the flow
Hunter would run. Only the transforms in TRANSFORMS may stand between it and the executed flow.

Usage: uv run --frozen python Sigma/hunter-sim/convert.py <worktree> [<hunter scenarios dir>] [--timezone Asia/Kolkata]
Writes eval_tests/sigma_v29_hunter/<slug>/{flow.json,params.yaml,scenarios/<slug>.yaml,hunter.json}
"""
import copy, hashlib, json, os, re, sys, yaml

WT = sys.argv[1] if len(sys.argv) > 1 else ""  # importable for the offline checks
SRC = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/Sigma/hunter/scenarios"
# the Sigma node text and its calling window are Asia/Kolkata; the export carries no timezone
TIMEZONE = sys.argv[sys.argv.index("--timezone") + 1] if "--timezone" in sys.argv else "Asia/Kolkata"
ROOT = os.path.join(WT, "eval_tests", "sigma_v29_hunter")
TARGET = re.compile(r"(TARGET is achieved[^\n]*)", re.S)


def slug(name: str) -> str:
    s = re.sub(r"^sigma v2\.9\s*-\s*", "", name.strip(), flags=re.I)
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:70]


def params_for(payload: dict) -> dict:
    iv = payload.get("initiationVariables") or {}
    body = json.loads(payload["initiationRequest"]["bodyTemplate"])
    out = {}
    for key, value in body.items():
        if isinstance(value, str) and value.startswith("{{"):
            ref = value.strip("{}").strip()
            value = "+15550100" if ref == "INBOUND_NUMBER" else iv.get(ref, "")
        out[key] = "" if value is None else str(value)
    return out


SCREENING_NODE = "c2e8bf31-06ec-42db-8a60-a72874b1ceb5"
V29_NODE = "f66906be-0fc9-43e5-bcf7-20117357082c"


def entry_node_for(name: str) -> str:
    """Scenarios that test the screening node enter there; every other one enters at the V2.9 node."""
    low = name.lower()
    return SCREENING_NODE if ("screening -" in low or "wrong person guard" in low) else V29_NODE


PLACEHOLDER = re.compile(r"{{\s*[0-9a-f-]{36}\.http\.params\.([A-Za-z0-9_]+)\s*}}")


def render_flow(flow, params: dict):
    """Pre-render every Start-param placeholder in the flow's text fields: the sim substitutes the
    node instructions but not the screening node's own greeting fields, which then get spoken raw."""
    if isinstance(flow, dict):
        return {k: render_flow(v, params) for k, v in flow.items()}
    if isinstance(flow, list):
        return [render_flow(v, params) for v in flow]
    if isinstance(flow, str):
        return PLACEHOLDER.sub(lambda m: params.get(m.group(1), m.group(0)), flow)
    return flow


def bind_intent_edges(flow: dict, repairs=None) -> dict:
    """H-2: rekey an AI node's outgoing edges by intent id, which is what the sim resolves an outcome to.

    A console export writes the intent NAME as sourceHandle; the sim maps the fired outcome to the
    intent's id and, without a fallback, finds no edge, so the run stops at the node exit with
    no_matching_handoff (simulation/runner.py:506-514) and the end node never speaks. graph.py
    resolve_handle (4fbc8a93) now takes whichever of the id or the name the flow authored, so this is
    not used by the canonical pipeline: rekeying would hide which shape Hunter really ships.
    """
    by_name = {}
    for node in flow.get("nodes") or []:
        config = ((node.get("data") or {}).get("config")) or {}
        names = {i["intent_name"]: i["id"] for i in (config.get("intents") or []) if i.get("intent_name") and i.get("id")}
        if names:
            by_name[node["id"]] = names
    rekeyed = []
    for edge in flow.get("edges") or []:
        names = by_name.get(edge.get("source")) or {}
        if edge.get("sourceHandle") in names:
            rekeyed.append(edge["sourceHandle"])
            edge["sourceHandle"] = names[edge["sourceHandle"]]
    if rekeyed and repairs is not None:
        repairs.append(f"rekeyed {len(rekeyed)} AI edges from the intent name to the intent id: {', '.join(rekeyed)}")
    return flow


def set_timezone(flow: dict, timezone: str, repairs=None) -> dict:
    """H-4: the sim's clock is UTC unless the flow carries one, and the calling window is local."""
    for key in ("agentSettings", "agent_settings"):
        if ((flow.get(key) or {}).get("schedule") or {}).get("timezone"):
            return flow
    flow.setdefault("agent_settings", {}).setdefault("schedule", {})["timezone"] = timezone
    if repairs is not None:
        repairs.append(f"set the missing flow timezone to {timezone}")
    return flow


def _asks(var: dict) -> str:
    return (var.get("variable_instructions") or "").strip()


def unshare_copied_questions(flow: dict, repairs=None) -> dict:
    """H-8: an Input copied in the console keeps its twin's collection block, question and all.

    collection_configuration.py:155 prepends that block to the collector's instructions, so the copy
    is handed the twin's question and asks it instead of its own. Drop the block the copy carried
    verbatim; the id and the fingerprint are left alone, no unit reads either one.
    """
    for node in flow.get("nodes") or []:
        config = ((node.get("data") or {}).get("config")) or {}
        groups = {}
        # ponytail: a console copy shares both the id and the fingerprint; a half share is not grouped
        for var in config.get("extract_variables") or []:
            groups.setdefault((var.get("id"), (var.get("collection") or {}).get("fingerprint")), []).append(var)
        for group in groups.values():
            if len(group) < 2:
                continue
            # the Input the shared block belongs to is the one whose own instructions are the block's question
            keeper = next((v for v in group if _asks(v) == ((v.get("collection") or {}).get("instructions") or "").strip()), group[0])
            for var in group:
                collection = var.get("collection") or {}
                if var is keeper or collection != (keeper.get("collection") or {}):
                    continue
                collection["version"] = None  # the twin's version, it only marks this Input stale
                collection["instructions"] = None  # the twin's question is not this Input's question
                if repairs is not None:
                    repairs.append(f"dropped the copied question from the Input {var.get('variable_name')}")
    return flow


#: The only transforms allowed between a scenario's frozen agentConfig and the flow it executes.
#: Each entry is the prefix of the repair line the transform records in hunter.json. preflight.py
#: fails the board on any repair that is not one of these, and on any difference these do not explain.
TRANSFORMS = ("set the missing flow timezone",
              "dropped the copied question from the Input")


def frozen_source(payload: dict) -> dict:
    """The canonical frozen flow input for one scenario: the agentConfig Hunter itself would run."""
    config = payload.get("agentConfig")
    if not config or not config.get("nodes"):
        raise SystemExit("scenario carries no agentConfig: there is no frozen source to convert")
    return config


def canonical_flow(payload: dict, params: dict, timezone: str, repairs=None) -> dict:
    """The one flow a workspace executes: that scenario's frozen source plus the declared transforms.

    Rendering the Start-param placeholders is the third transform and leaves no repair line: it
    substitutes only what a live Start node would already have substituted.
    """
    flow = copy.deepcopy(frozen_source(payload))
    flow = set_timezone(flow, timezone, repairs)
    flow = unshare_copied_questions(flow, repairs)
    return render_flow(flow, params)


def hunter_metadata(document: dict, payload: dict, source: str, timezone: str, repairs=None) -> dict:
    """What the board and the judge read per scenario: the judge's clock label (H-5) and the repairs
    the converter applied, so a board states which of its numbers were won on a repaired flow."""
    return {"id": document.get("id"), "name": document["name"], "entry_node": entry_node_for(document["name"]),
            "evaluationPrompt": payload["evaluationPrompt"], "evaluationThreshold": payload.get("evaluationThreshold", 0.8),
            "timezone": timezone, "repairs": list(repairs or []), "source": source}


def scenario_for(name: str, payload: dict) -> dict:
    prompt = payload["conversationPrompt"].strip()
    m = TARGET.search(prompt)
    goal = m.group(1).strip() if m else "Take part in the screening call as this person would until it ends."
    persona = prompt[: m.start()].strip() if m else prompt
    return {
        "name": slug(name),
        "description": name,
        # Start params reach a live node through Initial Context, not through the instructions:
        # _all_node_vars flattens this to <node>.http.params.<key>, which is what the prompt reads.
        "initial_variables": {"http": {"params": params_for(payload)}},
        "simulated_user": {
            "persona": persona,
            "goal": goal + " You are the CALLED party: you answered your own phone. Never hang up before the agent ends the call.",
            "opening": "Hello?" if entry_node_for(name) == SCREENING_NODE else "Yes, go ahead.",
            "max_turns": min(int(payload.get("maxTurns") or 40), 60),
        },
        "expect": {"ended": True},
    }


def main() -> None:
    files = sorted(f for f in os.listdir(SRC) if f.endswith(".json"))
    made, seen = [], set()
    for f in files:
        d = json.load(open(os.path.join(SRC, f)))
        name, payload = d["name"], d["payload"]
        if payload.get("testType") != "outbound-agent":
            continue
        s = slug(name)
        ws = os.path.join(ROOT, s)
        os.makedirs(os.path.join(ws, "scenarios"), exist_ok=True)
        os.makedirs(os.path.join(ws, "reports"), exist_ok=True)
        params = params_for(payload)
        repairs = []
        # each workspace is rendered from its OWN scenario's frozen agentConfig, never from a shared
        # copy: a shared copy silently dropped the authored callback calendar off all 38 flows
        json.dump(canonical_flow(payload, params, TIMEZONE, repairs), open(os.path.join(ws, "flow.json"), "w"), indent=1)
        yaml.safe_dump({"params": params, "substitutions": {}}, open(os.path.join(ws, "params.yaml"), "w"), sort_keys=False, allow_unicode=True)
        yaml.safe_dump(scenario_for(name, payload), open(os.path.join(ws, "scenarios", f"{s}.yaml"), "w"), sort_keys=False, allow_unicode=True, width=1000)
        meta = hunter_metadata(d, payload, f, TIMEZONE, repairs)
        meta["source_sha256"] = hashlib.sha256(open(os.path.join(SRC, f), "rb").read()).hexdigest()
        meta["frozen_sha256"] = hashlib.sha256(json.dumps(frozen_source(payload), sort_keys=True).encode()).hexdigest()
        meta["flow_sha256"] = hashlib.sha256(open(os.path.join(ws, "flow.json"), "rb").read()).hexdigest()
        json.dump(meta, open(os.path.join(ws, "hunter.json"), "w"), indent=1)
        seen.update(meta["repairs"])
        made.append(s)
    print(f"{len(made)} workspaces under {ROOT}")
    for r in sorted(seen): print("  repair:", r)
    for s in made: print("  ", s)


if __name__ == "__main__":
    main()
