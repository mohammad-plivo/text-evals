"""Tally the Choose Slot A/B: per run, was a slot time voiced in the agent's FIRST turn, and read back before the yes?"""
import json, glob, re, sys
SLOT = re.compile(r"august (thirty[- ]?first|31)|september (first|1\b|2\b|second)|9:30|nine thirty|11:00|eleven|3:45|three forty[- ]five", re.I)
def runs(arm):
    out = []
    for f in sorted(glob.glob(f"chooseslot/arm{arm}/reports/*.json")):
        d = json.load(open(f)); out += d if isinstance(d, list) else [d]
    return out
for arm in ("A", "B"):
    rs = runs(arm); voiced = readback = 0; n = len(rs)
    for r in rs:
        turns = r.get("turns") or []
        agent = [t.get("agent") or "" for t in turns if t.get("agent")]
        if agent and SLOT.search(agent[0]): voiced += 1
        # read-back: an agent turn that both mentions a slot time and asks to confirm, after the opener
        if any(SLOT.search(a) and re.search(r"confirm|book|is that (right|correct)", a, re.I) for a in agent[1:]): readback += 1
    print(f"arm {arm}: runs={n}  slot voiced in first turn={voiced}/{n}  slot read back at confirm={readback}/{n}")
    for r in rs[:2]:
        for t in (r.get("turns") or [])[:4]:
            if t.get("agent"): print("   AGENT:", t["agent"][:200])
            if t.get("user"): print("   USER :", t["user"][:120])
        print("   ---")
