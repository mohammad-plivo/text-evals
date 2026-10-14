#!/usr/bin/env python3
"""Measure the CLOSING check-word distribution (and opener) on confirmation readback turns,
per task, since a timestamp. Shows whether the agent still defaults to 'right?'.

Usage: python3 _exp/checkword_score.py "<since 'YYYY-MM-DD HH:MM:SS'>" task1 task2 ...
"""
import json, os, re, sys, collections

TX = os.path.join(os.path.dirname(__file__), "..", "cx-skills-subtle",
                  "eval_conversations", "transcripts", "tasks")
CONF = ("right?", "correct?", "yeah?", "that right", "that's the one", "है?", "सही", "correcto",
        "c'est", "है ना", "है?", "okay?", "correcte")

def tail(t):
    s = t.strip().rstrip().lower()
    if not s.endswith("?"):
        return "no-question"
    s2 = s[:-1].rstrip()
    for w, lab in [("right", "right?"), ("correct", "correct?"), ("yeah", "yeah?"),
                   ("that's the one", "that's-the-one?"), ("that right", "that-right?"),
                   ("okay", "okay?"), ("सही", "<lang>"), ("correcto", "<lang>"),
                   ("c'est bien ça", "<lang>"), ("है", "<lang>")]:
        if s2.endswith(w) or s2.endswith(w + ","):
            return lab
    return "no-tag(bare-?)"

def readbacks(task, since):
    fp = os.path.join(TX, f"{task}.jsonl")
    if not os.path.exists(fp):
        return []
    out, seen = [], set()
    for l in open(fp):
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get("run_ts", "") < since:
            continue
        cid = r.get("case_id")
        if cid in seen:
            continue
        a = [(m.get("content") or "").strip().replace("\n", " ")
             for m in r.get("transcript", []) if m.get("role") == "assistant"]
        a = [x for x in a if x]
        rb = [x for x in a[1:] if any(c in x.lower() for c in CONF) and len(x) < 200]
        if rb:
            out.append(rb[0]); seen.add(cid)
    return out

def main():
    since = sys.argv[1]
    tasks = sys.argv[2:]
    for task in tasks:
        rbs = readbacks(task, since)
        if not rbs:
            print(f"\n{task}: no readbacks since {since}")
            continue
        tails = collections.Counter(tail(t) for t in rbs)
        openers = collections.Counter((t.split()[0].strip(",:.¿").lower() if t.split() else "") for t in rbs)
        n = len(rbs)
        top_tail, top_tail_ct = tails.most_common(1)[0]
        print(f"\n=== {task} · {n} readbacks ===")
        print(f"  closing check-word: {dict(tails.most_common())}")
        print(f"    top tail '{top_tail}' = {round(100*top_tail_ct/n)}%   |  distinct tails: {len(tails)}")
        print(f"  openers top-5: {[o for o,_ in openers.most_common(5)]}  (top {round(100*openers.most_common(1)[0][1]/n)}%)")
        for s in rbs[:5]:
            print(f"    · {s[:90]}")

if __name__ == "__main__":
    main()
