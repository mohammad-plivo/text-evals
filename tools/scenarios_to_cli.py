"""Convert the console's generated simulation scenarios into simulation-CLI YAML.

The console stores a scenario as {goal, persona{}, world_state{node:{action_mocks}},
interruption, stt_noise, non_answer, eval_metadata{expected_route_outcome}}. The CLI
wants {simulated_user{persona,goal,...}, action_mocks{}, expect{}}.

Two console features have no CLI field and are folded into the persona text instead,
which is the only channel that reaches the simulated caller:
  - stt_noise   -> instructions to mis-render words the way STT does
  - non_answer  -> instructions to dodge a question some of the time
"""
import json
import pathlib
import re
import sys

import yaml

TERMINAL_TYPES = {"end_conversation", "call_forward"}

# What "the caller was mis-transcribed" looks like when the only input channel is text.
STT_NOISE = {
    "light": "Occasionally (about 1 turn in 5) a word comes out slightly wrong, as speech-to-text would garble it — a name letter swapped, a digit misheard. Do not correct yourself unless the agent asks.",
    "medium": "Your speech is being transcribed imperfectly. Roughly 1 turn in 3, render a word the way STT would mangle it: run syllables together ('see pap' for CPAP), double a letter in your name, blur a date ('the twelf of March'). Do not correct yourself unless the agent asks.",
    "heavy": "Your speech is badly transcribed. In most turns at least one word is wrong — names, dates and numbers especially ('Ramesh Kumaar', 'nineteen sixty seven' as 'nineteen sixty seventh'). Do not correct yourself unless the agent asks you to repeat.",
}


def slug(name, i):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"{i:03d}-{s or 'scenario'}"[:60]


def persona_text(sc):
    p = sc.get("persona") or {}
    details = p.get("details") or {}
    bits = []
    if p.get("personality"):
        bits.append(f"{p['personality'].capitalize()} caller.")
    if p.get("emotional_state"):
        bits.append(f"Emotional state: {p['emotional_state']}.")
    traits = p.get("behavioral_traits") or []
    if traits:
        bits.append("Traits: " + ", ".join(traits) + ".")
    if details:
        known = ", ".join(f"{k}={v}" for k, v in details.items() if v)
        if known:
            bits.append(f"Your details: {known}. Give these when asked, not before.")
    lang = (sc.get("language") or "").strip()
    if lang and lang.lower() != "english":
        bits.append(f"Speak {lang}.")

    noise = sc.get("stt_noise") or {}
    if noise.get("enabled"):
        bits.append(STT_NOISE.get(noise.get("severity", "light"), STT_NOISE["light"]))

    na = sc.get("non_answer") or {}
    if na.get("enabled") and na.get("probability"):
        pct = int(float(na["probability"]) * 100)
        bits.append(
            f"About {pct}% of the time, do not answer the question you were asked — "
            "reply with something adjacent, a question back, or a half-answer."
        )
    return " ".join(bits)


def flatten_mocks(sc):
    """world_state is keyed by node uuid; the CLI keys action_mocks by tool name."""
    out = {}
    for node_state in (sc.get("world_state") or {}).values():
        out.update((node_state or {}).get("action_mocks") or {})
    return out


def expectation(sc, known_nodes=None, entry_node=None):
    """Turn the console's ONE-HOP outcome into a CLI expectation.

    `expected_route_outcome` describes a single edge (source -> target), NOT how the
    call ends. Asserting it as the final intent is only correct when the source is
    the node that makes the LAST decision. When the source is the entry node, the hop
    is the front desk's routing choice and the call carries on past it — asserting it
    as the final intent fails every correctly-routed call. What that hop means is
    "the walk reached this collector", which is what `node` checks.
    """
    ero = (sc.get("eval_metadata") or {}).get("expected_route_outcome") or {}
    exp = {}
    src, tgt = ero.get("source_node_id"), ero.get("target_node_id")

    # No target at all: empty node id and name, type "ai_agent_v2", intent "call"
    # (the Start node's port leaking in). Unusable.
    if not tgt:
        return exp
    # Source is a node that is not in the flow — a stale id from an older version.
    # Nothing about this expectation can be trusted against the current graph.
    if known_nodes and src not in known_nodes:
        return exp

    if entry_node and src == entry_node:
        # Front-desk routing hop. `node` tracks the active AI node only, so it can
        # never equal a terminal's name — asserting node="Emergency"/"Staff"/"Close"
        # fails on every run no matter what the flow does (20 such failures).
        # A hop into a terminal is really "the front desk exited this way", which
        # is exactly what intent + ended check.
        if ero.get("target_node_type") in TERMINAL_TYPES:
            exp["ended"] = True
            if ero.get("expected_intent_name"):
                exp["intent"] = ero["expected_intent_name"]
        elif ero.get("target_node_name"):
            exp["node"] = ero["target_node_name"]
        return exp

    # A decision made by a collector: this really is how the walk exits.
    # `ended` first — a bare intent assertion passes vacuously on a walk that never exits.
    if ero.get("target_node_type") in TERMINAL_TYPES:
        exp["ended"] = True
    if ero.get("expected_intent_name"):
        exp["intent"] = ero["expected_intent_name"]
    return exp


def convert(sc, i, max_turns, known_nodes=None, entry_node=None):
    return slug(sc.get("name"), i), {
        "description": (sc.get("name") or "").strip(),
        "simulated_user": {
            "persona": persona_text(sc),
            "goal": sc.get("goal") or "",
            "max_turns": max_turns,
            "interruption_probability": float((sc.get("interruption") or {}).get("probability") or 0)
            if (sc.get("interruption") or {}).get("enabled")
            else 0.0,
        },
        "action_mocks": flatten_mocks(sc),
        "expect": expectation(sc, known_nodes, entry_node),
    }


def main(src, outdir, max_turns=25, known_nodes=None, entry_node=None):
    scenarios = json.load(open(src))["scenarios"]
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written, orphaned = 0, []
    for i, sc in enumerate(scenarios, 1):
        if known_nodes:
            unknown = [n for n in (sc.get("world_state") or {}) if n not in known_nodes]
            if unknown:
                orphaned.append((sc.get("name"), unknown[0][:8]))
        name, body = convert(sc, i, max_turns, known_nodes, entry_node)
        (out / f"{name}.yaml").write_text(yaml.safe_dump(body, sort_keys=False, width=100))
        written += 1
    print(f"wrote {written} scenarios -> {out}")
    if orphaned:
        print(f"WARNING: {len(orphaned)} scenarios mock a node that is not in the flow:")
        for n, u in orphaned[:5]:
            print(f"    {u}...  {n}")
    return written


if __name__ == "__main__":
    flow = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else None
    known = {n["id"] for n in flow["nodes"]} if flow else None
    entry = None
    if flow:
        entry = next((n["id"] for n in flow["nodes"] if n["type"] == "ai_agent_v2"), None)
    main(sys.argv[1], sys.argv[2], known_nodes=known, entry_node=entry)
