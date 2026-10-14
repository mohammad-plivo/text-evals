"""Build sim-fh/flow.json (console download format) from the DB truth of dev flow ed2c0c6c.

Recipe: General Instructions/flow-paste-builder.md. Run: .venv/bin/python build_flow.py (any cwd).
Type strings: start / end_conversation / call_forward / initiate_call from eval_tests/*/flow.json,
contact_screening from tests/fixtures/flows/initiate_screening_ai.json, the merged composite
outbound_screening from src/simulation/flow/graph.py:29 and FHCSD/flows/fhcsd-v29-agent-config.json.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner"
REPO = os.path.join(ROOT, "repos", "agent-runner-choice-offlist")
DB = os.environ.get("FH_NODE_DB") or "/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/e4e421e8-e52c-4582-8600-df886be5a50d/scratchpad/fh-node-db"
DOWNLOAD = os.path.join(ROOT, "FHCSD", "flows", "fhcsd-v29-agent-config.json")
OUT = os.path.join(HERE, "ws", "flow.json")
FLOW_ID = os.environ.get("FH_FLOW_ID") or "ed2c0c6c-955a-448a-b0e7-db60b8782271"
START = os.environ.get("FH_START") or "7650cec0-f0ec-4167-82bd-13ab0eaa1fb3"
AI_NODE = os.environ.get("FH_AI_NODE") or "ee727068-51d5-4019-92d7-56f1324c2914"

TYPES = {
    "Start": "start", "Initiate Call": "initiate_call", "Contact Screening": "contact_screening",
    "AI conversation v2.9": "ai_agent_v29", "End Conversation": "end_conversation", "Call Forward": "call_forward", "Route Call": "call_forward",
}
COMPOSITE_KEYS = ["ask_permission", "context", "description", "events", "from", "initial_wait_time",
                  "is_validate_caller_id", "max_call_duration", "name", "ring_timeout", "to"]
EXTRAS = ["systemPrompt", "sttGuidance", "agentName", "agentPersona", "conversationGoals", "agentSettings"]
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def load():
    names, types = {}, {}
    for line in open(os.path.join(DB, "names.txt")):
        uuid, name, component = line.rstrip("\n").split("|")
        names[uuid], types[uuid] = name, TYPES[component]
    global START, AI_NODE
    if os.environ.get("FH_NODE_DB") and not os.environ.get("FH_START"):
        START = next(u for u, t in types.items() if t == "start")
    if os.environ.get("FH_NODE_DB") and not os.environ.get("FH_AI_NODE"):
        AI_NODE = next(u for u, t in types.items() if t == "ai_agent_v29")
    conns = json.load(open(os.path.join(DB, "connections.json")))
    rows = {u: json.load(open(os.path.join(DB, u + ".json")))["model"] for u in names}
    return names, types, conns, rows


def reachable(conns):
    seen, queue = {START}, [START]
    while queue:
        cur = queue.pop()
        for c in conns:
            src, dst = c["source"].split(".", 1)[0], c["target"].split(".", 1)[0]
            if src == cur and dst not in seen:
                seen.add(dst)
                queue.append(dst)
    return seen


def rewrite_refs(config, names):
    text = re.sub(r"\{\{(" + UUID + r")\.", lambda m: "{{" + names[m.group(1)] + ".", json.dumps(config))
    return json.loads(text)


def build():
    names, types, conns, rows = load()
    live = reachable(conns)
    live_conns = [c for c in conns if c["source"].split(".", 1)[0] in live]
    internal = [c for c in live_conns if c["source"].endswith(".answered")
                and types[c["target"].split(".", 1)[0]] == "contact_screening"]
    assert len(internal) == 1, f"expected one dial->screening answered edge, got {len(internal)}"
    dial, unit = internal[0]["source"].split(".", 1)[0], internal[0]["target"].split(".", 1)[0]
    alias = {unit: dial}
    download = json.load(open(DOWNLOAD))
    meta = {n["type"]: n["data"]["meta"] for n in download["nodes"]}

    nodes = []
    for uuid in sorted(live - {unit}, key=lambda u: names[u]):
        model, t = dict(rows[uuid]), types[uuid]
        if t == "initiate_call":
            merged = {**model, **rows[unit], "name": names[unit]}
            if not any((e or {}).get("url") for e in (merged.get("events") or {}).values()):
                merged["events"] = []
            merged["max_call_duration"] = min(int(merged.get("max_call_duration") or 14400), 14400)
            model, t = {k: merged[k] for k in COMPOSITE_KEYS}, "outbound_screening"
        elif t == "start":
            model.setdefault("events", [])
        elif t == "ai_agent_v29":
            model.setdefault("instruction_attachments", [])
        elif t == "end_conversation":
            model = {k: model.get(k, "") for k in ("name", "description", "end_message")}
        nodes.append({"id": uuid, "type": t, "data": {"meta": meta.get(t, {}), "_meta": None,
                                                       "config": rewrite_refs(model, names)}})

    intent_ids = {i["intent_name"]: i["id"] for i in rows[AI_NODE]["intents"]}
    edges = []
    for c in live_conns:
        if c in internal:
            continue
        src, handle = c["source"].split(".", 1)
        if types[src] == "ai_agent_v29":
            assert handle in intent_ids, f"agent handle {handle!r} has no intent"
            handle = intent_ids[handle]
        dst = c["target"].split(".", 1)[0]
        edges.append({"id": c["data"]["id"], "source": alias.get(src, src), "target": alias.get(dst, dst),
                      "sourceHandle": handle, "data": c["data"]})

    doc = {"name": f"Family Health Agent 2 Outbound (prod {FLOW_ID[:8]} v148674, sim)", "flowId": FLOW_ID, "nodes": nodes, "edges": edges,
           **{k: download.get(k) for k in EXTRAS}}
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    return doc, live, live_conns, internal, names, dial, intent_ids


PARSE_CHECK = """
import json, sys
from src.simulation.flow.graph import build_graph
from src.simulation.cli.flow import load_flow_bundle
doc = json.load(open(sys.argv[1]))
g = build_graph(doc)
ai = [n for n in g.nodes_by_id.values() if n.type == "ai_agent_v29"]
assert ai, "no ai_agent_v29 node after parse"
node = ai[0]
bad = [i["intent_name"] for i in node.config["intents"] if g.edge_target(node.id, g.resolve_handle(node, i["intent_name"])) is None]
assert not bad, f"intents with no edge target: {bad}"
b = load_flow_bundle(sys.argv[1], {})
print(f"graph.py parse OK: {len(g.nodes_by_id)} nodes, {sum(map(len, g.edges_by_source.values()))} edges, "
      f"ai_agent_v29 {node.name!r} with {len(node.config['intents'])} intents all routed; "
      f"CLI loader entry={b.name_of(b.entry_node_id)!r} ({g.nodes_by_id[b.entry_node_id].type}), flow_session={b.flow_session}")
