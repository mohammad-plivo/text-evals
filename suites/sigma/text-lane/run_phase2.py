"""Run every full-length Sigma case N times on the model the env file routes to, K at a time.

Usage: python3 run_phase2.py <worktree> <reps> <tag> [parallel=3]
A Python driver on purpose: zsh does not word-split and macOS bash 3.2 has no mapfile / wait -n.
"""
import subprocess, sys, pathlib, concurrent.futures, datetime
WT, REPS, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
PAR = int(sys.argv[4]) if len(sys.argv) > 4 else 3
SP = pathlib.Path("/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/cd27465f-3644-41c6-9c4c-1e7142e58b3b/scratchpad")
RUN = pathlib.Path(__file__).with_name("run_case.sh")
out = SP / "eval" / TAG; out.mkdir(parents=True, exist_ok=True)
cases = subprocess.run(["uv", "run", "--frozen", "python", "-c",
    "from tests.v29_model_eval.session_cases import MULTI_TURN_CASES\n"
    "print('\\n'.join(c['id'] for c in MULTI_TURN_CASES if c['id'].startswith('sigma_full_')))"],
    cwd=WT, capture_output=True, text=True).stdout.split()
print(f"cases: {len(cases)} reps: {REPS} parallel: {PAR} tag: {TAG}", flush=True)
def one(case):
    with open(out / f"{case}.summary", "w") as f:
        subprocess.run(["bash", str(RUN), WT, case, REPS, TAG], stdout=f, stderr=subprocess.STDOUT)
    return f"done {case} {datetime.datetime.now():%H:%M:%S}"
with concurrent.futures.ThreadPoolExecutor(max_workers=PAR) as pool:
    for line in pool.map(one, cases): print(line, flush=True)
print(f"ALL-DONE {datetime.datetime.now():%H:%M:%S}")
