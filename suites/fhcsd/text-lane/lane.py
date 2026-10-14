"""Leader text lane: Hunter-style scenarios as text conversations through the real Jev leader in the sim runner.

  python3 lane.py convert [--only SLUG ...]          sim-fh twins -> pack/<slug>/ (restamped dates, synthesized rubric)
  python3 lane.py preflight                         fail-closed checks, no spend
  python3 lane.py run --campaign NAME --campaign-cap USD --only SLUG ... [--repeat N] [--run-usd 2.0] [--max-parallel 2]
  python3 lane.py rejudge CAMPAIGN SLUG [--pack PACK] [--judge-usd 1.0]   grade the stored runs again; only the judge is paid
  python3 lane.py board runs/<campaign>

General flows (no custom_code, no FHCSD mock: every action answers from its sim mock or contract mock result):
  python3 lane.py preflight --flow-ws WS --pack PACK
  python3 lane.py run --flow-ws WS --pack PACK --campaign NAME --campaign-cap USD --only SLUG ...   rows land in PACK/../runs
  WS/flow.json is the flow; PACK/<slug>/{scenario.yaml, params.yaml, spec.json}, spec keys as convert writes them, plus
  expect_saved {field: {op: value}} with an op from judge_lane.RULES, and expect_unsaved [field]. The clinic-day canary, IST window,
  flow-db dump and E2B key are skipped; the tree, intents, env, ledger and every per-run validity check are not.

Every run: a private redis, the lane env, the wire meter, a ledger reservation before and a settle after
(meter.py), a structured trace and the judge (run_one.py, judge_lane.py). A run whose first Jev fault lands before
the caller's first line is run once more and its row says so. Scripts, packs and runs live in
v2.9.1-jev/text-evals (a reboot wiped the scratchpad copy on 1 Oct); the env file with keys goes to a private temp dir.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

LANE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LANE)
import judge_lane  # noqa: E402
import meter  # noqa: E402

ROOT = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner"
TREE = os.environ.get("LANE_TREE") or f"{ROOT}/v2.9.1-jev/rw-text-lane"
FLOW = os.path.join(LANE, "flows", "fhcsd-472875c4", "flow.json")
FLOW_DB = os.path.join(LANE, "flow-db")
FLOW_ID = "472875c4-6044-45f8-a145-087c10bb82a0"
NODE = "518895a9-dd2c-4128-b050-36f39b463c4c"
PACK, RUNS = os.path.join(LANE, "pack"), os.path.join(LANE, "runs")
SIMFH_WS = f"{ROOT}/v29-revamp/stress-evals/sim-fh/ws"
OLD_PAYLOAD = f"{ROOT}/FHCSD/hunter/v29/scenarios/01-happy-first-slot.json"
WORKER_JS = f"{ROOT}/FHCSD/mock-real/worker.js"
LIVEKIT_ENV = f"{ROOT}/repos/cx-dev-dockerized-v291-jev/services/plivo-cx-livekit/.env"
JEV_ENV = f"{ROOT}/v2.9.1-jev/.jev-env"
MOCK_HOST = "fhcsd-mock-real.<your-account>.workers.dev"
REQUIRED_ENV = ("TYPESAFE_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "LIVEKIT_INFERENCE_API_KEY",
                "LIVEKIT_INFERENCE_API_SECRET", "E2B_API_KEY", "REDIS_URL")
TOOLS = ["fhcsd_match_patient_fresh_auth", "fhcsd_get_patient_appointments_fresh_auth",
         "fhcsd_search_available_appointments_fresh_auth", "fhcsd_reschedule_appointment_fresh_auth"]
TIMES = ["09:30 AM", "11:00 AM", "03:45 PM"]
NOAPPT = {"achterberg", "noappt"}
# the option each booking twin's caller finally takes, read from its persona; the judge books offers[option-1] of the last search
BOOK_OPTION = {**dict.fromkeys(
    ["L-happy-first-slot", "L-none-of-these-then-date", "L-one-slot-returned", "L-two-values-one-breath", "L-closure-followup-question",
     "L-dob-corrected-after-stating", "L-dob-misheard-then-correct", "L-dob-partial-then-complete", "L-interrupts-readback",
     "L-asks-cost-midwalk", "L-details-before-verification", "L-mildly-annoyed-not-upset", "L-preferred-weekend-date",
     "L-asks-second-appointment"], 1),
    "L-happy-second-slot": 2, "L-two-slots-returned": 2, "L-slot-hesitation": 2, "L-slot-corrected-after-choosing": 3}
BOOK_KEYS = ["appointment_date", "from_slot_id", "prov_schedule_id"]
ACCEPT_EXITS = {"L-upset": ["Patient Upset", "Do Not Call"],  # C1: "stop calling me" fits Do Not Call too
                "L-reschedule-callback-later": ["Callback Requested"],  # MK 30 Sep: "call me next week" is a callback
                "L-no-appointment-on-file": ["No Missed Appointment", "Conflict Or API Failure"]}  # local route for an empty lookup
# a machine greets once and then records silence; a simulated caller has to answer every turn
MACHINE = {"L-voicemail": "Hi, you've reached the Mendes family. Please leave a message after the beep."}
# local exits checked against the pack's expectations; a new local intent fails preflight until it is listed here
REVIEWED_INTENTS = {"Rescheduled", "Declined", "No Availability", "Verification Failed", "Conflict Or API Failure",
                    "Emergency Mentioned", "Patient Upset", "Human Requested", "Do Not Call",
                    "Callback Requested", "Caller Requested End", "No Missed Appointment"}
UA = "curl/8.4.0"  # the mock's edge refuses urllib's default agent

# The mock's clock (America/Los_Angeles) dates the data; the persona names a Monday 7-13 days out (align_dev_board.py).
T = datetime.now(ZoneInfo("America/Los_Angeles")).date()
PREF = T + timedelta(days=7)
PREF += timedelta(days=(7 - PREF.weekday()) % 7)
TWIN_PREF = date(2026, 9, 28)  # the Monday the 19-21 Sep twins were written around
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
SPOKEN = re.compile(r"(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) )?the (\d{1,2})(?:st|nd|rd|th) of "
                    r"(" + "|".join(MONTHS) + r")")
SLOT = re.compile(r"(" + "|".join(MONTHS) + r") (\d{1,2}), (\d{4}) at (\d{2}:\d{2} [AP]M)")


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def long(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def restamp(text: str) -> str:
    """Move every spoken date by whole weeks so the twins' Monday becomes PREF and weekday names stay true."""
    delta = PREF - TWIN_PREF

    def move(m):
        d = date(2026, MONTHS.index(m.group(3)) + 1, int(m.group(2))) + delta
        return (f"{d:%A} " if m.group(1) else "") + f"the {ordinal(d.day)} of {d:%B}"
    return SPOKEN.sub(move, text)