"""


def validate(doc, live, live_conns, internal, names, dial, intent_ids):
    ids = {n["id"] for n in doc["nodes"]}
    print(f"nodes: {len(doc['nodes'])} (DB reachable rows {len(live)} minus 1 merged screening unit)")
    assert len(doc["nodes"]) == len(live) - 1
    print(f"edges: {len(doc['edges'])} (DB live connections {len(live_conns)} minus {len(internal)} internal answered edge)")
    assert len(doc["edges"]) == len(live_conns) - len(internal)
    text = json.dumps(doc, ensure_ascii=False)
    uuid_refs = re.findall(r"\{\{" + UUID, text)
    print(f"uuid template refs left: {len(uuid_refs)}")
    assert not uuid_refs
    allowed = {n["data"]["config"]["name"] for n in doc["nodes"]} | {names[dial]}
    roots = sorted({m.split(".", 1)[0] for m in re.findall(r"\{\{\s*([^}]+?)\s*\}\}", text)})
    dangling = [r for r in roots if r not in allowed]
    print(f"template roots: {roots}; dangling: {dangling}")
    assert not dangling
    loose = [e["id"] for e in doc["edges"] if e["source"] not in ids or e["target"] not in ids]
    print(f"edge endpoints outside node set: {len(loose)}")
    assert not loose
    agent_edges = [e for e in doc["edges"] if e["source"] == AI_NODE]
    unrouted = sorted(set(intent_ids.values()) - {e["sourceHandle"] for e in agent_edges})
    print(f"agent intent handles: {len(agent_edges)} edges, all keyed by intent id; intents without an edge: {unrouted}")
    assert all(e["sourceHandle"] in intent_ids.values() for e in agent_edges) and not unrouted
    for n in doc["nodes"]:
        print(f"  {n['type']:<18} {n['data']['config']['name']}")
    r = subprocess.run([os.path.join(REPO, ".venv", "bin", "python"), "-c", PARSE_CHECK, OUT],
                       cwd=REPO, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-2000:])
    assert r.returncode == 0, "graph.py / CLI loader parse failed"
    print(f"wrote {OUT}")


if __name__ == "__main__":
    validate(*build())
    sys.exit(0)
