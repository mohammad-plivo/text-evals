"""Classify a text-lane campaign's rows by the structural signatures the Sigma boards fail on.

Usage:  python3 Sigma/text-lane/classify_campaign.py <results.jsonl> [<ledger.json>]

Signatures are read from the trace, never from judge prose:
  LEAK      an agent utterance carries a tool name, an Input name, an <instructions> block, or the
            spoken renderings a voice transcript produces (underscore, equal sign)
  PUSHBACK  the collector's templated first-refusal line ("we only ask because")
  REPEAT    the same question substance put to the caller more than once (normalised prefix)
  DECLINE   every decline_* call with its reason, and whether the router pressed after it
  UNAUTH    an update_* tool call for a field the case authored no offer for
  DATEMIS   an utterance naming a weekday and a calendar date that disagree
  AZURE     any request served by an Azure host (a Gemma board that fell through)
"""
from __future__ import annotations

import collections
import datetime
import json
import re
import sys

TOOL = re.compile(r"\b(collect|update|decline|confirm)_[a-z_]+\b|\bsubmit_details\b|\bhandoff_[a-z_]+\b")
SPOKEN = re.compile(r"\bunderscore\b|\bequal sign\b|\bcurly brace", re.I)
BLOCK = re.compile(r"<instructions>|^\s*instructions\s*[:.]", re.I | re.M)
PUSHBACK = re.compile(r"only ask because", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                          "august", "september", "october", "november", "december"])}
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
       "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
       "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
       "twentieth": 20, "thirtieth": 30}


def _spoken_day(text: str) -> int | None:
    t = text.lower().replace("-", " ")
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(twenty|thirty)?\s*(" + "|".join(ORD) + r")\b", t)
    if not m:
        return None
    base = {"twenty": 20, "thirty": 30}.get(m.group(1) or "", 0)
    return base + ORD[m.group(2)] if base else ORD[m.group(2)]


def date_mismatch(text: str, year: int) -> str:
    """The weekday and calendar date an utterance names, when they disagree; '' otherwise."""
    low = text.lower()
    wd = next((w for w in WEEKDAYS if w in low), None)
    mo = next((m for m in MONTHS if m in low), None)
    if not wd or not mo:
        return ""
    after = low[low.find(mo):]
    day = _spoken_day(after)
    if not day:
        return ""
    try:
        actual = datetime.date(year, MONTHS[mo], day).strftime("%A").lower()
    except ValueError:
        return f"invalid date {mo} {day}"
    return "" if actual == wd else f"said {wd} but {mo} {day} {year} is a {actual}"


def question_key(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    t = re.sub(r"\b(please|could you|can you|would you|kindly|share|tell me|answer|in a format like.*)\b", " ", t)
    return " ".join(t.split())[:48]


def classify(row: dict) -> dict:
    trace = row.get("trace") or row.get("partial_trace") or {}
    year = int(str(row.get("frozen_time") or "2026")[:4])
    fields = set((row.get("configurations") or {}).keys())
    out = collections.defaultdict(list)
    speeches = [(m.get("speech") or "").strip() for m in trace.get("model_calls", [])]
    asked = collections.Counter()
    for sp in speeches:
        if not sp:
            continue
        if TOOL.search(sp) or SPOKEN.search(sp) or BLOCK.search(sp) or any(f"{f}" in sp for f in fields if "_" in f):
            out["LEAK"].append(sp[:140])
        if PUSHBACK.search(sp):
            out["PUSHBACK"].append(sp[:140])
        mis = date_mismatch(sp, year)
        if mis:
            out["DATEMIS"].append(f"{mis} :: {sp[:100]}")
        if "?" in sp:
            asked[question_key(sp.split("?")[0][-120:])] += 1
    for k, n in asked.items():
        if n > 1:
            out["REPEAT"].append(f"x{n} {k}")
    steps = row.get("caller_steps")  # absent on live.py rows: UNAUTH is then unknowable, never reported
    offered = set()
    for step in steps or []:
        offered.update((step.get("offers") or {}).keys())
    for e in trace.get("emitted", []):
        name = e.get("name", "")
        args = e.get("effective_arguments") or {}
        if name.startswith("decline_"):
            out["DECLINE"].append(f"{name} reason={args.get('reason')}")
        if steps is not None and name.startswith("update_") and (e.get("collector") or {}).get("name") not in offered:
            out["UNAUTH"].append(f"{name} for {(e.get('collector') or {}).get('name')} args={json.dumps(args)[:80]}")
    for host, n in (row.get("served_by") or {}).items():
        if "azure" in host:
            out["AZURE"].append(f"{host} x{n}")
    return dict(out)


def main(path: str, ledger: str | None) -> None:
    rows = [json.loads(line) for line in open(path)]
    by_case = collections.defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)
    for case, rs in by_case.items():
        passed = sum(1 for r in rs if r.get("structural_status") == "passed")
        print(f"\n=== {case}  {passed}/{len(rs)} passed")
        for r in rs:
            sig = classify(r)
            err = (r.get("error") or {}).get("oracle_detail", "")[:110]
            tags = ", ".join(f"{k}x{len(v)}" for k, v in sig.items()) or "-"
            print(f"  rep{r['repetition']} {r.get('structural_status'):7s} [{tags}] {err}")
            for k, v in sig.items():
                for item in v[:3]:
                    print(f"      {k}: {item}")
    if ledger:
        d = json.load(open(ledger))
        print(f"\nspend standard ${d.get('standard_estimated_usd')} | requests {d.get('request_count')} | models {d.get('observed_model_ids')}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
