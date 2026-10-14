"""Assemble sim-prepared/ws from the shipped v29-agent-node pack plus this campaign's agent node.

    STRESS_REPO=<tree> <tree>/.venv/bin/python build_ws.py [--self-test]

Everything but the ONE ai_agent_v29 node is copied byte-for-byte from the pack, so the http hops,
the call_forward and the end nodes keep their ids and handles and the walk still routes. The node's
Inputs each carry a saved collection configuration, stamped with the runtime's OWN digest
(scripts.stamp_collection_versions) so no field reads stale on every call.

No placeholders in the node's prose on purpose: the CLI substitutes {{Start.*.params.*}} in the raw
flow TEXT before parsing, so a placeholder in the Task would be digested rendered and never match
the authored version stamped here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True  # the tree is read-only for this campaign, caches included

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("STRESS_REPO") or os.path.abspath(os.path.join(HERE, "..", "trees", "cd6ac6c5"))
sys.path.insert(0, REPO)

PACK = os.path.join(REPO, "examples", "simulation", "v29-agent-node")
WS = os.path.join(HERE, "ws")
SCENARIOS = os.path.join(HERE, "scenarios")
NODE_ID = "e03023cc-980f-41ef-8d63-18601740d07b"
MODEL = "gpt-4.1"

TASK = """\
You are Maya from the Ridgeway Clinic scheduling desk, calling a patient who asked to move an \
appointment they already have. Be warm and brief, one question at a time.

Work through the Inputs in the order they are listed, and let each Input's own collector ask its \
question -- you never ask for a value yourself and you never fill one in for the caller. Each Input \
says what the desk needs it for; if the caller asks why, say that reason in your own words. Do what \
each collector's result asks you to do next, then carry on to the next Input.

The record is opened first, from the name it is booked under and the patient's date of birth. Then \
the appointment itself: the day the caller wants and which part of the day suits them. Then what the \
desk needs to hold the slot: the journey time reception allows for, whether an interpreter is booked \
into the room, and anything reception should know about getting the caller into the building. Then \
the unpaid amount billing has to check, and last the mobile the new time is texted to and the address \
the written confirmation goes to.

The written confirmation is optional. If the caller would rather not give an address for it, tell \
them that is fine and move on.

