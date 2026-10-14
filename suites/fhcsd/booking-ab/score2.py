"""Score sim reports for the afternoon-slot fix and its regression set. usage: score2.py <label> <report.jsonl>... [--quiet]
A run passes when the behaviour its scenario names is seen in the tool calls and the agent's words after the options are read."""
import json, re, sys
from datetime import datetime, timedelta, timezone

WALK = 4  # turns before the three morning options are on the table
LATER = None


def runs(paths):
    for p in paths:
        cur = None
        for l in open(p):
            d = json.loads(l)
            if d.get("type") == "scenario_started":
                cur = {"name": d["name"], "run": d.get("run"), "turns": []}
            elif d.get("type") == "turn" and cur is not None:
                cur["turns"].append(d)
            elif d.get("type") == "scenario_finished" and cur is not None:
                cur["failures"] = d.get("failures") or []
                yield cur
                cur = None


def facts(run):
    after = run["turns"][WALK:]
    calls = []
    for t in after:
        for c in t.get("tool_calls") or []:
            try: args = json.loads(c.get("arguments") or "{}")
            except ValueError: args = {}
            calls.append((c["name"], args))
    said = " ".join(str(t.get("agent") or "") for t in after)
    searches = [a for n, a in calls if "search_available" in n]
    books = [a for n, a in calls if "schedule_appointment" in n or "reschedule_appointment" in n]
    return {
        "reached": len(run["turns"]) > WALK,
        "said": said,
        "searches": [(a.get("start_date"), a.get("time_preference")) for a in searches],
        "booked_slot": [a.get("from_slot_id") for a in books],
        "choices": [a.get("choice") for n, a in calls if n == "update_choice"],
        "tools": [n for n, _ in calls if not n.startswith("fhcsd_")],
        "intents": [t.get("intent") for t in run["turns"] if t.get("intent") and t.get("intent") != "reached"],
        "unavailable": bool(re.search(r"not available|unavailable|isn.t available|only available", said, re.I)),
    }


def later_date(paths):
    stamp = re.search(r"(\d{8})-\d{6}", paths[0]).group(1)
    day = datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=timezone.utc)
    return None  # the scenario file carries the date; matched loosely below


PM_READ = re.compile(r"1:10|one ten|1:30|one thirty|1:50|one fifty", re.I)
AM_READ = re.compile(r"8:10|eight ten", re.I)
PM_BOOKED = lambda f: any(str(x) in ("159", "163", "167") for x in f["booked_slot"])  # an afternoon slot was booked
NONE = lambda f: "none of these" in [str(c).lower() for c in f["choices"]]
RULES = {
    "afternoon-statement": lambda f: PM_BOOKED(f) and any(p == "afternoon" for _, p in f["searches"]) and not f["unavailable"],
    "afternoon-question": lambda f: PM_BOOKED(f) and any(p == "afternoon" for _, p in f["searches"]) and not f["unavailable"],
    "pick-third": lambda f: ("107" in map(str, f["booked_slot"])) and not f["searches"],
    "none-of-these": lambda f: NONE(f) and len(f["searches"]) >= 1,
    # the three below must stay with the options on the table: no new search, nothing recorded, nothing booked
    "who-is-provider": lambda f: not f["searches"] and not f["choices"] and not f["booked_slot"],
    "different-provider": lambda f: not f["searches"] and not f["choices"] and not f["booked_slot"],
    "repeat-options": lambda f: not f["searches"] and not f["choices"] and bool(AM_READ.search(f["said"])),
    "date-change": lambda f: len(f["searches"]) >= 1 and all(d != f.get("first_date") for d, _ in f["searches"]) and not NONE(f),
    "human-request": lambda f: any("human" in str(i).lower() for i in f["intents"]),
}

quiet = "--quiet" in sys.argv
label, paths = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")]
tot = {}
for r in runs(paths):
    f = facts(r)
    first = r["turns"][WALK - 1].get("tool_calls") or [] if len(r["turns"]) >= WALK else []
    f["first_date"] = next((json.loads(c["arguments"]).get("start_date") for c in first if "search_available" in c["name"]), None)
    ok = bool(f["reached"] and RULES[r["name"]](f))
    t = tot.setdefault(r["name"], [0, 0])
    t[0] += ok; t[1] += 1
    if not quiet:
        print(f"{label} {r['name']} #{r['run']}: {'PASS' if ok else 'FAIL'} | searches={f['searches']} booked={f['booked_slot']} choices={f['choices']} tools={f['tools']} intents={f['intents']} unavailable={f['unavailable']}")
        print(f"      said: {f['said'].strip().replace(chr(10), ' ')[:300]}")
print()
for k in RULES:
    if k in tot: print(f"{label:10} {k:22} {tot[k][0]}/{tot[k][1]}")
