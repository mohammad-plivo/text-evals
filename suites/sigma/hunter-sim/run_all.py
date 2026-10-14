"""Run every Hunter-derived sim workspace K at a time, entering at the V2.9 node, on the lane env.

Usage: python3 Sigma/hunter-sim/run_all.py <worktree> <repeat> <parallel> <env-file> [<slug-substring>]
                                           [--child-deadline S] [--deadline S] [--stall S]
Each attempt logs to reports/run-<launch>.log; the driver prints 'done <slug> <exit>' lines and ends
with ALL-DONE or CAMPAIGN-INCOMPLETE. The launch manifest is written after every state change, so a
campaign that is killed or that dies still leaves the selected ids, every attempt and every exit code.
A child that outlives its deadline is stopped with its process group and recorded INCOMPLETE, never as
a pass or a fail. A deadline is a stop rule, not a diagnosis: nothing here establishes why a run was
slow, and CPU competition remains a hypothesis.
"""
import os, signal, subprocess, sys, time, glob, json

def _opt(name, default):  # optional flags, removed before the positional args are read
    if name in sys.argv:
        i = sys.argv.index(name); v = int(sys.argv[i + 1]); del sys.argv[i:i + 2]; return v
    return default

CHILD_DEADLINE = _opt("--child-deadline", 2700)  # a normal repeat-3 workspace settles far inside this
DEADLINE = _opt("--deadline", 21600)
STALL = _opt("--stall", 2700)  # nothing settled for this long while children are alive
WT, REPEAT, PAR, ENV = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
ONLY = sys.argv[5] if len(sys.argv) > 5 else ""
NODE = "f66906be-0fc9-43e5-bcf7-20117357082c"
ROOT = os.path.join(WT, "eval_tests", "sigma_v29_hunter")
ws = sorted(d for d in glob.glob(os.path.join(ROOT, "*")) if os.path.isdir(d) and os.path.exists(os.path.join(d, "hunter.json"))
            and any(o in os.path.basename(d) for o in ONLY.split(",")))
print(f"{len(ws)} workspaces, repeat {REPEAT}, parallel {PAR}, child deadline {CHILD_DEADLINE}s, "
      f"campaign deadline {DEADLINE}s, stall {STALL}s", flush=True)

LAUNCH = time.strftime("%Y%m%d-%H%M%S")  # auditor 03:13: a board is one launch, never "latest after a time"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launches", f"{LAUNCH}.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
stamp = lambda: time.strftime("%Y-%m-%d %H:%M:%S")
launch_record = {"launch": LAUNCH, "worktree_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=WT, capture_output=True, text=True).stdout.strip(),
                 "worktree_dirty": bool(subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=WT, capture_output=True, text=True).stdout.strip()),
                 "repeat": REPEAT, "selected": [os.path.basename(d) for d in ws],
                 "config": {"parallel": PAR, "env_file": ENV, "only": ONLY, "child_deadline_s": CHILD_DEADLINE,
                            "campaign_deadline_s": DEADLINE, "stall_s": STALL},
                 "started": stamp(), "ended": None, "status": "RUNNING", "stop_reason": "",
                 "attempts": [], "reports": {}, "exit": {}, "incomplete": [],
                 "note": "A deadline or stall stop bounds the campaign, it does not explain it. Why a run was "
                         "slow is unestablished here; CPU competition is a hypothesis, not a cause."}

def save():  # incremental: a killed campaign still leaves the manifest it had reached
    tmp = OUT + ".tmp"; json.dump(launch_record, open(tmp, "w"), indent=1); os.replace(tmp, OUT)

save()
before = {d: set(glob.glob(os.path.join(d, "reports", "2026*.json"))) for d in ws}

def launch(d):
    log_path = os.path.join(d, "reports", f"run-{LAUNCH}.log")  # per attempt, so no attempt overwrites another
    log = open(log_path, "w")
    node = json.load(open(os.path.join(d, "hunter.json"))).get("entry_node") or NODE
    env = dict(os.environ, PYTHONUNBUFFERED="1")  # the last logged line must be the stall point, not a buffer flush
    p = subprocess.Popen(["uv", "run", "--frozen", "python", "-m", "src.simulation.cli", "run", d, "--node", node,
                          "--repeat", REPEAT, "--max-parallel", "1", "--env-file", ENV, "--no-open", "--verbose"],
                         cwd=WT, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)  # own the group so a hung child's descendants can be stopped too
    att = {"workspace": os.path.basename(d), "pid": p.pid, "log": os.path.relpath(log_path, ROOT),
           "started": stamp(), "ended": None, "exit": None, "status": "RUNNING", "reports": []}
    launch_record["attempts"].append(att); save()
    return p, att, time.monotonic()

