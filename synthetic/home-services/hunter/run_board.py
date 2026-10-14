#!/usr/bin/env python3
"""Launch a V2.9 example-flow Hunter run and poll it to completion (adapted from Sigma/hunter/run_board.py).

    python3 V29-Hunter-Example/hunter/run_board.py --cookie <path> --name "..." --only 01-happy-full-walk
    python3 V29-Hunter-Example/hunter/run_board.py --cookie <path> --name "..." --all --parallel 4

The dev Hunter pod is shared with other teams, so it pre-flights `/api/runs` and refuses to start
while another run is in flight unless --force is given. Scenario ids come from created.json, so a
scenario that was never pushed cannot be run by accident. It prints a per-scenario result table and
writes the full run plus every call record to runs/<run-id>.json for reading afterwards.
"""
from __future__ import annotations

import argparse
import json
import time
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)  # a board run is long; stream it

HERE = Path(__file__).parent
BASE = "https://hunter.contactodev.com"
STATE = HERE / "created.json"
OUT = HERE / "runs"


def call(cookie: str, method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Cookie": cookie, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read()[:300].decode(errors='replace')}")


def refuse_stale_build(files) -> None:
    """Every date in a scenario is today's (IST); a file built on another day judges the wrong dates."""
    import datetime, zoneinfo
    today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date().isoformat()
    stale = sorted(f.name for f in files if json.loads(f.read_text()).get("_built_ist") != today)
    if stale:
        raise SystemExit(f"built on another IST day ({len(stale)} files, e.g. {stale[0]}); re-run build.py first")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--name", required=True, help="run name as it appears on the dashboard")
    ap.add_argument("--only", nargs="*", default=[], help="scenario file stems, e.g. 01-screen-wrong-person")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--parallel", type=int, default=4, help="dev boards starve STT above 4")
    ap.add_argument("--interval", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="start even if another run is in flight")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--stop", metavar="RUN_ID", help="stop a run that is stuck, then exit")
    ap.add_argument("--stall", type=int, default=900, help="seconds with nothing settling before reporting incomplete")
    ap.add_argument("--deadline", type=int, default=7200, help="seconds before the watcher gives up")
    args = ap.parse_args()

    cookie = Path(args.cookie).read_text().strip()
    if not cookie.startswith("hunter_session="):
        cookie = "hunter_session=" + cookie
    print(f"as {call(cookie, 'GET', '/api/auth/me').get('email')}")

    if args.stop:
        before = call(cookie, "GET", f"/api/runs/{args.stop}")
        before = before.get("run", before)
        stuck = [i for i in (before.get("items") or []) if not i.get("result")]
        print(f"stopping {args.stop} ({before.get('status')}), {len(stuck)} item(s) without a result")
        call(cookie, "POST", f"/api/runs/{args.stop}/stop")
        after = call(cookie, "GET", f"/api/runs/{args.stop}")
        after = after.get("run", after)
        print(f"now {after.get('status')}")
        for i in after.get("items") or []:
            if not i.get("result"):
                print(f"  still without a result: {str(i.get('scenario_name'))[:58]} ({i.get('status')})")
        return

    ids: dict[str, str] = json.loads(STATE.read_text())["ids"]
    if args.all:
        chosen = {k: v for k, v in ids.items()}
    else:
        want = {f"{s}.json" if not s.endswith(".json") else s for s in args.only}
        missing = want - set(ids)
        assert not missing, f"not on Hunter: {sorted(missing)}"
        chosen = {k: ids[k] for k in sorted(want)}
    assert chosen, "nothing selected; pass --only or --all"
    refuse_stale_build([HERE / "scenarios" / k for k in chosen])

    # The pod is shared: a board started under someone else's run steals their phone lines.
    live = [r for r in (call(cookie, "GET", "/api/runs?limit=10").get("runs") or [])
            if str(r.get("status")) in ("running", "queued", "pending", "in_progress")]
    if live and not args.force:
        raise SystemExit("another run is in flight: " + "; ".join(f"{r.get('name')} ({r.get('status')})" for r in live))
    free = call(cookie, "GET", "/api/phone-numbers/availability").get("free", 0)
    if free < min(args.parallel, len(chosen)) and not args.force:
        raise SystemExit(f"only {free} Hunter numbers free for parallelism {args.parallel}")

    run = call(cookie, "POST", "/api/runs", {
        "name": args.name, "scenarioIds": list(chosen.values()),
        "maxParallel": args.parallel, "intervalSeconds": args.interval,
    })
    rid = run.get("runId") or run.get("id")
    print(f"run {rid}: {len(chosen)} scenarios at parallelism {args.parallel}")
    print(f"  https://hunter.contactodev.com/dashboard/runs/{rid}")

    # A result label is not completion: board 6 had an item in status "running" that already carried
    # a fail result, and the watcher reported 34/38 "done" for five hours while nothing progressed.
    TERMINAL = ("completed", "passed", "failed", "error", "stopped", "skipped")

    def settled(i: dict) -> bool:
        return str(i.get("status") or "").lower() in TERMINAL

    body: dict = {}
    last_progress, last_count = time.monotonic(), -1
    started = time.monotonic()
    while True:
        time.sleep(args.poll)
        try:
            body = call(cookie, "GET", f"/api/runs/{rid}", timeout=30)
        except SystemExit as e:  # a transient poll failure is not a failed run
            print(f"  poll error, retrying: {str(e)[:90]}")
            continue
        items = body.get("items") or []
        done = [i for i in items if settled(i)]
        scored = [i for i in items if i.get("result")]
        waiting = [i for i in items if not settled(i)]
        print(f"  {body.get('status')}: {len(done)}/{len(items)} settled, {len(scored)} with a result"
              + (f", oldest unsettled: {str(waiting[0].get('scenario_name'))[12:44]}" if waiting else ""))

        if len(done) != last_count:
            last_progress, last_count = time.monotonic(), len(done)
        stalled_for = time.monotonic() - last_progress
        if stalled_for > args.stall:
            print(f"\nSTALLED: no item has settled for {stalled_for/60:.0f} min "
                  f"({len(waiting)} unsettled of {len(items)}). Reporting incomplete and stopping the watcher.")
            print("The remote run is left running: cancelling it is a separate, explicit decision (--stop).")
            break
        if time.monotonic() - started > args.deadline:
            print(f"\nDEADLINE: {args.deadline/60:.0f} min elapsed; reporting incomplete, remote run untouched.")
            break
        if str(body.get("status")) in ("completed", "stopped", "failed"):
            break

        OUT.mkdir(exist_ok=True)
        (OUT / f"{rid}.progress.json").write_text(json.dumps(body, indent=1))

    OUT.mkdir(exist_ok=True)
    calls = {}
    for i in body.get("items") or []:
        if i.get("call_id"):
            calls[i["call_id"]] = call(cookie, "GET", f"/api/calls/{i['call_id']}", timeout=60)
    (OUT / f"{rid}.json").write_text(json.dumps({"run": body, "calls": calls}, indent=1))

    print(f"\n{'result':8s} {'score':>6s} {'turns':>6s}  scenario")
    for i in sorted(body.get("items") or [], key=lambda x: str(x.get("scenario_name"))):
        score = i.get("score")
        print(f"{str(i.get('result') or i.get('status')):8s} "
              f"{(f'{score:.2f}' if isinstance(score, (int, float)) else '-'):>6s} "
              f"{str(i.get('turn_count') or '-'):>6s}  {str(i.get('scenario_name'))[:62]}")
    items = body.get("items") or []
    passed = sum(1 for i in items if i.get("result") == "pass" and settled(i))
    unsettled = [i for i in items if not settled(i)]
    print(f"\n{passed}/{len(items)} passed and settled; {len(unsettled)} INCOMPLETE")
    for i in unsettled:
        print(f"  incomplete: {str(i.get('scenario_name'))[12:58]} (status {i.get('status')}, "
              f"result {i.get('result')}, call {i.get('call_id')})")
    print(f"full records in {OUT / f'{rid}.json'}")


if __name__ == "__main__":
    main()