def caller_dates(persona: str) -> list[str]:
    """Every "the 12th of October" the caller is scripted to say, in order (dates of birth are spoken in words)."""
    out = []
    for m in SPOKEN.finditer(persona):
        d = date(T.year, MONTHS.index(m.group(3)) + 1, int(m.group(2)))
        out.append((d if d >= T - timedelta(days=30) else d.replace(year=T.year + 1)).isoformat())
    return out


def record_block(last: str) -> str:
    """The clinic record in align_dev_board.py's wording; the slots come from the call's own searches at judge time."""
    head = "THE CLINIC RECORD. These are the only true facts on this call; any other date, time, provider or facility the agent states is invented:\n"
    if last in NOAPPT:
        return head + ("- the clinic has NO appointment on file for this patient: there is nothing to move, and any "
                       "appointment, date, time, provider, facility or slot the agent states as this patient's is invented.\n")
    later = T + timedelta(days=14)
    body = (f"- the ONE appointment the patient missed: {long(T)} at 10:30 AM with Dr. Rismiller at Logan Heights Family "
            f"Health Center. The patient also has a later appointment on file, {long(later)} at 02:15 PM with Dr. Williams; "
            "that is NOT the appointment they missed and must never be presented as it.\n")
    return head + body + judge_lane.SLOT_RECORD + "\n"


def passcode() -> str:
    return open(WORKER_JS).read().split('const PASSCODE = "')[1].split('"')[0]  # the mock's documented constant


# ---------------------------------------------------------------- convert

def twin_path(slug: str) -> str:
    hits = glob.glob(os.path.join(SIMFH_WS, "*", "scenarios", slug + ".yaml"))
    if len(hits) != 1:
        raise SystemExit(f"{slug}: {len(hits)} twins found")
    return hits[0]


