"""Read the failed calls of a Hunter run: the judge's NOT MET criteria and the ids that tie each call to the local logs.

  python3 read_jev_failures.py --cookie <file> <run id> [--all] [--local [--stack v210] | --dev] [--only <name part>]

--local adds the call as the local stack logged it (exact agent words, tool calls, node steps); --dev the same from dev's
agent-runner log in VictoriaLogs (the vlogs CLI), found by the flow run Hunter binds to the call, with Jev's picks. Hunter's transcript is
its own speech-to-text of the audio, so a wrong word there may never have been said.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import align_dev_board as dev

# the local run whose Start node dialled this Hunter number nearest the call's start
LOCAL_RUN = """
WITH start AS (SELECT flow_run_uuid FROM conversation_run_logs
  WHERE created_at BETWEEN to_timestamp({t} - 120) AND to_timestamp({t} + 90)
    AND log_data->>'current_node_type' = 'start' AND log_data::text LIKE '%{digits}%'
  ORDER BY abs(extract(epoch FROM created_at) - {t}) LIMIT 1)
SELECT json_agg(json_build_object('at', to_char(created_at, 'HH24:MI:SS'), 'run', flow_run_uuid, 'log', log_data) ORDER BY id)
FROM conversation_run_logs WHERE flow_run_uuid = (SELECT flow_run_uuid FROM start)"""


def local_call(phone, started_at, stack):
    sql = LOCAL_RUN.format(t=float(started_at), digits=re.sub(r"\D", "", phone or "")[-10:])
    out = subprocess.run(["docker", "exec", f"{stack}-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", sql],
                         capture_output=True, text=True, check=True).stdout.strip()
    rows = json.loads(out) if out else None
    if not rows:
        print("   local: no run found")
        return
    print(f"   local flow run {rows[0]['run']}")
    for r in rows:
        log = r["log"]
        if log.get("event_name") == "NODE_EXECUTED":
            print(f"   {r['at']} node  {log.get('current_node')}")
        elif log.get("type") == "TOOL_CALL_EVENT":
            print(f"   {r['at']} tool  {log.get('tool_name')} {json.dumps(log.get('tool_input'))[:160]} -> {str(log.get('tool_response'))[:160]}")
        elif log.get("type") == "text" and log.get("text", "").strip():
            print(f"   {r['at']} {'AGENT ' if log.get('sender') == 'assistant' else 'caller'} {' '.join(log['text'].split())}")
        elif log.get("type") == "text" and (log.get("node_config") or {}).get("variables"):
            print(f"   {r['at']} set   {json.dumps(log['node_config']['variables'])[:200]}")


DEV_QUERY = ('{aws.ecs.cluster="dev-contacto-agent-runner"} "%s" ("LLM response committed" or "User message committed" or '
             '"Tool call tool=" or "system_one: step=" or "system_one: dropped" or "Jev did not lead" or "system_one: the model wrote")')


def dev_call(flow_run, since_epoch):
    since = datetime.fromtimestamp(float(since_epoch) - 120, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = subprocess.run([str(Path.home() / "go" / "bin" / "vlogs"), "query", f"_time:>={since} " + DEV_QUERY % flow_run, "--since", "72h", "--limit", "2000"],
                       capture_output=True, text=True)
    rows = []
    for line in r.stdout.splitlines():
        try:
            entry = json.loads(line)
            body = json.loads(entry["_msg"])
        except (ValueError, KeyError):
            continue
        m = " ".join(str(body.get("message", "")).split())
        if m.startswith("LLM response committed"):
            m = "AGENT  " + m[m.find('text="') + 6:m.find('" interrupted=')]
        elif m.startswith("User message committed"):
            m = "caller " + m[m.find('text="') + 6:m.find('" id=')]
        elif m.startswith("Tool call tool="):
            m = "tool   " + m[len("Tool call tool="):][:230]
        elif m.startswith("system_one: step="):
            m = "jev    " + m[len("system_one: step="):].split(" jev=")[0][:150]
        rows.append((entry.get("_time", ""), m[:260]))
    print(f"   dev flow run {flow_run}" if rows else f"   dev: nothing logged for {flow_run}")
    for when, m in sorted(rows):
        print(f"   {when[11:19]} {m}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--all", action="store_true", help="every call, not only the failed ones")
    ap.add_argument("--local", action="store_true", help="also print the call as the local stack logged it")
    ap.add_argument("--stack", default="jev", help="compose project of the local stack")
    ap.add_argument("--dev", action="store_true", help="also print the call as dev's agent-runner logged it")
    ap.add_argument("--only", help="only scenarios whose name contains this")
    ap.add_argument("run")
    a = ap.parse_args()
    c = open(a.cookie).read().strip()
    c = c if c.startswith("hunter_session=") else "hunter_session=" + c
    run = dev.req("GET", f"/api/runs/{a.run}", c)
    for it in sorted(run.get("items") or [], key=lambda it: it.get("scenario_name") or ""):
        if not a.all and it.get("result") == "pass" or a.only and a.only not in (it.get("scenario_name") or ""):
            continue
        name = (it.get("scenario_name") or "").replace("FHCSD dev test — ", "").replace(" (jev)", "")
        print(f"\n== {name} | {it.get('result')} {it.get('score')} | {it.get('turn_count')}t | tags {it.get('failure_tags_json')}")
        if not it.get("call_id"):
            print("   no call:", it.get("error_message"))
            continue
        d = dev.req("GET", f"/api/calls/{it['call_id']}", c)
        print(f"   call_uuid {d.get('call_uuid')} | flow run {d.get('cx_flow_run_uuid')} | {round(int(d.get('duration_ms') or 0) / 1000)}s"
              f" | auto_disconnected {d.get('auto_disconnected')}")
        for line in ((d.get("eval_breakdown") or {}).get("criteria") or []):
            if "NOT MET" in line:
                print("   " + re.sub(r"\s+", " ", line).strip()[:420])
        if a.local:
            local_call(d.get("phone_number"), d.get("started_at"), a.stack)
        if a.dev and d.get("cx_flow_run_uuid"):
            dev_call(d["cx_flow_run_uuid"], d.get("started_at") or 0)


if __name__ == "__main__":
    main()
