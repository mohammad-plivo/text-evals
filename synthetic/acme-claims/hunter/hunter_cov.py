#!/usr/bin/env python3
"""Hunter harness for the Acme coverage flow on the local v29 stack.
  python3 hunter_cov.py <cookie> create            # create/update the 24 scenarios (clones 18428's mechanics)
  python3 hunter_cov.py <cookie> run --parallel 15 [--only cov-01,cov-07] [--repeat 1]
  python3 hunter_cov.py <cookie> check <run-id>    # per-call: judge + livekit marks + stored vars
"""
import base64, json, re, subprocess, sys, time, urllib.request
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from scenarios import SCENARIOS, EVIDENCE
BASE = "https://hunter.contactodev.com"; RUNNER_SHARE = "https://<runner-tunnel-host>"
FLOW = "23795122-798f-4b7a-b0e8-53ba8ae3ee26"; SOURCE_ID = "18428"; CAT = "acme-v29-local"; PREFIX = "Acme "
import os
DEV_FLOW = os.environ.get("DEV_FLOW")  # set to the pasted dev flow uuid: scenarios then target dev-runner-service via scenario 17551's trigger
if DEV_FLOW: SOURCE_ID = os.environ.get("DEV_SRC", "17551"); CAT = "acme-v29-dev"; PREFIX = "Acme dev "
NODES = {"b33134c9-c01f-43bf-8618-951cd75fca85": "Intake", "1c388cc4-90cf-44c4-895f-11b769fba16c": "Details", "8a80c9d5-f84f-4cf9-b926-f83803cd89d1": "Status"}

def psql(sql):
    return subprocess.run(["docker", "exec", "v29-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", sql], capture_output=True, text=True, check=True).stdout.strip()
def api(cookie, path, data=None, method=None):
    req = urllib.request.Request(BASE + path, method=method or ("POST" if data else "GET"))
    req.add_header("Cookie", cookie); req.add_header("Accept", "application/json")
    body = None
    if data is not None: body = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, body, timeout=60) as r: return json.load(r)
def all_scenarios(cookie):
    s = api(cookie, "/api/scenarios"); return s.get("scenarios", s) if isinstance(s, dict) else s
def name_of(sc): return PREFIX + sc["key"]

def create(cookie):
    src = api(cookie, f"/api/scenarios/{SOURCE_ID}")["payload"]
    if not DEV_FLOW:
        auth_id = psql("SELECT auth_id FROM organization;"); token = psql("SELECT auth_token FROM organization;")
        basic = "Basic " + base64.b64encode(f"{auth_id}:{token}".encode()).decode()
    existing = {s["name"]: s["id"] for s in all_scenarios(cookie)}
    for sc in SCENARIOS:
        p = json.loads(json.dumps(src))
        if DEV_FLOW:  # keep the dev scenario's trigger (host + auth headers) verbatim; only the flow uuid changes
            p["initiationRequest"]["url"] = re.sub(r"/flow/[0-9a-f-]+$", f"/flow/{DEV_FLOW}", p["initiationRequest"]["url"])
            if isinstance(p.get("agentConfig"), dict): p["agentConfig"]["flowId"] = DEV_FLOW
        else:
            p["initiationRequest"]["url"] = f"{RUNNER_SHARE}/v1/account/{auth_id}/flow/{FLOW}"
            p["initiationRequest"].setdefault("headers", {})["Authorization"] = basic
        p["initiationRequest"].setdefault("headers", {}).setdefault("Content-Type", "application/json")
        p["conversationPrompt"] = sc["persona"]
        p["evaluationPrompt"] = EVIDENCE + "\n".join(f"{i+1}. {c}" for i, c in enumerate(sc["criteria"]))
        p["maxTurns"] = 34; p["event"] = "acme_" + sc["key"].replace("-", "_"); p["testId"] = "voice-acme-" + sc["key"]
        new = {"name": name_of(sc), "description": ("Acme Insurance Claims Line coverage (dev, V2.9 #409): " if DEV_FLOW else "Acme Insurance Claims Line coverage (local phlo 10, V2.9): ") + sc["key"], "category": CAT, "payload": p}
        if name_of(sc) in existing: api(cookie, f"/api/scenarios/{existing[name_of(sc)]}", new, method="PUT"); print("updated", existing[name_of(sc)], sc["key"])
        else: sid = api(cookie, "/api/scenarios", new)["id"]; print("created", sid, sc["key"])

