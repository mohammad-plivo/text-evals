"""Negative controls for the Sigma board gates: the board must refuse these, offline, no model call.

Each case is one false pass the 2026-09-21 audit found or forbade: the no_matching_handoff exit that
every one of the 19 reported passes stopped on, a double close, a close before the last turn, an end
node the scenario never declared, accuracy 1 read as 100, a NOT MET criterion carrying accuracy 100,
an attempt that never reported, and a declared callback variable the run recorded with another value.
One clean run is the positive control: if it does not PASS, the gates prove nothing.

The board runs with --reuse-judged against stub workspaces in a temp tree, so no model is called and
the campaign worktree is never read. Run: python3 test_gate_negative.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCREEN = "c2e8bf31-06ec-42db-8a60-a72874b1ceb5"
AGENT = "f66906be-0fc9-43e5-bcf7-20117357082c"
# the two ends the stub graph offers: the one every case declares, and the one no case declares
DONE, WARM = "175e6df0-f453-4cbf-88cd-ca4cc6f8c7dd", "2df92228-2f50-4e07-8505-d872260ac899"
FLOW = {
    "name": "stub", "flowId": "stub",
    "nodes": [{"id": SCREEN, "type": "contact_screening", "data": {"meta": {"name": "Screening Contact"}}},
              {"id": AGENT, "type": "ai_agent_v29", "data": {"meta": {"name": "Recruitment Screener"}}},
              {"id": DONE, "type": "end_conversation", "data": {"meta": {"name": "Interview Completed"}}},
              {"id": WARM, "type": "end_conversation", "data": {"meta": {"name": "Warm Farewell"}}}],
    "edges": [{"source": SCREEN, "sourceHandle": "reached", "target": AGENT},
              {"source": AGENT, "sourceHandle": "Interview Completed", "target": DONE},
              {"source": AGENT, "sourceHandle": "Callback Scheduled", "target": WARM}],
}
RUBRIC = "You are judging a stub call.\n1. The agent completes the screening.\n"
WANT = {"notice_period_negotiable": "yes/negotiable"}
MET = [{"id": 1, "status": "MET", "accuracy": 100, "evidence": "stub: the agent completed the screening"}]


def turn(**kw):
    """One transcript turn in the shape the simulator writes."""
    base = {"user": "hi", "agent": "ok", "node": "Recruitment Screener", "intent": "", "transitions": []}
    base.update(kw)
    return base


def hunter(slug):
    """A workspace rubric carrying its own declared exit and callback variables, so no scenario lookup."""
    return {"name": slug, "entry_node": AGENT, "evaluationPrompt": RUBRIC, "evaluationThreshold": 0.8,
            "timezone": "Asia/Kolkata", "repairs": [],
            "_expected_variables": {"_exits": ["screening:reached", "agent:Interview Completed"]},
            "payload": {"expectedCallbackVariables": dict(WANT)}}


CLEAN = ("clean_control", [turn(intent="Interview Completed", ended=True)], dict(WANT), MET,
         ("PASS", "OK", "OK", "PASS"), "Interview Completed -> Interview Completed")
BAD = [
    ("no_matching_handoff", [turn(intent="Interview Completed", ended=True, stop_reason="no_matching_handoff")],
     dict(WANT), MET, ("PASS", "FAIL", "OK", "FAIL"), "no_matching_handoff at turn 1"),
    ("closes_twice", [turn(intent="Interview Completed", ended=True), turn(intent="Interview Completed", ended=True)],
     dict(WANT), MET, ("PASS", "FAIL", "OK", "FAIL"), "closed 2 times"),
    ("closes_before_last_turn", [turn(intent="Interview Completed", ended=True), turn()],
     dict(WANT), MET, ("PASS", "FAIL", "OK", "FAIL"), "last close at turn 1 of 2"),
    ("undeclared_end_node", [turn(intent="Callback Scheduled", ended=True)],
     dict(WANT), MET, ("PASS", "FAIL", "OK", "FAIL"), "expected Interview Completed"),
    ("accuracy_one_percent", [turn(intent="Interview Completed", ended=True)], dict(WANT),
     [{"id": 1, "status": "MET", "accuracy": 1, "evidence": "stub: one percent, not one hundred"}],
     ("FAIL", "OK", "OK", "FAIL"), "one percent, not one hundred"),
    ("not_met_at_accuracy_100", [turn(intent="Interview Completed", ended=True)], dict(WANT),
     [{"id": 1, "status": "NOT MET", "accuracy": 100, "evidence": "stub: never completed the screening"}],
     ("FAIL", "OK", "OK", "FAIL"), "never completed the screening"),
    ("variable_recorded_wrong", [turn(intent="Interview Completed", ended=True)],
     {"notice_period_negotiable": "no/not negotiable"}, MET,
     ("PASS", "OK", "FAIL", "FAIL"), "want 'yes/negotiable'"),
]
NO_REPORT = "attempt_with_no_report"


def board(name, cases, unreported=()):
    """Stub a launch and its workspaces in a temp tree, run the real board offline, return its rows."""
    tmp = tempfile.mkdtemp(prefix="sigma-gate-")
    root = os.path.join(tmp, "eval_tests", "sigma_v29_hunter")
    # board.py writes beside itself, so shadow it with symlinks and keep every output in the temp tree
    hs = os.path.join(tmp, "hunter-sim")
    os.makedirs(os.path.join(hs, "boards"))
    os.symlink(os.path.join(HERE, "board.py"), os.path.join(hs, "board.py"))
    os.symlink(os.path.join(HERE, "audited"), os.path.join(hs, "audited"))
    reports, judged = {}, []
    for slug, turns, variables, criteria, _, _ in cases:
        os.makedirs(os.path.join(root, slug, "reports"))
        json.dump(FLOW, open(os.path.join(root, slug, "flow.json"), "w"))
        json.dump(hunter(slug), open(os.path.join(root, slug, "hunter.json"), "w"))
        rel = f"{slug}/reports/20260921-000000.json"
        json.dump([{"scenario": slug, "run": 1, "turns": turns, "variables": variables, "failures": []}],
                  open(os.path.join(root, rel), "w"))
        reports[slug] = [rel]
        judged.append({"workspace": slug, "report": rel,
                       "runs": [{"scenario": slug, "run": 1, "ended": True, "criteria": criteria, "ungraded_ids": []}]})
    json.dump({"manifest_sha256": "stub", "reports": judged},
              open(os.path.join(hs, "boards", f"{name}.judged.json"), "w"))
    launch = {"launch": "20260921-000000", "worktree_head": "0" * 40, "worktree_dirty": False, "repeat": "1",
              "status": "COMPLETE", "stop_reason": "", "reports": reports,
              "selected": sorted([c[0] for c in cases] + list(unreported)),
              "exit": {**{c[0]: 0 for c in cases}, **{s: 143 for s in unreported}}}
    launch_path = os.path.join(tmp, "launch.json")
    json.dump(launch, open(launch_path, "w"))
    proc = subprocess.run([sys.executable, os.path.join(hs, "board.py"), tmp, launch_path, name, "--reuse-judged"],
                          capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    rows = {}
    for line in proc.stdout.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) == 12 and cells[1].isdigit():
            rows[cells[2]] = {"rubric": cells[6], "route": cells[7], "variables": cells[8],
                              "verdict": cells[9], "why": cells[10]}
    return proc, rows, tmp


def check(rows, case):
    """The whole row, not just the verdict: a gate that fires in the wrong column proved nothing."""
    slug, _, _, _, (rubric, route, variables, verdict), why = case
    got = rows.get(slug)
    assert got, f"{slug}: no row on the board"
    assert (got["rubric"], got["route"], got["variables"], got["verdict"]) == (rubric, route, variables, verdict), \
        f"{slug}: {got}"
    assert why in got["why"], f"{slug}: why {got['why']!r} does not carry {why!r}"


# positive control first: if a clean run does not pass and exit 0, every FAIL below is meaningless
proc, rows, tmp = board("gate-positive", [CLEAN])
assert proc.returncode == 0, proc.stdout + proc.stderr
assert "BOARD CLEAN" in proc.stdout, proc.stdout
check(rows, CLEAN)
shutil.rmtree(tmp)

# one board carrying the control and every false pass: each must be caught in its own column
proc, rows, tmp = board("gate-negative", [CLEAN] + BAD, unreported=[NO_REPORT])
assert proc.returncode == 1, f"the board exited {proc.returncode} with {len(BAD) + 1} defects present"
assert "BOARD NOT CLEAN" in proc.stdout, proc.stdout
check(rows, CLEAN)  # the control still passes beside the failures, so the board is not failing everything
for case in BAD:
    check(rows, case)
missing = rows.get(NO_REPORT)
assert missing and missing["verdict"] == "INCOMPLETE", f"{NO_REPORT}: {missing}"
assert "no report, child exit 143" in missing["why"], missing
shutil.rmtree(tmp)

# the judge's one contract is an integer 0 through 100, so a float 1.0 is an error, never 100 percent
slug, turns, variables, _, expect, why = CLEAN
proc, rows, tmp = board("gate-accuracy-contract", [(slug, turns, variables,
                                                    [{"id": 1, "status": "MET", "accuracy": 1.0, "evidence": "stub"}],
                                                    expect, why)])
assert not rows, f"a float accuracy was graded instead of refused: {rows}"
assert "is not an integer 0-100" in proc.stderr, proc.stderr or proc.stdout
shutil.rmtree(tmp)

print(f"board gate negative controls: {len(BAD) + 2}/{len(BAD) + 2} behave as required "
      f"({len(BAD) + 1} must not pass, 1 control passes), board exit 1 with defects and 0 without")
