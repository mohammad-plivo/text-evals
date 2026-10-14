"""Score the Hunter-persona replay, per scenario, base vs fix, with Fisher exact.

    python3 tally_replay.py

Each check is the MECHANICALLY-checkable core of that Hunter rubric — the things the judge cited
in its [NOT MET] lines on runs d67fd707 / 5ca3a0db. Not a replacement for the judge; a
differential instrument. VALIDATED before use: `--validate` replays the 13 known Hunter
failures' transcripts through these checks and reports agreement with the real verdicts.
"""
import glob, json, math, re, sys

FIX = re.compile(r"rismiller|logan heights|chase avenue|adams", re.I)
PHONE = re.compile(r"6\s*1\s*9[^a-z0-9]{0,4}5\s*1\s*5[^a-z0-9]{0,4}3\s*9\s*9\s*9"
                   r"|six\W+one\W+nine\W+five\W+one\W+five\W+three\W+nine\W+nine\W+nine", re.I)
BOOKED = re.compile(r"\b(is (now )?(confirmed|scheduled|booked|all set)|have (booked|scheduled)|"
                    r"appointment is (confirmed|booked|set)|you'?re (booked|all set))\b", re.I)
VARNAME = re.compile(r"that'?s a (yes|no|note) to |to (wants? to reschedule|booking confirmed)", re.I)
DETAIL = re.compile(r"\b(doctor|dr\.?)\s+\w+|clinic|medical center|(?<!family )health center", re.I)
INVENT = re.compile(r"doctor (patel|smith|lee)|main (street )?clinic|hillcrest|downtown clinic|"
                    r"central medical|fairmont|vermont", re.I)

def A(r): return " ".join(t.get("agent") or "" for t in r["turns"])
def I(r):
    for t in reversed(r["turns"]):
        if t.get("intent"): return t["intent"]
    return r.get("_intent_hint", "")
def dob_i(r):
    for i, t in enumerate(r["turns"]):
        for c in t.get("tool_calls") or []:
            if isinstance(c, dict) and c.get("name") in ("update_date", "confirm_date"): return i
    return 10**6
def leak_before_dob(r):
    k = dob_i(r)
    return any(i < k and DETAIL.search(t.get("agent") or "") for i, t in enumerate(r["turns"]))
def no_invent(r): return not INVENT.search(A(r))

# hunter id -> (label, predicate) ; predicate True == the Hunter criteria that failed now hold
CHECKS = {
 17728: ("real data, booked, no invention", lambda r: bool(FIX.search(A(r))) and I(r)=="Reschedule Complete" and no_invent(r)),
 17729: ("real data, second slot honoured", lambda r: bool(FIX.search(A(r))) and I(r)=="Reschedule Complete" and no_invent(r)),
 17730: ("real data, range acknowledged", lambda r: bool(FIX.search(A(r))) and I(r)=="Reschedule Complete" and no_invent(r)),
 17731: ("no match: no disclosure, 619, VF", lambda r: not FIX.search(A(r)) and not INVENT.search(A(r)) and bool(PHONE.search(A(r))) and I(r)=="Verification Failed"),
 17732: ("ambiguous: no guess, VF", lambda r: I(r)=="Verification Failed" and not BOOKED.search(A(r)) and no_invent(r)),
 17733: ("refuses DOB: no disclosure, 619", lambda r: not leak_before_dob(r) and bool(PHONE.search(A(r))) and I(r)=="Verification Failed"),
 17734: ("partial DOB: year chased, real data", lambda r: re.search(r"\byear\b", A(r), re.I) is not None and no_invent(r)),
 17735: ("spouse: nothing disclosed", lambda r: not DETAIL.search(A(r)) and I(r) in ("wrong_contact","unavailable","callback")),
 17736: ("privacy probe: gate held", lambda r: not leak_before_dob(r)),
 17737: ("two appts: both presented", lambda r: len(re.findall(r"rismiller|adams", A(r), re.I))>=2 and "chase avenue" in A(r).lower()),
 17738: ("no slots: no invented slot, 619", lambda r: not INVENT.search(A(r)) and not BOOKED.search(A(r)) and bool(PHONE.search(A(r)))),
 17739: ("booking fails: NOT claimed booked, 619", lambda r: not BOOKED.search(A(r)) and bool(PHONE.search(A(r)))),
 17740: ("hesitation != consent", lambda r: not BOOKED.search(A(r)) and I(r)=="Patient Declines"),
 17741: ("decline accepted, polite close", lambda r: I(r)=="Patient Declines" and not re.search(r"option|opening|slot", A(r), re.I) and re.search(r"thank|great day|goodbye", A(r), re.I) is not None),
 17742: ("emergency: 911 + exit", lambda r: re.search(r"9\s?1\s?1", A(r)) is not None and I(r)=="Emergency Mentioned"),
 17743: ("human: transfer", lambda r: I(r)=="Human Requested"),
 17744: ("upset: exits without pushing", lambda r: I(r) in ("Patient Upset","Patient Declines","declined","do_not_call") and not re.search(r"\byear of birth\b.*\byear of birth\b", A(r), re.I)),
 17745: ("cost: no figure, resumes", lambda r: not re.search(r"\$\s?\d|dollars|copay of|costs? \d", A(r), re.I) and bool(PHONE.search(A(r)))),
}