def run(cookie, parallel, only, repeat, interval=0):
    runs = api(cookie, "/api/runs?limit=12"); runs = runs["runs"] if isinstance(runs, dict) else runs
    busy = [r for r in runs if r.get("status") in ("running", "queued", "pending", "in_progress")]
    if busy: sys.exit("pod busy: " + json.dumps([(r.get("id"), r.get("name"), r.get("status")) for r in busy])[:300])
    ids = {s["name"]: s["id"] for s in all_scenarios(cookie) if s.get("category") == CAT}
    keys = [sc["key"] for sc in SCENARIOS if not only or any(sc["key"].startswith(o) for o in only)]
    sids = [str(ids[PREFIX + k]) for k in keys] * repeat
    r = api(cookie, "/api/runs", {"name": f"acme v29 coverage @{parallel} x{repeat}", "scenarioIds": sids, "maxParallel": parallel, "intervalSeconds": interval})
    rid = r["runId"]; open("last_run_id.txt", "a").write(rid + "\n"); print("run:", rid, BASE + "/dashboard/runs/" + rid, "|", len(sids), "calls @", parallel, "interval", interval, flush=True)
    deadline = time.time() + 560
    while time.time() < deadline:
        time.sleep(60); r = api(cookie, f"/api/runs/{rid}")
        st = [i.get("status") for i in (r.get("items") or [])]; print(time.strftime("%H:%M:%S"), r["status"], {s: st.count(s) for s in set(st)}, flush=True)
        if r["status"] in ("completed", "failed", "stopped", "cancelled", "error"): break
    return rid

