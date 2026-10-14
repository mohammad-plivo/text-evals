#!/usr/bin/env python3
"""Did the collect node collect? — config-7 TeleCRM flow."""
import json, sys, re
REQ = ("sales_team_size", "industry", "crm_need_or_current_process")
SUBMIT = "submit_crm_outcome_with_status_mapping"
IDENT = re.compile(r"am i speaking with|is this |speaking with\b", re.I)

def main() -> int:
    paths = [a for a in sys.argv[1:] if a.endswith(".json")]
    labels = [a for a in sys.argv[1:] if not a.endswith(".json")]
    label = labels[0] if labels else "runs"
    runs = [r for p in paths for r in json.load(open(p))]
    fields, upd, early, unknown, reask = [], [], 0, 0, 0
    for r in runs:
        got = {k for k, v in (r.get("variables") or {}).items() if v not in (None, "")}
        fields.append(sum(1 for f in REQ if f in got))
        n_upd = 0
        sub_turn = None
        in_collect = False
        for i, t in enumerate(r.get("turns", []), 1):
            node = str(t.get("node") or "")
            if "Qualifier" in node:
                if not in_collect and IDENT.search(t.get("agent") or ""):
                    reask += 1
                in_collect = True
            for tc in (t.get("tool_calls") or []):
                nm = tc.get("name") or ""
                if nm.startswith("update_"): n_upd += 1
                if nm == SUBMIT:
                    if sub_turn is None: sub_turn = i
                    if '"unknown"' in (tc.get("arguments") or ""): unknown += 1
        upd.append(n_upd)
        if sub_turn is not None and sub_turn < len(r.get("turns", [])): early += 1
    n = len(runs) or 1
    print(f"\n=== {label} ({len(runs)} runs) ===")
    print(f"  REQUIRED fields captured : {fields}  (mean {sum(fields)/n:.1f} of 3)   <- counts")
    print(f"  all three                : {sum(1 for x in fields if x==3)}/{len(runs)}")
    print(f"  update_* calls per run   : {upd}")
    print(f"  CRM filed early          : {early}/{len(runs)}")
    print(f"  submissions with 'unknown': {unknown}")
    print(f"  re-asked identity        : {reask}/{len(runs)}")
    return 0

raise SystemExit(main())