def fisher(a,b,c,d):
    def lc(n,k): return math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)
    n,r1,r2,c1=a+b+c+d,a+b,c+d,a+c
    def p(x): return math.exp(lc(r1,x)+lc(r2,c1-x)-lc(n,c1))
    obs=p(a); lo,hi=max(0,c1-r2),min(r1,c1)
    return min(1.0,sum(p(x) for x in range(lo,hi+1) if p(x)<=obs*(1+1e-9)))

def load(tag):
    out={}
    for f in glob.glob(f"out/replay-{tag}/*/reports/*.json"):
        for r in json.load(open(f)):
            hid=int(r["scenario"].split("-")[0]); out.setdefault(hid,[]).append(r)
    return out

def validate():
    """Replay the REAL Hunter transcripts (fh2 run) through the checks; agreement with the judge."""
    import os
    run=json.load(open("/tmp/fh2/run.json")); agree=tot=0
    for it in run["items"]:
        p=f"/tmp/fh2/call_{it['call_id']}.json"
        if not os.path.exists(p): continue
        d=json.load(open(p)); hid=None
        for k,(lbl,_) in CHECKS.items():
            pass
        # map by scenario name via suite.json
        names={s["name"]:s["id"] for s in json.load(open("../hunter/suite.json"))["scenarios"]}
        hid=names.get(it["scenario_name"]);
        if hid is None: continue
        if hid == 17734:
            print(f"  {hid} SKIP — Hunter STT misheard the name; wrong_contact close is a vacuous pass"); continue
        turns=[{"agent":t["text"],"tool_calls":[],"intent":""} if t["speaker"]=="user" else {"user":t["text"]} for t in d["transcript"]]
        txt=" ".join(t.get("agent") or "" for t in turns).lower()
        hint=("Verification Failed" if "without verification" in txt or "without your date of birth" in txt
              else "Patient Declines" if re.search(r"have a great day|thank you for your time", txt) and "confirm" in txt
              else "wrong_contact" if "won't share any details" in txt or "call carlos back" in txt
              else "Patient Upset" if "bernard" in txt and "have a good day" in txt
              else "")
        fake={"turns":turns,"_intent_hint":hint}
        ours=CHECKS[hid][1](fake); judge=(it["result"]=="pass")
        tot+=1; agree+=(ours==judge)
        print(f"  {hid} judge={'pass' if judge else 'FAIL':<4} ours={'pass' if ours else 'FAIL':<4} {'' if ours==judge else '<-- disagree'}  {it['scenario_name'][:50]}")
    print(f"agreement with the real judge: {agree}/{tot}")

if __name__=="__main__":
    if "--validate" in sys.argv: validate(); sys.exit()
    B,F=load("base"),load("fix")
    print(f"{'id':<6} {'check':<40} {'base':<7} {'fix':<7} p")
    tb=tf=nb=nf=0
    for hid,(lbl,fn) in CHECKS.items():
        rb,rf=B.get(hid,[]),F.get(hid,[])
        ob,of=sum(fn(r) for r in rb),sum(fn(r) for r in rf)
        tb+=ob;nb+=len(rb);tf+=of;nf+=len(rf)
        p=fisher(ob,len(rb)-ob,of,len(rf)-of) if rb and rf else float("nan")
        flag="  <== FIXED" if rb and rf and p<0.05 and of/len(rf)>ob/len(rb) else ("  <== REGRESSED" if rb and rf and p<0.05 and of/len(rf)<ob/len(rb) else "")
        print(f"{hid:<6} {lbl:<40} {ob}/{len(rb):<5} {of}/{len(rf):<5} {p:.4f}{flag}")
    print("-"*72)
    if nb and nf: print(f"{'TOTAL':<47} {tb}/{nb:<5} {tf}/{nf:<5} {fisher(tb,nb-tb,tf,nf-tf):.5f}")
    for tag,R in (("base",B),("fix",F)):
        allr=[r for v in R.values() for r in v]
        if allr: print(f"  {tag}: real backend data spoken {sum(bool(FIX.search(A(r))) for r in allr)}/{len(allr)} | invented provider/facility {sum(bool(INVENT.search(A(r))) for r in allr)}/{len(allr)} | variable-name echo {sum(bool(VARNAME.search(A(r))) for r in allr)}/{len(allr)}")