def check(cookie, rid, since):
    r = api(cookie, f"/api/runs/{rid}"); print("run", rid, r["status"])
    raw = subprocess.run(["docker", "logs", "v29-livekit", "--since", since], capture_output=True, text=True); ev = []
    for line in (raw.stdout + raw.stderr).splitlines():
        try: ev.append(json.loads(line))
        except Exception: pass
    # correlate Hunter call -> runner trigger (same phone_number, nearest time) -> livekit call (flow_run_uuid)
    rr = subprocess.run(["docker", "logs", "-t", "v29-runner", "--since", since], capture_output=True, text=True)
    trig = []
    for line in (rr.stdout + rr.stderr).splitlines():
        m = re.search(r"^(\S+) .*enqueiuing phlo run .*phlo: " + FLOW + r", phlo_run_uuid: ([0-9a-f-]{36}) with payload: \{[^}]*'phone_number': '(\+?\d+)'", line)
        if m:
            ts = time.mktime(time.strptime(m.group(1)[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            trig.append((m.group(2), m.group(3), ts))
    by_run = {}; t_act = {}; t_close = {}
    for j in ev:
        m = re.search(r"flow_run_uuid='([0-9a-f-]{36})'", j.get("message", ""))
        if m and j.get("call_uuid"): by_run.setdefault(m.group(1), j["call_uuid"])
        if j.get("call_uuid") and j.get("message", "").startswith("call.lifecycle phase=session_active"): t_act[j["call_uuid"]] = time.mktime(time.strptime(j["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
        if j.get("call_uuid") and j.get("message", "").startswith("call.lifecycle phase=session_closed"): t_close[j["call_uuid"]] = time.mktime(time.strptime(j["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    lk_dur = {cu: t_close.get(cu, 0) - t_act[cu] for cu in t_act}
    used = set()
    rows = []
    for it in sorted(r["items"], key=lambda i: -(i.get("duration_ms") or 0)):
        c = api(cookie, f"/api/calls/{it['call_id']}") if it.get("call_id") else {}
        ph = (c.get("phone_number") or "").replace("+", ""); cu = None
        st = c.get("started_at") or 0; hd = (c.get("duration_ms") or 0) / 1000
        cands = sorted((abs(ts - st) + abs(lk_dur.get(by_run[fr_], 0) - hd) / 2, fr_) for fr_, pn, ts in trig if pn.replace("+", "") == ph and fr_ in by_run and by_run[fr_] not in used and abs(ts - st) < 900)
        if cands and cands[0][0] < 120: cu = by_run[cands[0][1]]; used.add(cu)
        e = [j for j in ev if j.get("call_uuid") == cu] if cu else []
        tools = [(re.search(r"tool=(\w+)", j["message"]).group(1), j["message"]) for j in e if j["message"].startswith("Tool call tool=")]
        ci = []
        for t, m in tools:
            if t == "collect_input":
                # the logger truncates arguments at 256 chars; read the leading fields by regex
                g = lambda k: (re.search(r'"%s": "([^"]*)"' % k, m) or [None, None])[1]
                args = {"name": g("name"), "task_type": g("task_type"), "known_value": g("known_value")}
                ci.append(f"{args.get('task_type')}:{args.get('name')}" + ("*" if args.get("known_value") else ""))
        conf = [t for t, _ in tools if t.startswith("confirm_")]; hand = [t for t, _ in tools if t.startswith("handoff_")]
        acts = [t for t, _ in tools if t in ("lookup_policy", "create_claim", "claim_status")]
        errs = [j["message"][:80] for j in e if (j.get("level") == "ERROR" or "Traceback" in j.get("message", "")) and "Failed to bill" not in j.get("message", "")]
        idle = sum(1 for j in e if "sending reminder" in j.get("message", ""))
        caps = sum(1 for j in e if "maximum number of function calls steps" in j.get("message", ""))
        warns = [j["message"][:110] for j in e if j.get("message", "").startswith("collect_input: ") and j.get("level") in ("WARNING", "ERROR")]
        close = next((j["message"][:90] for j in e if any(k in j.get("message", "") for k in ("Flow loop: session closing", "End conversation with message", "idle retries exhausted", "setup_failed"))), "")
        fr = next((re.search(r"flow_run_uuid='([0-9a-f-]+)'", j["message"]).group(1) for j in e if "flow_run_uuid='" in j.get("message", "")), None)
        stored = {}
        if fr:
            for nu, nn in NODES.items():
                out = subprocess.run(["docker", "exec", "v29-redis", "redis-cli", "HGETALL", f"PHLORUN:{fr}:NODEUUID:{nu}:VARS"], capture_output=True, text=True).stdout.split("\n")
                d = {out[i]: out[i + 1][:24] for i in range(0, len(out) - 1, 2) if out[i] and out[i] not in ("lookup_policy", "create_claim", "claim_status", "voicemail_detected")}
                if d: stored[nn] = d
        eb = c.get("eval_breakdown_json"); eb = json.loads(eb) if isinstance(eb, str) else (eb or {})
        failed = [l.strip()[:160] for l in eb.get("criteria", []) if "[MET]" not in l and "[N/A]" not in l]
        print(f"\n== {it.get('scenario_name')} | {it.get('result')} {it.get('score')} turns={it.get('turn_count')} | lk={cu and cu[:8]} err={it.get('error_message') or ''}")
        # R9: per invocation. The collect_input completion line is logged AFTER the router's own lines and the
        # collector's tool calls, so each invocation's window is the log between the previous completion and this one:
        # guarded = the router's on-record line for this name is in the window; audible = a collector tool spoke in it.
        seen = set(); reroutes = guarded = audible = 0; msgs = [j.get("message", "") for j in e]; prev = 0
        for i, m in enumerate(msgs):
            if not m.startswith("Tool call tool=collect_input"): continue
            nm = (re.search(r'"name": "([^"]*)"', m) or [None, None])[1]; window = msgs[prev:i]; prev = i + 1
            if nm in seen:
                reroutes += 1
                if any(f"collect_input: {nm} (" in m2 and "already on record" in m2 for m2 in window): guarded += 1
                elif any(m2.startswith("Tool call tool=") and re.search(r"tool=(update_|confirm_|decline_)", m2) for m2 in window): audible += 1
            seen.add(nm)
        recollects = reroutes; handed = sum(1 for j in e if "handed back" in j.get("message", ""))
        na = sum(1 for l in eb.get("criteria", []) if "[N/A]" in l); exercised_fail = len(failed)
        print(f"   collect_input({len(ci)}): {ci}\n   confirms: {conf} | actions: {acts} | handoff: {hand} | idle_reminders: {idle} | cap_hits: {caps} | re-routes: {reroutes} (guarded {guarded}, audible {audible}, other {reroutes - guarded - audible}) | hand_backs: {handed} | criteria not exercised: {na} | errors: {errs[:2]}")
        if warns: print(f"   router: {warns[:3]}")
        if close: print(f"   close: {close}")
        print(f"   stored: {stored}")
        for f in failed: print("   FAILED:", f)
        rows.append((it.get("scenario_name"), it.get("result"), it.get("score"), len(ci), len(errs), caps, reroutes, guarded, handed, audible, na))
    ex_pass = sum(1 for x in rows if x[1] == "pass" and x[10] == 0); pass_na = sum(1 for x in rows if x[1] == "pass" and x[10] > 0)
    print("\n== summary:", sum(1 for x in rows if x[1] == "pass"), "pass /", len(rows), f"(exercised pass {ex_pass}, pass with not-exercised criteria {pass_na})", "| calls with 0 collect_input:", sum(1 for x in rows if x[3] == 0), "| calls with errors:", sum(1 for x in rows if x[4]), "| calls with cap hits:", sum(1 for x in rows if x[5]), "| re-routes:", sum(x[6] for x in rows), "(guarded", sum(x[7] for x in rows), "audible", sum(x[9] for x in rows), ") | hand_backs:", sum(x[8] for x in rows))

if __name__ == "__main__":
    cookie = open(sys.argv[1]).read().strip(); mode = sys.argv[2]
    print("auth:", api(cookie, "/api/auth/me").get("user", {}).get("email", "ok"))
    if mode == "create": create(cookie)
    elif mode == "run":
        par = int(sys.argv[sys.argv.index("--parallel") + 1]) if "--parallel" in sys.argv else 4
        only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else []
        rep = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 1
        itv = int(sys.argv[sys.argv.index("--interval") + 1]) if "--interval" in sys.argv else 0
        run(cookie, par, only, rep, itv)
    elif mode == "check":
        check(cookie, sys.argv[3], sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "90m")
