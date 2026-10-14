"""Lane B pack runner: every enabled scenario of every sim-fh workspace through the simulation CLI, then the spend tally.

Run with the repo venv from any cwd:
  run_pack.py --campaign N [--slug S ...] [--repeat 1] [--max-parallel 1] [--concurrency 3] [--cap-usd 100]
  --dry-run       print the CLI commands, run nothing
  --report-only   rebuild results.md and results.json from the logs already under campaign-N/lane-b/<workspace>/
  --log-dir DIR   use DIR as the one selected workspace's log directory (dry-run prints into it, report-only reads it)
  --out DIR       write results.md and results.json to DIR instead of campaign-N/lane-b/
Entry rule: a workspace whose enabled scenarios name a screening disposition (the t32 and t34 twins) runs at the flow
entry; every other workspace runs with --node SCHEDULER, because the CLI does not cross from screening into the
scheduler (laneB-step3-report.md, smoke attempt 1). A workspace mixing both is refused.
Report keys: engine.py run_scenario result (scenario, run, turns, failures), run_suite attempts; turn keys send_turn.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

import yaml

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tally_spend as ts  # noqa: E402

STARTS, START_LOCK = {}, threading.Lock()  # CLI report names are stamped to the second per workspace

REPO = os.environ.get("STRESS_REPO") or os.path.abspath(os.path.join(HERE, "..", "..", "repo"))  # STRESS_REPO pins a test tree
WS_ROOT = os.path.join(HERE, "ws")
ENV_FILE = ("/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/"
            "cd27465f-3644-41c6-9c4c-1e7142e58b3b/scratchpad/v29-eval.env")
SCHEDULER = "ee727068-51d5-4019-92d7-56f1324c2914"
REPORT_LINE = re.compile(r"^\s+report: (.+\.json)\s*$", re.M)  # __main__.py:108
CALL = re.compile(r"^sim-cli-(.+)-(\d+)$")  # engine.py:100 phlo_run_uuid


def screening_handles():
    flow = json.load(open(os.path.join(HERE, "flow.json")))
    types = {n["id"]: n["type"] for n in flow["nodes"]}
    if types.get(SCHEDULER) != "ai_agent_v29":
        raise SystemExit(f"flow.json has no ai_agent_v29 node {SCHEDULER}")
    return {e["sourceHandle"] for e in flow["edges"] if types[e["source"]] == "outbound_screening"}


def plan(slugs):
    """[(workspace, chosen slugs, whole workspace?, needs --node)] for workspaces with a selected enabled scenario."""
    screening, out, seen = screening_handles(), [], set()
    for ws in sorted(os.listdir(WS_ROOT)):
        sdir = os.path.join(WS_ROOT, ws, "scenarios")
        names = sorted(f[:-5] for f in os.listdir(sdir) if f.endswith(".yaml")) if os.path.isdir(sdir) else []
        chosen = [n for n in names if not slugs or n in slugs]
        if not chosen:
            continue
        kinds = set()
        for n in names:
            x = (yaml.safe_load(open(os.path.join(sdir, n + ".yaml"))) or {}).get("expect") or {}
            kinds.add(bool({x.get("intent"), x.get("not_intent")} & screening))
        if len(kinds) != 1:
            raise SystemExit(f"{ws}: mixes screening and scheduler scenarios, so no single entry fits; split it")
        seen.update(chosen)
        out.append((ws, chosen, chosen == names and not slugs, not kinds.pop()))  # explicit slugs always run one CLI each
    if set(slugs or ()) - seen:
        raise SystemExit(f"unknown or disabled slugs: {sorted(set(slugs) - seen)}")
    return out


def commands(ws, chosen, whole, node, args, log_dir):
    """[(argv, stdout log, stderr log)]: one CLI run for a whole workspace, else one per slug (--scenario takes one)."""
    stamp, cmds = time.strftime("%Y%m%d-%H%M%S"), []
    for slug in [None] if whole else chosen:
        argv = [".venv/bin/python", "-m", "src.simulation.cli", "run", os.path.join(WS_ROOT, ws)]
        argv += (["--scenario", slug] if slug else []) + (["--node", SCHEDULER] if node else [])
        argv += ["--env-file", ENV_FILE, "--no-open", "--repeat", str(args.repeat),
                 "--max-parallel", str(args.max_parallel), "--verbose"]
        base = os.path.join(log_dir, stamp + (f"__{slug}" if slug else ""))
        cmds.append((argv, base + ".stdout.log", base + ".stderr.log"))
    return cmds


def run_workspace(cmds):
    """Run each command from the repo with unbuffered stdout, then write its exit code and spend tally beside the logs."""
    logs = []
    for argv, out, err in cmds:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with START_LOCK:  # space CLI starts in one workspace so their report stamps differ
            time.sleep(max(0.0, STARTS.get(argv[4], 0) + 3 - time.time()))
            STARTS[argv[4]] = time.time()
        with open(out, "w") as fo, open(err, "w") as fe:
            code = subprocess.run(argv, cwd=REPO, env={**os.environ, "PYTHONUNBUFFERED": "1"}, stdout=fo, stderr=fe).returncode
        base = out[: -len(".stdout.log")]
        with open(base + ".exit", "w") as f:
            f.write(f"{code}\n")
        log = collect(out)
        with open(base + ".tally.txt", "w") as f:
            f.write(ts.tally(err, log["report"])[0] + "\n")
        logs.append(log)
    return logs


def add(*rows):
    return [sum(col) for col in zip([0, 0, 0, 0], *rows)]


def collect(out):
    """One stdout/stderr log pair -> a row per scenario run from the CLI's own report, agent spend matched by call_uuid."""
    base = out[: -len(".stdout.log")]
    found = REPORT_LINE.findall(open(out, errors="replace").read())
    report = found[-1] if found and os.path.isfile(found[-1]) else None
    calls = {}
    if os.path.isfile(base + ".stderr.log"):
        for (call, _), usage in ts.parse_log(base + ".stderr.log", by_call=True)[0].items():
            calls[call] = add(calls.get(call, [0, 0, 0, 0]), usage)
    code = open(base + ".exit").read().strip() if os.path.isfile(base + ".exit") else None
    log, ws_dir = {"log": base, "report": report, "exit": code, "rows": []}, None
    if report:
        ws_dir = os.path.dirname(os.path.dirname(report))
    for run in json.load(open(report)) if report else []:
        spend = add(calls.pop(f"sim-cli-{run['scenario']}-{run['run']}", [0, 0, 0, 0]), ts.caller_run(run, ws_dir))
        path = os.path.join(ws_dir, "scenarios", run["scenario"] + ".yaml")
        x = ((yaml.safe_load(open(path)) or {}).get("expect") or {}) if os.path.isfile(path) else {}
        turns = [t for t in run.get("turns", []) if t.get("stop_reason") != "caller_hung_up"]  # drop the hang-up row
        log["rows"].append(row(os.path.basename(ws_dir), run["scenario"], run["run"],
                               "FAIL" if run["failures"] else "PASS",
                               x.get("intent") or (f"not {x['not_intent']}" if x.get("not_intent") else ""),
                               turns[-1] if turns else {}, run["failures"], len(turns), run.get("attempts", 1), spend))
    for call, spend in calls.items():  # metrics no report run claims: a crashed run, an empty stdout, a missing report
        m = CALL.match(call)
        ws = os.path.basename(ws_dir) if ws_dir else os.path.basename(os.path.dirname(os.path.abspath(out)))
        log["rows"].append(row(ws, m.group(1) if m else call or "(no call_uuid)", int(m.group(2)) if m else 0,
                               "UNATTRIBUTED" if report else "NO REPORT", "", {}, [], 0, 0, spend))
    log["standard_usd"] = sum(r["standard_usd"] for r in log["rows"])
    log["conservative_usd"] = sum(r["conservative_usd"] for r in log["rows"])
    return log


