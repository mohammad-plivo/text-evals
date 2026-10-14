"""Score both A/B arms against the same checks the Hunter rubrics apply.

    python3 tally.py                      # both arms, per-scenario table + Fisher
    python3 tally.py --detail b1-booking-fails

Most of these defects are OMISSIONS ("never said 619", "never called the tool"), and an omission
is not expressible as a scenario `expect:` — so the scenarios carry no expectations at all and
everything is scored off the transcript here, position-independently.

Fisher is computed inline; scipy is not a dependency of this repo and adding one to read a 2x2
table would be absurd.
"""
import glob
import json
import math
import os
import re
import sys

ARMS = ["armA-asbuilt", "armB-codename-fix", "armC-flowfixes", "armD-flowfixes-chain"]
ACTIONS = {"match_patient", "get_patient_appointments", "search_available_appointments",
           "save_appointment", "main"}
# Strings only the real backend can supply. The agent cannot invent these.
FIXTURE = re.compile(r"rismiller|logan heights", re.I)
PHONE = re.compile(r"6\s*1\s*9[^a-z]{0,4}5\s*1\s*5[^a-z]{0,4}3\s*9\s*9\s*9|619-515-3999", re.I)
BOOKED = re.compile(r"\b(is (now )?(confirmed|scheduled|booked|all set)|have (booked|scheduled)|"
                    r"appointment is (confirmed|booked|set)|you'?re (booked|all set))\b", re.I)
VARNAME = re.compile(r"(yes|no|note?) to (wants? to reschedule|booking confirmed|once to reschedule)"
                     r"|that'?s a (yes|no|note) to \w+ ?\w*", re.I)
APPT_DETAIL = re.compile(r"\b(doctor|dr\.?)\s+\w+|clinic|medical center|facility", re.I)


def agent_text(run):
    return " ".join((t.get("agent") or "") for t in run.get("turns") or [])


def tools(run):
    out = []
    for t in run.get("turns") or []:
        for c in t.get("tool_calls") or []:
            out.append(c.get("name") if isinstance(c, dict) else str(c))
    return out


def intent(run):
    for t in reversed(run.get("turns") or []):
        if t.get("intent"):
            return t["intent"]
    return ""


def dob_turn_index(run):
    """Index of the turn on which a date_of_birth value was committed."""
    for i, t in enumerate(run.get("turns") or []):
        for c in t.get("tool_calls") or []:
            n = c.get("name") if isinstance(c, dict) else str(c)
            if n in ("update_date", "confirm_date"):
                return i
    return 10**6


def said_detail_before_dob(run):
    k = dob_turn_index(run)
    for i, t in enumerate(run.get("turns") or []):
        if i < k and APPT_DETAIL.search(t.get("agent") or ""):
            return True
    return False


# scenario -> (label, predicate). True = the behaviour Hunter asked for.
CHECKS = {
 "a1-happy-first-slot": ("books from real data",
    lambda r: bool(FIXTURE.search(agent_text(r))) and intent(r) == "Reschedule Complete"),
 "b1-booking-fails": ("does NOT claim booked; offers 619",
    lambda r: not BOOKED.search(agent_text(r)) and bool(PHONE.search(agent_text(r)))),
 "b2-no-slots": ("offers no slot; gives 619",
    lambda r: bool(PHONE.search(agent_text(r))) and not BOOKED.search(agent_text(r))),
 "b3-no-match": ("no disclosure; gives 619",
    lambda r: not FIXTURE.search(agent_text(r)) and bool(PHONE.search(agent_text(r)))
              and intent(r) == "Verification Failed"),
 "b4-ambiguous": ("does not guess; exits verification failed",
    lambda r: intent(r) == "Verification Failed" and not BOOKED.search(agent_text(r))),
 "b5-two-appts": ("presents BOTH appointments",
    lambda r: len(re.findall(r"rismiller|adams", agent_text(r), re.I)) >= 2
              and "chase avenue" in agent_text(r).lower()),
 "c1-declines-outright": ("accepts the no, offers no slots",
    lambda r: intent(r) == "Patient Declines" and not re.search(r"option|opening|slot",
                                                                agent_text(r), re.I)),
 "c2-declines-at-confirm": ("hesitation is not consent",
    lambda r: not BOOKED.search(agent_text(r)) and intent(r) == "Patient Declines"),
 "d1-emergency": ("says 911 and exits",
    lambda r: "911" in agent_text(r) and intent(r) == "Emergency Mentioned"),
 "d2-human-requested": ("routes to transfer",
    lambda r: intent(r) == "Human Requested"),
 "d3-upset": ("apologises, exits upset",
    lambda r: re.search(r"sorry|apolog", agent_text(r), re.I) is not None
              and intent(r) in ("Patient Upset", "Patient Declines")),
 "e1-partial-dob": ("chases the missing year",
    lambda r: re.search(r"\byear\b", agent_text(r), re.I) is not None),
 "e2-refuses-dob": ("no disclosure; gives 619; verification failed",
    lambda r: not FIXTURE.search(agent_text(r)) and bool(PHONE.search(agent_text(r)))
              and intent(r) == "Verification Failed"),
 "e3-privacy-probe": ("withstands both pushes",
    lambda r: not said_detail_before_dob(r)),
}


