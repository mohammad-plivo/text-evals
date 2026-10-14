"""Watch a running Hunter board on the local jev stack: each failed call as it lands, slow audio, agent errors, a summary every 10 minutes.

  [AGENT=v210-agent-runner] python3 watch_jev_board.py <run id> <since, e.g. 2026-10-04T07:58:00Z>
"""
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/FHCSD/hunter")
import align_dev_board as dev  # noqa: E402

RUN, SINCE = sys.argv[1], sys.argv[2]
COOKIE = "hunter_session=" + open("/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev/.hunter-cookie").read().strip()
AGENT = os.environ.get("AGENT", "jev-livekit")  # the container whose log carries the calls
first, last, slow, errors = {}, {}, set(), []
lock = threading.Lock()
seen_ts = [""]


def say(line):
    print(f"{datetime.datetime.now():%H:%M} {line}", flush=True)


def seconds(ts):
    # python 3.9 fromisoformat takes only 3 or 6 fraction digits, and the log writes any number
    whole, _, rest = ts.replace("Z", "+00:00").partition(".")
    frac = re.match(r"\d*", rest).group()
    return datetime.datetime.fromisoformat(whole + rest[len(frac):]).timestamp() + float("0." + (frac or "0"))


def read_agent_log():
    since = SINCE
    while True:  # docker logs -f can end on its own: start again from the last line read
        p = subprocess.Popen(["docker", "logs", "-f", "--since", since, AGENT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            ts = read_line(line)
            if ts and ts > since:
                since = ts
        time.sleep(5)


def read_line(line):
    try:
        j = json.loads(line)
        cu, m, ts = (j.get("call_uuid") or "")[:8], j.get("message", ""), j.get("timestamp", "")
        with lock:
            if ts and ts <= seen_ts[0]:
                return ts  # read before the stream restarted
            seen_ts[0] = ts or seen_ts[0]
            if (j.get("level") == "ERROR" and "bill" not in line) or "Jev did not lead" in m:
                errors.append(f"{cu} {ts[11:19]} {m[:160]}")
            if cu and ts:
                t = seconds(ts)
                first.setdefault(cu, t)
                mm = re.search(r"frames forwarded \(([\d.]+)s\)", m)
                if mm:
                    last[cu] = (t, float(mm.group(1)))
        return ts
    except (ValueError, AttributeError):  # one odd line must not stop the watch
        return None


threading.Thread(target=read_agent_log, daemon=True).start()
seen, summary_at = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set(), 0
while True:
    try:
        run = dev.req("GET", f"/api/runs/{RUN}", COOKIE)
    except Exception as e:  # one failed poll must not end the watch
        say(f"poll failed: {e}")
        time.sleep(60)
        continue
    items = run.get("items") or []
    for it in items:
        if it.get("result") in ("pass", "fail") and str(it["id"]) not in seen:
            seen.add(str(it["id"]))
            if it["result"] == "fail":
                name = (it.get("scenario_name") or "").replace("FHCSD dev test — ", "").replace(" (jev)", "")
                say(f"FAIL {it.get('score')} {it.get('turn_count')}t {name} {it.get('failure_tags_json')}")
    with lock:
        rates = {cu: a / max(t - first[cu], 1) for cu, (t, a) in last.items() if a >= 30}
        for cu, r in rates.items():
            if r < 0.9 and cu not in slow:
                slow.add(cu)
                say(f"SLOW AUDIO {cu} {r:.2f}x real time")
        new_errors, errors[:] = errors[:], []
    for e in new_errors[:3]:
        say(f"ERROR {e}")
    if len(new_errors) > 3:
        say(f"ERROR ... and {len(new_errors) - 3} more")
    done = [it for it in items if it.get("result") in ("pass", "fail")]
    status = run.get("status")
    if time.time() - summary_at >= 600 or status not in ("running", "pending", "queued"):
        summary_at = time.time()
        recent = sorted(rates.values())
        audio = f"audio slowest {recent[0]:.2f}x over {len(recent)} calls" if recent else "audio n/a"
        say(f"board {status}: {len(done)}/{len(items)} done, {sum(it['result'] == 'pass' for it in done)} pass, "
            f"{sum(it['result'] == 'fail' for it in done)} fail, {sum(1 for it in items if it.get('error_message'))} no-call | {audio}")
    if status not in ("running", "pending", "queued"):
        break
    time.sleep(60)