def convert(slug: str) -> dict:
    path = twin_path(slug)
    twin = yaml.safe_load(open(path))
    params = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(path)), "params.yaml")))["params"]
    desc = twin["description"]
    su = twin["simulated_user"]
    persona, goal = restamp(su["persona"]), restamp(su["goal"])
    crit = desc.split("criteria:", 1)[1].strip() if "criteria:" in desc else desc
    crit = SLOT.sub(lambda m: (f"option {TIMES.index(m.group(4)) + 1} in THE CLINIC RECORD above ({m.group(4)} on the date "
                               f"the record gives for option {TIMES.index(m.group(4)) + 1})") if m.group(4) in TIMES else m.group(0), crit)
    old = json.load(open(OLD_PAYLOAD))["payload"]["evaluationPrompt"]
    last = params["last_name"].lower()
    dates = caller_dates(persona)
    rubric = (old[:old.index("THE CLINIC RECORD.")] + record_block(last) +
              old[old.index("Treat phonetic renderings"):old.index("Evaluate these criteria:")] + "Evaluate these criteria:\n" + crit)
    exit_ = (twin.get("expect") or {}).get("intent")
    expect = ACCEPT_EXITS.get(slug) or exit_
    option = BOOK_OPTION.get(slug)
    expect_tools, forbid, rule = [], [], []
    if "NOT give your date of birth" in persona:
        forbid, rule = list(TOOLS), ["never gives a date of birth: no tool may run"]
    elif exit_ == "Verification Failed":
        forbid, rule = TOOLS[2:], ["verification fails: no search, no booking"]
    elif exit_ in ("Declined", "No Availability", "Human Requested", "Emergency Mentioned", "Patient Upset"):
        forbid, rule = TOOLS[3:], [f"exit {exit_}: no booking"]
    if option:
        expect_tools = [
            {"tool": TOOLS[0], "args": {"first_name": {"ci": params["first_name"]}, "last_name": {"ci": params["last_name"]},
                                        "date_of_birth": {"date": params["date_of_birth"]}, "phone_number": {"digits": params["phone_number"]}}},
            {"tool": TOOLS[1], "args": {}},
            {"tool": TOOLS[2], "caller_dates": dates},
            {"tool": TOOLS[3], "option": option, "offer_keys": BOOK_KEYS},
        ]
        rule.append(f"booking walk: all four tools, option {option} of the last search booked once")
    caller = ({"turns": [{"user": MACHINE[slug]}] + [{"idle": True}] * 3} if slug in MACHINE
              else {"simulated_user": {**su, "persona": persona, "goal": goal}})
    scenario = {"description": f"Lane twin of sim-fh {slug} (restamped {date.today()}): {desc.split(chr(10))[0][:300]}",
                **caller, "real_actions": list(TOOLS), "action_envs": {"FHCSD_PASSCODE": passcode()},
                "expect": {"intent": expect} if isinstance(expect, str) else {"ended": True}}
    screening = slug.startswith("L-screening") or slug in ("L-voicemail", "L-wrong-person-spouse")
    spec = {"slug": slug, "source": path, "rubric": rubric, "threshold": 0.8, "judge_model": "gpt-4.1",
            "expect_exit": expect, "expect_tools": expect_tools, "forbid_tools": forbid, "tools_rule": rule, "search_tool": TOOLS[2],
            # every twin enters at the flow entry: screening runs, then the V2.9 node, as on a call
            "idle_limit_s": 15, "entry": "flow", "hunter_entry": "screening" if screening else "scheduler", "caller_dates": dates,
            "clinic_day": T.isoformat(), "params": {k: v for k, v in params.items()}}
    out = os.path.join(PACK, slug)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "scenario.yaml"), "w") as fh:
        fh.write("# generated by text-lane/lane.py convert; mock passcode inline, never commit\n")
        yaml.safe_dump(scenario, fh, sort_keys=False, allow_unicode=True, width=110)
    with open(os.path.join(out, "params.yaml"), "w") as fh:
        yaml.safe_dump({"params": params, "substitutions": {}}, fh, sort_keys=False)
    json.dump(spec, open(os.path.join(out, "spec.json"), "w"), indent=1)
    os.chmod(os.path.join(out, "scenario.yaml"), 0o600)
    return spec


# ---------------------------------------------------------------- env, redis, preflight

def env_file(path: str, redis_url: str) -> str:
    lane = {"REDIS_URL": redis_url, "REDIS_IS_CLUSTER": "false", "E2B_POOL_KEEP_ALIVE_MS": "900000",  # the sandbox TIMEOUT: 60 s killed a booking at 65 s (dryrun-1 attempt 3)
            "JEV_TRACE_PROBS": "true",  # jev.request lines and full probabilities, so a decision's why is on record
            "TYPESAFE_API_KEY": open(JEV_ENV).read().split("TYPESAFE_API_KEY=", 1)[1].split("\n")[0].strip().strip('"')}
    keep = [ln for ln in open(LIVEKIT_ENV).read().splitlines()
            if "=" in ln and not ln.lstrip().startswith("#") and ln.split("=", 1)[0].strip() not in lane]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(keep + [f"{k}={v}" for k, v in lane.items()]) + "\n")
    return path


