#!/usr/bin/env python3
"""Build everything for the v2.10 logic flow from spec.py and callers.py into out/.

    python3 build.py            # out/flow.json, out/sim/<caller>/ (text simulator), out/hunter/<caller>.json, then self-checks

Run it again on the day of a board: every date said on a call is worked out from today (India time). The caller id, the
transfer number and the voice settings are read from the working local flow 17, so no number is written in this folder's
source. out/ is local only.
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from pathlib import Path

import callers
import spec

HERE = Path(__file__).parent
OUT = HERE / "out"
ROOT = HERE.parent.parent
TUNNELS = ROOT / "v2.10/tunnels/run-2026-10-08/tunnels.json"
OLD = json.loads((ROOT / "V29-Hunter-Example/hunter/urls.json").read_text())   # Hunter's webhook base, the account id
CATEGORY = "v2.10 Stress Test"
VOICES = {"female": "21m00Tcm4TlvDq8ikWAM", "male": "ErXwobaYiN019PkySvjV"}
IDLE_SECONDS = 20   # the Hunter caller often takes 12 s to answer; at the default 15 a slow answer sets off a reminder


def sql(query: str) -> str:
    return subprocess.run(["docker", "exec", "v210-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", query],
                          capture_output=True, text=True, check=True).stdout.strip()


def borrowed() -> tuple[dict, dict, dict]:
    """The dial, transfer and voice settings of local flow 17, in the shape the builder and the simulator use."""
    dial = json.loads(sql("select config::jsonb->'model' from node where id = 304"))
    transfer = json.loads(sql("select config::jsonb->'model' from node where id = 309"))
    voice, schedule = (json.loads(part) for part in sql(
        "select voice_ai_config::jsonb::text || E'\\x1f' || schedule::jsonb::text from phlo where id = 17").split("\x1f"))
    for model in (dial, transfer):
        model.pop("name", None), model.pop("description", None)
        model["events"] = []
    dial.pop("to")
    dial["max_call_duration"] = 10   # minutes in this shape; a test call is over in five
    idle = {"retries": 3, **(voice.get("user_idle_config") or {}), "idling_timeout": IDLE_SECONDS, "hold_timeout": IDLE_SECONDS}
    return dial, transfer, {"schedule": schedule, "voice_ai_config": {**voice, "user_idle_config": idle}}


def exit_name(caller: dict) -> str | None:
    """The exit the caller's last AI node takes to reach its end, by the flow's own wiring."""
    path = [name for name in caller["log"]["path"] if name in spec.NODES]
    if not path:
        return None
    target = spec.TRANSFER if caller["log"]["end"] == "End Transfer" else caller["log"]["end"]
    return next(name for name, _, _, to in spec.NODES[path[-1]]["exits"] if to == target)


def sim_workspace(caller: dict, flow: dict) -> None:
    """One simulator workspace per caller, because the trigger values belong to the workspace."""
    ws = OUT / "sim" / caller["slug"]
    (ws / "scenarios").mkdir(parents=True)
    (ws / "flow.json").write_text(json.dumps(flow, indent=1))
    params = {"customer_name": caller["name"], "phone_number": "+15550100001", "city": spec.CITY}
    (ws / "params.yaml").write_text("params:\n" + "".join(f"  {key}: {json.dumps(value)}\n" for key, value in params.items())
                                    + "substitutions: {}\n")
    text = callers.persona(caller)
    person, goal = text.split("\n\nTARGET", 1)
    expect = {"ended": True, **({"intent": exit_name(caller)} if exit_name(caller) else {})}
    scenario = {"description": caller["title"],
                "simulated_user": {"persona": person, "goal": "TARGET" + goal, "opening": "Hello?", "max_turns": 30},
                "real_actions": sorted(spec.actions({})), "expect": expect}
    (ws / "scenarios" / f"{caller['slug']}.yaml").write_text(json.dumps(scenario, indent=1))   # JSON is YAML


def hunter_payload(caller: dict, flow: dict, runner: str) -> dict:
    body = {key: "{{INBOUND_NUMBER}}" if key == "phone_number" else "{{%s}}" % key for key in spec.PAYLOAD}
    slug = caller["slug"].split("-", 1)[1].replace("-", "_")
    return {"name": f"V210 {caller['slug']}", "category": CATEGORY,
            "description": f"{caller['title']}. Ends at {caller['log']['end']}. Planned {caller['seconds']} s."
                           + (" Run alone: it transfers." if caller.get("alone") else ""),
            "_built_ist": spec.TODAY.isoformat(), "_log": caller["log"], "_alone": bool(caller.get("alone")),
            "payload": {
                "testType": "outbound-agent",
                "initiationRequest": {"method": "POST", "url": f"{runner}/v1/account/{OLD['auth_id']}/flow/{flow['flowId']}",
                                      # the trigger needs the account's header; hunter.py copies it from a working local caller
                                      "headers": {"Content-Type": "application/json", "Authorization": "__FROM_A_WORKING_CALLER__"},
                                      "bodyTemplate": json.dumps(body, indent=2), "inboundNumberPlaceholder": "{{INBOUND_NUMBER}}"},
                "initiationVariables": {"customer_name": caller["name"], "city": spec.CITY},
                "expectedCallbackVariables": {},
                "botGreetsFirst": False, "allowInterruptions": True,
                "conversationPrompt": callers.persona(caller), "evaluationPrompt": callers.rubric(caller),
                "evaluationThreshold": 0.8, "maxTurns": 150,
                "evaluationConfig": {"autoDisconnectEnabled": True, "maxConsecutiveOffContext": 50,
                                     "maxNonActualIntentRetries": 3, "maxResponseTime": 60.0},
                "voiceId": VOICES[caller["voice"]], "webhookBaseUrl": OLD["webhook_base_url"],
                "event": "v210_" + slug, "testId": f"voice-v210-{caller['slug']}", "testRegion": "us-east"}}


def check(flow: dict) -> None:
    """Fails if the flow or an action is not what the callers were written against."""
    nodes = {node["data"]["config"]["name"]: node for node in flow["nodes"]}
    kinds = {row["collection"]["type"] for node in flow["nodes"] for row in node["data"]["config"].get("extract_variables", [])}
    assert kinds == {"address", "boolean", "choice", "currency", "date", "dob", "dtmf", "email", "name", "number", "phone", "text"}, kinds
    wired = {(edge["source"], edge["sourceHandle"]) for edge in flow["edges"]}
    for name in spec.NODES:
        for intent in nodes[name]["data"]["config"]["intents"]:
            assert (nodes[name]["id"], intent["id"]) in wired, f"{name}: exit {intent['intent_name']} has no edge"
    tools = {}
    for name, action in spec.actions(callers.ACCOUNTS).items():
        scope: dict = {}
        exec(compile(action["code_body"], name, "exec"), scope)   # noqa: S102 - our own generated code
        tools[name] = scope["main"]
    day, other = spec.VISIT.isoformat(), spec.VISIT_2.isoformat()
    for caller in callers.CALLERS:
        account, name = caller["account"], caller["name"]
        if account.get("lookup") == "error":   # this caller's lookup must crash, not answer
            try:
                tools["lookup_account"](customer_name=name, date_of_birth=account["dob"])
            except RuntimeError:
                continue
            raise AssertionError(name)
        assert tools["lookup_account"](customer_name=name, date_of_birth=account["dob"]) == {
            "verified": True, "open_item": account["open_item"] or "none"}, name
        month, dom, year = account["dob"][5:7], account["dob"][8:], account["dob"][:4]
        assert tools["lookup_account"](customer_name=name.split()[0], date_of_birth=f"{month}/{dom}/{year}")["verified"], name
    assert tools["lookup_account"](customer_name="Amit Patel", date_of_birth="1985-06-05") == {
        "verified": False, "reason": "date_of_birth_does_not_match"}
    slots = tools["find_slots"](visit_date=day)["slots"]
    assert slots == [f"{spec.slot_day(spec.VISIT)}, {time}" for time in spec.SLOTS], slots
    assert tools["find_slots"](visit_date=spec.SUNDAY.isoformat())["slots"] == []
    assert tools["book_visit"](customer_name="Vikram Rao", visit_date=day, slot=slots[0])["booked"] is True
    assert tools["book_visit"](customer_name="someone else", visit_date=day, slot=slots[0])["reason"] == "no_account_for_that_name"
    assert tools["book_visit"](customer_name="Vikram Rao", visit_date=other, slot=slots[1])["reason"] == "slot_is_from_another_day"
    assert tools["book_visit"](customer_name="Vikram Rao", visit_date=other, slot="2:00 PM")["time"] == "2:00 PM"
    assert tools["book_visit"](customer_name="Anita Desai", visit_date=day, slot=slots[0])["reason"] == "slot_taken"
    assert tools["take_payment"](customer_name="Arjun Shah", amount="INR 800.0", pin="4 8 1 2")["paid"] is True
    assert tools["take_payment"](customer_name="Arjun Shah", amount="INR 800.0", pin="4821")["reason"] == "wrong_pin"
    assert tools["save_site_details"](customer_name="Sunita Joshi", service_address="x", access_note=None) == {
        "saved": True, "fields": ["service_address"]}
    assert tools["save_site_details"](customer_name="Shreya Ghosh", service_address="x")["reason"] == "could_not_be_saved"
    assert tools["take_payment"](customer_name="Nisha Pillai", amount="INR 750.0", pin="8050")["reason"] == "wrong_pin"
    assert all(caller["seconds"] <= 240 for caller in callers.CALLERS)


def main() -> None:
    dial, transfer, settings = borrowed()
    flow = spec.flow(callers.ACCOUNTS, dial, transfer, settings)
    check(flow)
    for built in ("sim", "hunter"):   # only what this script writes: the saved text runs and the pages stay
        shutil.rmtree(OUT / built, ignore_errors=True)
    (OUT / "hunter").mkdir(parents=True)
    (OUT / "flow.json").write_text(json.dumps(flow, indent=1))
    runner = json.loads(TUNNELS.read_text())["runner"]["url"]
    for caller in callers.CALLERS:
        sim_workspace(caller, flow)
        (OUT / "hunter" / f"{caller['slug']}.json").write_text(json.dumps(hunter_payload(caller, flow, runner), indent=1, ensure_ascii=False))
    inputs = sum(len(node["data"]["config"].get("extract_variables", [])) for node in flow["nodes"])
    print(f"flow {flow['flowId']}: {len(flow['nodes'])} nodes, {len(flow['edges'])} edges, {inputs} Inputs of 12 types, "
          f"{len(spec.actions({}))} actions; {len(callers.CALLERS)} callers, {sum(c['seconds'] for c in callers.CALLERS)} planned seconds")
    print(f"built {spec.TODAY} IST: visit {spec.VISIT}, second search {spec.VISIT_2}, no times {spec.SUNDAY}; checks pass")


if __name__ == "__main__":
    assert datetime.datetime.now(spec.IST).date() == spec.TODAY
    main()
