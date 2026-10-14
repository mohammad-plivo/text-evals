"""Freeze the effective configuration of a text-lane board, and prove the actions work before it starts.

  preflight.py --tree DIR --payloads DIR [--out FILE] [--flow flow.json] [--no-canary]

Writes one manifest: hashes of everything that decides a result (flow, node instructions, model settings,
harness, personas, rubrics, dependencies), the tree's commit AND tree object, and the date and timezone the
run is anchored to. A board published without this manifest is not evidence: two of the three faults that
invalidated the 2026-09-20 board (a flow four days stale, a missing action passcode) would each have shown
up here as a changed or failing line.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
CANARY_ACTION = "fhcsd_match_patient_fresh_auth"
# the edge in front of the mock refuses urllib's default agent with a 403, which would read as a red canary
UA = "curl/8.4.0"


def sha(data) -> str:
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def sha_files(paths) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(os.path.basename(p).encode())
        h.update(open(p, "rb").read())
    return h.hexdigest()[:16]


def git(tree, *args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=tree, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def canary(tree, flow, env_file) -> dict:
    """A dedicated successful action call, end to end: authenticate with the passcode, then match a patient,
    and require a real match. Scenarios that deliberately test an API failure can never serve as this proof,
    which is why the canary is its own call. A missing passcode reads here as a red canary, not as 21 calls
    that all exit "Conflict Or API Failure" and look like an agent defect."""
    import urllib.error
    import urllib.request
    node = next(n for n in json.load(open(flow))["nodes"] if n["type"] == "ai_agent_v29")
    code = json.dumps(next((a for a in node["data"]["config"]["actions"] if CANARY_ACTION in json.dumps(a)), {}))
    host = re.search(r"https://([a-z0-9.\-]+)", code)
    if not host:
        return {"ok": False, "why": f"{CANARY_ACTION} is not in the flow, or carries no endpoint"}
    base = "https://" + host.group(1)
    passcode = os.environ.get("FHCSD_PASSCODE") or CANARY_PASSCODE()
    if not passcode:
        return {"ok": False, "endpoint": base, "why": "no action passcode available to the canary"}
    try:
        req = urllib.request.Request(base + "/api/ExternalAccess/AuthenticateVendor", method="POST", data=b"{}",
                                     headers={"fhcsd-external-passcode": passcode, "User-Agent": UA,
                                              "Content-Type": "application/json"})
        token = json.load(urllib.request.urlopen(req, timeout=20))[0]["VendorToken"]
        q = "?FirstName=Carlos&LastName=Rivera&DOB=02/18/1977&Phone=6195550016"
        req2 = urllib.request.Request(base + "/api/Druid/GetPatients" + q.replace("/", "%2F"),
                                      headers={"x-my-authentication-token": token, "User-Agent": UA})
        patients = json.load(urllib.request.urlopen(req2, timeout=20))
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
        return {"ok": False, "endpoint": base, "why": f"{type(e).__name__}: {str(e)[:120]}"}
    ok = isinstance(patients, list) and len(patients) == 1
    result = {"ok": ok, "action": CANARY_ACTION, "endpoint": base,
              "why": "one patient matched" if ok else f"expected one patient, got {patients!r}"[:160]}
    if not ok:
        return result
    # The rubrics assert a missed-appointment date; the API generates one on the CLINIC's clock. If the
    # two disagree the whole board fails on dates alone, and every failure reads as the agent inventing
    # an appointment (board 6, 2026-09-21: rubrics said 21 September, the API said 20 September).
    try:
        mid = patients[0]["MasterId"]
        req3 = urllib.request.Request(f"{base}/api/Druid/GetPatientAppointments?MasterId={mid}",
                                      headers={"x-my-authentication-token": token, "User-Agent": UA})
        appts = json.load(urllib.request.urlopen(req3, timeout=20))
        result["api_appointment"] = sorted(a["AppointmentDate"] for a in appts)[0]
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
        result.update(ok=False, why=f"could not read the patient's appointments: {type(e).__name__}")
    return result


def rubric_appointment(payloads: str) -> str:
    """The missed-appointment date the rubrics assert, as MM/DD/YYYY, or "" if none is stated."""
    import datetime as _dt
    for f in sorted(glob.glob(os.path.join(payloads, "*.json"))):
        if not os.path.basename(f)[0].isdigit():
            continue
        ep = (json.load(open(f)).get("payload") or {}).get("evaluationPrompt") or ""
        m = re.search(r"the ONE appointment the patient missed: ([A-Z][a-z]+ \d{1,2}, \d{4})", ep)
        if m:
            return _dt.datetime.strptime(m.group(1), "%B %d, %Y").strftime("%m/%d/%Y")
    return ""


def CANARY_PASSCODE() -> str:
    """The mock's passcode is a documented non-secret constant in this repo; a real one is never read here."""
    w = os.path.join(os.path.dirname(HERE), "..", "..", "FHCSD", "mock-real", "worker.js")
    try:
        return open(os.path.abspath(w)).read().split('const PASSCODE = "')[1].split('"')[0]
    except (OSError, IndexError):
        return ""