def env_values(path: str) -> dict:
    out = {}
    for ln in open(path):
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, _, v = ln.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def start_redis(dirname: str) -> tuple[int, int]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(["/opt/homebrew/bin/redis-server", "--port", str(port), "--bind", "127.0.0.1", "--save", "",
                             "--appendonly", "no", "--dir", dirname], stdout=open(os.path.join(dirname, "redis.log"), "w"),
                            stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2) as c:
                c.sendall(b"PING\r\n")
                if c.recv(16).startswith(b"+PONG"):
                    return proc.pid, port
        except OSError:
            time.sleep(0.1)
    os.kill(proc.pid, signal.SIGTERM)
    raise SystemExit("private redis did not start")


def mock_get(path: str, token: str | None = None, data: bytes | None = None, pc: str = ""):
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    if token:
        headers["x-my-authentication-token"] = token
    if pc:
        headers["fhcsd-external-passcode"] = pc
    req = urllib.request.Request(f"https://{MOCK_HOST}{path}", data=data, headers=headers, method="POST" if data else "GET")
    return json.load(urllib.request.urlopen(req, timeout=20))


def intent_failures(flow: dict, specs: list[dict], reviewed: set | None = REVIEWED_INTENTS) -> list[str]:
    local = {i.get("intent_name") for n in flow["nodes"] for i in (n["data"]["config"].get("intents") or [])}
    unreviewed = sorted(local - reviewed) if reviewed is not None else []  # None: the flow was built with its pack
    missing = sorted({x for s in specs for x in judge_lane.exits(s)} - local)
    return ([f"local intents not reviewed against the pack: {unreviewed}"] if unreviewed else []) + (
        [f"expected exits the local flow does not have: {missing}"] if missing else [])


def general_failures(flow: dict, scenarios: dict[str, dict], specs: list[dict]) -> list[str]:
    """A general flow runs on sim mocks only: custom code always runs for real in E2B, and real_actions bypass the mocks."""
    code = sorted({str(n.get("id"))[:8] for n in flow["nodes"] for a in (n["data"]["config"].get("actions") or [])
                   if a.get("action_type") == "CUSTOM_CODE" or MOCK_HOST in json.dumps(a)})
    real = sorted(s for s, sc in scenarios.items() if (sc or {}).get("real_actions") or (sc or {}).get("action_envs"))
    def graded(s: dict) -> bool:  # an op arg_ok does not know falls back to string equality: a certain red
        rules = [*(s.get("expect_saved") or {}).values(), *(r for t in s.get("expect_tools") or [] for r in (t.get("args") or {}).values())]
        return all(isinstance(r, dict) and len(r) == 1 and {*r} <= {*judge_lane.RULES} for r in rules)
    loose = sorted(str(s.get("slug")) for s in specs if not {"slug", "rubric", "entry"} <= s.keys() or not graded(s))
    return ([f"custom_code or the FHCSD mock on nodes {code}"] if code else []) + (
        [f"scenarios name real_actions or action_envs: {real}"] if real else []) + (
        [f"specs missing slug/rubric/entry, or a saved/tool rule outside {judge_lane.RULES}: {loose}"] if loose else []) + ([] if specs else ["the pack has no spec.json"])