def stop_group(p):
    for sig, grace in ((signal.SIGTERM, 20), (signal.SIGKILL, 5)):
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except (ProcessLookupError, PermissionError):
            break
        end = time.monotonic() + grace
        while time.monotonic() < end:
            if p.poll() is not None: return
            time.sleep(0.5)
    p.poll()

def tail(path, n=3):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 4000)); text = f.read().decode("utf-8", "replace")
    except OSError:
        return 0, []
    return size, [ln[:200] for ln in text.splitlines() if ln.strip()][-n:]

def settle(p, d, att, status, t0):
    slug = os.path.basename(d)
    new = sorted(x for x in set(glob.glob(os.path.join(d, "reports", "2026*.json"))) - before[d] if not x.endswith(".judged.json"))
    rels = [os.path.relpath(x, ROOT) for x in new]
    size, lines = tail(os.path.join(d, "reports", f"run-{LAUNCH}.log"))
    att.update(ended=stamp(), exit=p.returncode, status=status, elapsed_s=round(time.monotonic() - t0),
               log_bytes=size, log_tail=lines, reports=rels)
    # an INCOMPLETE attempt keeps its partial artifacts as evidence but is never handed to the board to grade
    launch_record["reports"][slug] = [] if status == "INCOMPLETE" else rels
    launch_record["exit"][slug] = p.returncode
    if status == "INCOMPLETE": launch_record["incomplete"].append(slug)
    save()

caught = []
signal.signal(signal.SIGINT, lambda s, f: caught.append(s))
signal.signal(signal.SIGTERM, lambda s, f: caught.append(s))

queue, running = list(ws), {}
t_start = t_progress = time.monotonic()
stop_reason = ""
while queue or running:
    while queue and len(running) < PAR:
        d = queue.pop(0); p, att, t0 = launch(d); running[p] = (d, att, t0); time.sleep(3)
    for p, (d, att, t0) in list(running.items()):
        if p.poll() is not None:
            settle(p, d, att, "DONE", t0)
            print(f"done {os.path.basename(d)} exit={p.returncode} {time.strftime('%H:%M:%S')}", flush=True)
            del running[p]; t_progress = time.monotonic()
        elif time.monotonic() - t0 > CHILD_DEADLINE:
            att["stop_reason"] = f"child deadline {CHILD_DEADLINE}s reached"
            stop_group(p); settle(p, d, att, "INCOMPLETE", t0)
            print(f"incomplete {os.path.basename(d)} stopped at child deadline {CHILD_DEADLINE}s "
                  f"exit={p.returncode} {time.strftime('%H:%M:%S')} (a bound, not a diagnosis)", flush=True)
            del running[p]; t_progress = time.monotonic()
    now = time.monotonic()
    if caught: stop_reason = f"driver received signal {caught[0]}"
    elif running and now - t_progress > STALL: stop_reason = f"no attempt settled for {now - t_progress:.0f}s with {len(running)} alive"
    elif now - t_start > DEADLINE: stop_reason = f"campaign deadline {DEADLINE}s reached"
    if stop_reason:
        print(f"STOP: {stop_reason}. Stopping {len(running)} child group(s); {len(queue)} never started.", flush=True)
        print("This bound stops the campaign, it does not explain it: why a run was slow is unestablished.", flush=True)
        for p, (d, att, t0) in list(running.items()):
            att["stop_reason"] = stop_reason
            stop_group(p); settle(p, d, att, "INCOMPLETE", t0); del running[p]
        for d in queue:
            slug = os.path.basename(d)
            launch_record["attempts"].append({"workspace": slug, "status": "NOT_STARTED", "stop_reason": stop_reason,
                                              "started": None, "ended": stamp(), "exit": None, "reports": []})
            launch_record["reports"][slug] = []; launch_record["exit"][slug] = None; launch_record["incomplete"].append(slug)
        queue = []; save(); break
    time.sleep(10)

launch_record["ended"] = stamp()
launch_record["stop_reason"] = stop_reason
launch_record["status"] = "INCOMPLETE" if launch_record["incomplete"] else "COMPLETE"
save()
print(f"LAUNCH-MANIFEST {OUT}", flush=True)
if launch_record["incomplete"]:
    print(f"CAMPAIGN-INCOMPLETE {len(launch_record['incomplete'])}/{len(ws)} without a result: "
          f"{', '.join(launch_record['incomplete'])} {time.strftime('%H:%M:%S')}", flush=True)
    sys.exit(1)
print("ALL-DONE", time.strftime('%H:%M:%S'), flush=True)
