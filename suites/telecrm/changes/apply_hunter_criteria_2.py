"""Second Hunter criteria pass — for the follow-up field becoming a DATE and moving LAST.

The flow now collects `follow_up_call_date` (type Date, optional, last in the walk) instead of an
`open_to_a_follow_up_call` yes/no followed by a Scribe-extracted `callback_datetime`. Three criteria
were written against the old shape.

Deliberately NOT touched (checked, still exact): 16986 all criteria — "DATE ASKED EXACTLY ONCE" and
"NO INVENTED DATE" are the same contract, and the second matters MORE now the Scribe twin is gone.
16536 / 16542 order criteria — they assert form/team-size/industry come BEFORE the follow-up-time
question, which the reorder makes more likely to hold, not less. 16541 order criterion — it names
only the three REQUIRED fields, whose order is unchanged. 16543 / 16548 / 16984 — still satisfiable
and still able to fail.

    HUNTER_COOKIE='hunter_session=<jwt>' python3 apply_hunter_criteria_2.py [--dry-run]
"""
import json, os, sys, urllib.request

BASE, COOKIE, DRY = "https://hunter.contactodev.com", os.environ.get("HUNTER_COOKIE", ""), "--dry-run" in sys.argv

EDITS = {
    # UNSATISFIABLE as written: it wants the CRM-requirement question asked AFTER the follow-up
    # decline, but crm_need_or_current_process is now 4th and follow_up_call_date is 7th, so the
    # requirement question always comes first. Reworded to be order-independent — it asserts the
    # agent ACTS on "no longer valid" rather than where in the walk it hears it.
    16545: [("eval",
        "1. VALIDITY ASKED AFTER DECLINE (KEY): after the follow-up decline, the agent asks whether the CRM requirement is still valid.",
        "1. VALIDITY ACTED ON (KEY): when the caller says their CRM requirement is no longer valid, the agent treats that as the answer — it acknowledges it and stops qualifying, rather than continuing with the remaining questions or re-asking for the requirement. It may confirm the point once; it must not argue it or ask for the requirement again.")],
    # References a yes/no willingness step that no longer exists. The logic (no day+time captured ->
    # Qualified Close, not Callback Close) is still right; only the mode named is stale.
    16534: [("eval",
        "if the caller only gave a yes/no willingness to a follow-up call and no specific day+time was ever solicited or stated, the call went through Qualified Close, not",
        "if no specific day+time was ever solicited or stated, the call went through Qualified Close, not")],
    # Adds the POSITIVE assertion for the new contract: the field is a date, so the agent must ask
    # for a day and time, not merely whether they would like a call. Without this nothing tests that
    # the date field is actually being asked as a date.
    16986: [("eval",
        "1. PATH REACHED (LIVENESS): before the time exchange the agent asked the qualification questions — sales team size, business/industry, and CRM need — and then asked about a follow-up call or preferred time,",
        "1. PATH REACHED (LIVENESS): before the time exchange the agent asked the qualification questions — sales team size, business/industry, and CRM need — and then asked for a preferred day and time for a follow-up call. Asking ONLY whether he would like a follow-up, with no request for a day or time, does not satisfy this;")],
}
FIELD = {"eval": "evaluationPrompt", "conv": "conversationPrompt"}


def req(method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body else None)
    r.add_header("Cookie", COOKIE)
    if body: r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=40) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def main():
    if not COOKIE: sys.exit("set HUNTER_COOKIE")
    print("authenticated as", req("GET", "/api/auth/me")[1].get("email"))
    backup = {}
    for sid, edits in EDITS.items():
        _, d = req("GET", f"/api/scenarios/{sid}")
        backup[sid] = json.loads(json.dumps(d))
        notes = []
        for where, find, repl in edits:
            key = FIELD[where]; txt = d["payload"].get(key) or ""
            if repl in txt: notes.append("already applied"); continue
            if find not in txt:
                notes.append("ANCHOR MISS"); print(f"  !! {sid}: anchor not found: {find[:100]}..."); continue
            d["payload"][key] = txt.replace(find, repl, 1); notes.append("replaced")
        print(f"{sid} [{d.get('tier')}] {d['name']}\n     " + " | ".join(notes))
        if DRY or "ANCHOR MISS" in notes: continue
        code, _ = req("PUT", f"/api/scenarios/{sid}",
                      {"name": d["name"], "description": d.get("description"), "category": d["category"],
                       "tier": d.get("tier"), "payload": d["payload"]})
        print(f"     PUT {code}")
    json.dump(backup, open("hunter-criteria-backup-2.json", "w"), indent=1)
    if DRY: print("\nDRY RUN — nothing written"); return
    print("\n=== round-trip verification ===")
    for sid in EDITS:
        _, now = req("GET", f"/api/scenarios/{sid}"); old = backup[sid]
        top = [k for k in ("name", "description", "category", "tier") if now.get(k) != old.get(k)]
        pk = [k for k in set(now["payload"]) | set(old["payload"]) if now["payload"].get(k) != old["payload"].get(k)]
        print(f"  {sid} tier={now.get('tier')}  top-level changed: {top or 'none'}  payload changed: {pk}")


if __name__ == "__main__":
    main()
