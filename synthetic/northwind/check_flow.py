"""$0 offline: the example flow parses, every Input resolves, every contract compiles, and leader preflight passes.

  cd <tree> && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <this> <flow.json | ws dir>
A ws dir also validates every scenario through the sim CLI's own loader and checks mocks against the actions.
"""
import json
import logging
import os
import socket
import sys
from urllib.parse import urlparse


def _deny(*a, **k):
    raise RuntimeError("network denied in the offline check")


socket.socket.connect = _deny
socket.create_connection = _deny
logging.disable(logging.CRITICAL)

from src.jev_leader.effects import compile_actions  # noqa: E402
from src.jev_leader.harness import preflight_reasons  # noqa: E402
from src.jev_leader.route_domain import compile_route_contracts  # noqa: E402
from src.jev_leader.tools.defaults import apply_defaults  # noqa: E402
from src.jev_leader.view import VIEW_INSTRUCTION_CHARS  # noqa: E402
from src.simulation.cli.flow import load_flow_bundle  # noqa: E402
from src.simulation.cli.workspace import Workspace  # noqa: E402
from src.simulation.runner import SimSession  # noqa: E402
from src.units.collection_configuration import ConfigurationError, resolve_collection_configurations  # noqa: E402

ws = Workspace.load(sys.argv[1]) if os.path.isdir(sys.argv[1]) else None
bundle = load_flow_bundle(ws.flow_path if ws else sys.argv[1], ws.load_mapping() if ws else {})
sim = SimSession(phlo_run_uuid="check", auth_id="check", node_uuid=bundle.entry_node_id, node_run_uuid="check",
                 graph=bundle.graph, flow_session=bundle.flow_session)
sim._refresh_agent_config()
ai = sim._ai_config()
apply_defaults(ai, {})
node = ai.agent_config
configs = resolve_collection_configurations(node)
bad = {k: v.reason for k, v in configs.items() if isinstance(v, ConfigurationError)}
routes = compile_route_contracts(ai)
actions = compile_actions(list(node.actions), set(configs))
reasons = preflight_reasons(ai)

raw = bundle.graph.nodes_by_id[bundle.entry_node_id]
raw_actions = next(n for n in bundle.flow["nodes"] if n["id"] == bundle.entry_node_id)["data"]["config"]["actions"]
names = {a["http_tool_name"] for a in raw_actions}
fail = []
fail += [f"instructions {len(node.instructions)} > {VIEW_INSTRUCTION_CHARS}"] * (len(node.instructions) > VIEW_INSTRUCTION_CHARS)
fail += [f"{a['http_tool_name']}: not HTTP to example.invalid" for a in raw_actions
         if a["action_type"] != "HTTP" or urlparse(a["http_url"]).hostname != "example.invalid"]
fail += [f"{n}: no compiled leader_contract" for n in sorted(names - set(actions))]
scenarios = ws.load_scenarios() if ws else []
for s in scenarios:
    fail += [f"{s.name}: unmocked {sorted(names - set(s.action_mocks))}"] * bool(names - set(s.action_mocks))
    fail += [f"{s.name}: real_actions {s.real_actions}"] * bool(s.real_actions)
    fail += [f"{s.name}: exit {s.expect.intent} is not a route"] * (s.expect.intent not in routes)
print(json.dumps({
    "entry": bundle.name_of(bundle.entry_node_id), "entry_type": raw.type, "flow_session": bundle.flow_session,
    "params": ws.load_mapping() if ws else None,
    "instructions_chars": [len(node.instructions), VIEW_INSTRUCTION_CHARS],
    "inputs": {k: {"type": v.type, "required": v.required, "policy": v.policy,
                   **{f: getattr(v, f) for f in ("choices", "num_digits", "spell_back", "readback") if getattr(v, f, None)}}
               for k, v in configs.items() if not isinstance(v, ConfigurationError)},
    "input_errors": bad,
    "routes": {k: r.operation_id for k, r in routes.items()},
    "actions": {k: [a.effect_kind, a.transport, list(a.consent_fields)] for k, a in actions.items()},
    "scenarios": {"loaded": len(scenarios), "by_exit": {i: sum(s.expect.intent == i for s in scenarios) for i in routes}} if ws else None,
    "checks_failed": fail,
    "preflight_reasons": reasons,
}, indent=1))
sys.exit(1 if bad or reasons or fail else 0)
