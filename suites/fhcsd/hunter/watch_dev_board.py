"""Watch a Hunter board running on dev: each failed call as it lands, Jev faults and errors from dev's agent-runner log
(VictoriaLogs, vlogs CLI), and a summary every 10 minutes. Ends when the run ends.

  python3 watch_dev_board.py <run id> <since, UTC e.g. 2026-10-04T11:58:00Z>
"""
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import align_dev_board as dev  # noqa: E402

RUN, SINCE = sys.argv[1], sys.argv[2]
COOKIE = "hunter_session=" + (Path(__file__).parents[2] / "v2.9.1-jev" / ".hunter-cookie").read_text().strip()
VLOGS = str(Path.home() / "go" / "bin" / "vlogs")
QUERY = ('{aws.ecs.cluster="dev-contacto-agent-runner"} _time:>=%s ("Jev did not lead" or "system_one: dropped" or '
         '"TYPESAFE_API_KEY" or "level\\":\\"ERROR" or "\\"level\\": \\"ERROR")' % SINCE)


def say(line):
    print(f"{datetime.datetime.now():%H:%M} {line}", flush=True)


def dev_alerts(seen):
    r = subprocess.run([VLOGS, "query", QUERY, "--limit", "200"], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        try:
            entry = json.loads(line)
            body = json.loads(entry["_msg"]) if entry.get("_msg", "").startswith("{") else {"message": entry.get("_msg", "")}
        except (ValueError, KeyError):
            continue
        key = (entry.get("_time"), body.get("message", "")[:80])
        if key not in seen:
            seen.add(key)
            out.append(f"{entry.get('_time', '')[11:19]} {(body.get('flow_run_uuid') or '')[:8]} {' '.join(str(body.get('message', '')).split())[:170]}")
    return sorted(out)


done, alerts, summary_at, alerts_at = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set(), set(), 0.0, 0.0
while True:
    try:
        run = dev.req("GET", f"/api/runs/{RUN}", COOKIE)
    except Exception as error:  # one failed poll must not end the watch
        say(f"poll failed: {error}")
        time.sleep(60)
        continue
    items = run.get("items") or []
    for it in items:
        if it.get("result") in ("pass", "fail") and str(it["id"]) not in done:
            done.add(str(it["id"]))
            if it["result"] == "fail":
                name = (it.get("scenario_name") or "").replace("FHCSD dev test — ", "")
                say(f"FAIL {it.get('score')} {it.get('turn_count')}t {name} {it.get('failure_tags_json')} {it.get('error_message') or ''}")
    if time.time() - alerts_at >= 120:
        alerts_at = time.time()
        new = dev_alerts(alerts)
        for line in new[:4]:
            say(f"DEV {line}")
        if len(new) > 4:
            say(f"DEV ... and {len(new) - 4} more")
    status = run.get("status")
    finished = [it for it in items if it.get("result") in ("pass", "fail")]
    if time.time() - summary_at >= 600 or status not in ("running", "pending", "queued"):
        summary_at = time.time()
        say(f"board {status}: {len(finished)}/{len(items)} done, {sum(it['result'] == 'pass' for it in finished)} pass, "
            f"{sum(it['result'] == 'fail' for it in finished)} fail, {sum(1 for it in items if it.get('error_message'))} no-call")
    if status not in ("running", "pending", "queued"):
        break
    time.sleep(60)