If the caller asks for a scheduling coordinator, or wants something this desk cannot place, use \
Transfer To Coordinator. When the new appointment is agreed and the desk has what it needs, use \
Reschedule Booked. If the caller cannot talk now and wants calling back, use Callback Requested; if \
they ask never to be called again, use Do Not Contact.\
"""

# (variable_name, what the desk needs it for, collection configuration). No example values in any of
# this prose: the model speaks an example back as if it were the caller's own answer.
INPUTS: list[tuple[str, str, dict]] = [
    (
        "patient_full_name",
        "The name the appointment is booked under, so the desk opens the right record.",
        {"type": "name", "options": {"first_name": True, "last_name": True, "middle_name": False},
         "required": True},
    ),
    (
        "date_of_birth",
        "The patient's date of birth, checked against the record before anything is moved.",
        {"type": "dob", "options": {"require_time": False}, "required": True},
    ),
    (
        "new_appointment_date",
        "The day the caller would like the appointment moved to; it has to be a later day than today.",
        {"type": "date", "options": {"accept_past": False, "accept_today": False, "require_time": False},
         "required": True},
    ),
    (
        "preferred_time_of_day",
        "Which part of the day the caller wants, so the desk looks in the right block of slots.",
        {"type": "choice", "choices": ["Early morning", "Late morning", "Afternoon", "Early evening"],
         "options": {"multiple": False, "present_options": True}, "required": True},
    ),
    (
        "journey_time_minutes",
        "How long the caller's journey to the clinic takes, in whole minutes, so reception allows for it.",
        {"type": "number", "options": {"allow_decimal": False, "allow_negative": False}, "required": True},
    ),
    (
        "interpreter_needed",
        "Whether an interpreter should be booked into the room for this appointment.",
        {"type": "boolean", "options": {}, "required": True},
    ),
    (
        "access_notes",
        "Anything reception should know about getting the caller into the building, in the caller's "
        "own words. The caller may have nothing to add.",
        {"type": "text", "options": {}, "required": False},
    ),
    (
        "outstanding_fee",
        "The amount still showing as unpaid from the caller's last visit, so billing can check it "
        "against the record.",
        {"type": "currency", "options": {"required_currency": False, "required_period": False},
         "required": True},
    ),
    (
        "mobile_number",
        "The mobile the new appointment time is texted to.",
        {"type": "phone", "options": {"vanity": False}, "required": True},
    ),
    (
        "confirmation_email",
        "Where the written confirmation is sent. It is optional and the caller may decline it.",
        {"type": "email", "options": {}, "required": False},
    ),
]

# the pack's own intent ids, kept so every edge handle still resolves: transfer -> http hop ->
# call_forward, booked -> http hop -> end, and the three the walk may also land on.
INTENTS: list[tuple[str, str, str]] = [
    ("9d007cee-3717-4c38-8939-f9bb11807878", "Transfer To Coordinator",
     "Trigger when the caller asks to speak to a scheduling coordinator, or when what they want cannot "
     "be placed from this desk and they have agreed to be put through. Finish the Input you are on "
     "first. Do not trigger on a yes that was answering something else, and if your previous turn was "
     "interrupted before the caller heard the whole offer, it was not made: offer it again."),
    ("0d567305-1dce-4733-86a5-6982de293ffc", "Reschedule Booked",
     "Trigger when the new appointment is agreed and the desk has everything it needs for it. This is "
     "the ordinary end of this call. Do not use it when the caller wants a callback or asks not to be "
     "contacted again."),
    ("5bcfddf2-5b67-4077-9427-e51853fa0f86", "Callback Requested",
     "Trigger when the caller cannot talk now and wants the desk to call them back, and you have asked "
     "when suits them. Use this rather than ending the call for good."),
    ("740c82d0-f78a-440c-9889-4f20ba60e865", "Do Not Contact",
     "Trigger only when the caller asks not to be contacted again. Not for a caller who is merely busy, "
     "declining the transfer, or in a hurry."),
    ("0a67e8e9-cfb5-458c-89e8-c74121af6a24", "Voicemail Detected",
     "Trigger when the call reaches voicemail or an answering machine. Fire it silently with no message "
     "of your own -- the voicemail message is left automatically as the call ends."),
]


def node_config() -> dict:
    """The campaign node, in the console's own config shape."""
    return {
        "name": "Clinic Reschedule Desk",
        "description": "Moves an existing clinic appointment and collects what the desk needs to hold the slot.",
        "channel": "call",
        "instructions": TASK,
        "instruction_attachments": None,
        "allow_greeting_interruption": True,
        "inputs_complete": True,  # the Inputs list IS this node's whole collection contract
        "intents": [
            {"id": uuid, "intent_name": name, "intent_instructions": text,
             "intent_speech": {"intent_speech_text": "", "speech_enabled": False}}
            for uuid, name, text in INTENTS
        ],
        "extract_variables": [
            {"variable_name": name, "variable_instructions": prose, "variable_format_instructions": "",
             "variable_type": "string", "variable_enum_values": [], "configure_data_format": False,
             "collection": dict(collection, fresh_question=False, version=None)}
            for name, prose, collection in INPUTS
        ],
        "actions": [],
        "screening_name": "Hi, I'm calling from the Ridgeway Clinic scheduling desk.",
        "screening_reason": "this is about the appointment you asked to move",
        "initial_wait_time": 3,
        "voicemail_detection_next_node": "end_conversation",
        "model_config": {"model": MODEL, "provider": "openai"},
        "update_similar_nodes": False,
    }


