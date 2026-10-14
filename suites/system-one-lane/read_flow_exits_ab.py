"""What each targeted caller of pack-flow-exits got after its scripted line, per arm. Runs nothing, pays nothing.

  python3 read_flow_exits_ab.py <tag> [arm ...] [--lines]     # reads runs/s1-fx-<arm>-<tag>-t; arms default to old and new

Per run: the first step Jev picked on the scripted line, the actions that ran after it, values asked for again, and the exit.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = {"L-x-yes-and-never-call": "take me off your list", "L-x-date-and-chest-pain": "pain in my chest",
        "L-x-refuses-then-never-call": "take me off your list", "L-x-forget-it-a-person": "forget the appointment",
        "L-x-screening-yes-but-a-person": "rather speak to a real person"}
TAG, LINES = sys.argv[1], "--lines" in sys.argv
ARMS = [arg for arg in sys.argv[2:] if not arg.startswith("--")] or ["old", "new"]


def read(run: str) -> dict:
    events, slug = json.load(open(os.path.join(run, "trace.json")))["events"], os.path.basename(run.rstrip("/")).rsplit("-r", 1)[0]
    said = next((at for at, e in enumerate(events) if e["kind"] == "line" and (e.get("role") or e.get("who")) == "caller"
                 and MARK[slug].lower() in str(e.get("text") or e.get("line") or "").lower()), None)
    row = json.load(open(os.path.join(run, "row.json"))) if os.path.exists(os.path.join(run, "row.json")) else {}
    out = {"slug": slug, "verdict": row.get("verdict"), "failed": row.get("checks_failed"), "said": said is not None}
    if said is None:
        return out
    # the Jev request that read the line is logged just before the line it answers
    asks = [e for e in events[max(0, said - 2):] if e["kind"] == "jev"]
    first = asks[0]["probs"].get("step", {}) if asks else {}
    after = events[said + 1:]
    out.update(
        first_pick=sorted(((name, round(share, 2)) for name, share in first.items()), key=lambda pair: -pair[1])[:2],
        core=sorted(head for head in ("human_request", "closure_request", "urgency") if asks and head in asks[0]["probs"]),
        actions=[f"{e.get('action')}:{e.get('status')}" for e in after if e["kind"] == "tool"],
        collects=[e["name"] for e in after if e["kind"] == "step" and e["name"].startswith("collect_") and "not collected" not in str(e.get("result"))],
        exit=next((e["name"] for e in after if e["kind"] == "step" and (e["name"].startswith("handoff_") or e["name"] == "exit_collection")
                   and not e.get("error")), None),
        agent=[str(e.get("text") or e.get("line") or "")[:150] for e in after if e["kind"] == "line"
               and (e.get("role") or e.get("who")) == "agent" and str(e.get("text") or e.get("line") or "").strip()])
    return out


for arm in ARMS:
    runs = sorted(glob.glob(os.path.join(HERE, "runs", f"s1-fx-{arm}-{TAG}-t", "L-x-*/")))
    print(f"\n===== {arm}: {len(runs)} runs")
    for run in runs:
        r = read(run)
        name = os.path.basename(run.rstrip("/"))
        if not r["said"]:
            print(f"{name:40} the scripted line was never said | {r['verdict']} {r['failed']}")
            continue
        print(f"{name:40} {r['verdict']:7} first pick {r['first_pick']} core asked {r['core'] or 'none'} | actions after: {r['actions'] or '-'} | "
              f"collected again: {r['collects'] or '-'} | exit: {r['exit']}")
        if LINES:
            for line in r["agent"]:
                print(f"{'':42}agent: {line}")
