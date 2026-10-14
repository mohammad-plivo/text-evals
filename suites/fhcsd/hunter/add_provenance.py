import os
"""R2 (D-018): make the NO INVENTED DETAIL criterion checkable by naming the mock's fixtures.

The judge never sees tool outputs, so "must be one the system returned" let invented appointments
pass twice in run 2c2f8390. Replaces that trailer with a numbered criterion. Tier-preserving PUT
(see refresh_dates.py); idempotent. Usage: HUNTER_COOKIE=<jwt> python3 add_provenance.py [--dry]
"""
import json, os, re, sys, urllib.request

BASE = "https://hunter.contactodev.com"
CATEGORY = os.environ.get("HUNTER_CATEGORY", "FHCSD v2.5 tests")
# Scenarios without the trailer where the agent can still state appointment/slot details.
APPEND = {17731, 17732, 17736, 17738, 17739, 17740, 17741, 17745}
OLD = re.compile(r"\nNO INVENTED DETAIL:[^\n]*\n?")
NEW = ("\n{n}. NO INVENTED DETAIL (check against the clinic record): the ONLY missed appointment that exists is on "
       "{date} at 10:30 AM with Dr. Rismiller at Logan Heights Family Health Center — there is exactly one; the ONLY slots "
       "that can be offered are on weekdays after {date} at 9:30 AM, 11:00 AM or 3:45 PM with Dr. Rismiller at Logan Heights. "
       "Treat {date} as correct — it is "
       "the date the call is about — and treat phonetic renderings of the provider (Ris Miller, Bris Miller, Rismiller) "
       "as Dr. Rismiller. If the agent states any other date, year, time, provider or facility (for example June 2024, "
       "Dr. Patel, Dr. Smith, Dr. Lee, Fairmont, Main Street, Maine Medical), or offers any other slot, this criterion "
       "is NOT MET. If the agent states no appointment detail at all, it is MET.\n")
MARK = re.compile(r"\n\d+\. NO INVENTED DETAIL \(check against the clinic record\):[^\n]*\n?")

def req(method, path, body=None, cookie=""):
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None)
    r.add_header("Cookie", cookie); r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.loads(resp.read() or b"{}")

def main():
    cookie = "hunter_session=" + (os.environ.get("HUNTER_COOKIE") or sys.exit("set HUNTER_COOKIE=<jwt>"))
    dry = "--dry" in sys.argv
    _, listing = req("GET", "/api/scenarios", cookie=cookie)
    items = listing if isinstance(listing, list) else (listing.get("scenarios") or listing.get("items") or [])
    ids = [s["id"] for s in items if isinstance(s, dict) and s.get("category") == CATEGORY]
    changed = skipped = 0
    for sid in ids:
        _, d = req("GET", f"/api/scenarios/{sid}", cookie=cookie)
        ep = d["payload"].get("evaluationPrompt", "")
        date = (d["payload"].get("initiationVariables") or {}).get("missed_appointment_date", "")
        m, d_ = re.match(r"(\d\d)/(\d\d)/(\d{4})", date), None
        import datetime; date_txt = datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime("%A, %B %-d, %Y") if m else date
        if "there is exactly one; the ONLY slots" in ep and "Treat " + date_txt + " as correct" in ep or not (OLD.search(ep) or MARK.search(ep) or int(sid) in APPEND):
            skipped += 1; continue
        n = max(int(m) for m in re.findall(r"(?m)^(\d+)\. ", ep)) + 1
        crit = NEW.format(n=n, date=date_txt)
        if MARK.search(ep):
            n = int(MARK.search(ep).group(0).strip().split(".")[0]); crit = NEW.format(n=n, date=date_txt)
            d["payload"]["evaluationPrompt"] = MARK.sub(crit, ep, count=1)
        elif OLD.search(ep): d["payload"]["evaluationPrompt"] = OLD.sub(crit, ep, count=1)
        else: d["payload"]["evaluationPrompt"] = ep.rstrip("\n") + crit
        print(f"{sid} {d['name'][:50]:50s} -> criterion {n}{' (dry)' if dry else ''}")
        if dry: continue
        body = {"name": d["name"], "description": d["description"], "category": d["category"], "tier": d.get("tier"), "payload": d["payload"]}
        req("PUT", f"/api/scenarios/{sid}", body, cookie)
        _, back = req("GET", f"/api/scenarios/{sid}", cookie=cookie)
        assert back.get("tier") == d.get("tier"), f"{sid}: tier drifted"
        assert "Treat " + date_txt + " as correct" in back["payload"]["evaluationPrompt"], f"{sid}: PUT did not land"
        changed += 1
    print(f"changed {changed}, skipped {skipped}, total {len(ids)}")

if __name__ == "__main__":
    main()
