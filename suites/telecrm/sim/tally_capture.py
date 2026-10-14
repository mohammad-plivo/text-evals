"""Cross-field capture: update_text/update_choice arguments containing a concrete day+time."""
import json,glob,re,sys
DAY=re.compile(r"\btomorrow\b|\btoday\b|monday|tuesday|wednesday|thursday|friday|saturday|sunday",re.I)
TIME=re.compile(r"\d{1,2}\s*(am|pm)|noon|morning|afternoon|evening|o.?clock|\bat (one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",re.I)
for ws in sys.argv[1:]:
    n=cap=0; ex=[]
    for p in sorted(glob.glob(f"{ws}/reports/*.json")):
        for r in json.load(open(p)):
            n+=1; hit=None
            for x in r["turns"]:
                for tc in (x.get("tool_calls") or []):
                    if tc["name"] in ("update_text","update_choice"):
                        try: v=json.loads(tc.get("arguments") or "{}").get("value","")
                        except: v=""
                        if DAY.search(v) and TIME.search(v): hit=v
            if hit: cap+=1; len(ex)<2 and ex.append(hit[:70])
    print(f"{ws.split('/')[-1]:<46} day+time captured by a TEXT tool: {cap}/{n}")
    for e in ex: print("    CAP:",e)
