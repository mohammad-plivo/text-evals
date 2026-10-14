"""Did Jev decide every step of a local voice board, or did the node's model (Gemma, gpt-4.1 on screening) act on its own?

  python3 audit_jev_led.py <since> <until>          (UTC, e.g. 2026-10-04T08:20:00Z 2026-10-04T09:02:00Z): the local stack
  python3 audit_jev_led.py <since> <until> --dev    dev's agent-runner, read from VictoriaLogs with the vlogs CLI

Reads jev-livekit's log. For every tool that ran, finds the step Jev picked for it: the latest pick before it, or for a
collect tool (logged only when its collector finishes, after the caller's turns inside it) a pick of a collect step made since
the previous collector finished. Also counts
the calls the model made outside Jev's pick (blocked), Jev faults (the model led alone), and step names written as words.
"""
import collections
import json
import subprocess
import sys
from pathlib import Path

since, until = sys.argv[1], sys.argv[2]
if "--dev" in sys.argv:
    query = ('{aws.ecs.cluster="dev-contacto-agent-runner"} _time:[%s, %s] ("system_one:" or "Tool call tool=" or '
             '"User message committed")' % (since, until))
    vlogs = str(Path.home() / "go" / "bin" / "vlogs")
    raw = subprocess.run([vlogs, "query", query, "--limit", "100000"], capture_output=True, text=True)
    # oldest first, as the docker log reads, and each envelope's own message and flow run
    entries = sorted((json.loads(line) for line in raw.stdout.splitlines() if line.startswith("{")), key=lambda e: e.get("_time", ""))
    lines = [json.dumps({**json.loads(e["_msg"]), "timestamp": e.get("_time")}) if e.get("_msg", "").startswith("{") else "" for e in entries]
else:
    raw = subprocess.run(["docker", "logs", "--since", since, "--until", until, "jev-livekit"], capture_output=True, text=True)
    lines = (raw.stdout + raw.stderr).splitlines()
flows = collections.defaultdict(list)
for line in lines:
    try:
        j = json.loads(line)
    except ValueError:
        continue
    flow, m = (j.get("flow_run_uuid") or "")[:8], j.get("message", "")
    if not flow:
        continue
    if m.startswith("system_one: step="):
        flows[flow].append(("pick", [name.strip() for name in m[len("system_one: step="):].split(" kind=")[0].split(" or ")]))
    elif m.startswith("Tool call tool="):
        flows[flow].append(("tool", m.split("tool=")[1].split(" ")[0]))
    elif m.startswith("User message committed"):
        flows[flow].append(("caller", None))
    elif m.startswith("system_one: dropped"):
        flows[flow].append(("blocked", m[len("system_one: dropped "):][:150]))
    elif "Jev did not lead" in m:
        flows[flow].append(("fault", m[:150]))
    elif m.startswith("system_one: the model wrote a step out"):
        flows[flow].append(("cut", m[:120]))


def covers(pick, tool):
    return pick == tool or (tool.startswith("collect_") and (pick.startswith("collect ") or pick == "collect a value"))


count = collections.Counter()
unled, blocked, faults = [], [], []
for flow, events in flows.items():
    collect_picked, last = False, None
    for kind, data in events:
        if kind == "caller":
            continue
        if kind == "pick":
            count["picks"] += 1
            count["only speak" if data == ["only speak"] else "step picks"] += 1
            collect_picked = collect_picked or any(covers(p, "collect_") for p in data)
            last = data
        elif kind == "tool":
            count["tools"] += 1
            led = (last and any(covers(p, data) for p in last)) or (data.startswith("collect_") and collect_picked)
            if data.startswith("collect_"):
                collect_picked = False
            count["tools led by a Jev pick" if led else "tools with no Jev pick"] += 1
            if not led:
                unled.append((flow, data, last))
        elif kind == "blocked":
            blocked.append((flow, data))
        elif kind == "fault":
            faults.append((flow, data))
        else:
            count["step names cut from speech"] += 1

print(f"calls {len(flows)} | Jev picks {count['picks']} ({count['step picks']} steps, {count['only speak']} only speak) | "
      f"tools run {count['tools']}: {count['tools led by a Jev pick']} led by a Jev pick, {count['tools with no Jev pick']} with none")
print(f"model calls blocked as outside Jev's pick: {len(blocked)} | Jev faults (model led alone): {len(faults)} | "
      f"step names cut from speech: {count['step names cut from speech']}")
for flow, tool, last in unled:
    print(f"  NO PICK  {flow} {tool} (latest pick {last})")
for flow, what in blocked[:12]:
    print(f"  BLOCKED  {flow} {what}")
for flow, what in faults:
    print(f"  FAULT    {flow} {what}")
