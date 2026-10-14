"""Wait for the clinic window, convert the pack, run the 48-call board with the switch on and then off, and print the tables.

  python board_at_window.py <tag>      (launch detached: it outlives the harness shell)

Writes s1-thin-audit/lane/<tag>.driver.log; its last line is ALL-DONE or a FAILED line.
"""
import datetime
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

V = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LANE = os.path.join(V, "text-evals", "text-lane")
TREE = os.path.join(V, "s1-fix-lane")
PY = os.path.join(TREE, ".venv", "bin", "python")
TAG = sys.argv[1]
LOG = open(os.path.join(V, "s1-thin-audit", "lane", f"{TAG}.driver.log"), "a", buffering=1)


def say(line: str) -> None:
    LOG.write(f"{datetime.datetime.now(ZoneInfo('Asia/Kolkata')):%H:%M:%S} {line}\n")


def window_open() -> bool:
    ist, pt = datetime.datetime.now(ZoneInfo("Asia/Kolkata")), datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    return (ist.hour, ist.minute) >= (12, 31) and ist.date() == pt.date()


def run(argv: list[str], log: str, cwd: str = V) -> int:
    with open(log, "w") as out:
        return subprocess.run(argv, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env={**os.environ, "LANE_TREE": TREE}).returncode


say(f"waiting for 12:31 IST with the clinic day equal to the IST day; tree {TREE}")
while not window_open():
    time.sleep(30)
say("window open: converting the pack")
if run([PY, "lane.py", "convert"], os.path.join(V, "s1-thin-audit", "lane", f"{TAG}.convert.log"), cwd=LANE):
    say("FAILED convert")
    sys.exit(1)
only = sorted(os.listdir(os.path.join(LANE, "pack")))
for arm, flag in (("", "--main-shaped"), ("-off", "--switch-off")):
    campaign = f"{TAG}{arm}"
    say(f"start {campaign} ({len(only)} scenarios)")
    code = run([PY, "s1-thin-audit/lane/s1_lane.py", "run", flag, "--campaign", campaign, "--campaign-cap", "14", "--run-usd", "1.0",
                "--max-parallel", "4", "--timeout", "540", "--only", *only], os.path.join(V, "s1-thin-audit", "lane", f"{campaign}.launch.log"))
    say(f"done {campaign} exit={code}")
board = [PY, "s1-thin-audit/lane/board_s1.py"]
run([*board, f"text-evals/text-lane/runs/{TAG}", "--out", f"text-evals/text-lane/runs/{TAG}/board-s1.md"], os.path.join(V, "s1-thin-audit", "lane", f"{TAG}.board.log"))
run([*board, f"text-evals/text-lane/runs/{TAG}-off", "--switch-off", "--out", f"text-evals/text-lane/runs/{TAG}-off/board-s1.md"],
    os.path.join(V, "s1-thin-audit", "lane", f"{TAG}-off.board.log"))
say("ALL-DONE")
