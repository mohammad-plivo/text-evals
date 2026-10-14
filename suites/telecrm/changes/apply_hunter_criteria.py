"""Re-point 4 TeleCRM Hunter scenarios from the choice-field contract to the number-field one.

Run with a live hunter_session cookie:
    HUNTER_COOKIE='hunter_session=<jwt>' python3 apply_hunter_criteria.py [--dry-run]

Why each edit, and why it is not just a deletion: once sales_team_size is a Number field there are
no category codes in existence, so "the agent never speaks a category code" passes without testing
anything — a vacuous green, which is the failure mode setup.md calls out. Each is replaced by an
assertion the new contract can still fail.

Sends the FULL object including `tier`. A previous pass omitted it and the server silently reset
tier to "custom" on 33 scenarios; 200 OK said nothing about it. Always diff the round-trip.
"""
import json, os, sys, urllib.request

BASE = "https://hunter.contactodev.com"
COOKIE = os.environ.get("HUNTER_COOKIE", "")
DRY = "--dry-run" in sys.argv

NEW_CRITERION_4 = (
    "4. TEAM SIZE ASKED OPENLY AND READ BACK IN THE CALLER'S OWN TERMS: the agent asks for the "
    "sales team size as one open question and never offers, lists or suggests ranges or bands to "
    "choose from (no 'is it up to 2, 3-5, ...', no 'would you say under five or over five'). When "
    "it acknowledges the answer it uses the caller's own number in natural words ('two people', "
    "'five'), never a range or a band. Offering ranges, or reading a band back, -> NOT MET."
)

# scenario id -> list of (find, replace) applied to payload.evaluationPrompt / conversationPrompt
EDITS = {
    16532: [("eval", "4. NO CATEGORY CODES ALOUD: the agent never speaks category codes like 'Upto 2' or '3-5' as labels; it may naturally say 'at least 3 sales users' or repeat the caller's own words.", NEW_CRITERION_4)],
    16534: [("eval", "4. NO CATEGORY CODES ALOUD: the agent never says 'Upto 2', '3-5' or similar codes to the caller.", NEW_CRITERION_4)],
    16983: [("eval", "4. NO CATEGORY CODES ALOUD: the agent never speaks category labels like 'Upto 2' or '3-5' aloud as labels; it may naturally say 'at least 3 sales users' or repeat the caller's own words. Any spoken category code -> NOT MET.", NEW_CRITERION_4)],
    # 16531: two thirds of this criterion was ALREADY vacuous — initiationVariables only seeds
    # COMPANY_NAME, so industry and sales_team_size are never sent to the flow and the agent could
    # not voice them under any circumstance. Narrow it to the value that is actually seeded.
    16531: [
        ("eval",
         "CONTEXT NOTE for you the judge: the lead record silently contains company_name='Sharma Realty', industry='Real Estate', sales_team_size='6-10'. The agent is FORBIDDEN from speaking these hidden values.",
         "CONTEXT NOTE for you the judge: the lead record silently contains company_name='Sharma Realty'. That is the ONLY hidden value actually sent to the flow, and the agent is FORBIDDEN from speaking it."),
        ("eval",
         "1. HIDDEN VALUES NEVER VOICED: no agent turn ever contains 'Sharma Realty', 'Real Estate' (as a claim about her business), '6-10', or 'six to ten' — and the agent never asks a confirmation like 'is your team six to ten people?'.",
         "1. HIDDEN VALUE NEVER VOICED: no agent turn ever contains 'Sharma Realty', and the agent never asks a confirmation like 'is your company Sharma Realty?'."),
        ("conv",
         "If the agent says the words 'Sharma Realty', '6-10', 'six to ten', or 'Real Estate' — details you never told it —",
         "If the agent says the words 'Sharma Realty' — a detail you never told it —"),
    ],
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
    if not COOKIE:
        sys.exit("set HUNTER_COOKIE='hunter_session=<jwt>'")
    _, me = req("GET", "/api/auth/me")
    print("authenticated as", me.get("email"))
    backup = {}
    for sid, edits in EDITS.items():
        _, d = req("GET", f"/api/scenarios/{sid}")
        backup[sid] = json.loads(json.dumps(d))
        applied = []
        for where, find, repl in edits:
            key = FIELD[where]
            txt = d["payload"].get(key) or ""
            if repl in txt:
                applied.append(f"{key}: already applied"); continue
            if find not in txt:
                print(f"  !! {sid} {key}: ANCHOR NOT FOUND — skipping, nothing written")
                print(f"     looked for: {find[:110]}...")
                applied.append(f"{key}: ANCHOR MISS"); continue
            d["payload"][key] = txt.replace(find, repl, 1)
            applied.append(f"{key}: replaced")
        print(f"{sid} [{d.get('tier')}] {d['name']}\n     " + " | ".join(applied))
        if DRY or any("ANCHOR MISS" in a for a in applied):
            continue
        body = {"name": d["name"], "description": d.get("description"),
                "category": d["category"], "tier": d.get("tier"), "payload": d["payload"]}
        code, _ = req("PUT", f"/api/scenarios/{sid}", body)
        print(f"     PUT {code}")
    json.dump(backup, open("hunter-criteria-backup.json", "w"), indent=1)
    print("\nbackup written to hunter-criteria-backup.json")
    if DRY:
        print("DRY RUN — nothing written"); return
    print("\n=== round-trip verification ===")
    for sid in EDITS:
        _, now = req("GET", f"/api/scenarios/{sid}")
        old = backup[sid]
        diffs = [k for k in ("name", "description", "category", "tier")
                 if now.get(k) != old.get(k)]
        pk = [k for k in set(now["payload"]) | set(old["payload"])
              if now["payload"].get(k) != old["payload"].get(k)]
        print(f"  {sid} tier={now.get('tier')}  top-level changed: {diffs or 'none'}  payload changed: {pk}")


if __name__ == "__main__":
    main()
