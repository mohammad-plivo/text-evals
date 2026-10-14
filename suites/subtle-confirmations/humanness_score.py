#!/usr/bin/env python3
"""Offline humanness linter for the agent's confirmation turns.

Scores the AUDIBLE AI-tells (not written ones) on a task's eval transcripts:
  - em-dash rate         (the tell Mohammad flagged; inaudible but signals the cadence + our exemplars)
  - canned-ack rate      ("got it", "perfect", "wonderful", ... — the #1 voice tell)
  - ack-opener repetition(distinct openers + share of the single most-common opener)
  - contraction usage    (human) vs stiff expanded forms (robotic)

Usage:  python3 humanness_score.py <task> [--since YYYYMMDD_HHMMSS] [--label NAME]
Analyzes the LAST spoken assistant turn per case (the confirmation), latest run per case in the window.
NOT in the live path — offline measurement only.
"""
import json, sys, re, os, collections

DIR = os.path.dirname(os.path.abspath(__file__))
task = sys.argv[1]
since = sys.argv[sys.argv.index('--since') + 1] if '--since' in sys.argv else None
label = sys.argv[sys.argv.index('--label') + 1] if '--label' in sys.argv else (since or 'all')
store = os.path.join(DIR, 'cx-skills-subtle', 'eval_conversations', 'transcripts', 'tasks', f'{task}.jsonl')

CANNED = ['got it', 'perfect', 'wonderful', 'absolutely', 'certainly', 'of course',
          'no problem', 'i understand', 'great', 'excellent', 'fantastic', 'awesome']
CONTRACTIONS = re.compile(r"\b(i'll|you're|that's|don't|it's|we'll|i'm|can't|we're|you'll|isn't|aren't|won't|let's|here's|there's|what's|they're|you've|i've|didn't|doesn't|wouldn't|shouldn't)\b", re.I)
STIFF = re.compile(r"\b(i will|you are|that is|do not|it is|we will|i am|cannot|we are|you will|is not|are not|will not|let us|i have|you have|did not|does not)\b", re.I)

def ts_of(run_id):
    m = re.search(r'_(\d{8}_\d{6})_', run_id or '')
    return m.group(1) if m else ''

recs = [json.loads(l) for l in open(store) if l.strip()]
latest = {}
for r in recs:
    rid = r.get('run_id', '')
    t = ts_of(rid)
    if since and t and t.replace('_', '') < since.replace('_', ''):
        continue
    if not t:
        continue
    latest[r['case_id']] = r  # append order → last wins = latest in window

confs = []
for r in latest.values():
    asst = [(t.get('content') or '').strip() for t in r.get('transcript', [])
            if t.get('role') == 'assistant' and (t.get('content') or '').strip()]
    if asst:
        confs.append(asst[-1])  # last spoken turn = the confirmation

N = len(confs) or 1
emdash = sum('—' in c or '–' in c for c in confs)
canned = sum(any(k in c.lower() for k in CANNED) for c in confs)
gotit = sum('got it' in c.lower() for c in confs)
contr = sum(bool(CONTRACTIONS.search(c)) for c in confs)
stiff = sum(bool(STIFF.search(c)) for c in confs)
openers = collections.Counter(re.sub(r'[^a-z]', '', c.split()[0].lower()) for c in confs if c.split())
top_op, top_n = (openers.most_common(1)[0] if openers else ('', 0))

def pct(x): return f'{x}/{len(confs)} ({100*x//N}%)'
print(f'=== humanness [{task}] · window={label} · {len(confs)} confirmation turns ===')
print(f'  em-dash              : {pct(emdash)}')
print(f'  canned ack (any)     : {pct(canned)}')
print(f'    of which "got it"  : {pct(gotit)}')
print(f'  contractions present : {pct(contr)}')
print(f'  stiff expanded forms : {pct(stiff)}')
print(f'  opener diversity     : {len(openers)} distinct openers over {len(confs)} turns; '
      f'top opener "{top_op}" = {top_n}/{len(confs)} ({100*top_n//N}%)')
print(f'  top-5 openers        : {[w for w,_ in openers.most_common(5)]}')
