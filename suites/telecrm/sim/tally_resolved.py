"""Rate of speaking the RESOLVED calendar date after a relative day ('tomorrow', weekday)."""
import json,glob,re,sys
REL=re.compile(r"\btomorrow\b|next monday|\bsaturday\b|\btuesday\b",re.I)
RESOLVED=re.compile(r"(twenty|thirty|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\b.{0,25}(august|september)|\b(august|september)\b.{0,25}\d{1,2}|(29th|30th|31st|1st|2nd|3rd|4th|5th)",re.I)
for ws in sys.argv[1:]:
    hits=n=0; ex=[]
    for p in sorted(glob.glob(f"{ws}/reports/*.json")):
        for r in json.load(open(p)):
            seq=[]
            for x in r["turns"]:
                u=(x.get("user") or "").strip(); a=(x.get("agent") or "").strip()
                if u: seq.append(("C",u))
                if a: seq.append(("A",a))
            gi=next((i for i,(s,t) in enumerate(seq) if s=="C" and REL.search(t) and re.search(r"\bat\b|morning|afternoon|evening|noon",t,re.I)),None)
            if gi is None: continue
            n+=1
            after=" ".join(t for s,t in seq[gi+1:gi+4] if s=="A")
            ok=bool(RESOLVED.search(after)); hits+=ok
            if not ok and len(ex)<2: ex.append(after[:90])
    print(f"{ws.split('/')[-1]:<48} resolved-date spoken: {hits}/{n}")
    for e in ex: print("    MISS:",e)
