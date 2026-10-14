"""Run the sim CLI on one tree with the local livekit env exported into the child process (never printed).
usage: launch.py <tree> <workspace> <label> [cli args after 'run <ws>', e.g. --repeat 5 --scenario x]"""
import os, re, subprocess, sys, time

ENV_FILE = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/cx-dev-dockerized-v291-jev/services/plivo-cx-livekit/.env"
tree, ws, label, extra = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3], sys.argv[4:]
env = dict(os.environ)
for line in open(ENV_FILE, errors="replace"):
    m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
    if m and m.group(2).strip().strip('"').strip("'"):
        env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
env["LIVEKIT_INFERENCE_ENABLED"] = "true"
os.makedirs(f"{ws}/logs", exist_ok=True)
log = f"{ws}/logs/{label}-{time.strftime('%H%M%S')}.log"
head = subprocess.run(["git", "-C", tree, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(["git", "-C", tree, "status", "--short"], capture_output=True, text=True).stdout.strip()
if dirty:  # the arm is the base commit plus exactly this patch
    open(f"{ws}/logs/{label}.diff", "w").write(subprocess.run(["git", "-C", tree, "diff"], capture_output=True, text=True).stdout)
cmd = [f"{tree}/.venv/bin/python", "-m", "src.simulation.cli", "run", ws, "--env-file", ENV_FILE, "--verbose", "--no-open", *extra]
with open(log, "w") as f:
    f.write(f"# tree {tree} @ {head} dirty={bool(dirty)}\n# {' '.join(cmd[1:])}\n")
    f.flush()
    rc = subprocess.run(cmd, cwd=tree, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
print(f"{label}: exit {rc}, tree {head}{' +local changes' if dirty else ''}, log {log}")
