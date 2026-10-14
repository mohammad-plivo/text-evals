#!/usr/bin/env python3
"""Refuse to start a board until the flow, the fixes and the tree are the ones we mean to test.

    python3 Sigma/hunter/preflight.py <worktree> [--expect "text that must be in the node" ...]

Board 6 was read for a night before anyone noticed the lane was executing a different flow from a
different day, and three of FHCSD's seven "failures" were scored against rules their agent never had.
Both were silent. This prints the four facts that make a board mean anything and exits non-zero if
any of them is wrong:

  1. the flow dump is the dev flow, and how old it is
  2. every scenario's agentConfig is that same flow and carries the expected fixes
  3. the tree under test is a known commit, and whether it is dirty
  4. nothing in the node still carries a rule a fix was supposed to remove
  5. every converted workspace executes its scenario's frozen agentConfig, transform for transform

Check 5 is the one board 6 needed and did not have. Every workspace flow carried only accept_past,
accept_today and require_time on the callback_time Input while the frozen source carried the authored
business calendar, so the lane graded a calendar policy the agent had never been given, and a
preflight that only compared flow ids passed it. This one rebuilds each workspace flow from its own
frozen source and fails on the first field that differs.

Run it before the text lane and before Hunter. A board published without it is not evidence.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DEV_FLOW = "6ada7153-7147-456d-ac1f-e3e3ef1c0b25"
sys.path.insert(0, str(HERE.parent / "hunter-sim"))

#: Text that must be present in the deployed node, one per fix that has landed. Add a line when a fix
#: lands; a board that runs without it is testing something else.
#: The guard rails the 2026-09-21 rebuild kept, in their rebuilt wording.
EXPECTED = [
    ("bundling", "Never hand a collector wording that asks for more than one thing"),
    ("location applicability", "If location data is missing or ambiguous, skip rather than invent a city"),
    ("wrong person stops collection", "do not ask for a callback time, and share nothing about the candidate"),
    ("wrong person outranks whereabouts", "Identity outranks every other reading of a turn"),
    ("human request precedence", "route to Human Followup"),
    ("collector confirmation is not a repeat", "That is not a repeat: never suppress it"),
    ("immediate joiner scope", "only when they are not an immediate joiner"),
    ("ug always collected", "Collect `ug_score` even when"),
    ("completion gate", "last available technical question"),
]
#: MK, 2026-09-21: the node had grown to 36,354 chars against 16,459 in the customer's own flow.
CEILING = 18000
#: Rules a fix removed. If one is back, the node has been reverted or re-saved from a stale copy.
FORBIDDEN = [
    ("old location rule", "If the candidate current location matches the only job location"),
    ("old wrong-person callback ask", "is not available, ask for a suitable callback time"),
    ("the variable nothing produces", "final_tech_question_answered"),
]

fails: list[str] = []


def check(ok: bool, good: str, bad: str) -> None:
    print(("  OK   " if ok else "  FAIL ") + (good if ok else bad))
    if not ok:
        fails.append(bad)


def first(problems: list[str], summary: str) -> str:
    """The failure line for a set of problems: check() builds both strings, so this must not index [0] when empty."""
    return f"{len(problems)} {summary}, first: {problems[0]}" if problems else ""


def drift(want, got, path: str = "") -> list[str]:
    """Every field where the executed flow differs from the frozen source, as a dotted path."""
    if type(want) is not type(got):
        return [f"{path or '<flow>'}: frozen is {type(want).__name__}, workspace is {type(got).__name__}"]
    if isinstance(want, dict):
        out = []
        for key in sorted(set(want) | set(got)):
            if key not in got:
                out.append(f"{path}.{key}: missing from the workspace flow")
            elif key not in want:
                out.append(f"{path}.{key}: in the workspace flow but not in the frozen source")
            else:
                out += drift(want[key], got[key], f"{path}.{key}")
        return out
    if isinstance(want, list):
        if len(want) != len(got):
            return [f"{path}: frozen has {len(want)} items, workspace has {len(got)}"]
        return [d for i, pair in enumerate(zip(want, got)) for d in drift(pair[0], pair[1], f"{path}[{i}]")]
    if want == got:
        return []
    # a node's instructions are thousands of characters; the path plus a window is what names the field
    short = lambda v: (r[:90] + "..." if len(r := repr(v)) > 90 else r)
    return [f"{path}: frozen {short(want)}, workspace {short(got)}"]


def main() -> None:
    worktree = sys.argv[1] if len(sys.argv) > 1 else ""
    dump_path = HERE / "flow-dump.json"

    print("1. flow dump")
    dump = json.loads(dump_path.read_text())
    age_h = (datetime.now(timezone.utc) - datetime.fromtimestamp(dump_path.stat().st_mtime, timezone.utc)).total_seconds() / 3600
    check(dump["phlo"]["uuid"] == DEV_FLOW, f"dev flow {DEV_FLOW}", f"NOT the dev flow: {dump['phlo']['uuid']}")
    check(age_h < 12, f"dumped {age_h:.1f}h ago", f"dumped {age_h:.1f}h ago — refresh it from the database first")
    ai = [n for n in dump["nodes"] if str(n["component"]).startswith("AI conversation")]
    check(len(ai) == 1, "one V2.9 node in the dump", f"{len(ai)} V2.9 nodes in the dump")
    node_text = json.dumps(ai[0]["config"]) if ai else ""

    print("2. the fixes are in the node")
    for label, marker in EXPECTED:
        check(marker in node_text, label, f"{label}: MISSING from the node")
    instr = len(ai[0]["config"]["model"]["instructions"]) if ai else 0
    check(instr <= CEILING, f"instructions {instr} chars, under the {CEILING} ceiling",
          f"instructions have grown to {instr} chars, over the {CEILING} ceiling")
    for label, marker in FORBIDDEN:
        check(marker not in node_text, f"{label} is gone", f"{label}: STILL PRESENT — the node looks reverted")

    print("3. scenarios point at that same flow")
    files = sorted((HERE / "scenarios").glob("*.json"))
    wrong = [f.name for f in files if json.loads(f.read_text())["payload"].get("agentConfig", {}).get("flowId") != DEV_FLOW]
    check(bool(files), f"{len(files)} scenarios", "no scenarios found")
    check(not wrong, "every agentConfig is the dev flow", f"{len(wrong)} scenarios carry another flow: {wrong[:3]}")
    stale = [f.name for f in files
             if not all(m in json.dumps(json.loads(f.read_text())["payload"].get("agentConfig", {})) for _, m in EXPECTED)]
    check(not stale, "every agentConfig carries the fixes", f"{len(stale)} scenarios predate a fix: {stale[:3]} — rebuild")

    print("4. every entry node the lane uses exists in this flow")
    uuids = {n["uuid"]: n["name"] for n in dump["nodes"]}
    ws_root = Path(worktree) / "eval_tests" / "sigma_v29_hunter" if worktree else None
    entries: dict[str, str] = {}
    if ws_root and ws_root.is_dir():
        for hunter in sorted(ws_root.glob("*/hunter.json")):
            node = json.loads(hunter.read_text()).get("entry_node")
            if node:
                entries.setdefault(node, hunter.parent.name)
    for node, where in entries.items():
        check(node in uuids, f"{node[:8]} ({uuids.get(node, '?')})",
              f"{node[:8]} is not a node in this flow — first seen in {where}")
    if not entries:
        print("  ..    no converted workspaces yet, entry nodes not checked")

    print("5. every workspace flow is its frozen source plus the declared transforms")
    payloads = {f.name: json.loads(f.read_text())["payload"] for f in files}
    shapes = {hashlib.sha256(json.dumps(p.get("agentConfig"), sort_keys=True).encode()).hexdigest()
              for p in payloads.values()}
    check(len(shapes) == 1, f"one canonical frozen source across {len(payloads)} scenarios ({min(shapes)[:12]})",
          f"{len(shapes)} different agentConfigs across the scenarios: there is no one frozen source")
    if ws_root and ws_root.is_dir() and entries:
        import convert  # the converter declares the transforms, so it is the one that can redo them
        import yaml

        unknown, undeclared, mislabelled, drifted, checked = [], [], [], [], 0
        for hunter_path in sorted(ws_root.glob("*/hunter.json")):
            ws, meta = hunter_path.parent, json.loads(hunter_path.read_text())
            name = ws.name
            payload = payloads.get(meta.get("source"))
            if not (payload or {}).get("agentConfig", {}).get("nodes"):
                unknown.append(f"{name}: source {meta.get('source')!r} has no frozen agentConfig here")
                continue
            recorded = meta.get("repairs") or []
            undeclared += [f"{name}: undeclared transform {r!r}" for r in recorded if not r.startswith(convert.TRANSFORMS)]
            redone: list[str] = []
            params = convert.params_for(payload)
            want = convert.canonical_flow(payload, params, meta.get("timezone") or "", redone)
            if redone != recorded:
                mislabelled.append(f"{name}: hunter.json records {recorded}, the conversion does {redone}")
            # the flow is not all a workspace executes: the Start params and the persona run too
            for label, expected, actual in (
                    ("flow.json", want, json.loads((ws / "flow.json").read_text())),
                    ("params.yaml", {"params": params, "substitutions": {}}, yaml.safe_load((ws / "params.yaml").read_text())),
                    (f"scenarios/{name}.yaml", convert.scenario_for(meta["name"], payload),
                     yaml.safe_load((ws / "scenarios" / f"{name}.yaml").read_text()))):
                found = drift(expected, actual)
                if found:
                    drifted.append((f"{name} {label}", found))
            checked += 1
        check(not unknown, f"{checked} workspaces trace back to a scenario", first(unknown, "workspaces do not trace back to a scenario"))
        check(not undeclared, "only declared transforms were applied", first(undeclared, "undeclared transforms"))
        check(not mislabelled, "hunter.json records the transforms the board will print", first(mislabelled, "repair lists are wrong"))
        check(not drifted, f"all {checked} workspaces match their frozen source: flow, params and persona",
              f"{len(drifted)} workspace file(s) drift from the frozen source")
        for name, found in drifted[:3]:
            print(f"        {name}: {len(found)} field(s) differ")
            for line in found[:5]:
                print(f"          {line}")
    else:
        print("  ..    no converted workspaces yet, executed flows not compared")

    print("6. the tree under test")
    if worktree:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=worktree, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=worktree, capture_output=True, text=True).stdout.strip()
        check(bool(head), f"HEAD {head}", "not a git worktree")
        check(not dirty, "src is clean", f"src has uncommitted changes:\n{dirty[:300]}")
    else:
        print("  ..    no worktree given, tree not checked")

    print()
    if fails:
        print(f"PRE-FLIGHT FAILED: {len(fails)} problem(s). Do not start a board.")
        raise SystemExit(1)
    print("PRE-FLIGHT PASSED: the flow, the fixes and the tree are the ones you meant to test.")


if __name__ == "__main__":
    main()
