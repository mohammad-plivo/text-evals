"""Language-following A/B on the Rapido Hindi V2.9 flow: the old flow (fixed Hindi lines) against the new one.

python3 lang_ab.py            builds, per arm, ws-lang-<arm> (callers that start at the V2.9 node) and
                              ws-lang-open-<arm> (callers that start at screening, to hear the opening);
                              Inputs come from each flow's Detect preview with the console's wire keys, as make_ws.py does
python3 lang_ab.py score      scores the newest report in each workspace
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = {
    "old": os.path.join(HERE, "lang-old", "rapido-hindi-v29-flow"),
    "new": os.path.join(HERE, "..", "rapido-hindi-v29-flow"),
}
WIRE = ["type", "options", "choices", "choices_from_call", "num_digits", "spell_back", "readback",
        "fresh_question", "required", "instructions", "version"]

# Six caller turns each: the screening "yes", then five answers. The mixed callers switch on their third turn.
SCENARIOS = {
    "all-hindi": ["हाँ, बोलिए।", "अभी मैं Uber चलाता हूँ।", "फुल-टाइम चलाता था, रोज़ दस घंटे।",
                  "इंसेंटिव कम हो गए थे, कमाई नहीं हो रही थी।", "हाँ, अच्छा लग रहा है, मुझे इंटरेस्ट है।",
                  "हाँ, हो गया, प्लान एक्टिवेट हो गया।"],
    "all-english": ["Yes, tell me.", "Right now I drive for Uber.", "I was full time, almost every day.",
                    "The incentives went down, so it was not worth it.", "No, I am not interested.",
                    "Call me tomorrow evening at six."],
    "hindi-then-english": ["हाँ, बोलिए।", "अभी मैं Ola चलाता हूँ।", "I used to do part time, mostly in the evenings.",
                           "The payouts were too slow, so I stopped.", "No, I don't want it.",
                           "Call me on Saturday at eleven in the morning."],
    "english-then-hindi": ["Yes, tell me.", "Right now I do deliveries for Swiggy.", "पहले मैं फुल-टाइम चलाता था।",
                           "बाइक खराब हो गई थी, इसलिए छोड़ दिया।", "हाँ, यह तो अच्छा है, मुझे इंटरेस्ट है।",
                           "हो गया, प्लान अब एक्टिव है।"],
}
# From screening: a hello (Latin, or Devanagari as speech-to-text may write it), then the identity answer. Two turns only: the simulator cannot carry
# a call from screening into a V2.9 node (it restarts screening), so the V2.9 side starts at the node above.
OPENERS = {
    "open-english": ["Hello?", "Yes, speaking."],
    "open-hindi": ["Hello?", "हाँ, मैं बोल रहा हूँ।"],
    "open-hello-devanagari": ["हेलो?", "हाँ, मैं बोल रहा हूँ।"],
}
DEV, LAT = re.compile(r"[ऀ-ॿ]"), re.compile(r"[A-Za-z]")


def build():
    import yaml

    for arm, base in ARMS.items():
        flow, preview = json.load(open(base + ".json")), json.load(open(base + "-detect-preview.json"))
        node = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")
        node["data"]["config"]["extract_variables"] = [
            {"variable_name": p["variable_name"], "variable_instructions": p["variable_instructions"],
             "variable_type": "string", "variable_format_instructions": "", "variable_enum_values": [],
             "configure_data_format": False, "collection": {k: p["collection"].get(k) for k in WIRE}}
            for p in preview["proposed"]
        ]
        for ws, scenarios in ((f"ws-lang-{arm}", SCENARIOS), (f"ws-lang-open-{arm}", OPENERS)):
            ws = os.path.join(HERE, ws)
            os.makedirs(os.path.join(ws, "scenarios"), exist_ok=True)
            json.dump(flow, open(os.path.join(ws, "flow.json"), "w"), ensure_ascii=False, indent=1)
            yaml.safe_dump({"params": {"captain_name": "Mohammad", "phone_number": "+919876543210"}, "substitutions": {}},
                           open(os.path.join(ws, "params.yaml"), "w"), allow_unicode=True)
            for name, turns in scenarios.items():
                yaml.safe_dump({"description": f"Rapido Hindi V2.9 language: {name}", "turns": [{"user": t} for t in turns]},
                               open(os.path.join(ws, "scenarios", f"{name}.yaml"), "w"), allow_unicode=True, sort_keys=False)
        screening = next(n for n in flow["nodes"] if n["type"] == "outbound_screening")
        print(f"{arm}: agent node {node['id']} | screening node {screening['id']} | "
              f"Inputs {[v['variable_name'] for v in node['data']['config']['extract_variables']]}")


def lang(text):
    """'hi' or 'en' by letter count, '' for a silent turn."""
    d, l = len(DEV.findall(text)), len(LAT.findall(text))
    return "" if not d + l else ("hi" if d >= l else "en")


def runs(report):
    out, cur = [], None
    for line in open(report):
        d = json.loads(line)
        if d.get("type") == "scenario_started":
            cur = {"name": d["name"], "turns": []}
            out.append(cur)
        elif d.get("type") == "turn" and cur is not None:
            cur["turns"].append((d.get("user") or "", " ".join(str(d.get("agent") or "").split()),
                                 [c["name"] for c in d.get("tool_calls") or []]))
    return out


def newest(ws):
    report = max(glob.glob(os.path.join(HERE, ws, "reports", "*.jsonl")), key=os.path.getmtime)
    print(f"{ws}: {report}")
    return runs(report)


def score():
    table = defaultdict(lambda: defaultdict(int))
    firsts = defaultdict(set)
    for arm in ARMS:
        for r in newest(f"ws-lang-{arm}"):
            row = table[(r["name"], arm)]
            row["runs"] += 1
            for user, agent, tools in r["turns"]:
                spoke = lang(agent)
                row["turns"] += 1
                row["silent"] += not spoke
                row["match"] += spoke == lang(user)
            row["saved"] += sum(any(t.startswith("update_") for t in tools) for _, _, tools in r["turns"][1:6])
            if r["turns"]:
                user, agent, _ = r["turns"][0]
                row["first"] += lang(agent) == lang(user)
                firsts[(r["name"], arm)].add(re.sub(r"[\s.,!?।…]+$", "", agent))
        for r in newest(f"ws-lang-open-{arm}"):
            row = table[(r["name"], arm)]
            row["runs"] += 1
            row["greeting"] += len(r["turns"]) > 0 and lang(r["turns"][0][1]) == "en"
            row["minute"] += len(r["turns"]) > 1 and lang(r["turns"][1][1]) == lang(r["turns"][1][0])
    print("\nscenario            | arm | runs | first V2.9 turn in reply's language | agent turns in caller's language "
          "| silent | answers saved | first-question wordings")
    for name in SCENARIOS:
        for arm in ARMS:
            row = table[(name, arm)]
            print(f"{name:19s} | {arm:3s} | {row['runs']:4d} | {row['first']:3d}/{row['runs']:<31d} | "
                  f"{row['match']:3d}/{row['turns']:<29d} | {row['silent']:6d} | {row['saved']:3d}/{5 * row['runs']:<9d} | "
                  f"{len(firsts[(name, arm)])}")
    print("\nscreening           | arm | runs | greeting in English | minute ask in the identity answer's language")
    for name in OPENERS:
        for arm in ARMS:
            row = table[(name, arm)]
            print(f"{name:19s} | {arm:3s} | {row['runs']:4d} | {row['greeting']:3d}/{row['runs']:<15d} | {row['minute']}/{row['runs']}")
    if "--show" in sys.argv:
        for (name, arm), texts in sorted(firsts.items()):
            for t in sorted(texts):
                print(f"{name:19s} {arm}: {t[:160]}")


if __name__ == "__main__":
    score() if "score" in sys.argv else build()
