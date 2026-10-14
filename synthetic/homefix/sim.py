#!/usr/bin/env python3
"""Run callers of the logic flow in the text simulator inside the v210 agent container, and save each conversation.

    python3 sim.py [slug part ...]        # default: every caller that reaches an AI node
    python3 sim.py --check                # count the saved runs of each caller again, run nothing

The plain simulator cannot cross from the screening step into an AI node, so a run starts at Account Check. The three
callers that end inside screening (13, 14, 15) and the opening line of caller 04 are for voice only. Actions run for real
in the sandbox. Three runs at a time; nothing is dialled. The simulator's own verdict only looks at the ending, so each
conversation also gets the log check a voice call gets: the steps passed, the actions run, the values saved.

Each invocation is kept in its own folder under out/sim-results/, because one text run is an anecdote: run it a few times
and read the counts. After spec.py or callers.py changes, move the old folders away so the counts are of one flow.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import callers
import hunter
import spec

HERE = Path(__file__).parent
BOX = "v210-agent-runner"
STAMP = time.strftime("%m%d-%H%M%S")
BASE = "/tmp/v210-logic/run-" + STAMP   # a new folder each time: a run left behind cannot mark a new one done
ENGINE = os.environ.get("ENGINE_DIR", "/app")   # another copy of the engine inside the container, to compare two engines
RUNS = HERE / "out" / ("sim-results" if ENGINE == "/app" else "sim-results-other-engine")


def box(script: str, detach: bool = False) -> str:
    return subprocess.run(["docker", "exec", *(["-d"] if detach else []), "-w", ENGINE, BOX, "sh", "-c", script],
                          capture_output=True, text=True).stdout


def did(talk: list[str]) -> dict:
    """What a text run did, in the shape the voice log check reads: steps passed, actions run, values saved."""
    nodes, tools, saved, intent = [spec.CHECK], [], {}, None
    for line in talk:
        hop = re.search(r"↪ node: .* → (.+)$", line)
        call = re.match(r"\s*TOOL : (\w+)\((.*)\)\s*$", line)
        if hop:
            nodes.append(hop.group(1).strip())
        elif call and call.group(1) in spec.actions({}):
            tools.append((call.group(1), call.group(2)))
        elif call and call.group(1).startswith("record_") and call.group(1) != "record_inputs":
            saved[call.group(1)[len("record_"):]] = str(json.loads(call.group(2)).get("value"))
        elif "INTENT:" in line:
            intent = line.split("INTENT:", 1)[1].strip()
    target = next((to for name, _, _, to in spec.NODES[nodes[-1]]["exits"] if name == intent), None)
    return {"nodes": nodes + ([target] if target else []), "tools": tools, "saved": saved}


def faults(slug: str, talk: list[str]) -> list[str]:
    """Why a text run is not a pass: the simulator's own verdict (the planned way out, the call ended), then the voice log check."""
    ending = [] if any("✓ PASS" in line for line in talk) else ["the call did not end by the planned way out"]
    return ending + hunter.problems(next(caller["log"] for caller in callers.CALLERS if caller["slug"] == slug), did(talk))


def saved() -> dict[str, list[list[str]]]:
    """The faults of every saved text run of each caller, oldest run first. An empty list is a pass."""
    runs: dict[str, list[list[str]]] = {}
    for path in sorted(RUNS.glob("*/*.txt")):
        runs.setdefault(path.stem, []).append(faults(path.stem, path.read_text().splitlines()))
    return runs


def check_saved() -> None:
    for slug, runs in sorted(saved().items()):
        print(f"{slug:44s} {sum(not run for run in runs)} of {len(runs)} pass")
        for fault in sorted({"; ".join(run) for run in runs if run}):
            print(f"      {fault[:260]}")


def main() -> None:
    if sys.argv[1:2] == ["--check"]:
        return check_saved()
    flow = json.loads((HERE / "out/flow.json").read_text())
    entry = next(node["id"] for node in flow["nodes"] if node["data"]["config"]["name"] == spec.CHECK)
    wanted = [caller["slug"] for caller in callers.CALLERS if caller["log"]["path"]
              and (not sys.argv[1:] or any(part in caller["slug"] for part in sys.argv[1:]))]
    subprocess.run(["docker", "exec", BOX, "sh", "-c", f"mkdir -p {BASE}"], check=True)
    for slug in wanted:
        subprocess.run(["docker", "cp", str(HERE / "out/sim" / slug), f"{BOX}:{BASE}/{slug}"], check=True)
    results = RUNS / STAMP
    results.mkdir(parents=True)
    waiting, running, passed = list(wanted), [], 0
    while waiting or running:
        while waiting and len(running) < 3:
            slug = waiting.pop(0)
            box(f"python -m src.simulation.cli run {BASE}/{slug} --node {entry} --env-file /app/.env --no-open --verbose "
                f"> {BASE}/{slug}/run.log 2>&1; echo $? > {BASE}/{slug}/done.flag", detach=True)
            running.append(slug)
        time.sleep(5)
        for slug in list(running):
            code = box(f"cat {BASE}/{slug}/done.flag 2>/dev/null").strip()
            if code:
                running.remove(slug)
                log = box(f"cat {BASE}/{slug}/run.log")
                (results / f"{slug}.log").write_text(log)
                talk = [line for line in log.splitlines() if not line.startswith("{")]
                (results / f"{slug}.txt").write_text("\n".join(talk) + "\n")
                found = faults(slug, talk)
                passed += not found
                print(f"{slug:44s} {'pass' if not found else 'FAIL: ' + '; '.join(found)}", flush=True)
    print(f"{passed} of {len(wanted)} reached the planned end with the planned steps, actions and values; saved in {results}")


if __name__ == "__main__":
    main()
