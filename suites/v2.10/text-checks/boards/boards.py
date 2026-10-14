"""One full board of each suite, one after the other, on the engine the stack runs. Each run is started once and never retried.
Usage: boards.py <out dir> [suite ...]      (writes board-<suite>.txt there, and prints one line per step; suites in the order given,
                                             default logic-flow then rapido-flow)"""
import subprocess, sys, time
from pathlib import Path

ROOT = Path("/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.10")
OUT = Path(sys.argv[1])
COOKIE = "../../v2.9.1-jev/.hunter-cookie"


def hunt(suite, *args):
    return subprocess.run([sys.executable, "hunter.py", *args], cwd=ROOT / suite, capture_output=True, text=True)


def wait(suite, module, cookie, run, minutes):
    """Until the run ends, or nothing has finished for 12 minutes (no call lasts that long, so Hunter has lost the run)."""
    deadline, moved, seen, now = time.time() + minutes * 60, time.time(), -1, "running"
    while time.time() < deadline:
        try:
            board = module.dev.req("GET", f"/api/runs/{run}", cookie)
            now, done = board.get("status") or "?", sum(item.get("status") == "completed" for item in board.get("items") or [])
        except Exception as error:  # noqa: BLE001 - Hunter answers 502 now and then; the run itself goes on
            print("  poll failed:", str(error)[:80], flush=True)
            now, done = "running", -1
        if now not in ("running", "pending", "queued"):
            break
        if done > seen:
            seen, moved = done, time.time()
            print(f"  {suite}: {done} calls finished", flush=True)
        if time.time() - moved > 720:
            return "stuck"
        time.sleep(30)
    time.sleep(45)   # the judge writes its verdict a little after the call ends
    return now


STEPS = {"logic-flow": (("board", [], 80), ("alone", ["--alone"], 30)), "rapido-flow": (("board", [], 90),)}
for suite, steps in ((name, STEPS[name]) for name in (sys.argv[2:] or list(STEPS))):
    sys.path.insert(0, str(ROOT / suite))
    for name in ("hunter", "spec", "callers"):
        sys.modules.pop(name, None)
    import hunter  # noqa: E402
    cookie = hunter.cookie_from(str(ROOT / suite / COOKIE))
    runs = []
    for label, args, minutes in steps:
        started = hunt(suite, "run", "--cookie", COOKIE, *args)
        words = started.stdout.split()
        if started.returncode or not words or len(words[0]) != 36:
            print(f"{suite} {label} did not start: {(started.stdout + started.stderr).strip()[-300:]}", flush=True)
            break
        print(f"{suite} {label} started: {started.stdout.strip()}", flush=True)
        ended = wait(suite, hunter, cookie, words[0], minutes)
        print(f"{suite} {label} ended: {ended}", flush=True)
        runs.append(words[0])
        if ended != "completed":
            break
    sys.path.pop(0)
    if not runs:
        continue
    for _ in range(4):
        checked = hunt(suite, "check", "--cookie", COOKIE, *runs)
        if checked.returncode == 0:
            break
        print("  check failed, again in 30 s:", checked.stderr.strip()[-160:], flush=True)
        time.sleep(30)
    (OUT / f"board-{suite}.txt").write_text(" ".join(runs) + "\n" + checked.stdout + checked.stderr)
    print(f"{suite}: " + (checked.stdout.strip().splitlines()[-1] if checked.stdout.strip() else checked.stderr[-300:]), flush=True)
