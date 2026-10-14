"""Build arm C (four flow changes) and arm D (C + explicit tool-chaining wording).

    python3 build_cd.py

Arm C — the four changes that need no code:
  1. each action's `code_name` set to its own schema name          (measured in arm B: +15/70)
  2. the patient identity passed into match_patient as template variables, not scraped from
     conversation — arm B called it with "John Smith" for Paulo Ferreira
  3. `require_confirmation` dropped from both booleans — it is what produces
     "So that's a note of booking confirmed. Is that correct?"
  4. the two optional date collectors collapsed to one — both were asked on every call and both
     were skipped, four wasted turns

Arm D — C, plus one wording change per tool-using step: name the tool, forbid speaking before its
result is back, and forbid inventing what it would have returned. Arm B showed the chain stops
after the first tool (match_patient fired 20/70; the other three, 0/70), so C alone is unlikely
to be enough.

Kept apart so the wording change can be attributed separately from the structural ones.
"""
import json
import pathlib
import re
import shutil

HERE = pathlib.Path(__file__).parent
SRC = HERE / "armB-codename-fix"          # already carries change 1
FIRST = "{{cdcb0c46-bf35-4bcf-809b-fc2f987b950f.http.params.patient_first_name}}"
LAST = "{{cdcb0c46-bf35-4bcf-809b-fc2f987b950f.http.params.patient_last_name}}"
PHONE = "{{cdcb0c46-bf35-4bcf-809b-fc2f987b950f.http.params.phone_number}}"
MISSED = "{{cdcb0c46-bf35-4bcf-809b-fc2f987b950f.http.params.missed_appointment_date}}"

IDENTITY = (
    f'Call match_patient with first_name "{FIRST}", last_name "{LAST}", phone "{PHONE}", and the '
    "date of birth just confirmed formatted as MM/DD/YYYY. Use exactly those values for the name — "
    "never a name you heard in conversation, and never one you have guessed."
)

# --- arm C wording: structural only, identity threaded in ------------------------------------
C_WANTS = (
    "Before you ask this question, do three things in order. "
    f"First, {IDENTITY} Continue only if it returns exactly one patient; if it returns none or "
    "more than one, ask the patient to repeat the date of birth once and if it is still not "
    "exactly one, select Verification Failed. Keep the MasterId it returns. "
    "Second, call get_patient_appointments with that MasterId and find the appointment matching "
    f'"{MISSED}". If the lookup fails or returns nothing usable, apologise once, give the patient '
    "6 1 9, 5 1 5, 3 9 9 9 and select API Failure. If more than one appointment matches that date, "
    "read out only the time, the provider and the facility for each and ask which one they mean. "
    "Third, and only now, tell the patient they missed that appointment, stating the date, the "
    "time, the provider and the facility exactly as the lookup returned them. "
    "Then ask whether they would like to reschedule now. If they say no, thank them warmly and "
    "select Patient Declines."
)
C_DATES = (
    "Ask once what dates work best for the patient. If they name a single day, record that day. If "
    "they give a range such as \"sometime next week\", record the earliest day of that range. If "
    "they have no preference, leave this empty, do not ask again, and search from the next "
    "business day."
)

# --- arm D adds, per tool-using step, the same three sentences --------------------------------
CHAIN = (
    " YOU MUST CALL THE TOOL. Do not say anything about the result until the tool has returned. "
    "Never state an appointment, slot, date, time, provider or facility that a tool did not return "
    "to you in this call — if you have not called the tool yet, you do not know these things."
)


def load(arm):
    return json.loads((SRC / "flow.json").read_text())


def agent_cfg(flow):
    return [n for n in flow["nodes"] if n["type"] == "agent_node"][0]["data"]["config"]


def build(arm, chain):
    root = HERE / arm
    if root.exists():
        shutil.rmtree(root)
    (root / "scenarios").mkdir(parents=True)
    flow = load(arm)
    cfg = agent_cfg(flow)
    at = cfg["agent_tasks"]

    by = {v["name"]: v for v in at["variables"]}

    # 3. drop require_confirmation from both booleans
    for n in ("wants_to_reschedule", "booking_confirmed"):
        p = by[n].get("params") or {}
        p.pop("require_confirmation", None)
        by[n]["params"] = p

    # 2. identity threaded into the lookup step
    by["wants_to_reschedule"]["instructions"] = C_WANTS + (CHAIN if chain else "")

    # 4. collapse the two optional date collectors into one
    at["variables"] = [v for v in at["variables"] if v["name"] != "preferred_end_date"]
    by["preferred_start_date"]["instructions"] = C_DATES

    if chain:
        for n in ("selected_slot", "booking_confirmed"):
            by[n]["instructions"] = (by[n].get("instructions") or "") + CHAIN

    (root / "flow.json").write_text(json.dumps(flow, indent=1))
    (root / "params.yaml").write_text((SRC / "params.yaml").read_text())
    for f in sorted((SRC / "scenarios").glob("*.yaml")):
        shutil.copy(f, root / "scenarios" / f.name)

    # per-scenario workspaces, identity varied exactly as arms A/B
    import yaml
    base = yaml.safe_load((SRC / "params.yaml").read_text())
    for src_ws in sorted((SRC / "per").iterdir()):
        key = src_ws.name
        p = yaml.safe_load((src_ws / "params.yaml").read_text())
        d = root / "per" / key
        (d / "scenarios").mkdir(parents=True, exist_ok=True)
        (d / "flow.json").write_text((root / "flow.json").read_text())
        (d / "params.yaml").write_text(yaml.safe_dump(p, sort_keys=False, width=100))
        shutil.copy(src_ws / "scenarios" / f"{key}.yaml", d / "scenarios" / f"{key}.yaml")
    return root, cfg


for arm, chain in (("armC-flowfixes", False), ("armD-flowfixes-chain", True)):
    root, cfg = build(arm, chain)
    at = cfg["agent_tasks"]
    print(f"{arm}:")
    print("   code_names :", [a["code_name"] for a in cfg["actions"]])
    print("   collectors :", [(v["name"], v.get("params") or {}) for v in at["variables"]])
    print("   identity in wants_to_reschedule:",
          "patient_first_name" in at["variables"][1]["instructions"])
    print("   chain wording:", "YOU MUST CALL THE TOOL" in at["variables"][1]["instructions"])
    print(f"   workspaces : {len(list((root/'per').iterdir()))}")
