"""Re-stamp every scenario's missed_appointment_date to today, in place.

    HUNTER_COOKIE='hunter_session=<jwt>' python3 refresh_dates.py [--dry-run]

Why this exists: the mock returns the missed appointment dated TODAY (the brief is "missed earlier
the same day"), and the flow matches it against `missed_appointment_date` from the trigger. Run the
suite on a later day without this and step 3 stops matching — the agent finds no appointment on the
stated date and exits API Failure, which reads as an agent defect rather than a stale fixture.

Sends the FULL object including `tier`: a PUT that omits it silently resets tier to "custom" and
still returns 200.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

BASE = "https://hunter.contactodev.com"
CATEGORY = os.environ.get("HUNTER_CATEGORY", "FHCSD v2.5 tests")
import datetime as _dt, zoneinfo as _zi
TODAY = _dt.datetime.now(_zi.ZoneInfo("America/Los_Angeles")).strftime("%m/%d/%Y")  # clinic day, same clock as the mock (D-027)


def req(method, path, body=None, cookie=""):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body is not None else None)
    r.add_header("Cookie", cookie)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def main():
    dry = "--dry-run" in sys.argv
    cookie = os.environ.get("HUNTER_COOKIE") or sys.exit("set HUNTER_COOKIE=...")
    _, listing = req("GET", "/api/scenarios", cookie=cookie)
    rows = listing if isinstance(listing, list) else listing.get("scenarios", [])
    ids = [r["id"] for r in rows if r.get("category") == CATEGORY]
    print(f"{len(ids)} scenario(s) in {CATEGORY!r}; target date {TODAY}")

    changed = 0
    for sid in ids:
        _, d = req("GET", f"/api/scenarios/{sid}", cookie=cookie)
        iv = d["payload"].get("initiationVariables") or {}
        old = iv.get("missed_appointment_date")
        if old == TODAY:
            continue
        iv["missed_appointment_date"] = TODAY
        d["payload"]["initiationVariables"] = iv
        print(f"  {sid}  {old} -> {TODAY}  {d['name']}")
        if not dry:
            body = {"name": d["name"], "description": d.get("description"),
                    "category": d["category"], "tier": d.get("tier"), "payload": d["payload"]}
            req("PUT", f"/api/scenarios/{sid}", body, cookie)
            _, back = req("GET", f"/api/scenarios/{sid}", cookie=cookie)
            got = back["payload"]["initiationVariables"]["missed_appointment_date"]
            assert got == TODAY, f"{sid}: round-trip says {got}"
            assert back.get("tier") == d.get("tier"), f"{sid}: tier drifted to {back.get('tier')}"
        changed += 1
    print(f"\n{changed} updated" + (" (DRY RUN — nothing written)" if dry else ""))


if __name__ == "__main__":
    main()
