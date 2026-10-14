import subprocess, sys, os
# detached lane launch: python3 launch.py LOG -- lane args...
log, args = sys.argv[1], sys.argv[3:]
lane = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "text-lane")
py = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev/rw-text-lane/.venv/bin/python"
p = subprocess.Popen([py, "lane.py", *args], cwd=lane, stdout=open(log, "w"), stderr=subprocess.STDOUT,
                     start_new_session=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
print(p.pid)
