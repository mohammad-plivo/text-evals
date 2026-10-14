#!/usr/bin/env python3
"""The Hunter side of the v2.10 Stress Test: register the 30 callers, start a run, and check a run two ways.

    python3 hunter.py create --cookie <file>            # create or update the callers in Hunter, read each back and compare
    python3 hunter.py run --cookie <file> [--alone]     # one run: the callers that can share the line, or the ones that must run alone
    python3 hunter.py run --cookie <file> 01 08         # one run of the callers named, for a first call
    python3 hunter.py check --cookie <file> <run id>    # Hunter's verdict next to what the stack's own log shows

Hunter judges the words of a call. `check` adds the logic: for each call it reads the stack's log and compares the end
node, the nodes passed, the actions run, what each was sent and the values saved with what callers.py expects. The
comparison is strict: a saved value must be the whole expected value. A call passes only when both do.
For every entry into an AI step it also prints the silence the caller heard, the step's first line and how many steps Jev picked in it.
Run build.py first on the day of a board, and `create` again after the tunnels are re-made. The cookie is never printed.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "FHCSD/hunter"))
import align_dev_board as dev  # noqa: E402  (the Hunter request helper)
import read_jev_failures as rig  # noqa: E402  (finds the local run of a Hunter call)

import spec  # noqa: E402

STATE = HERE / "created.json"   # Hunter's id for each caller; outside out/, which build.py rebuilds
WORKING_CALLER = 20018          # a local caller whose trigger header is known to work on this account
LOCAL_KEYS = ("_built_ist", "_log", "_alone")
STACK = "v210"


def cookie_from(path: str) -> str:
    text = Path(path).read_text().strip()
    return text if text.startswith("hunter_session=") else "hunter_session=" + text


def built() -> list[dict]:
    docs = [json.loads(path.read_text()) for path in sorted((HERE / "out/hunter").glob("*.json"))]
    today = datetime.datetime.now(spec.IST).date().isoformat()
    assert docs and all(doc["_built_ist"] == today for doc in docs), "built on another day: run build.py first"
    return docs


def create(cookie: str) -> None:
    header = dev.req("GET", f"/api/scenarios/{WORKING_CALLER}", cookie)["payload"]["initiationRequest"]["headers"]["Authorization"]
    ids = json.loads(STATE.read_text()) if STATE.exists() else {}
    for doc in built():
        slug = doc["name"].split(" ", 1)[1]
        body = {key: value for key, value in doc.items() if key not in LOCAL_KEYS}
        body["payload"]["initiationRequest"]["headers"]["Authorization"] = header
        if slug in ids:
            dev.req("PUT", f"/api/scenarios/{ids[slug]}", cookie, body)
        else:
            ids[slug] = dev.req("POST", "/api/scenarios", cookie, body)["id"]
            STATE.write_text(json.dumps(ids, indent=1))
        back = dev.req("GET", f"/api/scenarios/{ids[slug]}", cookie)
        differ = [key for key in body["payload"] if back["payload"].get(key) != body["payload"][key]]
        print(f"  {ids[slug]} {slug:46s} {'DIFFERS: ' + ', '.join(differ) if differ else 'stored as sent'}")
    print(f"{len(ids)} callers in {built()[0]['category']!r}; no call was placed")


def run(cookie: str, alone: bool, parts: list[str]) -> None:
    ids = json.loads(STATE.read_text())
    slugs = {doc["name"].split(" ", 1)[1]: doc["_alone"] for doc in built()}
    wanted = [slug for slug, single in slugs.items() if (any(part in slug for part in parts) if parts else single == alone)]
    alone = alone or any(slugs[slug] for slug in wanted)
    tests = subprocess.run(["pgrep", "-fl", "python.* -m pytest"], capture_output=True, text=True).stdout.strip()
    assert not tests, f"a test suite is running on this laptop, so no call is placed:\n{tests}"
    name = f"v2.10 Stress Test {'alone ' if alone else ''}{datetime.datetime.now(spec.IST):%m%d %H%M}"
    dev.req("POST", "/api/runs", cookie, {"name": name, "scenarioIds": [str(ids[slug]) for slug in wanted], "maxParallel": 1 if alone else 4})
    started = next(row for row in dev.req("GET", "/api/runs?limit=5", cookie)["runs"] if row["name"] == name)
    print(started["id"], started["status"], f"{len(wanted)} callers, {'one at a time' if alone else '4 at a time'}")


def local_log(phone: str, started_at: float) -> list[dict]:
    query = rig.LOCAL_RUN.format(t=float(started_at), digits=re.sub(r"\D", "", phone or "")[-10:])
    out = subprocess.run(["docker", "exec", f"{STACK}-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c", query],
                         capture_output=True, text=True, check=True).stdout.strip()
    return [row["log"] for row in json.loads(out)] if out else []


def seen(rows: list[dict]) -> dict:
    """What a call did, from the stack's own log: the nodes it passed, the actions it ran, the values it saved."""
    nodes = [row.get("current_node") for row in rows if row.get("event_name") == "NODE_EXECUTED"]
    calls = [row for row in rows if row.get("type") == "TOOL_CALL_EVENT"]
    tools = [(row.get("tool_name"), json.dumps(row.get("tool_input"))) for row in calls]
    errors = [row.get("tool_name") for row in calls if re.match(r"\s*(Code execution failed|Error|Traceback)", str(row.get("tool_response")))]
    saved: dict[str, str] = {}
    for row in rows:
        if row.get("type") == "text":
            saved.update({key: str(value) for key, value in ((row.get("node_config") or {}).get("variables") or {}).items()})
    return {"nodes": nodes, "tools": tools, "saved": saved, "errors": errors}


