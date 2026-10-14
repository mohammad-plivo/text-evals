"""Summarise an example-flow campaign by collector type: python3 board_ex.py runs/NAME > runs/NAME/summary.md"""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
camp = sys.argv[1]
flow = json.load(open(os.path.join(HERE, "ws", "flow.json")))
agent = next(n for n in flow["nodes"] if n["type"] == "ai_agent_v29")["data"]["config"]
FIELDS = [(v["variable_name"], v["collection"]["type"]) for v in agent["extract_variables"]]


def titles(slug):
    rub = json.load(open(os.path.join(HERE, "pack", slug, "spec.json")))["rubric"]
    return {int(m.group(1)): m.group(2) for m in re.finditer(r"^(\d+)\. ([A-Z][A-Z0-9 ,'\-/]+):", rub.split("Evaluate these criteria:")[-1], re.M)}


rows = []
for rj in sorted(glob.glob(os.path.join(camp, "*", "row.json"))):
    row = json.load(open(rj))
    jp = os.path.join(row["dir"], "judge.json")
    j = json.load(open(jp)) if os.path.exists(jp) else {}
    spec = json.load(open(os.path.join(HERE, "pack", row["scenario"], "spec.json")))
    checks = {c["check"]: c for c in j.get("checks") or []}
    saved = {}
    for name, _ in FIELDS:
        c = checks.get(f"saved {name}")
        if c:
            got = re.match(r"got (.*) want", c["detail"]).group(1)
            saved[name] = {"ok": c["ok"], "got": got, "empty": got in ("None", "''")}
    last = max((i for i, (n, _) in enumerate(FIELDS) if n in saved and not saved[n]["empty"]), default=-1)
    trace = json.load(open(os.path.join(row["dir"], "trace.json"))) if os.path.exists(os.path.join(row["dir"], "trace.json")) else {"events": []}
    outcomes = defaultdict(list)  # field -> extract outcomes, in order
    for e in trace["events"]:
        m = e["kind"] == "log" and re.match(r'jev\.extract field="([^"]+)" outcome=(\S+)', e["msg"])
        if m:
            outcomes[m.group(1)].append(m.group(2))
    t = titles(row["scenario"])
    row.update(group=spec.get("group"), type=spec.get("type") or spec.get("facet"), facet=spec.get("facet"), saved=saved,
               reached={n for i, (n, _) in enumerate(FIELDS) if i <= last} | set(outcomes), outcomes=dict(outcomes),
               stopped_at=next((n for n, _ in FIELDS if not saved.get(n, {}).get("ok", True) and saved[n]["empty"]), "-"),
               failed_checks={c["check"]: c["detail"] for c in j.get("checks") or [] if not c["ok"]},
               not_met_titles={t.get(c["n"], str(c["n"])): c["reason"] for c in j.get("criteria") or [] if not c.get("met")},
               exit_check=checks.get("expected exit fired", {}).get("detail"))
    rows.append(row)

out = [f"Campaign {os.path.basename(camp)}: {len(rows)} runs, " + ", ".join(
    f"{v} {sum(r['verdict'] == v for r in rows)}" for v in ("PASS", "FAIL", "INVALID", "NOT RUN")) +
    f". Cost ${sum(r.get('cost_usd') or 0 for r in rows):.4f}.", ""]
out += ["| Scenario | Group | Verdict | Rubric | Stopped at | Exit | Failed checks | Not met | Cost | Jev asks/200/faults | Gemma req, served_by | Azure label |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in sorted(rows, key=lambda r: (r["group"] != "type", r["type"] or "", r["scenario"])):
    p = r.get("proof") or {}
    out.append(f"| {r['scenario']} | {r['type'] or r['group']} | {r['verdict']} | {r.get('rubric_verdict')} | {r['stopped_at']} | {r['exit_check']} | "
               f"{'; '.join(r['failed_checks']) or '-'} | {'; '.join(r['not_met_titles']) or '-'} | ${(r.get('cost_usd') or 0):.3f} | "
               f"{p.get('jev_asks')}/{p.get('jev_wire_200')}/{len(p.get('jev_faults') or [])} | "
               f"{p.get('gemma_requests')}, {'+'.join(p.get('gemma_served_by') or []) or '-'} | {p.get('azure_label')} |")
out += ["", "Per field across every run (reached = saved, a later field saved, or an extraction was attempted):", "",
        "| Field | Type | Reached | Saved right | Saved wrong | Empty although reached | Extract outcomes | Wrong values seen |", "|---|---|---|---|---|---|---|---|"]
for name, typ in FIELDS:
    reached = [r for r in rows if name in r["reached"]]
    right = [r for r in reached if r["saved"].get(name, {}).get("ok")]
    wrong = [r for r in reached if name in r["saved"] and not r["saved"][name]["ok"] and not r["saved"][name]["empty"]]
    empty = [r for r in reached if name in r["saved"] and r["saved"][name]["empty"]]
    out.append(f"| {name} | {typ} | {len(reached)} | {len(right)} | {len(wrong)} | {len(empty)} | "
               f"{dict(Counter(o for r in rows for o in r['outcomes'].get(name, [])))} | "
               f"{'; '.join(sorted({r['scenario'] + ': ' + r['saved'][name]['got'][:40] for r in wrong}))[:400] or '-'} |")
stall = defaultdict(list)
for r in rows:
    if r["verdict"] != "PASS" and r["stopped_at"] != "-":
        stall[r["stopped_at"]].append(r["scenario"])
out += ["", "First expected field left empty, per failing run: " + "; ".join(f"{k}: {len(v)} ({', '.join(v)})" for k, v in stall.items())]
json.dump(rows, open(os.path.join(camp, "summary.json"), "w"), indent=1, default=list)
print("\n".join(out))
