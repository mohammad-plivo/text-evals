"""Score the exit_collection A/B: did the mid-walk exit fire with the right intent?

    python3 tally_exit.py
"""
import glob, json, math, re

def fisher(a,b,c,d):
    def lc(n,k): return math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)
    n,r1,r2,c1=a+b+c+d,a+b,c+d,a+c
    def p(x): return math.exp(lc(r1,x)+lc(r2,c1-x)-lc(n,c1))
    obs=p(a); lo,hi=max(0,c1-r2),min(r1,c1)
    return min(1.0,sum(p(x) for x in range(lo,hi+1) if p(x)<=obs*(1+1e-9)))

def intent(r):
    for t in reversed(r.get("turns") or []):
        if t.get("intent"): return t["intent"]
    return ""

def agent_text(r):
    return " ".join((t.get("agent") or "") for t in r.get("turns") or [])

WANT = {
    "d1-emergency": ("Emergency Mentioned", lambda r: intent(r)=="Emergency Mentioned" and ("9 1 1" in agent_text(r) or "911" in agent_text(r))),
    "d2-human-requested": ("Human Requested", lambda r: intent(r)=="Human Requested"),
    "d3-upset": ("Patient Upset", lambda r: intent(r) in ("Patient Upset","Patient Declines")),
}

def load(arm):
    runs={}
    for f in glob.glob(f"{arm}/per/*/reports/*.json"):
        try:
            for r in json.load(open(f)): runs.setdefault(r["scenario"],[]).append(r)
        except Exception: pass
    return runs

A,B = load("exitAB2-base"), load("exitAB2-fix")
print(f"{'scenario':<22} {'want intent':<22} {'base':<7} {'fix':<7} p")
ta=tb=na=nb=0
for k,(want,fn) in WANT.items():
    ra,rb=A.get(k,[]),B.get(k,[])
    oa,ob=sum(1 for r in ra if fn(r)),sum(1 for r in rb if fn(r))
    ta+=oa; na+=len(ra); tb+=ob; nb+=len(rb)
    p = fisher(oa,len(ra)-oa,ob,len(rb)-ob) if ra and rb else float("nan")
    print(f"{k:<22} {want:<22} {oa}/{len(ra):<5} {ob}/{len(rb):<5} {p:.4f}")
print("-"*70)
if na and nb: print(f"{'TOTAL':<45} {ta}/{na:<5} {tb}/{nb:<5} {fisher(ta,na-ta,tb,nb-tb):.5f}")
print()
for arm,runs in (("base",A),("fix",B)):
    ints={}
    for k,v in runs.items():
        for r in v: ints.setdefault(k,[]).append(intent(r) or "(none)")
    print(f"--- {arm}: intents actually picked ---")
    for k,v in ints.items(): print(f"   {k:<22} {v}")
