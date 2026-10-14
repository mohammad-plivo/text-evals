"""How the address step went in each run of an example-flow campaign: python3 address_cx.py runs/NAME

For every run: did Gemma add an inferred country to the address, did Jev refuse the candidate, was the address saved
as the scenario expects, was the booking summary refused as not matching the saved values, and the verdict.
"""
import collections
import glob
import json
import os
import sys

camp = sys.argv[1]
table, runs = collections.Counter(), []
for path in sorted(glob.glob(os.path.join(camp, "*", "row.json"))):
    row = json.load(open(path))
    out = os.path.dirname(path)
    if not os.path.exists(os.path.join(out, "trace.json")):
        continue
    logs = [e["msg"] for e in json.load(open(os.path.join(out, "trace.json")))["events"] if e["kind"] == "log"]
    replies = [m for m in logs if m.startswith('jev.extract_reply field="service_address"')]
    judge = json.load(open(os.path.join(out, "judge.json"))) if os.path.exists(os.path.join(out, "judge.json")) else {}
    saved = next((c["ok"] for c in judge.get("checks") or [] if c["check"] == "saved service_address"), None)
    facts = {"reached": bool(replies), "country": any("country_inferred" in m for m in replies),
             "refused": any("outcome=grounding_unsupported" in m for m in replies), "saved": saved,
             "summary_refused": sum("stage=value_unmatched purpose=statement:booking_summary" in m for m in logs)}
    runs.append((row["scenario"], row["run"], row["verdict"], facts))
    table[(row["verdict"], "country added" if facts["country"] else "no country" if facts["reached"] else "address not reached",
           "Jev refused it" if facts["refused"] else "not refused", f"saved right: {saved}",
           "summary refused" if facts["summary_refused"] else "summary ok or not reached")] += 1
for key, n in sorted(table.items(), key=lambda kv: -kv[1]):
    print(n, " | ".join(key))
if "-v" in sys.argv:
    for scenario, run, verdict, facts in runs:
        print(scenario, run, verdict, facts)
