#!/usr/bin/env python3
"""Tally the gemma-31b eval run store. Usage:
    .venv/bin/python ../aggregate.py [--date 20260721] [--verbose]
Filter is regex-based (the substring bug that hid shard_0_of_10 behind shard_0_of_1 is fixed):
sweep runs = shard_i_of_N with N > 1; smoke/one-off runs (N == 1) are excluded.
"""
import argparse, json, re, sys
from pathlib import Path

SUITES = ["address", "boolean", "choice", "confirm_known_values", "contact_screening",
          "credit_card", "currency", "datetime", "dob", "dtmf", "email", "name",
          "number", "phone", "text"]
RX = re.compile(r"shard_(\d+)_of_(\d+)_(\d{8})_")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260721")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--store", default="eval_conversations/transcripts/tasks")
    args = ap.parse_args()

    grand_runs = grand_pass = grand_corrupt = grand_infra = 0
    all_fails: list[tuple[str, str]] = []
    print(f"{'suite':24s} {'runs':>5s} {'pass':>5s} {'fail':>4s} {'infra':>5s} {'corrupt':>7s}")
    for suite in SUITES:
        p = Path(args.store) / f"{suite}.jsonl"
        if not p.exists():
            print(f"{suite:24s} {'—':>5s}  (no store file)")
            continue
        corrupt = 0
        latest: dict[str, dict] = {}   # case_id -> latest matching run (file order = append order)
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                corrupt += 1
                continue
            m = RX.search(r.get("run_id", ""))
            if not m or m.group(3) != args.date:
                continue
            # latest record per case wins, whatever its shard layout — single-case
            # redo runs (shard_0_of_1) legitimately supersede earlier sweep records.
            latest[r["case_id"]] = r
        runs = list(latest.values())
        fails = [r for r in runs if not r["passed"]]
        infra = [r for r in runs if r.get("infra_error")]
        grand_runs += len(runs); grand_pass += len(runs) - len(fails)
        grand_corrupt += corrupt; grand_infra += len(infra)
        all_fails += [(suite, r["case_id"]) for r in fails]
        print(f"{suite:24s} {len(runs):5d} {len(runs)-len(fails):5d} {len(fails):4d} {len(infra):5d} {corrupt:7d}")
    print(f"{'TOTAL':24s} {grand_runs:5d} {grand_pass:5d} {len(all_fails):4d} {grand_infra:5d} {grand_corrupt:7d}")
    if all_fails:
        print("\nfailing cases:")
        for suite, cid in all_fails:
            print(f"  {suite} :: {cid}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
