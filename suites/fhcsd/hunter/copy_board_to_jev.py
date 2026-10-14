"""Copy the 'FHCSD dev test' board (48 + the soonest persona) into a category for the LOCAL jev stack.

  python3 copy_board_to_jev.py --cookie <file> --runner https://<runner tunnel> [--flow <local flow uuid>] [--dry-run] [--only <source id>,...]

Each copy is the dev scenario re-dated for today's clinic day by align_dev_board's own rules (keyed by the dev id), with
its trigger pointed at the jev runner tunnel and the local FHCSD flow (flow 10, the import of dev b363ccd7), its testId
suffixed -jev, and no callback-variable checks (MK, 29 Sep q14: the local flow posts no callbacks). The dev scenarios are
only read, never written. A copy is found again by its name, so a rerun (after a tunnel re-mint or the 12:30 IST clinic-day
roll) updates in place; every write is read back and compared.
"""
import argparse
import json
import re

import align_dev_board as dev

CATEGORY = "FHCSD v2.9 - Jev (local)"
FLOW = "db6ac8b9-50b6-4116-b7d8-81c228217169"
ACCOUNT = "<AUTH_ID>"


def soonest(base):
    """The no-preference persona, built from the clean walk exactly as align_dev_board.ensure_soonest builds it on dev."""
    p = json.loads(json.dumps(base["payload"]))
    p["initiationVariables"] = {"date_of_birth": "03/14/1975", "first_name": "Owen", "last_name": "Marchetti"}
    p["conversationPrompt"], p["testId"], p["event"] = dev.SOONEST_PERSONA, "voice-fhcsd29-soonest-next-day", "soonest-next-day"
    ep = p["evaluationPrompt"]
    ep = ep[:ep.index("THE CLINIC RECORD.")] + dev.soonest_record() + ep[ep.index(dev.TAIL):]
    ep = re.sub(r"\n\d+\. ASKS WHICH DATE TO LOOK FROM.*?(?=\n\d+\. |\Z)", "", ep, flags=re.S).rstrip()
    p["evaluationPrompt"] = ep + "\n%d. %s\n" % (max(int(m) for m in re.findall(r"(?m)^(\d+)\. ", ep)) + 1, dev.SOONEST_CRITERION)
    return {"name": dev.SOONEST_NAME, "description": base.get("description"), "tier": base.get("tier"), "payload": p}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("--flow", default=FLOW)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    cookie = open(a.cookie).read().strip()
    cookie = cookie if cookie.startswith("hunter_session=") else "hunter_session=" + cookie
    url = f"{a.runner.rstrip('/')}/v1/account/{ACCOUNT}/flow/{a.flow}"
    print(f"clinic day {dev.T:%A %d %B %Y} | trigger {url}")
    rows = dev.req("GET", "/api/scenarios?limit=2000", cookie)["scenarios"]
    sources = [r for r in rows if r.get("category") == dev.CATEGORY]
    copies = {r["name"]: r["id"] for r in rows if r.get("category") == CATEGORY}
    walk = next(r["id"] for r in sources if "clean walk" in r["name"])
    if a.only:
        sources = [r for r in sources if str(r["id"]) in a.only.split(",")]
    done = 0
    for row in sources:
        live = dev.req("GET", f"/api/scenarios/{row['id']}", cookie)
        d = soonest(dev.req("GET", f"/api/scenarios/{walk}", cookie)) if live["name"] == dev.SOONEST_NAME else dev.edit(live)
        p = d["payload"]
        p["expectedCallbackVariables"] = {}
        p["initiationRequest"]["url"] = url
        p["testId"] = f"{p['testId']}-jev"
        body = {"name": f"{d['name']} (jev)", "description": d.get("description"), "category": CATEGORY, "tier": d.get("tier"),
                "payload": p}
        sid = copies.get(body["name"])
        if a.dry_run:
            print(f"  {'update' if sid else 'create'} {body['name'][:90]}")
            continue
        if sid:
            dev.req("PUT", f"/api/scenarios/{sid}", cookie, body)
        else:
            sid = dev.req("POST", "/api/scenarios", cookie, body)["id"]
        back = dev.req("GET", f"/api/scenarios/{sid}", cookie)
        assert json.dumps(back["payload"], sort_keys=True) == json.dumps(p, sort_keys=True), f"{sid}: round trip differs"
        done += 1
        print(f"  {sid} {body['name'][:90]}")
    print(f"{'would write' if a.dry_run else 'wrote'} {len(sources) if a.dry_run else done} of {len(sources)} into {CATEGORY!r}")


if __name__ == "__main__":
    main()