def build(tree, payloads, flow, env_file, run_canary=True) -> dict:
    doc = json.load(open(flow))
    node = next(n for n in doc["nodes"] if n["type"] == "ai_agent_v29")
    cfg = node["data"]["config"]
    lock = os.path.join(tree, "uv.lock")
    m = {
        "stamped_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timezone": time.strftime("%Z%z"),
        "date_anchor": time.strftime("%Y-%m-%d"),
        "flow": {"file": os.path.basename(flow), "sha": sha(doc), "mtime": time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(flow))), "flowId": doc.get("flowId"),
            "instructions_sha": sha(cfg["instructions"]), "actions_sha": sha(cfg["actions"]),
            "extract_variables_sha": sha(cfg.get("extract_variables")),
            "node_id": node["id"], "nodes": len(doc["nodes"])},
        "model": {"config": cfg.get("model_config"), "gemma_env": os.environ.get("LIVEKIT_INFERENCE_ENABLED")},
        "tree": {"dir": tree, "commit": git(tree, "rev-parse", "--short", "HEAD"),
                 "tree_object": git(tree, "rev-parse", "HEAD^{tree}"),
                 "dirty": bool(git(tree, "status", "--porcelain")),
                 "lock_sha": sha(open(lock, "rb").read()) if os.path.exists(lock) else ""},
        "harness": {f: sha(open(os.path.join(HERE, f), "rb").read())
                    for f in ("judge.py", "run_live.py", "build_live_twins.py")},
        "personas_and_scenarios": sha_files(glob.glob(os.path.join(HERE, "ws", "*", "scenarios", "*.yaml"))),
        "rubrics": {"dir": payloads, "sha": sha_files([f for f in glob.glob(os.path.join(payloads, "*.json"))
                                                       if os.path.basename(f)[0].isdigit()]),
                    "count": len([f for f in glob.glob(os.path.join(payloads, "*.json"))
                                  if os.path.basename(f)[0].isdigit()])},
    }
    if run_canary:
        m["canary"] = canary(tree, flow, env_file)
        asserted = rubric_appointment(payloads)
        served = m["canary"].get("api_appointment", "")
        m["dates_agree"] = {"rubrics_say": asserted, "api_says": served,
                            "ok": bool(asserted) and asserted == served}
        if not m["dates_agree"]["ok"]:
            m["canary"]["ok"] = False
            m["canary"]["why"] = (f"the rubrics assert a missed appointment on {asserted or '(none found)'} "
                                  f"but the API serves {served or '(none)'}: the board would fail on dates alone")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True); ap.add_argument("--payloads", required=True)
    ap.add_argument("--flow", default=os.path.join(HERE, "flow.json"))
    ap.add_argument("--env-file", default=""); ap.add_argument("--out", default="")
    ap.add_argument("--no-canary", action="store_true")
    a = ap.parse_args()
    m = build(a.tree, a.payloads, a.flow, a.env_file, run_canary=not a.no_canary)
    if a.out:
        json.dump(m, open(a.out, "w"), indent=1)
    print(json.dumps(m, indent=1))
    return 0 if m.get("canary", {"ok": True})["ok"] and not m["tree"]["dirty"] else 1


if __name__ == "__main__":
    sys.exit(main())
