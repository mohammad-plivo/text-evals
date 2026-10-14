#!/usr/bin/env python3
"""Compare the two most recent report sets for every workspace, structurally, with no judge.

Written for the 2026-09-21 prompt shrink: the question is whether cutting the node instructions from
36,354 to 15,985 characters changed what the agent does, and the judge is neither needed nor
trustworthy for that. Routes, turn counts, collected variables and runner failures answer it, and
they cost nothing.

    python3 Sigma/hunter-sim/compare_runs.py <worktree> <launch stamp, e.g. 20260921-054>

A workspace whose newest report predates the stamp did not run in this board, and comparing it would
silently compare two older runs to each other.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

WT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
ROOT = WT / "eval_tests" / "sigma_v29_hunter"


def shape(path: str) -> list[dict]:
    """One row per attempt: where it ended, how long it took, what it captured, what broke."""
    return [
        {
            "route": (r.get("nodes_visited") or ["?"])[-1],
            "turns": len(r.get("turns") or []),
            "vars": tuple(sorted((r.get("variables") or {}))),
            "fails": len(r.get("failures") or []),
        }
        for r in json.load(open(path))
    ]


def verdict(new: list[dict], old: list[dict]) -> tuple[str, str]:
    if {r["route"] for r in new} != {r["route"] for r in old}:
        return "ROUTE", f"{sorted({r['route'] for r in old})} -> {sorted({r['route'] for r in new})}"
    nf, of = sum(r["fails"] for r in new), sum(r["fails"] for r in old)
    nt, ot = sum(r["turns"] for r in new) / len(new), sum(r["turns"] for r in old) / len(old)
    if nf > of:
        return "FAILURES", f"{of} -> {nf}"
    # A walk that got longer because it stopped dying is not a regression, so failures are read first.
    if nf < of:
        return "BETTER", f"{of} -> {nf} failures, {ot:.1f} -> {nt:.1f} turns"
    lost = set.union(*[set(r["vars"]) for r in old]) - set.union(*[set(r["vars"]) for r in new])
    if lost:
        return "VARS", "lost " + ", ".join(sorted(lost))
    if nt > ot + 2:
        return "LONGER", f"{ot:.1f} -> {nt:.1f} turns"
    return "SAME", f"{ot:.1f} -> {nt:.1f} turns, {of} -> {nf} failures"


SINCE = sys.argv[2] if len(sys.argv) > 2 else ""

rows, missing, stale = [], [], []
for ws in sorted(p for p in ROOT.iterdir() if p.is_dir()):
    reports = sorted(glob.glob(str(ws / "reports" / "*.json")))
    if len(reports) < 2:
        missing.append(ws.name)
        continue
    if SINCE and Path(reports[-1]).stem < SINCE:
        stale.append(ws.name)
        continue
    rows.append((ws.name, *verdict(shape(reports[-1]), shape(reports[-2]))))

order = {"ROUTE": 0, "FAILURES": 1, "VARS": 2, "LONGER": 3, "SAME": 4, "BETTER": 5}
for name, tag, detail in sorted(rows, key=lambda r: (order[r[1]], r[0])):
    print(f"{tag:9s} {name[:58]:58s} {detail}")
counts = {t: sum(1 for r in rows if r[1] == t) for t in order}
print("\n" + "  ".join(f"{t}={counts[t]}" for t in order) + f"  (compared {len(rows)})")
if stale:
    print(f"DID NOT RUN in this board, {len(stale)}: {', '.join(sorted(stale))}")
if missing:
    print(f"no previous run to compare, {len(missing)}: {', '.join(sorted(missing)[:6])}")
