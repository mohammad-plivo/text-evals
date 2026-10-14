"""Run the live twins (build_live_twins.py) through the sim CLI on a chosen tree, judge each run with judge.py
against its Hunter payload, and print a board. Run with the tree's venv from any cwd:
  run_live.py --payloads DIR --env-file FILE [--tree DIR] [--only SLUG ...] [--repeat 1] [--max-parallel 3]
              [--gemma] [--out DIR] [--judge-model gpt-4.1] [--dry-run]
--gemma exports LIVEKIT_INFERENCE_ENABLED=true and the inference pair from --livekit-env (default: the local
livekit .env) into the CHILD environment only; nothing is written to disk. Entry: screening events run at the
flow entry, everything else with --node <the flow's ai_agent_v29 id> (the CLI does not cross screening).
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import subprocess
import sys
import time
import yaml
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_live_twins import MARKER, SCREENING_EVENTS, slug_of  # noqa: E402
WS_ROOT = os.path.join(HERE, "ws")
REPORT_LINE = re.compile(r"^\s+report: (.+\.json)\s*$", re.M)
LIVEKIT_ENV = ("/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized-v29/"
               "services/plivo-cx-livekit/.env")


def env_value(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def scheduler_id(flow_path):
    flow = json.load(open(flow_path))
    return next(n["id"] for n in flow["nodes"] if n["type"] == "ai_agent_v29")


def twins(payloads_dir):
    """[(slug, workspace dir, hunter payload path, screening entry?)] for every enabled live twin."""
    by_slug = {}
    for f in glob.glob(os.path.join(payloads_dir, "*.json")):
        if not os.path.basename(f)[0].isdigit():
            continue
        ev = json.load(open(f))["payload"]["event"]
        by_slug[slug_of(ev)] = (f, ev in SCREENING_EVENTS)
    out = []
    for path in sorted(glob.glob(os.path.join(WS_ROOT, "*", "scenarios", "L-*.yaml"))):
        if open(path).readline().rstrip("\n") != MARKER:
            continue
        slug = os.path.basename(path)[:-5]
        if slug not in by_slug:
            continue
        payload, screening = by_slug[slug]
        out.append((slug, os.path.dirname(os.path.dirname(path)), payload, screening))
    return out


def expected_intent(ws: str, slug: str) -> str:
    """The exit the twin asserts, from the generated scenario; "" when it is judged by rubric only."""
    path = os.path.join(ws, "scenarios", slug + ".yaml")
    try:
        return ((yaml.safe_load(open(path)) or {}).get("expect") or {}).get("intent") or ""
    except OSError:
        return ""


def run_one(item, args, env, node, log_dir):
    slug, ws, payload, screening = item
    expect_intent = expected_intent(ws, slug)
    argv = [".venv/bin/python", "-m", "src.simulation.cli", "run", ws, "--scenario", slug]
    if not screening:
        argv += ["--node", node]
    argv += ["--env-file", args.env_file, "--no-open", "--repeat", str(args.repeat), "--max-parallel", "1", "--verbose"]
    so, se = os.path.join(log_dir, slug + ".stdout.log"), os.path.join(log_dir, slug + ".stderr.log")
    if args.dry_run:
        return slug, " ".join(argv), None
    t0 = time.time()
    with open(so, "w") as fo, open(se, "w") as fe:
        code = subprocess.run(argv, cwd=args.tree, env=env, stdout=fo, stderr=fe).returncode
    m = REPORT_LINE.search(open(so).read())
    report = m.group(1) if m else None
    gemma = sum(1 for _ in open(se) if "livekit.agents.inference.llm.LLM" in _)
    azure = sum(1 for _ in open(se) if "livekit.plugins.openai.llm.LLM" in _)
    verdicts, judge_exit, problems = [], None, []
    for stale in glob.glob(os.path.join(log_dir, slug + "-run*.judge.json")):
        os.remove(stale)
    if report:
        argv_j = [".venv/bin/python", os.path.join(HERE, "judge.py"), "--report", report, "--hunter", payload,
                  "--out", log_dir, "--env-file", args.env_file, "--model", args.judge_model]
        if expect_intent:
            argv_j += ["--expect-intent", expect_intent]
        j = subprocess.run(argv_j, cwd=args.tree, env=env, capture_output=True, text=True)
        judge_exit = j.returncode
        open(os.path.join(log_dir, slug + ".judge.log"), "w").write(j.stdout + j.stderr)
        for jf in sorted(glob.glob(os.path.join(log_dir, slug + "-run*.judge.json"))):
            verdicts.append(json.load(open(jf)))
    else:
        problems.append("no report: the simulator produced none")
    # the gate must not read a short board as a green one
    if code != 0:
        problems.append(f"simulator exit {code}")
    if len(verdicts) != args.repeat:
        problems.append(f"{len(verdicts)} judged runs, {args.repeat} requested")
    return slug, {"exit": code, "judge_exit": judge_exit, "report": report, "seconds": round(time.time() - t0),
                  "gemma_calls": gemma, "azure_calls": azure, "runs": verdicts, "problems": problems}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payloads", required=True); ap.add_argument("--env-file", required=True)
    ap.add_argument("--tree", default=os.environ.get("STRESS_REPO") or os.path.abspath(os.path.join(HERE, "..", "..", "repo-dev")))
    ap.add_argument("--only", nargs="*", default=[]); ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--max-parallel", type=int, default=3); ap.add_argument("--gemma", action="store_true")
    ap.add_argument("--livekit-env", default=LIVEKIT_ENV); ap.add_argument("--out", default="")
    ap.add_argument("--judge-model", default="gpt-4.1"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-preflight", action="store_true", help="skip the freeze manifest (never for a board that is quoted)")
    args = ap.parse_args()
    items = [t for t in twins(args.payloads) if not args.only or t[0] in args.only]
    if not items:
        raise SystemExit("no live twins selected; run build_live_twins.py first")
    node = scheduler_id(os.path.join(HERE, "flow.json"))
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if args.gemma:
        env.update({"LIVEKIT_INFERENCE_ENABLED": "true",
                    "LIVEKIT_INFERENCE_API_KEY": env_value(args.livekit_env, "LIVEKIT_INFERENCE_API_KEY"),
                    "LIVEKIT_INFERENCE_API_SECRET": env_value(args.livekit_env, "LIVEKIT_INFERENCE_API_SECRET")})
        assert env["LIVEKIT_INFERENCE_API_KEY"] and env["LIVEKIT_INFERENCE_API_SECRET"], "inference pair missing"
    log_dir = args.out or os.path.join(HERE, "live-runs", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(log_dir, exist_ok=True)
    print(f"tree={args.tree} node={node} gemma={args.gemma} twins={len(items)} repeat={args.repeat} -> {log_dir}")
    # No board runs without a frozen manifest and a green canary: a stale flow or a missing action passcode
    # is caught here, in one line, instead of as a board of calls that all fail at their first action.
    if not args.no_preflight:
        import preflight
        man = preflight.build(args.tree, args.payloads, os.path.join(HERE, "flow.json"), args.env_file)
        json.dump(man, open(os.path.join(log_dir, "preflight.json"), "w"), indent=1)
        print(f"preflight: flow {man['flow']['sha']} ({man['flow']['mtime']}) instructions {man['flow']['instructions_sha']} | "
              f"tree {man['tree']['commit']} {man['tree']['tree_object'][:8]} dirty={man['tree']['dirty']} | "
              f"rubrics {man['rubrics']['sha']} x{man['rubrics']['count']} | harness {man['harness']['judge.py']} | "
              f"{man['date_anchor']} {man['timezone']} | canary {man['canary']['ok']}: {man['canary']['why']}", flush=True)
        if not man["canary"]["ok"] or man["tree"]["dirty"]:
            raise SystemExit("preflight failed: the board would not be evidence")
    results = {}
    with cf.ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
        for slug, res, _ in ex.map(lambda it: run_one(it, args, env, node, log_dir), items):
            results[slug] = res
            if args.dry_run:
                print(res); continue
            runs = res["runs"]; passed = sum(r["verdict"] == "PASS" for r in runs)
            partial = sum(r["verdict"] == "PARTIAL" for r in runs)
            green = bool(runs) and passed == len(runs) == args.repeat and not res["problems"]
            state = "PASS" if green else ("PART" if partial and not res["problems"] else "FAIL")
            res["verdict"] = state
            line = f"{state:4} {passed}/{args.repeat} {slug:38} exit={res['exit']} {res['seconds']}s gemma={res['gemma_calls']} azure={res['azure_calls']}"
            if partial: line += f" partial={partial}"
            for p_ in res["problems"]: line += f" | PROBLEM {p_}"
            for r in runs:
                bad = [str(c.get("n")) for c in r["criteria"] if not c.get("met")]
                miss = [v["key"] for v in r.get("variables", []) if not v["met"]]
                line += f" | run{r['run']} {r['score']:.2f} intent={r['final_intent']!r}" + (f" notmet={','.join(bad)}" if bad else "") + (f" vars!={','.join(miss)}" if miss else "")
            print(line, flush=True)
    if not args.dry_run:
        json.dump(results, open(os.path.join(log_dir, "board.json"), "w"), indent=1)
        total = args.repeat * len(results); ok = sum(sum(x["verdict"] == "PASS" for x in r["runs"]) for r in results.values())
        green = [s_ for s_, r in results.items() if r.get("verdict") == "PASS"]
        bad = {s_: r["problems"] for s_, r in results.items() if r["problems"]}
        print(f"board: {ok}/{total} runs PASS; {len(green)}/{len(results)} twins green -> {log_dir}/board.json")
        if bad:
            print(f"board problems (these twins are not evidence): {json.dumps(bad)}")
        raise SystemExit(0 if len(green) == len(results) else 1)


if __name__ == "__main__":
    main()
