"""Language switching with every Hindi turn in Devanagari (as Deepgram writes it). usage: lang_devanagari.py build | score"""
import json, os, shutil, sys
import yaml
import lang_switch_ab as ab

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(HERE, "ws-lang-deva")
ab.SCENARIOS.clear()
ab.SCENARIOS.update({
    "en-hi-en": [("Hello?", "en"), ("Yes, speaking.", "en"), ("हाँ, बोलिए।", "hi"), ("अभी मैं Uber चलाता हूँ।", "hi"),
                 ("I used to drive full time.", "en"), ("The earnings went down, so I stopped.", "en"),
                 ("हाँ, बताइए, interested हूँ।", "hi")],
    "hinglish": [("Hello?", "en"), ("हाँ, मैं ही बोल रहा हूँ।", "hi"), ("हाँ बोलो, एक minute है।", "hi"),
                 ("अभी मैं Ola पे drive करता हूँ।", "hi"), ("पहले full time चलाता था।", "hi"),
                 ("earning कम हो गई थी, इसलिए छोड़ दिया।", "hi"), ("अच्छा, plan अच्छा लग रहा है, बताओ।", "hi")],
    "short-hindi": [("Hello?", "en"), ("हाँ जी।", "hi"), ("हाँ, ठीक है।", "hi"), ("Uber।", "hi"),
                    ("हाँ जी, full time.", "hi"), ("पैसे कम थे।", "hi"), ("अच्छा, ठीक है।", "hi")],
    "hindi-questions": [("Hello?", "en"), ("हाँ, बोलो।", "hi"), ("हाँ, time है।", "hi"),
                        ("ये किस बारे में है? मैं अभी Rapido नहीं चलाता।", "hi"), ("अभी Uber चलाता हूँ, full time.", "hi"),
                        ("कितना पैसा मिलेगा इस plan में?", "hi"), ("ठीक है, interested हूँ।", "hi")],
    "back-and-forth": [("Hello?", "en"), ("Yes, speaking.", "en"), ("हाँ, बोलिए।", "hi"), ("I drive for Uber now.", "en"),
                       ("पहले full time चलाता था।", "hi"), ("The incentives were cut, that is why.", "en"),
                       ("हाँ, बताओ plan के बारे में।", "hi")],
    "hi-then-en": [("Hello?", "en"), ("हाँ, बोल रहा हूँ।", "hi"), ("हाँ, बोलिए।", "hi"),
                   ("Sorry, can we talk in English? I drive for Uber now.", "en"), ("I was full time.", "en"),
                   ("I stopped because the incentives were cut.", "en"), ("Yes, tell me more about the plan.", "en")],
})

def build():
    flow = json.load(open(ab.FLOW)); prev = json.load(open(ab.PREVIEW))
    node = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")
    node["data"]["config"]["extract_variables"] = [
        {"variable_name": p["variable_name"], "variable_instructions": p["variable_instructions"], "variable_type": "string",
         "variable_format_instructions": "", "variable_enum_values": [], "configure_data_format": False,
         "collection": {k: p["collection"].get(k) for k in ab.WIRE}} for p in prev["proposed"]]
    assert "even Hindi typed in English letters" in node["data"]["config"]["instructions"]
    shutil.rmtree(WS, ignore_errors=True); os.makedirs(os.path.join(WS, "scenarios"))
    json.dump(flow, open(os.path.join(WS, "flow.json"), "w"), ensure_ascii=False, indent=1)
    shutil.copy(os.path.join(HERE, "ws-base", "params.yaml"), os.path.join(WS, "params.yaml"))
    for name, turns in ab.SCENARIOS.items():
        yaml.safe_dump({"description": name, "turns": [{"user": u} for u, _ in turns]},
                       open(os.path.join(WS, "scenarios", f"{name}.yaml"), "w"), allow_unicode=True, sort_keys=False)
    print("node", node["id"])

build() if sys.argv[1] == "build" else ab.score(WS)
