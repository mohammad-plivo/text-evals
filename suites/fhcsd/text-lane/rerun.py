"""Run chosen runs of a lane campaign again: the ones that came back INVALID or NOT RUN.

  python3 rerun.py --campaign NAME --campaign-cap USD [--flow-ws WS --pack PACK] [--run-usd 2.0] [--max-parallel 1]
                   (--pairs SLUG:RUN ... | --not-valid)

Same preflight, env handling, ledger reservation, row.json and board as `lane.py run`; only the job list differs.
--not-valid picks every row of the campaign whose verdict is INVALID or NOT RUN. The run that is replaced keeps its
folder as <run>.not-valid-N with its row stored as row.first.json, so the board counts only the new run.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import shutil
import signal
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane  # noqa: E402


def set_aside(run_dir: str) -> None:
    """Keep the replaced run's evidence where the board does not read it."""
    if not os.path.exists(os.path.join(run_dir, "meter.jsonl")):
        return  # it never ran (NOT RUN): nothing to keep, and the new attempt clears the folder
    n = 1
    while os.path.exists(f"{run_dir}.not-valid-{n}"):
        n += 1
    kept = f"{run_dir}.not-valid-{n}"
    os.replace(run_dir, kept)
    if os.path.exists(os.path.join(kept, "row.json")):
        os.replace(os.path.join(kept, "row.json"), os.path.join(kept, "row.first.json"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--campaign-cap", type=float, required=True)
    ap.add_argument("--flow-ws")
    ap.add_argument("--pack", default=lane.PACK)
    ap.add_argument("--run-usd", type=float, default=2.0)
    ap.add_argument("--max-parallel", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--pairs", nargs="*", default=[])
    ap.add_argument("--not-valid", action="store_true")
    a = ap.parse_args()
    runs = lane.RUNS if a.pack == lane.PACK else os.path.join(os.path.dirname(os.path.abspath(a.pack)), "runs")
    camp = os.path.join(runs, a.campaign)
    jobs = [(p.rsplit(":", 1)[0], int(p.rsplit(":", 1)[1])) for p in a.pairs]
    if a.not_valid:
        rows = [json.load(open(path)) for path in sorted(glob.glob(os.path.join(camp, "*", "row.json")))]
        left = [(row["verdict"] == "NOT RUN", row["run"], row["scenario"]) for row in rows
                if row["verdict"] in ("INVALID", "NOT RUN")]
        jobs += [(slug, run) for _, run, slug in sorted(left)]  # invalid runs first, then run 1 of each scenario
    jobs = list(dict.fromkeys(jobs))  # the order given: the cap may stop the list early
    print(f"rerun {len(jobs)} runs: {jobs}", flush=True)
    if not jobs:
        return
    pid, port = lane.start_redis(camp)
    env_dir = tempfile.mkdtemp(prefix="lane-env-")  # keys never land in the lane folder
    try:
        env_path = lane.env_file(os.path.join(env_dir, "run.env"), f"redis://127.0.0.1:{port}/0")
        pre = lane.preflight(env_path, a.flow_ws, a.pack)
        print(f"preflight ok={pre['ok']} tree={pre['tree']['commit'][:9]} ledger={pre['ledger']} {pre['failures']}", flush=True)
        if not pre["ok"]:
            raise SystemExit("preflight failed; nothing ran")
        for slug, rep in jobs:
            set_aside(os.path.join(camp, f"{slug}-r{rep}"))
        with cf.ThreadPoolExecutor(max_workers=a.max_parallel) as ex:
            for row in ex.map(lambda j: lane.one(j[0], j[1], camp, env_path, a), jobs):
                if row.get("dir"):
                    os.makedirs(row["dir"], exist_ok=True)
                    json.dump(row, open(os.path.join(row["dir"], "row.json"), "w"), indent=1)
                print(f"{row['verdict']:8} {row['scenario']} r{row['run']} score={row.get('score')} cost=${row.get('cost_usd')} "
                      f"failed={row.get('checks_failed')} invalid={row.get('invalid_reasons') if row['verdict'] == 'INVALID' else ''}", flush=True)
    finally:
        os.kill(pid, signal.SIGTERM)
        shutil.rmtree(env_dir, ignore_errors=True)
    lane.board(camp)
    print(open(os.path.join(camp, "board.md")).read())


if __name__ == "__main__":
    main()