def jev_turns() -> collections.Counter:
    """Steps Jev picked per (flow run, node), from the agent-runner's own log."""
    out = subprocess.run(["docker", "logs", f"{STACK}-agent-runner"], capture_output=True, text=True)
    lines = [json.loads(line) for line in (out.stdout + out.stderr).splitlines() if line.startswith("{") and "system_one: step=" in line]
    return collections.Counter((line.get("flow_run_uuid"), line.get("node_uuid")) for line in lines)


def moves(rows: list[dict], jev: collections.Counter) -> tuple[list[dict], list[str]]:
    """Every entry into an AI step: the silence from the last word before it to its first word, its first line, the steps Jev
    picked in it. Then what went wrong."""
    at = lambda row: datetime.datetime.fromisoformat(row["timestamp"]).timestamp()   # noqa: E731
    notes, faults = [], []
    for index, row in enumerate(rows):
        if row.get("event_name") != "NODE_EXECUTED" or row.get("current_node") not in spec.NODES:
            continue
        name = row["current_node"]
        stopped = [at(earlier) for earlier in rows[:index] if earlier.get("type") in ("USER_STOPPED_SPEAKING", "BOT_STOPPED_SPEAKING")
                   or (earlier.get("type") == "text" and (earlier.get("text") or "").strip())]   # a spoken line is logged when it ends
        spoke = [at(later) for later in rows[index:] if later.get("type") == "BOT_STARTED_SPEAKING"]
        first = next((" ".join(later["text"].split()) for later in rows[index:] if later.get("type") == "text" and later.get("sender") != "user"
                      and later.get("node_run_uuid") == row.get("node_run_uuid") and (later.get("text") or "").strip()), "")
        turns = jev[(row.get("flow_run_uuid"), row.get("current_node_uuid"))]
        notes.append({"from": row.get("previous_node"), "to": name, "jev": turns, "first": first,
                      "silence": round(spoke[0] - max(stopped), 1) if stopped and spoke else None})
        if not first or "still there" in first.lower():
            faults.append(f"{name} said nothing after the move" + (" until the check-in" if first else ""))
        if not turns:
            faults.append(f"{name} ran without System One")
    return notes, faults


def _plain(text) -> str:
    return re.sub(r"[^a-z0-9@._+]", "", str(text).lower())


def _fits(want, got) -> bool:
    """Strict on purpose. Text must be the whole value. A number must be the only number in it. A list is parts that must
    all be in it, and a part that starts with ! must not be. True is any value at all."""
    if want is True:
        return _plain(got) not in ("", "none", "notprovided")
    if isinstance(want, (int, float)):
        return [float(number) for number in re.findall(r"\d+(?:\.\d+)?", str(got))] == [float(want)]
    if isinstance(want, list):
        return all((_plain(part[1:]) not in _plain(got)) if part.startswith("!") else (_plain(part) in _plain(got)) for part in want)
    return _plain(want) == _plain(got)


def _sent(text: str) -> dict:
    try:
        return json.loads(text)
    except ValueError:
        return {}


