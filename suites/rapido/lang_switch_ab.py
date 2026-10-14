"""Hindi flow language switching, old rule vs new rule. usage: python3 lang_switch_ab.py build | score <ws>
Each caller turn carries the language the agent's NEXT reply should be in: en, or hi (Hindi or Hinglish, any script).
"""
import json
import os
import re
import shutil
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW = os.path.join(HERE, "..", "rapido-hindi-v29-no-screening-flow.json")
PREVIEW = os.path.join(HERE, "..", "rapido-hindi-v29-no-screening-flow-detect-preview.json")
WIRE = ["type", "options", "choices", "choices_from_call", "num_digits", "spell_back", "readback", "fresh_question",
        "required", "instructions", "version"]
OLD_RULE = ("reply in the language of the captain's last turn: Hindi in Devanagari when they speak Hindi, English when "
            "they speak English, the same mix when they mix, and switch back when they do.")
SHORT_RULES = {
    "short1": "reply in Hindi in Devanagari whenever the captain's last turn has any Hindi or Hinglish; reply in English only when it is fully English.",
    "short2": "match the captain's last turn: Hindi or Hinglish gets Hindi in Devanagari, fully English gets English.",
    "short3": ("reply in Hindi in Devanagari whenever the captain's last turn has any Hindi, even in English letters; "
               "reply in English only when it is fully English."),
}
STEP5_EXTRA = " Keep the menu names Earnings and My Plan in English."  # the language rule already keeps them

NEW_RULE = ("every reply follows the captain's last turn: if it has any Hindi, even Hindi typed in English letters, "
            "reply in Hindi in Devanagari, keeping English words like plan, app or Earnings as they are; reply in "
            "English only when their turn is fully English.")

# (caller line, language the agent's reply to it should be in); the opening is always answered in English
SCENARIOS = {
    "en-hi-en": [("Hello?", "en"), ("Yes, speaking.", "en"), ("हाँ, बोलिए।", "hi"), ("अभी मैं Uber चलाता हूँ।", "hi"),
                 ("I used to drive full time.", "en"), ("The earnings went down, so I stopped.", "en"),
                 ("हाँ, बताइए, interested हूँ।", "hi")],
    "hinglish-devanagari": [("Hello?", "en"), ("हाँ, मैं ही बोल रहा हूँ।", "hi"), ("हाँ बोलो, एक minute है।", "hi"),
                            ("अभी मैं Ola पे drive करता हूँ।", "hi"), ("पहले full time चलाता था।", "hi"),
                            ("earning कम हो गई थी, इसलिए छोड़ दिया।", "hi"), ("अच्छा, plan अच्छा लग रहा है, बताओ।", "hi")],
    "hinglish-latin": [("Hello?", "en"), ("Haan, main hi bol raha hoon.", "hi"), ("Haan bolo, ek minute hai.", "hi"),
                       ("Abhi main Uber chalata hoon.", "hi"), ("Pehle full time chalata tha.", "hi"),
                       ("Earning kam ho gayi thi, isliye chhod diya.", "hi"), ("Haan, interested hoon, batao.", "hi")],
    "hi-then-en": [("हेलो?", "en"), ("हाँ, बोल रहा हूँ।", "hi"), ("हाँ, बोलिए।", "hi"),
                   ("Sorry, can we talk in English? I drive for Uber now.", "en"), ("I was full time.", "en"),
                   ("I stopped because the incentives were cut.", "en"), ("Yes, tell me more about the plan.", "en")],
    "english-only": [("Hello?", "en"), ("Yes, this is him.", "en"), ("Sure, go ahead.", "en"),
                     ("I drive for Uber now.", "en"), ("Part time.", "en"), ("I moved to another city for a while.", "en"),
                     ("Yes, I am interested, tell me more.", "en")],
    # short turns: the runtime's own language guess leans on the previous turn for three words or fewer
    "short-hindi": [("Hello?", "en"), ("हाँ जी।", "hi"), ("हाँ, ठीक है।", "hi"), ("Uber।", "hi"),
                    ("Haan ji, full time.", "hi"), ("Paise kam the.", "hi"), ("अच्छा, ठीक है।", "hi")],
    "hinglish-questions": [("Hello?", "en"), ("Haan, bolo.", "hi"), ("Haan, time hai.", "hi"),
                           ("Ye kis baare mein hai? Main abhi Rapido nahi chalata.", "hi"),
                           ("Abhi Uber chalata hoon, full time.", "hi"), ("Kitna paisa milega is plan mein?", "hi"),
                           ("Theek hai, interested hoon.", "hi")],
    "back-and-forth": [("Hello?", "en"), ("Yes, speaking.", "en"), ("हाँ, बोलिए।", "hi"),
                       ("I drive for Uber now.", "en"), ("पहले full time चलाता था।", "hi"),
                       ("The incentives were cut, that is why.", "en"), ("Haan, batao plan ke baare mein.", "hi")],
}
DEV = re.compile(r"[ऀ-ॿ]")
LAT = re.compile(r"[A-Za-z]")


