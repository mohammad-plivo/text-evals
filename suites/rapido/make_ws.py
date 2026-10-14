"""Sim workspace for the 'why do you need this?' A/B on the Rapido Hindi V2.9 flow.

The node's Inputs are the ones the runner's own Detect code proposed for this Task (detect_preview.py),
saved with the wire keys the console stores. usage: python3 make_ws.py
"""
import json
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.join(HERE, "..", "rapido-hindi-v29-flow.json")
PREVIEW = os.path.join(HERE, "..", "rapido-hindi-v29-flow-detect-preview.json")
WS = os.path.join(HERE, "ws")
WIRE = ["type", "options", "choices", "choices_from_call", "num_digits", "spell_back", "readback",
        "fresh_question", "required", "instructions", "version"]

OPEN = "हाँ, बोलिए।"
SCENARIOS = {
    # the dev call: the platform question, then "why do you need to know?"
    "why-platform": [OPEN, "यह आपको क्यों जानना है?", "अच्छा ठीक है, अभी मैं Uber चलाता हूँ।", "फुल-टाइम।"],
    # the same push-back on the date-and-time question
    "why-callback": [OPEN, "अभी मैं Uber चलाता हूँ।", "पार्ट-टाइम।", "कमाई कम हो गई थी।", "नहीं, अभी इंटरेस्ट नहीं है।",
                     "आपको ये क्यों जानना है?", "ठीक है, कल शाम छह बजे।"],
    # controls: a plain answer, and a second refusal that must be accepted, not pressed
    "answer-direct": [OPEN, "अभी मैं Uber चलाता हूँ।", "फुल-टाइम।"],
    "refuse-twice": [OPEN, "यह आपको क्यों जानना है?", "नहीं, मैं नहीं बताऊँगा।", "पार्ट-टाइम।"],
}

flow = json.load(open(FLOW))
preview = json.load(open(PREVIEW))
node = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")
node["data"]["config"]["extract_variables"] = [
    {"variable_name": p["variable_name"], "variable_instructions": p["variable_instructions"],
     "variable_type": "string", "variable_format_instructions": "", "variable_enum_values": [],
     "configure_data_format": False, "collection": {k: p["collection"].get(k) for k in WIRE}}
    for p in preview["proposed"]
]
os.makedirs(os.path.join(WS, "scenarios"), exist_ok=True)
json.dump(flow, open(os.path.join(WS, "flow.json"), "w"), ensure_ascii=False, indent=1)
yaml.safe_dump({"params": {"captain_name": "Mohammad", "phone_number": "+919876543210"}, "substitutions": {}},
               open(os.path.join(WS, "params.yaml"), "w"), allow_unicode=True)
for name, turns in SCENARIOS.items():
    yaml.safe_dump({"description": f"Rapido Hindi V2.9: {name}", "turns": [{"user": t} for t in turns]},
                   open(os.path.join(WS, "scenarios", f"{name}.yaml"), "w"), allow_unicode=True, sort_keys=False)
print("node", node["id"], "| Inputs", [v["variable_name"] for v in node["data"]["config"]["extract_variables"]],
      "| scenarios", list(SCENARIOS))