def problems(expect: dict, did: dict) -> list[str]:
    """Where the call's log differs from what the caller was written to make happen. Empty means the logic held."""
    out, nodes = [], did["nodes"]
    end = expect["end"]
    if end == "End Transfer":
        if spec.TRANSFER not in nodes:
            out.append(f"never reached {spec.TRANSFER}")
    elif not nodes or nodes[-1] != end:
        out.append(f"ended at {nodes[-1] if nodes else 'nothing'}, expected {end}")
    walked = [name for name in nodes if name in spec.NODES or name == spec.TRANSFER]
    if walked != expect["path"]:
        out.append(f"passed {walked or 'no AI node'}, expected {expect['path'] or 'no AI node'}")
    names = [name for name, _ in did["tools"]]
    out += [f"{tool} ran {names.count(tool)} times, expected {count}" for tool, count in expect.get("actions", {}).items() if names.count(tool) != count]
    out += [f"{tool} ran, and must never run on this call" for tool in expect.get("never", []) if tool in names]
    out += [f"{tool} failed with an error" for tool in sorted(set(did.get("errors", [])) - set(expect.get("fails", [])))]
    for tool, wanted in expect.get("args", {}).items():
        sent = [_sent(text) for name, text in did["tools"] if name == tool]
        right = lambda want, call: all(_fits(value, call.get(key, "")) for key, value in want.items())   # noqa: E731
        if isinstance(wanted, list):   # one entry per call, in order
            out += [f"call {number} of {tool} was sent {call}, expected {want}" for number, (want, call) in enumerate(zip(wanted, sent), 1)
                    if not right(want, call)]
        elif not any(right(wanted, call) for call in sent):
            out.append(f"no call of {tool} was sent {wanted}; it was sent {sent}")
    out += [f"{key} saved as {did['saved'].get(key)!r}, expected {value!r}" for key, value in expect.get("saved", {}).items()
            if not _fits(value, did["saved"].get(key, ""))]
    out += [f"{key} was saved as {did['saved'][key]!r} and should be empty" for key in expect.get("unsaved", [])
            if _fits(True, did["saved"].get(key, ""))]
    return out


def check(cookie: str, run_ids: list[str]) -> None:
    expected = {doc["name"]: doc["_log"] for doc in built()}
    both = total = 0
    jev = jev_turns()
    for run_id in run_ids:
        board = dev.req("GET", f"/api/runs/{run_id}", cookie)
        print(f"{board['name']} | {board['status']}")
        kept = []
        for item in sorted(board.get("items") or [], key=lambda item: item.get("scenario_name") or ""):
            name, total = item.get("scenario_name") or "", total + 1
            if not item.get("call_id"):
                print(f"  NO CALL   {name}: {item.get('error_message')}")
                continue
            call = dev.req("GET", f"/api/calls/{item['call_id']}", cookie)
            unjudged = str(call.get("comments") or "").startswith("Evaluation error")
            words = "not judged" if unjudged else item.get("result")
            rows = local_log(call.get("phone_number"), call.get("started_at"))
            notes, stuck = moves(rows, jev)
            unfilled = [f"a value was read out unfilled: {' '.join(row['text'].split())[:90]!r}" for row in rows
                        if row.get("type") == "text" and "{{" in (row.get("text") or "")]
            faults = problems(expected[name], seen(rows)) + stuck + unfilled
            both += words == "pass" and not faults
            seconds = round(int(call.get("duration_ms") or 0) / 1000)
            print(f"  words {words:10s} logic {'pass' if not faults else 'FAIL':4s} {seconds:4d}s  {name}")
            judge = [re.sub(r"\s+", " ", line).strip() for line in (call.get("eval_breakdown") or {}).get("criteria") or [] if "NOT MET" in line]
            checkins = sum("still there" in (row.get("text") or "").lower() for row in rows if row.get("type") == "text" and row.get("sender") != "user")
            kept.append({"caller": name, "words": words, "seconds": seconds, "judge": judge, "log": faults, "moves": notes, "checkins": checkins,
                         "flow_run": rows[0].get("flow_run_uuid") if rows else None, "call": item["call_id"]})
            for line in judge:
                print("      judge: " + line[:300])
            for fault in faults:
                print("      log:   " + fault)
            for note in notes:
                print(f"      move:  {note['from']} -> {note['to']}: {note['silence']} s of silence, {note['jev']} Jev steps, first line {note['first'][:110]!r}")
        (HERE / "out/voice").mkdir(exist_ok=True)   # read by page.py
        (HERE / "out/voice" / f"{run_id}.json").write_text(json.dumps({"name": board["name"], "calls": kept}, indent=1))
    print(f"{both} of {total} calls pass both the judge and the log check")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "run", "check"))
    parser.add_argument("--cookie", required=True)
    parser.add_argument("--alone", action="store_true")
    parser.add_argument("runs", nargs="*")
    args = parser.parse_intermixed_args()   # the caller numbers come after --cookie
    cookie = cookie_from(args.cookie)
    {"create": lambda: create(cookie), "run": lambda: run(cookie, args.alone, args.runs), "check": lambda: check(cookie, args.runs)}[args.command]()


if __name__ == "__main__":
    main()
