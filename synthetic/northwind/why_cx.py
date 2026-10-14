"""Why each run of a lane campaign did not pass: python3 why_cx.py CAMPAIGN_DIR [SCENARIO ...]

Prints, for every row that is not PASS, the failed checks with their detail, the rubric criteria the judge marked
not met with its reason, the invalid reasons, and the counts that show how the call went. No network, no spend.
"""
import glob
import json
import os
import sys

camp, only = sys.argv[1], set(sys.argv[2:])
for path in sorted(glob.glob(os.path.join(camp, "*", "row.json"))):
    row = json.load(open(path))
    if row["verdict"] == "PASS" or only and row["scenario"] not in only:
        continue
    out = os.path.dirname(path)
    judge = json.load(open(os.path.join(out, "judge.json"))) if os.path.exists(os.path.join(out, "judge.json")) else {}
    proof = row.get("proof") or {}
    print(f"\n=== {row['scenario']} r{row['run']} {row['verdict']} score={row.get('score')} cost=${row.get('cost_usd')} "
          f"jev={proof.get('jev_asks')}/{proof.get('jev_wire_200')} faults={len(proof.get('jev_faults') or [])} "
          f"gemma={proof.get('gemma_requests')} errors={proof.get('jev_errors')}")
    for reason in row.get("invalid_reasons") or []:
        print(f"  invalid: {reason[:300]}")
    for check in judge.get("checks") or []:
        if not check["ok"]:
            print(f"  check: {check['check']}: {str(check['detail'])[:260]}")
    for crit in judge.get("criteria") or []:
        if not crit.get("met"):
            print(f"  rubric {crit.get('n')} ({crit.get('accuracy')}): {str(crit.get('reason'))[:420]}")
