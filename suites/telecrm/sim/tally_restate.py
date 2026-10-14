"""Count runs where the callback time is spoken in >=2 agent turns after the caller gives it."""
import json,glob,re,sys
TIME=re.compile(r"\b(tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week)\b|\b\d{1,2}\s*(am|pm|o.?clock)|at (three|four|five|six|seven|eight|nine|ten|eleven|noon)|\b(eleven|noon|morning|afternoon|evening)\b",re.I)
GIVE=re.compile(r"tomorrow|next monday|saturday|tuesday|around (four|4)|at (eleven|11|three|3|four|4|five|5)",re.I)
def runs(ws):
    out=[]
    for p in sorted(glob.glob(f"{ws}/reports/*.json")):
        out.extend(json.load(open(p)))
    return out
for ws in sys.argv[1:]:
    rows=[]
    for r in runs(ws):
        turns=[]
        for x in r["turns"]:
            u=(x.get("user") or "").strip(); a=(x.get("agent") or "").strip()
            if u: turns.append(("C",u))
            if a: turns.append(("A",a))
        gi=next((i for i,(s,t) in enumerate(turns) if s=="C" and GIVE.search(t)),None)
        if gi is None: rows.append(None); continue
        speaks=[t for s,t in turns[gi+1:] if s=="A" and TIME.search(t)]
        rows.append(len(speaks))
    n=len([r for r in rows if r is not None])
    multi=len([r for r in rows if r is not None and r>=2])
    print(f"{ws.split('/')[-1]:<46} gave-time n={n:<3} restated>=2 turns: {multi}/{n}   counts={[r for r in rows if r is not None]}")