def build():
    flow = json.load(open(FLOW))
    preview = json.load(open(PREVIEW))
    node = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")
    node["data"]["config"]["extract_variables"] = [
        {"variable_name": p["variable_name"], "variable_instructions": p["variable_instructions"],
         "variable_type": "string", "variable_format_instructions": "", "variable_enum_values": [],
         "configure_data_format": False, "collection": {k: p["collection"].get(k) for k in WIRE}}
        for p in preview["proposed"]]
    task = node["data"]["config"]["instructions"]
    base_inputs = node["data"]["config"]["extract_variables"]
    assert task.count(OLD_RULE) == 1, "the old rule moved"
    arms = {"old": OLD_RULE, "new": NEW_RULE, **SHORT_RULES}
    arms.update({f"{a}-v2": r for a, r in list(arms.items())})  # -v2: the same rule, step 5's extra sentence removed
    for arm, rule in ((a, arms[a]) for a in (sys.argv[2:] or arms)):
        ws = os.path.join(HERE, f"ws-lang2-{arm}")
        shutil.rmtree(ws, ignore_errors=True)
        os.makedirs(os.path.join(ws, "scenarios"))
        text = task.replace(OLD_RULE, rule)
        inputs = json.loads(json.dumps(base_inputs))
        if arm.endswith("-v2"):  # Detect copies step 5 into the Input, so the sentence leaves both
            assert text.count(STEP5_EXTRA) == 1
            text = text.replace(STEP5_EXTRA, "")
            for v in inputs:
                v["variable_instructions"] = v["variable_instructions"].replace(STEP5_EXTRA, "")
                v["collection"]["instructions"] = (v["collection"].get("instructions") or "").replace(STEP5_EXTRA, "")
        node["data"]["config"]["instructions"] = text
        node["data"]["config"]["extract_variables"] = inputs
        json.dump(flow, open(os.path.join(ws, "flow.json"), "w"), ensure_ascii=False, indent=1)
        shutil.copy(os.path.join(HERE, "ws-base", "params.yaml"), os.path.join(ws, "params.yaml"))
        for name, turns in SCENARIOS.items():
            yaml.safe_dump({"description": f"language switching: {name}", "turns": [{"user": u} for u, _ in turns]},
                           open(os.path.join(ws, "scenarios", f"{name}.yaml"), "w"), allow_unicode=True, sort_keys=False)
    print("node", node["id"])


def language(text):
    d, l = len(DEV.findall(text)), len(LAT.findall(text))
    if d + l == 0:
        return None
    return "hi" if d / (d + l) >= 0.5 else "en" if d / (d + l) < 0.1 else "mixed"


def score(ws):
    report = sorted(f for f in os.listdir(os.path.join(ws, "reports")) if f.endswith(".jsonl"))[-1]
    runs, cur = [], None
    for line in open(os.path.join(ws, "reports", report)):
        d = json.loads(line)
        if d.get("type") == "scenario_started":
            cur = {"name": d["name"], "turns": [], "end": None}
            runs.append(cur)
        elif d.get("type") == "turn" and cur is not None:
            cur["turns"].append((d.get("user"), " ".join(str(d.get("agent") or "").split())))
        elif d.get("type") == "scenario_finished" and cur is not None:
            cur["end"] = d.get("failures")
    total = {"hi": [0, 0], "en": [0, 0]}
    per = {}
    misses = []
    for r in runs:
        want = dict(SCENARIOS[r["name"]])
        row = per.setdefault(r["name"], [0, 0, 0, 0])
        row[3] += bool(r["end"])
        for u, a in r["turns"]:
            got = language(a)
            if got is None or u not in want:
                continue
            ok = got == want[u]
            total[want[u]][0] += 1
            total[want[u]][1] += ok
            row[0] += 1
            row[1] += ok
            if not ok:
                row[2] += 1
                misses.append(f"{r['name']}: caller {u!r} -> {got}: {a[:90]}")
    for name, (n, ok, _, crashed) in per.items():
        print(f"{name:20s} replies in the right language {ok}/{n}  calls that crashed {crashed}")
    print(f"{'after Hindi/Hinglish':20s} {total['hi'][1]}/{total['hi'][0]}   after full English {total['en'][1]}/{total['en'][0]}")
    for m in misses[:12]:
        print("  miss:", m)


if __name__ == "__main__":
    build() if sys.argv[1] == "build" else score(sys.argv[2])
