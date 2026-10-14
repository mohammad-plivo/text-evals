"""Re-stamp the clinic day in the FHCSD Hunter rubrics: every "Month D[, YYYY]" date moves by the business-day
offset between the rubrics' clinic day and the mock's (America/Los_Angeles today), weekday names are recomputed.
  refresh_live_dates.py --payloads DIR [--old 2026-09-17] [--new 2026-09-18] [--dry-run] [--write-local] [--put --cookie FILE]
--dry-run prints per-scenario counts and samples; --write-local rewrites the pulled JSON copies (for the text lane);
--put PUTs each changed scenario back to Hunter and verifies the round-trip (for the next Hunter board).
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
MON = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTHS = {m: i + 1 for i, m in enumerate(MON.split("|"))}
NAMES = {v: k for k, v in MONTHS.items()}
WD = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
DATE = re.compile(rf"\b({MON}) (\d{{1,2}})(, (\d{{4}}))?\b")
WEEKDAY_AFTER = re.compile(rf"\b((?:{MON}) \d{{1,2}}(?:, \d{{4}})?)( is a | a )({WD})\b")
BASE = "https://hunter.contactodev.com"


def bdays_between(a: date, b: date) -> int:
    """Signed count of weekdays strictly after a up to and including b (negative when b < a)."""
    if b < a:
        return -bdays_between(b, a)
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def add_bdays(d: date, k: int) -> date:
    step = 1 if k >= 0 else -1
    while k:
        d += timedelta(days=step)
        if d.weekday() < 5:
            k -= step
    return d


def shift_text(text: str, old: date, new: date) -> tuple[str, int]:
    k = bdays_between(old, new)
    moved = 0

    def sub(m):
        nonlocal moved
        y = int(m.group(4) or 2026)
        d = date(y, MONTHS[m.group(1)], int(m.group(2)))
        if d.year < 2000 or d.weekday() >= 5:
            return m.group(0)
        nd = add_bdays(d, bdays_between(old, d) + k - bdays_between(old, d)) if False else add_bdays(d, k)
        moved += 1
        return f"{NAMES[nd.month]} {nd.day}" + (f", {nd.year}" if m.group(3) else "")

    out = DATE.sub(sub, text)

    def wd(m):
        y = 2026
        mm = re.match(rf"({MON}) (\d{{1,2}})(?:, (\d{{4}}))?", m.group(1))
        d = date(int(mm.group(3) or y), MONTHS[mm.group(1)], int(mm.group(2)))
        return f"{m.group(1)}{m.group(2)}{d.strftime('%A')}"

    out = WEEKDAY_AFTER.sub(wd, out)
    return out, moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payloads", required=True); ap.add_argument("--old"); ap.add_argument("--new")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--write-local", action="store_true")
    ap.add_argument("--put", action="store_true"); ap.add_argument("--cookie")
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(a.payloads, "*.json")) if os.path.basename(f)[0].isdigit())
    docs = {f: json.load(open(f)) for f in files}
    if a.old:
        old = date.fromisoformat(a.old)
    else:
        stated = Counter()
        for d in docs.values():
            m = re.search(rf"missed: ({MON}) (\d{{1,2}}), (\d{{4}})", d["payload"]["evaluationPrompt"])
            if m:
                stated[date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))] += 1
        old = stated.most_common(1)[0][0]
        print(f"clinic day stated by the rubrics: {old} ({stated[old]} of {len(docs)} state one)")
    new = date.fromisoformat(a.new) if a.new else datetime.now(ZoneInfo("America/Los_Angeles")).date()
    k = bdays_between(old, new)
    print(f"old={old} ({old:%A}) new={new} ({new:%A}) shift={k:+d} business days")
    if k == 0:
        print("nothing to do"); return
    changed = 0
    for f, d in docs.items():
        ep = d["payload"]["evaluationPrompt"]; out, moved = shift_text(ep, old, new)
        if out == ep:
            continue
        changed += 1
        if a.dry_run:
            m = re.search(rf"missed: ((?:{MON}) \d{{1,2}}, \d{{4}}) at", out)
            print(f"  {d['id']} moved {moved:3} dates; missed -> {m.group(1) if m else '-'}; {os.path.basename(f)}")
            continue
        d["payload"]["evaluationPrompt"] = out
        if a.write_local:
            json.dump(d, open(f, "w"), indent=1, ensure_ascii=False)
        if a.put:
            cookie = open(a.cookie).read().strip()
            body = {k2: d[k2] for k2 in ("name", "description", "category", "tier", "payload") if k2 in d}
            req = urllib.request.Request(f"{BASE}/api/scenarios/{d['id']}", method="PUT", data=json.dumps(body).encode(),
                                         headers={"Cookie": cookie, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                r.read()
            with urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/scenarios/{d['id']}", headers={"Cookie": cookie}), timeout=60) as r:
                got = json.loads(r.read())
            ok = got["payload"]["evaluationPrompt"] == out
            print(f"  PUT {d['id']} {'verified' if ok else 'ROUND-TRIP DIFFERS'}")
    print(f"{'would change' if a.dry_run else 'changed'} {changed}/{len(docs)} rubrics")


if __name__ == "__main__":
    main()
