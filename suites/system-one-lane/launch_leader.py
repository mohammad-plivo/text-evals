"""Detached launch of the V2.9 suite on the Jev leader (tree rw-v29-evals-jev, shared ledger).

  python3 launch_leader.py NAME CAMPAIGN_ID MAX_USD REPETITIONS [extra live.py args, e.g. --cases a,b]

Prints the wrapper's pid and returns. The wrapper builds the env file with keys in a private temp dir (mode 600),
runs the suite with stdout in runs/NAME.stdout.log and rows in runs/NAME/rows.jsonl, and deletes the env dir when
the suite ends, however it ends. Never print the env file.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EVALS = os.path.dirname(HERE)
TREE = os.path.join(os.path.dirname(EVALS), "rw-v29-evals-jev")


def suite(name: str, campaign: str, max_usd: str, repetitions: str, *extra: str) -> int:
    sys.path.insert(0, os.path.join(EVALS, "text-lane"))
    import lane

    env_dir = tempfile.mkdtemp(prefix="v29-leader-env-")
    try:
        env = lane.env_file(os.path.join(env_dir, "leader.env"), "redis://127.0.0.1:1/0")
        out = os.path.join(HERE, "runs", name)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(HERE, "runs", name + ".stdout.log"), "a") as log:
            return subprocess.run(
                [os.path.join(TREE, ".venv", "bin", "python"), "-m", "tests.v29_model_eval.live", "--leader",
                 "--env-file", env, "--ledger", os.path.join(EVALS, "text-lane", "ledger.json"),
                 "--campaign-id", campaign, "--output", os.path.join(out, "rows.jsonl"), "--repetitions", repetitions,
                 "--suite", "extended", "--max-usd", max_usd, *extra],
                cwd=TREE, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "UV_NO_SYNC": "1"}).returncode
    finally:
        shutil.rmtree(env_dir, ignore_errors=True)


if __name__ == "__main__":
    if os.environ.get("LEADER_WRAPPER") == "1":
        sys.exit(suite(*sys.argv[1:]))
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), *sys.argv[1:]], start_new_session=True,
                             env={**os.environ, "LEADER_WRAPPER": "1"}, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(child.pid)