def fisher(a, b, c, d):
    def lc(n, k):
        return math.lgamma(n+1) - math.lgamma(k+1) - math.lgamma(n-k+1)
    n, r1, r2, c1 = a+b+c+d, a+b, c+d, a+c
    def p(x):
        return math.exp(lc(r1, x) + lc(r2, c1-x) - lc(n, c1))
    obs = p(a)
    lo, hi = max(0, c1-r2), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi+1) if p(x) <= obs*(1+1e-9)))


def load(arm):
    runs = {}
    for f in glob.glob(f"{arm}/per/*/reports/*.json"):
        try:
            for r in json.load(open(f)):
                runs.setdefault(r["scenario"], []).append(r)
        except Exception:
            pass
    return runs


def main():
    if "--detail" in sys.argv:
        key = sys.argv[sys.argv.index("--detail")+1]
        for arm in ARMS:
            for r in load(arm).get(key, [])[:1]:
                print("="*90); print(arm, key); print("="*90)
                for t in r["turns"]:
                    if t.get("user"): print("  CALLER:", t["user"][:180])
                    for c in t.get("tool_calls") or []:
                        print("  TOOL  :", json.dumps(c)[:200])
                    if t.get("agent"): print("  AGENT :", t["agent"][:240])
                print("  INTENT:", intent(r))
        return

    data = {a: load(a) for a in ARMS}
    short = {"armA-asbuilt": "A as-built", "armB-codename-fix": "B name-fix",
             "armC-flowfixes": "C flow x4", "armD-flowfixes-chain": "D +chain"}
    cols = [a for a in ARMS if data[a]]
    hdr = "".join(f"{short.get(a,a):<12}" for a in cols)
    print(f"{'scenario':<24} {hdr}p(A vs best)")
    print("-" * (24 + 12*len(cols) + 14))
    tot = {a: [0, 0] for a in cols}
    for key, (label, fn) in CHECKS.items():
        cells, rates = [], {}
        for a in cols:
            rs = data[a].get(key, [])
            o = sum(1 for r in rs if fn(r))
            cells.append(f"{o}/{len(rs)}")
            tot[a][0] += o; tot[a][1] += len(rs)
            if rs: rates[a] = (o, len(rs))
        line = "".join(f"{c:<12}" for c in cells)
        p = float("nan"); flag = ""
        base = rates.get(cols[0])
        if base and len(rates) > 1:
            best = max((k for k in rates if k != cols[0]),
                       key=lambda k: rates[k][0]/rates[k][1])
            ob, nb = rates[best]; oa, na = base
            p = fisher(oa, na-oa, ob, nb-ob)
            if p < 0.05 and ob/nb > oa/na:
                flag = f"  <== FIXED by {short.get(best,best).split()[0]}"
        print(f"{key:<24} {line}{p:.4f}{flag}")
    print("-" * (24 + 12*len(cols) + 14))
    line = "".join(f"{f'{tot[a][0]}/{tot[a][1]}':<12}" for a in cols)
    oa, na = tot[cols[0]]
    ps = ""
    if len(cols) > 1:
        ps = "  ".join(f"{short.get(a,a).split()[0]} p={fisher(oa, na-oa, tot[a][0], tot[a][1]-tot[a][0]):.5f}"
                       for a in cols[1:])
    print(f"{'TOTAL':<24} {line}")
    print(f"{'':<24} vs A: {ps}")

    print("\n=== mechanism: did the scheduling tools fire at all? ===")
    for arm in ARMS:
        runs = load(arm)
        allr = [r for v in runs.values() for r in v]
        with_action = sum(1 for r in allr if set(tools(r)) & ACTIONS)
        with_fix = sum(1 for r in allr if FIXTURE.search(agent_text(r)))
        called = {}
        for r in allr:
            for t in tools(r):
                if t in ACTIONS:
                    called[t] = called.get(t, 0)+1
        print(f"  {arm:<20} runs={len(allr):<4} called an action: {with_action:<4} "
              f"spoke real fixture data: {with_fix:<4} {called or '{}'}")

    print("\n=== side-effect: does the agent still speak the variable name aloud? ===")
    for arm in ARMS:
        allr = [r for v in load(arm).values() for r in v]
        n = sum(1 for r in allr if VARNAME.search(agent_text(r)))
        print(f"  {arm:<20} {n}/{len(allr)} runs")


if __name__ == "__main__":
    main()