def build_flow() -> dict:
    """The pack flow with the one agent node replaced and every collection version stamped."""
    from scripts.stamp_collection_versions import stamp

    with open(os.path.join(PACK, "flow.json")) as f:
        flow = json.load(f)
    nodes = [n for n in flow["nodes"] if n["id"] == NODE_ID]
    if len(nodes) != 1 or nodes[0]["type"] != "ai_agent_v29":
        raise SystemExit(f"{PACK}/flow.json: expected one ai_agent_v29 node {NODE_ID}")
    nodes[0]["data"]["config"] = stamp(node_config())
    return flow


def _write(path: str, text: str) -> bool:
    """Write only when the bytes change, so a rebuild is a no-op."""
    if os.path.exists(path) and open(path).read() == text:
        return False
    with open(path, "w") as f:
        f.write(text)
    return True


def build() -> list[str]:
    os.makedirs(os.path.join(WS, "scenarios"), exist_ok=True)
    os.makedirs(os.path.join(WS, "reports"), exist_ok=True)
    written = []
    if _write(os.path.join(WS, "flow.json"), json.dumps(build_flow(), indent=2) + "\n"):
        written.append("flow.json")
    with open(os.path.join(PACK, "params.yaml")) as f:  # the pack's seeds; the node adds no placeholder
        if _write(os.path.join(WS, "params.yaml"), f.read()):
            written.append("params.yaml")
    wanted = sorted(n for n in os.listdir(SCENARIOS) if n.endswith(".yaml"))
    for name in wanted:
        with open(os.path.join(SCENARIOS, name)) as f:
            if _write(os.path.join(WS, "scenarios", name), f.read()):
                written.append(f"scenarios/{name}")
    for name in os.listdir(os.path.join(WS, "scenarios")):  # a scenario dropped upstream goes here too
        if name.endswith((".yaml", ".yml")) and name not in wanted:
            os.remove(os.path.join(WS, "scenarios", name))
            written.append(f"scenarios/{name} (removed)")
    return written


# ── checks ────────────────────────────────────────────────────────────────────────────────


def load_bundle():
    """The workspace through the CLI's own loader, exactly as `run` loads it."""
    from src.simulation.cli.flow import load_flow_bundle
    from src.simulation.cli.workspace import Workspace

    ws = Workspace.load(WS)
    return ws, load_flow_bundle(ws.flow_path, ws.load_mapping())


def resolved_inputs(bundle):
    """field -> ResolvedConfiguration for the campaign node, as the runtime resolves it."""
    from src.models.ai_config import AgentNodeConfig
    from src.units.collection_configuration import resolve_collection_configurations

    return resolve_collection_configurations(
        AgentNodeConfig.model_validate(bundle.agent_configs[bundle.entry_node_id])
    )


