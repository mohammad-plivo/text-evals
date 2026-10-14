"""The text lane (text-evals/text-lane/lane.py) pointed at the small System One version.

  <lane tree>/.venv/bin/python s1_lane.py <lane.py arguments>

Scenarios, flows, preflight, the private redis, the shared ledger, the judge and the board are the lane's own. Two
things change: the tree under test (LANE_TREE, default v2.9.1-jev/s1-thin-lane) and the one-run script, because the
lane's run_one.py hooks into the engine's classes, which this tree does not have (run_one_s1.py).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.environ.setdefault("LANE_TREE", os.path.join(ROOT, "s1-thin-lane"))
sys.path.insert(0, os.path.join(ROOT, "text-evals", "text-lane"))
import lane  # noqa: E402


def run_argv(slug: str, out: str, env_path: str, spec_path: str, budget: float) -> list[str]:
    return [os.path.join(lane.TREE, ".venv", "bin", "python"), os.path.join(HERE, "run_one_s1.py"), "--tree", lane.TREE,
            "--ws", os.path.join(out, "ws"), "--scenario", slug, "--env-file", env_path, "--out", out,
            "--budget", str(budget), "--spec", spec_path]


lane.run_argv = run_argv

# The lane's FHCSD flow was rewritten for the engine: its tool code takes only values the engine's code fills in,
# and its Task tells the model the runtime does the checking. --main-shaped runs the same pack on the FHCSD flow as
# it was built for main (make_fhcsd_flow.py), and hands the lane's flow to the adapter for the judge's result shapes.
# --switch-off runs the same flow with no switch, which is main alone: the baseline a failing scenario is read against.
# --screening-as-main puts the switch on the V2.9 node only (make_fhcsd_flow.py --v29-only).
KINDS = {"--main-shaped": os.path.join(HERE, "flows", "fhcsd-main-shaped", "flow.json"),
         "--screening-as-main": os.path.join(HERE, "flows", "fhcsd-main-shaped-v29only", "flow.json"),
         "--switch-off": os.path.join(HERE, "flows", "fhcsd-main-shaped-off", "flow.json")}  # the same flow with no switch
kind = next((flag for flag in KINDS if flag in sys.argv), None)
if kind:
    sys.argv.remove(kind)
    os.environ["S1_JUDGE_FLOW"] = lane.FLOW
    lane.FLOW = KINDS[kind]
    ABSENT = {"No Missed Appointment", "Callback Requested", "Do Not Call"}  # endings added to the engine's flow only
    checked = lane.intent_failures
    # the screening exit the owner set on 3 Oct (make_fhcsd_flow.py) is reviewed with it
    lane.intent_failures = lambda flow, specs, reviewed=lane.REVIEWED_INTENTS: checked(
        flow, [{**spec, "expect_exit": [e for e in lane.judge_lane.exits(spec) if e not in ABSENT]} for spec in specs],
        None if reviewed is None else {*reviewed, "Screening Exit"})
    # these runs read the flow file above, never the local stack's cached copy of the lane's flow (it expires after ~30 h)
    checked_stack = lane.fhcsd_failures
    lane.fhcsd_failures = lambda res: [why for why in checked_stack(res) if not why.startswith("local flow changed since the dump")]

# a pack converted on another day carries that day's clinic record, so the judge marks the true date as invented (3 Oct)
checked_day = lane.fhcsd_failures
lane.fhcsd_failures = lambda res: checked_day(res) + [
    f"pack converted for clinic day {day}, not {lane.T}: run lane.py convert" for day in sorted(
        {json.load(open(path))["clinic_day"] for path in glob.glob(os.path.join(lane.PACK, "*", "spec.json"))} - {lane.T.isoformat()})]

# --screening-only: these callers never reach the clinic, so its day and the clock cannot disagree for them
if "--screening-only" in sys.argv:
    sys.argv.remove("--screening-only")
    checked_fhcsd = lane.fhcsd_failures
    lane.fhcsd_failures = lambda res: [why for why in checked_fhcsd(res)
                                       if "IST window" not in why and "mock canary" not in why and "pack converted" not in why]

lane.main()