def preflight(env_path: str | None = None, flow_ws: str | None = None, pack: str = PACK) -> dict:
    general = flow_ws is not None
    res, fail = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, []
    head = subprocess.run(["git", "-C", TREE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", TREE, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip()
    res["tree"] = {"path": TREE, "commit": head, "dirty": bool(dirty)}
    if dirty:
        fail.append("tree has uncommitted changes")
    flow = json.load(open(os.path.join(flow_ws, "flow.json") if general else FLOW))
    hosts, envs, kinds = set(), set(), set()
    for n in flow["nodes"]:
        for a in (n["data"]["config"].get("actions") or []):
            body = json.dumps(a)
            kinds.add(a.get("action_type"))
            hosts |= set(re.findall(r"https?://([A-Za-z0-9.\-]+)", a.get("code_body") or body))
            envs |= set(re.findall(r'environ(?:\.get)?\(\s*["\']([A-Z0-9_]+)', a.get("code_body") or ""))
    res["actions"] = {"kinds": sorted(map(str, kinds)), "hosts": sorted(hosts), "env_vars": sorted(envs)}
    specs = [json.load(open(f)) for f in glob.glob(os.path.join(pack, "*", "spec.json"))]
    if general:
        fail += general_failures(flow, {os.path.basename(os.path.dirname(f)): yaml.safe_load(open(f))
                                        for f in glob.glob(os.path.join(pack, "*", "scenario.yaml"))}, specs)
    elif hosts - {MOCK_HOST} or kinds - {"CUSTOM_CODE"}:
        fail.append(f"an action reaches beyond the mock: hosts {sorted(hosts)} kinds {sorted(map(str, kinds))}")
    res["intents"] = intent_failures(flow, specs, None if general else REVIEWED_INTENTS)
    fail += res["intents"]
    if general:
        res["flow"] = {"id": flow.get("flowId"), "path": flow_ws, "pack": pack, "scenarios": len(specs)}
        res["canary"] = "skipped: no custom_code, no FHCSD mock"
    else:
        fail += fhcsd_failures(res)
    if env_path:
        vals = env_values(env_path)
        missing = [k for k in REQUIRED_ENV if not vals.get(k) and not (general and k == "E2B_API_KEY")]
        res["env_missing"] = missing
        if missing:
            fail.append(f"env missing {missing}")
    led = meter._read()
    res["ledger"] = {"cap_usd": led["cap_usd"], "spent_usd": led["spent_usd"], "reserved_usd": led["reserved_usd"]}
    res["ok"], res["failures"] = not fail, fail
    return res


def fhcsd_failures(res: dict) -> list[str]:
    """The FHCSD-only checks: the flow still matches its dump, the mock's clinic day, the IST window."""
    fail, stale = [], []
    for f in glob.glob(os.path.join(FLOW_DB, "*-*-*-*-*.json")):
        uuid = os.path.basename(f)[:-5]
        live = subprocess.run(["docker", "exec", "jev-redis", "redis-cli", "--raw", "GET", f"PHLO:{FLOW_ID}:NODE:{uuid}:CONFIG"],
                              capture_output=True, text=True).stdout
        if live.strip() != open(f).read().strip():
            stale.append(uuid[:8])
    overlay = os.path.join(os.path.dirname(FLOW), "overlay.json")  # approved flow edits the lane copy carries ahead of the local stack
    res["flow"] = {"id": FLOW_ID, "nodes_dumped": len(glob.glob(os.path.join(FLOW_DB, "*-*-*-*-*.json"))), "changed_since_dump": stale,
                   "lane_overlay": json.load(open(overlay)) if os.path.exists(overlay) else []}
    if stale:
        fail.append(f"local flow changed since the dump: {stale}; re-dump and rebuild")
    try:
        token = mock_get("/api/ExternalAccess/AuthenticateVendor", data=b"{}", pc=passcode())[0]["VendorToken"]
        pts = mock_get("/api/Druid/GetPatients?FirstName=Carlos&LastName=Rivera&DOB=02%2F18%2F1977&Phone=6195550016", token)
        appts = mock_get(f"/api/Druid/GetPatientAppointments?MasterId={pts[0]['MasterId']}", token)
        first = min(datetime.strptime(a["AppointmentDate"], "%m/%d/%Y").date() for a in appts)
        res["canary"] = {"ok": len(pts) == 1 and first == T, "patients": len(pts), "api_appointment": first.isoformat(), "clinic_day": T.isoformat()}
    except Exception as exc:
        res["canary"] = {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if not res["canary"]["ok"]:
        fail.append(f"mock canary: {res['canary']}")
    ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    res["ist"] = ist.strftime("%H:%M")
    if not ((ist.hour, ist.minute) >= (12, 30)):
        fail.append("outside the 12:30-23:59 IST window (mock day, agent clock and judge disagree)")
    res["dates"] = {"clinic_day": T.isoformat(), "look_from": PREF.isoformat()}
    return fail


# ---------------------------------------------------------------- run

def run_argv(slug: str, out: str, env_path: str, spec_path: str, budget: float) -> list[str]:
    return [os.path.join(TREE, ".venv", "bin", "python"), os.path.join(LANE, "run_one.py"), "--tree", TREE,
            "--ws", os.path.join(out, "ws"), "--scenario", slug, "--env-file", env_path, "--out", out,
            "--budget", str(budget), "--spec", spec_path]


def launch(argv: list[str], out: str, timeout: int, prefix: str = "") -> str | None:
    """One run_one.py process on the lane tree, logging to <out>/<prefix>stdout.log and stderr.log; returns why it
    was stopped, if it was."""
    with open(os.path.join(out, prefix + "stdout.log"), "w") as so, open(os.path.join(out, prefix + "stderr.log"), "w") as se:
        proc = subprocess.Popen(argv, stdout=so, stderr=se, cwd=TREE, start_new_session=True,
                                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.kill(proc.pid, signal.SIGTERM)
            proc.wait(timeout=30)
            return f"timed out after {timeout}s"
    return None


def judged(row: dict, out: str, labels: dict) -> dict:
    """The row's verdict, read from the run's judge.json; a run that left none is INVALID for the reason the row has."""
    path = os.path.join(out, "judge.json")
    j = json.load(open(path)) if os.path.exists(path) else {}
    reasons = j.get("invalid_reasons")  # an empty list is a valid run, not a missing judge
    return {**row, "verdict": j.get("verdict") or "INVALID", "score": j.get("score"), "verified_score": j.get("verified_score"),
            "rubric_verdict": j.get("rubric_verdict"), "checks_failed": j.get("checks_failed"),
            "invalid_reasons": reasons if reasons is not None else [row.get("why") or "no judge output"],
            "overturned": j.get("overturned") or [],
            "not_met": [c.get("n") for c in j.get("criteria") or [] if not c.get("met")],
            "proof": {**(j.get("proof") or {}), **labels}}


def attempt(slug: str, rep: int, camp: str, env_path: str, args) -> dict:
    spec = json.load(open(os.path.join(args.pack, slug, "spec.json")))
    out = os.path.join(camp, f"{slug}-r{rep}")
    ws = os.path.join(out, "ws")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(ws, "scenarios"))
    shutil.copy(os.path.join(args.flow_ws, "flow.json") if args.flow_ws else FLOW, os.path.join(ws, "flow.json"))
    shutil.copy(os.path.join(args.pack, slug, "params.yaml"), os.path.join(ws, "params.yaml"))
    shutil.copy(os.path.join(args.pack, slug, "scenario.yaml"), os.path.join(ws, "scenarios", slug + ".yaml"))
    spec_path = shutil.copy(os.path.join(args.pack, slug, "spec.json"), out)  # a later regrade reads the spec this run had
    row = {"scenario": slug, "run": rep, "dir": out}
    try:
        entry = meter.reserve(args.campaign, f"{slug}-r{rep}", args.run_usd, args.campaign_cap)
    except meter.Refused as exc:
        return {**row, "verdict": "NOT RUN", "why": str(exc)}
    argv = run_argv(slug, out, env_path, spec_path, args.run_usd - 0.1)
    if spec["entry"] not in ("flow", "screening"):
        argv += ["--node", spec["entry"]]
    t0 = time.time()
    if why := launch(argv, out, args.timeout):
        row["why"] = why
    actual, by = meter.settle_from_meter(os.path.join(out, "meter.jsonl"))
    meter.settle(entry, actual, {"by_dest": by, "run": f"{slug}-r{rep}"})
    labels = {"gemma_label": 0, "azure_label": 0}
    for ln in open(os.path.join(out, "stderr.log"), errors="replace"):
        labels["gemma_label"] += "livekit.agents.inference.llm.LLM" in ln
        labels["azure_label"] += "livekit.plugins.openai.llm.LLM" in ln
    return judged({**row, "cost_usd": actual, "cost_by_dest": by, "reserved_usd": args.run_usd,
                   "seconds": round(time.time() - t0)}, out, labels)


def start_fault(out: str) -> bool:
    """A Jev fault recorded before the caller's first line: a start-up blip outside the agent, not evidence about it."""
    path = os.path.join(out, "trace.json")
    for e in json.load(open(path))["events"] if os.path.exists(path) else ():
        if e["kind"] == "line" and e["role"] == "caller":
            return False
        if e["kind"] == "log" and e["msg"].startswith("jev.fault_recorded"):
            return True
    return False


def one(slug: str, rep: int, camp: str, env_path: str, args) -> dict:
    row = attempt(slug, rep, camp, env_path, args)
    if not start_fault(row["dir"]):
        return row
    kept = row["dir"] + ".start-fault"  # the first attempt's evidence; no row.json, so the board skips it
    shutil.rmtree(kept, ignore_errors=True)
    os.replace(row["dir"], kept)
    first = {"dir": kept, "cost_usd": row.get("cost_usd"), "invalid_reasons": row.get("invalid_reasons")}
    return {**attempt(slug, rep, camp, env_path, args), "rerun_after_start_fault": True, "first_attempt": first}


def rejudge(camp: str, slug: str, env_path: str, args) -> list[dict]:
    """Grade the stored runs of one scenario again from their trace, sim report and spec: only the judge is paid."""
    rows = []
    for path in sorted(glob.glob(os.path.join(camp, "*", "row.json"))):
        row, out = json.load(open(path)), os.path.dirname(path)
        if row["scenario"] != slug or not os.path.exists(os.path.join(out, "trace.json")):
            continue
        stored = os.path.join(out, "spec.json")  # runs before the spec was stored fall back to the pack's
        spec_path = stored if os.path.exists(stored) else os.path.join(args.pack, slug, "spec.json")
        wire, verdict = os.path.join(out, "rejudge-meter.jsonl"), os.path.join(out, "judge.json")
        if os.path.exists(wire):
            os.remove(wire)
        if os.path.exists(verdict):  # set aside, so a regrade that dies cannot pass the old verdict off as new
            os.replace(verdict, os.path.join(out, "judge.prev.json"))
        label = f"{slug}-r{row['run']}-rejudge"
        entry = meter.reserve(os.path.basename(camp), label, args.judge_usd)
        why = launch(run_argv(slug, out, env_path, spec_path, args.judge_usd) + ["--judge-only"], out, args.timeout, "rejudge.")
        actual, by = meter.settle_from_meter(wire)
        meter.settle(entry, actual, {"by_dest": by, "run": label})
        labels = {k: (row.get("proof") or {}).get(k) for k in ("gemma_label", "azure_label")}
        row = judged({**row, "dir": out, "rejudge_usd": actual, **({"why": why} if why else {})}, out, labels)
        json.dump(row, open(path, "w"), indent=1)
        rows.append(row)
    return rows


def board(camp: str) -> dict:
    rows = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(camp, "*", "row.json")))]
    pre = json.load(open(os.path.join(camp, "preflight.json"))) if os.path.exists(os.path.join(camp, "preflight.json")) else {}
    led = meter._read()
    doc = {"campaign": os.path.basename(camp), "preflight": pre, "rows": rows,
           "totals": {"runs": len(rows), "pass": sum(r["verdict"] == "PASS" for r in rows),
                      "fail": sum(r["verdict"] == "FAIL" for r in rows), "invalid": sum(r["verdict"] == "INVALID" for r in rows),
                      "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4)},
           "ledger": {"cap_usd": led["cap_usd"], "spent_usd": led["spent_usd"], "reserved_usd": led["reserved_usd"]}}
    json.dump(doc, open(os.path.join(camp, "board.json"), "w"), indent=1)
    md = [f"# Board: {doc['campaign']}", "",
          f"Tree {pre.get('tree', {}).get('commit', '?')[:9]}, flow {str(pre.get('flow', {}).get('id', FLOW_ID))[:8]}"
          + (f", clinic day {pre['dates'].get('clinic_day')}, look-from {pre['dates'].get('look_from')}" if pre.get("dates") else "")
          + f". {doc['totals']['pass']} pass, {doc['totals']['fail']} fail, "
          f"{doc['totals']['invalid']} invalid of {doc['totals']['runs']} runs. Cost ${doc['totals']['cost_usd']:.4f}. "
          f"Ledger ${led['spent_usd']:.4f} spent of ${led['cap_usd']:.0f}.", "",
          "| Scenario | Verdict | Rubric (min) | Overturned on re-read | Failed checks | Cost | Jev asks / faults | "
          "Gemma served_by (requests) | E2B |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        p = r.get("proof") or {}
        rerun = " (rerun after a start-up fault)" if r.get("rerun_after_start_fault") else ""
        md.append(f"| {r['scenario']} r{r['run']}{rerun} | {r['verdict']} | {r.get('score')} | "
                  f"{', '.join(f'criterion {n}' for n in r.get('overturned') or []) or '-'} | "
                  f"{', '.join(r.get('checks_failed') or []) or '-'} | "
                  f"${(r.get('cost_usd') or 0):.4f} | {p.get('jev_asks')} / {len(p.get('jev_faults') or [])} | "
                  f"{', '.join(p.get('gemma_served_by') or []) or '-'} ({p.get('gemma_requests')}) | {p.get('e2b_executions')} |")
    for r in rows:
        if r.get("invalid_reasons") and r["verdict"] == "INVALID":
            md.append(f"\n{r['scenario']} r{r['run']} is INVALID: {'; '.join(r['invalid_reasons'])}")
    open(os.path.join(camp, "board.md"), "w").write("\n".join(md) + "\n")
    return doc


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--only", nargs="*", default=[])
    p = sub.add_parser("preflight")
    r = sub.add_parser("run")
    for x in (p, r):
        x.add_argument("--flow-ws", help="a general flow's sim workspace (WS/flow.json); needs its own --pack")
        x.add_argument("--pack", default=PACK)
    r.add_argument("--campaign", required=True)
    r.add_argument("--campaign-cap", type=float, required=True)
    r.add_argument("--only", nargs="+", required=True)
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--run-usd", type=float, default=2.0, help="reservation per run (sim + judge), conservative")
    r.add_argument("--max-parallel", type=int, default=2)
    r.add_argument("--timeout", type=int, default=1200)
    j = sub.add_parser("rejudge")
    j.add_argument("campaign")
    j.add_argument("scenario")
    j.add_argument("--pack", default=PACK)
    j.add_argument("--judge-usd", type=float, default=1.0, help="reservation per regrade (the judge and its re-read)")
    j.add_argument("--timeout", type=int, default=300)
    b = sub.add_parser("board")
    b.add_argument("dir")
    a = ap.parse_args()
    if getattr(a, "flow_ws", None) and a.pack == PACK:
        ap.error("--flow-ws needs its own --pack")
    if a.cmd == "convert":
        slugs = a.only or sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(SIMFH_WS, "*", "scenarios", "L-*.yaml")))
        for s in slugs:
            spec = convert(s)
            print(f"{s:40} exit={spec['expect_exit']!s:24} dates={spec['caller_dates']} tools={len(spec['expect_tools'])} forbid={len(spec['forbid_tools'])}")
        return
    if a.cmd == "preflight":
        print(json.dumps(preflight(flow_ws=a.flow_ws, pack=a.pack), indent=1))
        return
    if a.cmd == "board":
        print(open(os.path.join(a.dir, "board.md")).read() if board(a.dir) else "")
        return
    camp = os.path.join(RUNS if a.pack == PACK else os.path.join(os.path.dirname(os.path.abspath(a.pack)), "runs"), a.campaign)
    if a.cmd == "rejudge":
        env_dir = tempfile.mkdtemp(prefix="lane-env-")  # keys never land in the lane folder
        try:
            for row in rejudge(camp, a.scenario, env_file(os.path.join(env_dir, "run.env"), ""), a):
                print(f"{row['verdict']:8} {row['scenario']} r{row['run']} score={row.get('score')} "
                      f"judge=${row['rejudge_usd']} failed={row.get('checks_failed')}", flush=True)
        finally:
            shutil.rmtree(env_dir, ignore_errors=True)
        print(open(os.path.join(camp, "board.md")).read() if board(camp) else "")
        return
    os.makedirs(camp, exist_ok=True)
    pid, port = start_redis(camp)
    env_dir = tempfile.mkdtemp(prefix="lane-env-")  # keys never land in the lane folder
    try:
        env_path = env_file(os.path.join(env_dir, "run.env"), f"redis://127.0.0.1:{port}/0")
        pre = preflight(env_path, a.flow_ws, a.pack)
        json.dump(pre, open(os.path.join(camp, "preflight.json"), "w"), indent=1)
        print(f"preflight ok={pre['ok']} tree={pre['tree']['commit'][:9]} canary={pre['canary']} ledger={pre['ledger']} {pre['failures']}", flush=True)
        if not pre["ok"]:
            raise SystemExit("preflight failed; nothing ran")
        jobs = [(s, i) for s in a.only for i in range(1, a.repeat + 1)]
        with cf.ThreadPoolExecutor(max_workers=a.max_parallel) as ex:
            for row in ex.map(lambda j: one(j[0], j[1], camp, env_path, a), jobs):
                if row.get("dir"):
                    json.dump(row, open(os.path.join(row["dir"], "row.json"), "w"), indent=1)
                print(f"{row['verdict']:8} {row['scenario']} r{row['run']} score={row.get('score')} cost=${row.get('cost_usd')} "
                      f"failed={row.get('checks_failed')} invalid={row.get('invalid_reasons') if row['verdict'] == 'INVALID' else ''}", flush=True)
    finally:
        os.kill(pid, signal.SIGTERM)
        shutil.rmtree(env_dir, ignore_errors=True)
    print(open(os.path.join(camp, "board.md")).read() if board(camp) else "")


if __name__ == "__main__":
    main()