def self_test() -> None:
    from src.tools import sanitize_tool_name
    from src.units.collect_input import _SHAPE, _STATE
    from src.units.collection_configuration import ConfigurationError
    from src.utils.prepared_display import RENDERABLE_TYPES

    first = build()
    digest = hashlib.sha256(open(os.path.join(WS, "flow.json"), "rb").read()).hexdigest()
    assert not build(), "rebuild rewrote files: not idempotent"
    assert hashlib.sha256(open(os.path.join(WS, "flow.json"), "rb").read()).hexdigest() == digest
    print(f"idempotent: first build touched {len(first)} file(s), second touched 0")

    ws, bundle = load_bundle()
    assert bundle.entry_node_id == NODE_ID, f"entry resolved to {bundle.entry_node_id}"
    config = bundle.agent_configs[NODE_ID]
    assert len(config["extract_variables"]) == len(INPUTS)

    # every Input resolves, and none is stale against the runtime's own digest
    resolved = resolved_inputs(bundle)
    bad = {f: r.reason for f, r in resolved.items() if isinstance(r, ConfigurationError)}
    assert not bad, f"configuration errors: {bad}"
    stale = [f for f, r in resolved.items() if r.stale]
    assert not stale, f"stale configurations: {stale}"
    assert set(resolved) == {sanitize_tool_name(n) for n, _, _ in INPUTS}

    # the display split NODE.md quotes, asserted against the runtime's own tables
    display = {f for f, r in resolved.items() if _SHAPE.get(r.type) == _STATE and r.type in RENDERABLE_TYPES}
    identity = {f for f, r in resolved.items() if r.type not in _SHAPE and r.type not in RENDERABLE_TYPES}
    assert len(display) == 6, sorted(display)
    assert identity == {"patient_full_name", "mobile_number", "confirmation_email"}, sorted(identity)
    assert _SHAPE[resolved["interpreter_needed"].type] != _STATE  # boolean acknowledges, never displays
    # a frame is refused outright when the policy names confirmation either way (prepared_state.state_eligibility)
    for field in display:
        policy = resolved[field].policy
        assert "require_confirmation" not in policy and "confirm_before_complete" not in policy, field
    print(f"prepared display: {sorted(display)}")
    print(f"identity (no display): {sorted(identity)}")

    # no example value in any tool-backed field text: the model speaks one back as the caller's answer
    for name, prose, collection in INPUTS:
        text = prose + " " + (collection.get("instructions") or "")
        assert "@" not in text and not any(c.isdigit() for c in text), name

    # the walk: the transfer exit and the ordinary exit each go through an http_request hop
    for intent, terminal in (("Transfer To Coordinator", "call_forward"), ("Reschedule Booked", "end_conversation")):
        handle = next(i["id"] for i in config["intents"] if i["intent_name"] == intent)
        hop = bundle.graph.edge_target(NODE_ID, handle)
        assert hop is not None and hop.type == "http_request", f"{intent} -> {hop}"
        after = bundle.graph.edge_target(hop.id, "success")
        assert after is not None and after.type == terminal, f"{intent} -> {hop.name} -> {after}"
        print(f"{intent}: -> {hop.name} (http_request) -> {after.name} ({after.type})")

    # every placeholder the sim ever RENDERS is covered by params.yaml; what is left is http params,
    # which the mocked hop never renders (simulation/flow/walk.py:_execute_http ignores the config)
    import re

    from src.simulation.cli.flow import substitute_placeholders

    text = substitute_placeholders(open(ws.flow_path).read(), ws.load_mapping())
    for node in json.loads(text)["nodes"]:
        for key, value in node["data"]["config"].items():
            left = re.findall(r"\{\{[^}]+\}\}", json.dumps(value))
            assert not left or (node["type"] == "http_request" and key == "http_request"), \
                f"{node['type']}.{key}: {left[:2]}"
    print("placeholders: all rendered fields resolved from params.yaml")

    # every scenario loads, every pin names a declared Input, every world_state key names a node:
    # a typo in either is silent for ever otherwise (the engine reads unknown names as "absent")
    scenarios = ws.load_scenarios()
    assert len(scenarios) == len(os.listdir(SCENARIOS)), "scenarios did not all load"
    declared = {sanitize_tool_name(n) for n, _, _ in INPUTS}
    node_names = {n["data"]["config"].get("name") for n in json.load(open(os.path.join(WS, "flow.json")))["nodes"]}
    for scenario in scenarios:
        pinned: set[str] = set()
        for e in [scenario.expect] + [t.expect for t in (scenario.turns or [])]:
            if e:
                pinned |= set(e.variables) | set(e.variables_absent)
        assert not pinned - declared, f"{scenario.name}: pins undeclared {sorted(pinned - declared)}"
        assert not set(scenario.world_state) - node_names, \
            f"{scenario.name}: world_state names no such node: {sorted(set(scenario.world_state) - node_names)}"
    print(f"scenarios: {[s.name for s in scenarios]}")
    print("SELF-TEST OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="build twice, then check the workspace")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        for name in build() or ["(nothing: already current)"]:
            print(f"wrote {name}")
        print(f"workspace: {WS}")
