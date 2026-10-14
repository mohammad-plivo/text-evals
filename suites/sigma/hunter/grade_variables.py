"""Grade each Hunter item's exported variables from the local rig (redis PHLORUN VARS), matched to the local flow run by call time.

    python3 grade_variables.py --cookie <path> --run <hunter run id>

Hunter correlation is not available on the local rig (the core service queues event callbacks to a localstack queue nothing consumes),
so the flow's exported variables are read from the local redis hash the runner writes per node run, and the local run is matched to the
Hunter item by start time. Expectations come from each scenario file's _expected_variables (exact, gist, absent)."""
import argparse, glob, json, re, subprocess, datetime, urllib.request
from pathlib import Path
HERE = Path(__file__).parent
FLOW = json.loads((HERE / "urls.json").read_text())["flow_uuid"]
AGENT_NODE = "549db00a-8489-4ab2-ae75-37bc85898de5"
START_NODE = "cdb03fdd-9d93-48c9-8ab6-fa2703acafdc"

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, timeout=60).stdout

def parse_ts(s):
    """Any of the timestamp shapes the two systems emit (ISO text or epoch seconds), to an aware UTC datetime."""
    if isinstance(s, (int, float)):
        return datetime.datetime.fromtimestamp(s, tz=datetime.timezone.utc)
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T")
    s = re.sub(r"\+00$", "+00:00", s)
    m = re.match(r"(.*?)(\.\d+)?([+-]\d\d:\d\d)?$", s)
    base, frac, tz = m.group(1), m.group(2) or "", m.group(3) or "+00:00"
    frac = (frac + "000000")[:7] if frac else ""
    return datetime.datetime.fromisoformat(f"{base}{frac}{tz}")

def local_runs():
    out = sh("docker", "exec", "v29-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-Atc",
             f"select phlo_run_uuid, created_at from conversation_run_summary where phlo_uuid='{FLOW}' and created_at > now() - interval '6 hours' order by created_at")
    runs = []
    for line in out.strip().splitlines():
        rid, ts = line.split("|"); runs.append((rid, parse_ts(ts)))
    return runs

def run_phone(rid):
    """The number the local run dialled, from the Start node's stored trigger parameters."""
    raw = [x for x in sh("docker", "exec", "v29-redis", "redis-cli", "--raw", "hgetall", f"PHLORUN:{rid}:NODEUUID:{START_NODE}:VARS").split("\n") if x != ""]
    d = dict(zip(raw[::2], raw[1::2]))
    return (d.get("http.params.candidate_phone") or "").strip('"')

def run_vars(rid):
    """Every node's exported variables for the run (screening and agent), the Start node's trigger params left out."""
    keys = [k for k in sh("docker", "exec", "v29-redis", "redis-cli", "--raw", "--scan", "--pattern", f"PHLORUN:{rid}:NODEUUID:*:VARS").split("\n") if k and START_NODE not in k]
    d = {}
    for key in keys:
        raw = [x for x in sh("docker", "exec", "v29-redis", "redis-cli", "--raw", "hgetall", key).split("\n") if x != ""]
        for k, v in zip(raw[::2], raw[1::2]):
            try: d[k] = json.loads(v)
            except Exception: d[k] = v
    return d

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cookie", required=True); ap.add_argument("--run", required=True); a = ap.parse_args()
    cookie = Path(a.cookie).read_text().strip()
    req = urllib.request.Request(f"https://hunter.contactodev.com/api/runs/{a.run}", headers={"Cookie": cookie})
    run = json.load(urllib.request.urlopen(req, timeout=30))
    expect = {}
    for f in glob.glob(str(HERE / "scenarios" / "*.json")):
        d = json.load(open(f)); expect[d["name"]] = d.get("_expected_variables", {})
    runs = local_runs(); phones = {rid: run_phone(rid) for rid, _ in runs}
    ok = bad = 0
    for it in run.get("items", []):
        if not it.get("call_id"): continue
        creq = urllib.request.Request(f"https://hunter.contactodev.com/api/calls/{it['call_id']}", headers={"Cookie": cookie})
        call = json.load(urllib.request.urlopen(creq, timeout=30))
        started = call.get("started_at") or call.get("created_at")
        if not started: continue
        t = parse_ts(started)
        # the pool number Hunter answered on is the number the local run dialled; time breaks ties when a number is reused
        phone = (call.get("phone_number") or "").strip()
        cands = [(abs((t - ts).total_seconds()), rid) for rid, ts in runs if phones.get(rid) == phone and abs((t - ts).total_seconds()) < 900]
        if not cands: print(f"[?] {it['scenario_name'][:55]} no local run dialled {phone} near {t:%H:%M}"); continue
        rid = min(cands)[1]; got = run_vars(rid); exp = expect.get(it["scenario_name"], {})
        misses = []
        for k, v in (exp.get("exact") or {}).items():
            if str(got.get(k, "")).strip().lower() != str(v).strip().lower(): misses.append(f"{k}: got {got.get(k)!r} want {v!r}")
        for k, v in (exp.get("gist") or {}).items():
            if not got.get(k): misses.append(f"{k}: absent (gist {v!r})")
        for k in (exp.get("absent") or []):
            if got.get(k): misses.append(f"{k}: present {got.get(k)!r} but expected absent")
        tag = "ok " if not misses else "BAD"; ok += not misses; bad += bool(misses)
        print(f"[{tag}] {it['scenario_name'][:55]} | hunter {it.get('result')} | run {rid[:8]} | vars {len(got)}")
        for m in misses: print("      ", m)
    print(f"\nvariables: {ok} scenarios clean, {bad} with a miss")

if __name__ == "__main__": main()