def row(ws, slug, run, verdict, expected, last, failures, turns, attempts, spend):
    return {"workspace": ws, "slug": slug, "run": run, "verdict": verdict, "expected_intent": expected,
            "exit_reached": last.get("intent") or "", "ended": bool(last.get("ended")), "failed_expectations": failures,
            "turns": turns, "attempts": attempts, "standard_usd": round(ts.usd(spend, ts.PRICES["standard"]), 6),
            "conservative_usd": round(ts.usd(spend, ts.PRICES["conservative"]), 6)}


def existing(dirs):
    return [collect(p) for d in dirs for p in sorted(glob.glob(os.path.join(os.path.abspath(d), "*.stdout.log")))]


def write_results(out_root, logs, skipped, args):
    os.makedirs(out_root, exist_ok=True)
    rows = [r for log in logs for r in log["rows"]]
    std, cons = sum(g["standard_usd"] for g in logs), sum(g["conservative_usd"] for g in logs)
    data = {"written": time.strftime("%Y-%m-%d %H:%M:%S"), "campaign": args.campaign, "cap_usd_standard": args.cap_usd,
            "standard_usd": round(std, 4), "conservative_usd": round(cons, 4), "caller_estimate": ts.CALLER_GAP,
            "not_launched_cap": skipped, "logs": [{k: v for k, v in g.items() if k != "rows"} for g in logs], "rows": rows}
    with open(os.path.join(out_root, "results.json"), "w") as f:
        json.dump(data, f, indent=1)
    cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    md = [f"# Lane B results{f', campaign {args.campaign}' if args.campaign is not None else ''}", "",
          f"Written {data['written']}. Scenario runs {len(rows)}, passed {sum(r['verdict'] == 'PASS' for r in rows)}. "
          f"Spend: standard {std:.4f} USD, conservative {cons:.4f} USD; the cap is {args.cap_usd} USD standard.", "",
          f"Agent tokens are measured from the --verbose stderr metrics lines; the {ts.CALLER_GAP}.",
          "", "| workspace | slug | run | verdict | expected intent | exit reached | failed expectations | turns | attempts "
          "| std USD | cons USD |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['workspace']} | {r['slug']} | {r['run']} | {r['verdict']} | {cell(r['expected_intent'])} | "
           f"{r['exit_reached'] or 'none'}{', ended' if r['ended'] else ''} | {cell('; '.join(r['failed_expectations']))} | "
           f"{r['turns']} | {r['attempts']} | {r['standard_usd']:.4f} | {r['conservative_usd']:.4f} |" for r in rows]
    md += ["", "| log | report | CLI exit | std USD | cons USD |", "|---|---|---|---|---|"]
    md += [f"| {cell(g['log'])} | {cell(g['report'] or 'none')} | {g['exit'] if g['exit'] is not None else 'unknown'} | "
           f"{g['standard_usd']:.4f} | {g['conservative_usd']:.4f} |" for g in logs]
    if skipped:
        md += ["", f"Not launched because the standard total reached the cap: {', '.join(skipped)}."]
    with open(os.path.join(out_root, "results.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"{len(rows)} scenario runs, standard {std:.4f} USD, conservative {cons:.4f} USD -> {out_root}/results.md")


def main():
    ap = argparse.ArgumentParser(description="Lane B pack runner (see the module docstring).")
    ap.add_argument("--campaign", type=int, help="writes logs and results under stress-evals/campaign-N/lane-b/")
    ap.add_argument("--slug", nargs="+", default=[], help="run only these scenario slugs")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--max-parallel", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=3, help="workspaces running at once")
    ap.add_argument("--split", type=int, default=1, help="chunks per workspace; chunks run in parallel")
    ap.add_argument("--cap-usd", type=float, default=100.0, help="no new workspace launches once the standard total reaches it")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--log-dir")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.campaign is None and not args.out:
        ap.error("--campaign N or --out DIR is required")
    logs_root = (os.path.join(os.path.dirname(HERE), f"campaign-{args.campaign}", "lane-b")
                 if args.campaign is not None else os.path.abspath(args.out))
    out_root = os.path.abspath(args.out) if args.out else logs_root
    all_logs = lambda: existing(sorted(glob.glob(os.path.join(logs_root, "*", ""))))  # noqa: E731

    if args.report_only:
        write_results(out_root, existing([args.log_dir]) if args.log_dir else all_logs(), [], args)
        return
    jobs = plan(args.slug)
    if args.log_dir and len(jobs) != 1:
        raise SystemExit("--log-dir holds one workspace's logs: select exactly one workspace with --slug")
    work = [(ws, commands(ws, chosen, whole, node, args, os.path.abspath(args.log_dir or os.path.join(logs_root, ws))), node)
            for ws, chosen, whole, node in jobs]
    work = [(ws, cmds[i::args.split], node) for ws, cmds, node in work for i in range(min(args.split, len(cmds)))]
    if args.dry_run:
        for ws, cmds, node in work:
            print(f"# {ws}: " + (f"scheduler entry, --node {SCHEDULER}" if node else "screening entry, no --node"))
            for argv, out, err in cmds:
                print(f"cd {shlex.quote(REPO)} && PYTHONUNBUFFERED=1 {shlex.join(argv)} > {shlex.quote(out)} 2> {shlex.quote(err)}")
        print(f"# {len(work)} workspaces, {sum(len(c) for _, c, _ in work)} CLI runs, concurrency {args.concurrency}, "
              f"cap {args.cap_usd} USD standard; then tally_spend per log and results under {out_root}")
        return
    if not os.path.isfile(ENV_FILE):
        raise SystemExit(f"env file not found: {ENV_FILE}")
    before = all_logs()
    std, cons = sum(g["standard_usd"] for g in before), sum(g["conservative_usd"] for g in before)
    print(f"campaign logs so far: standard {std:.4f} USD, conservative {cons:.4f} USD", flush=True)
    pending, running, new = list(work), {}, []
    with cf.ThreadPoolExecutor(args.concurrency) as pool:
        while pending or running:
            while pending and len(running) < args.concurrency and std < args.cap_usd:
                ws, cmds, _ = pending.pop(0)
                running[pool.submit(run_workspace, cmds)] = ws
                print(f"launched {ws}: {len(cmds)} CLI run(s)", flush=True)
            if not running:
                break
            done, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                ws = running.pop(fut)
                for log in fut.result():
                    new.append(log)
                    std, cons = std + log["standard_usd"], cons + log["conservative_usd"]
                print(f"finished {ws}: running total standard {std:.4f} USD, conservative {cons:.4f} USD", flush=True)
    write_results(out_root, before + new, [ws for ws, _, _ in pending], args)


if __name__ == "__main__":
    main()
