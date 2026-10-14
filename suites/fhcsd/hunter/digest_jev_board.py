"""Digest of a Hunter run on a local stack: one file per failed call with the judge's NOT MET lines, the local timeline and Jev's picks.

  [STACK=v210] python3 digest_jev_board.py <run id> <out dir> [--all]

A call with no NOT MET line and the comment "Evaluation error" was not judged: Hunter's judge gave up, the agent did not fail.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/FHCSD/hunter")
import align_dev_board as dev  # noqa: E402
import read_jev_failures as rj  # noqa: E402

RUN, OUT, ALL = sys.argv[1], sys.argv[2], "--all" in sys.argv
STACK = os.environ.get("STACK", "v210")
COOKIE = "hunter_session=" + open("/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev/.hunter-cookie").read().strip().split("=", 1)[-1]


def local_rows(phone, started_at):
    sql = rj.LOCAL_RUN.format(t=float(started_at), digits=re.sub(r"\D", "", phone or "")[-10:])
    out = subprocess.run(["docker", "exec", f"{STACK}-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", sql],
                         capture_output=True, text=True, check=True).stdout.strip()
    return json.loads(out) if out else []


def jev_lines(flow_run, since, until):
    log = subprocess.run(["docker", "logs", "--since", since, "--until", until, f"{STACK}-agent-runner"], capture_output=True, text=True)
    rows = []
    for line in (log.stdout + log.stderr).splitlines():
        if flow_run not in line:
            continue
        try:
            j = json.loads(line)
        except ValueError:
            continue
        m, ts = " ".join(str(j.get("message", "")).split()), str(j.get("timestamp", ""))[11:19]
        if m.startswith("system_one: step="):
            head, _, shares = m[len("system_one: step="):].partition(" jev=")
            rows.append((ts, "jev   " + head.split(" allowed=")[0] + " | " + shares[:330]))
        elif m.startswith("system_one:") or "Jev did not lead" in m:
            rows.append((ts, "s1    " + m[:260]))
        elif m.startswith("User idle, sending reminder"):
            rows.append((ts, "idle  reminder"))
    return rows


summary = []
run = dev.req("GET", f"/api/runs/{RUN}", COOKIE)
for it in sorted(run.get("items") or [], key=lambda it: it.get("scenario_name") or ""):
    if (it.get("result") == "pass" and not ALL) or not it.get("call_id"):
        continue
    name = (it.get("scenario_name") or "").replace("FHCSD dev test — ", "").replace(" (jev)", "")
    d = dev.req("GET", f"/api/calls/{it['call_id']}", COOKIE)
    lines = [f"== {name} | {it.get('result')} {it.get('score')} | {it.get('turn_count')}t | {round(int(d.get('duration_ms') or 0) / 1000)}s | tags {it.get('failure_tags_json')}"]
    if str(d.get("comments") or "").startswith("Evaluation error"):
        lines.append("  JUDGE gave up (Evaluation error): this call was not judged")
    for crit in ((d.get("eval_breakdown") or {}).get("criteria") or []):
        if "NOT MET" in crit:
            lines.append("  JUDGE " + re.sub(r"\s+", " ", crit).strip()[:560])
    rows = local_rows(d.get("phone_number"), d.get("started_at"))
    timeline, reminders, end = [], 0, ""
    if rows:
        flow_run = rows[0]["run"]
        first, last = rows[0]["at"], rows[-1]["at"]
        for r in rows:
            log = r["log"]
            if log.get("event_name") == "NODE_EXECUTED":
                timeline.append((r["at"], f"node  {log.get('current_node')}"))
                end = log.get("current_node") or end
            elif log.get("type") == "TOOL_CALL_EVENT":
                timeline.append((r["at"], f"tool  {log.get('tool_name')} {json.dumps(log.get('tool_input'))[:110]} -> {str(log.get('tool_response'))[:110]}"))
            elif log.get("type") == "text" and log.get("text", "").strip():
                who = "AGENT " if log.get("sender") == "assistant" else "caller"
                text = " ".join(log["text"].split())
                reminders += "still there" in text.lower()
                timeline.append((r["at"], f"{who} {text[:300]}"))
            elif log.get("type") == "text" and (log.get("node_config") or {}).get("variables"):
                timeline.append((r["at"], f"set   {json.dumps(log['node_config']['variables'])[:150]}"))
        start = float(d.get("started_at"))
        stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        timeline += jev_lines(flow_run, stamp(start - 120), stamp(start + int(d.get("duration_ms") or 0) / 1000 + 180))
        lines.append(f"  local flow run {flow_run}")
    for at, text in sorted(timeline, key=lambda row: row[0]):
        lines.append(f"  {at} {text}")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:60].strip("-")
    open(f"{OUT}/{slug}.txt", "w").write("\n".join(lines) + "\n")
    summary.append(f"{it.get('result') or '-':5s} {round(int(d.get('duration_ms') or 0) / 1000):4d}s reminders={reminders} end={end:28s} {slug}")
print("\n".join(summary))
