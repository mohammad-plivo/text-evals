"""Convert the console's internal phlo shape (/contacto-config/phlo/<id>) into the
console EXPORT shape that `simulation.cli init --flow` consumes.

Needed because the builder's Download button serialises the browser's in-memory
React-Flow store, which no API returns. The two shapes differ in exactly three
places: node config is a list of field descriptors rather than a merged dict,
edges are "<node>.<port>" strings, and the flow-level fields live in global_meta.
"""
import json
import sys


def _merge_model(model):
    """config.model is a list of form-field descriptors; the export merges their
    `data` payloads into one dict."""
    out = {}
    for item in model or []:
        if isinstance(item, dict):
            out.update(item.get("data") or {})
    return out


def convert(internal):
    phlo = internal.get("phlo") or {}
    meta = internal.get("global_meta") or {}

    nodes = [
        {
            "id": n["id"],
            "type": n["type"],
            "data": {"config": _merge_model((n.get("config") or {}).get("model"))},
        }
        for n in internal.get("nodes") or []
    ]

    # A connection's source port is the intent NAME, but the export — and the CLI's
    # _derive_plan — key edges by the intent ID. Without this remap every intent
    # logs "has no outgoing edge" and the walk dies at the first handoff.
    intent_id_by_name = {
        n["id"]: {
            i.get("intent_name"): i.get("id")
            for i in (n["data"]["config"].get("intents") or [])
        }
        for n in nodes
    }

    edges = []
    for c in internal.get("connections") or []:
        src, _, port = str(c.get("source", "")).partition(".")
        tgt = str(c.get("target", "")).partition(".")[0]
        handle = intent_id_by_name.get(src, {}).get(port, port)
        edges.append(
            {
                "id": (c.get("data") or {}).get("id") or f"{src}->{tgt}:{handle}",
                "source": src,
                "target": tgt,
                "sourceHandle": handle,
                "data": {},
            }
        )

    return {
        "name": phlo.get("name"),
        "flowId": phlo.get("id"),
        "nodes": nodes,
        "edges": edges,
        "systemPrompt": meta.get("system_prompt"),
        "sttGuidance": meta.get("stt_guidance"),
        "agentName": meta.get("agent_name"),
        "agentPersona": meta.get("agent_persona"),
        "conversationGoals": phlo.get("conversation_goals"),
        "agentSettings": {
            "voice_ai_config": phlo.get("voice_ai_config") or {},
            "schedule": phlo.get("schedule") or {},
        },
    }


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as f:
        out = convert(json.load(f))
    with open(dst, "w") as f:
        json.dump(out, f, indent=2)
    print(f"{dst}: {len(out['nodes'])} nodes, {len(out['edges'])} edges")
