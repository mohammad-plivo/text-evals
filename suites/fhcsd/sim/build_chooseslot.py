"""A/B for D-018 follow-up: Choose Slot's selected_slot as text (A, as published v23909) vs choice (B).
Builds sim/chooseslot/arm{A,B}/{flow.json,params.yaml,scenarios/first-slot.yaml} from the v23909 DB dump."""
import json, sys, pathlib, copy, yaml
S = sys.argv[1]
nodes = json.load(open(f"{S}/v23909_nodes.json")); conns = json.load(open(f"{S}/v23909_conns.json"))
live = json.load(open("live-v6/flow.json"))
TYPE = {"Start": "start", "Initiate Call and Screen · Dial": "initiate_call", "Initiate Call and Screen": "outbound_screening",
        "Transfer to Staff": "call_forward", "Verify Patient": "agent_node", "Reschedule Agent": "agent_node", "Choose Slot": "agent_node",
        "Lookup Appointment": "http_request", "Search Slots": "http_request", "Save Appointment": "http_request"}
def ntype(n): return TYPE.get(n["name"], "end_conversation")
byname = {n["name"]: n for n in nodes}
SLOTS = {1: ("Monday, August 31 at 09:30 AM", "08-31-2026"), 2: ("Tuesday, September 1 at 11:00 AM", "09-01-2026"), 3: ("Wednesday, September 2 at 03:45 PM", "09-02-2026")}
search = byname["Search Slots"]["uuid"]; lookup = byname["Lookup Appointment"]["uuid"]; start = byname["Start"]["uuid"]
subs = {f"{{{{{start}.http.params.from_number}}}}": "+12813056522", f"{{{{{start}.http.params.patient_first_name}}}}": "Carlos",
        f"{{{{{start}.http.params.patient_last_name}}}}": "Rivera", f"{{{{{start}.http.params.phone_number}}}}": "+13473345222",
        f"{{{{{lookup}.response.MasterId}}}}": "437638752", f"{{{{{lookup}.response.Id1}}}}": "900001",
        f"{{{{{lookup}.response.When1}}}}": "Saturday, August 29 at 10:30 AM", f"{{{{{lookup}.response.Provider1}}}}": "Dr. Rismiller",
        f"{{{{{lookup}.response.Facility1}}}}": "Logan Heights Family Health Center", f"{{{{{lookup}.response.Count}}}}": "1"}
for i, (when, date) in SLOTS.items():
    subs[f"{{{{{search}.response.Slot{i}When}}}}"] = when; subs[f"{{{{{search}.response.Slot{i}Date}}}}"] = date
    subs[f"{{{{{search}.response.Slot{i}Id}}}}"] = str(249668 + i); subs[f"{{{{{search}.response.Slot{i}Provider}}}}"] = "Dr. Rismiller"
    subs[f"{{{{{search}.response.Slot{i}Facility}}}}"] = "Logan Heights Family Health Center"
def edge(e):
    su, _, sh = e["source"].partition("."); tu, _, _ = e["target"].partition(".")
    return {"id": e.get("data", {}).get("id") or f"{su}-{sh}-{tu}", "source": su, "sourceHandle": sh, "target": tu, "targetHandle": "Input"}
base = {"name": "FHCSD OB v23909", "flowId": "7dd1a9aa-b1a4-4a10-9ba5-f5ba135abfdc",
        "nodes": [{"id": n["uuid"], "type": ntype(n), "data": {"config": n["config"]["model"]}} for n in nodes],
        "edges": [edge(e) for e in (json.loads(conns["connections"]) if isinstance(conns["connections"], str) else conns["connections"])],
        "agentSettings": live.get("agentSettings", {})}
scenario = {"description": "Choose Slot entry: are the three slot times voiced unprompted, and read back before the yes?",
  "simulated_user": {"persona": "You are Carlos Rivera on your mobile. Short natural sentences; never reveal this is a test. ALWAYS ANSWER THE QUESTION YOU WERE ASKED IMMEDIATELY. You want the FIRST option: whatever the agent asks about slots or options, answer 'Option one.' or 'The first one.' Never ask what the options are. When asked to confirm the booking, say 'Yes, confirm it.'",
    "goal": "Pick the first slot and confirm.", "opening": "Hello?", "max_turns": 10}}
for arm in ("A", "B"):
    f = copy.deepcopy(base)
    if arm == "B":
        cs = next(n for n in f["nodes"] if n["id"] == byname["Choose Slot"]["uuid"])["data"]["config"]
        v = next(v for v in cs["agent_tasks"]["variables"] if v["name"] == "selected_slot")
        v["type"] = "choice"; v["params"] = {"choices": [SLOTS[1][0], SLOTS[2][0], SLOTS[3][0]]}
        v["instructions"] = ("Present all three options to the caller — say each one's day, date and time — then ask which one they want. "
                             "Never offer any other time. Record the option they choose.")
    d = pathlib.Path(f"chooseslot/arm{arm}"); (d / "scenarios").mkdir(parents=True, exist_ok=True)
    json.dump(f, open(d / "flow.json", "w"), indent=1)
    yaml.safe_dump({"params": {"from_number": "+12813056522", "phone_number": "+13473345222", "patient_first_name": "Carlos",
                     "patient_last_name": "Rivera", "missed_appointment_date": "08/29/2026"}, "substitutions": subs}, open(d / "params.yaml", "w"))
    yaml.safe_dump(scenario, open(d / "scenarios" / "first-slot.yaml", "w"), width=110)
    print(f"arm{arm}: {len(f['nodes'])} nodes, {len(f['edges'])} edges, selected_slot type =", next(v['type'] for n in f['nodes'] if n['id']==byname['Choose Slot']['uuid'] for v in n['data']['config']['agent_tasks']['variables'] if v['name']=='selected_slot'))
print("CHOOSE_SLOT_UUID=" + byname["Choose Slot"]["uuid"])
