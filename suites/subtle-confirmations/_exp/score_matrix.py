#!/usr/bin/env python3
"""Score the 2x2 temp-vs-prompt matrix on the ACTUAL confirmation/readback turns.

Unlike humanness_score.py (which grabs the last assistant turn, often a closing turn),
this extracts the readback: the first assistant turn AFTER >=1 user turn that carries a
confirm cue, per run. Reports the collapse indicators that answer 'was it temperature?':
  - top-opener share (higher = more collapsed onto one phrasing)
  - distinct openers
  - avg words per confirmation
  - em-dash %, 'alright'-opener %
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
SB = os.path.join(ROOT, "..", "cx-skills-subtle")
TX = os.path.join(SB, "eval_conversations", "transcripts", "tasks")
TASKS = ["choice", "text", "currency"]
CONF = ("right?", "correct?", "correcto", "correcte", "c'est", "sahi", "ठीक", "सही",
        "that right", "is that", "yeah?", "yes?", "क्या यह", "¿es correcto", "¿correcto")

def load_windows():
    wf = os.path.join(ROOT, "windows.txt")
    cells = []
    for ln in open(wf):
        ln = ln.strip()
        if not ln:
            continue
        label, temp, ref, since, until = ln.split("|")
        cells.append(dict(label=label, temp=temp, ref=ref, since=since, until=until))
    return cells

def opener(t):
    w = t.split()
    return w[0].strip(",:.¿").lower() if w else ""

def readback_turns(task, since, until):
    fp = os.path.join(TX, f"{task}.jsonl")
    if not os.path.exists(fp):
        return []
    out = []
    for ln in open(fp):
        if not ln.strip():
            continue
        r = json.loads(ln)
        ts = r.get("run_ts", "")
        if not (since <= ts <= until):
            continue
        asst = [(m.get("content") or "").strip().replace("\n", " ")
                for m in r.get("transcript", []) if m.get("role") == "assistant"]
        asst = [a for a in asst if a]
        rb = [a for a in asst[1:] if any(c in a.lower() for c in CONF)]
        if rb:
            out.append((r.get("case_id", "?"), r.get("passed"), rb[0]))
    return out

def metrics(turns):
    texts = [t for _, _, t in turns]
    n = len(texts)
    if not n:
        return dict(n=0)
    openers = collections.Counter(opener(t) for t in texts)
    top_op, top_ct = openers.most_common(1)[0]
    emdash = sum(1 for t in texts if "—" in t)
    alright = sum(1 for t in texts if opener(t) == "alright")
    words = [len(t.split()) for t in texts]
    passed = sum(1 for _, p, _ in turns if p)
    return dict(
        n=n,
        distinct_openers=len(openers),
        top_opener=f"{top_op or '(value)'}",
        top_opener_share=round(100 * top_ct / n),
        alright_pct=round(100 * alright / n),
        emdash_pct=round(100 * emdash / n),
        avg_words=round(sum(words) / n, 1),
        passed=passed,
        top5=[o or "(value)" for o, _ in openers.most_common(5)],
    )

def main():
    cells = load_windows()
    print(f"{'CELL':6} {'temp':4} {'task':8} {'n':>3} {'topOpen%':>8} {'distinct':>8} {'avgW':>5} {'alright%':>8} {'em%':>4} {'pass':>6}  top-opener / samples")
    print("-" * 132)
    agg = {}
    for c in cells:
        for task in TASKS:
            turns = readback_turns(task, c["since"], c["until"])
            m = metrics(turns)
            key = (c["label"], task)
            agg[key] = m
            if m.get("n"):
                print(f"{c['label']:6} {c['temp']:4} {task:8} {m['n']:>3} {m['top_opener_share']:>7}% {m['distinct_openers']:>8} {m['avg_words']:>5} {m['alright_pct']:>7}% {m['emdash_pct']:>3}% {m['passed']:>3}/{m['n']:<2}  {m['top_opener']} | " + " · ".join(s[:1] for s in []))
            else:
                print(f"{c['label']:6} {c['temp']:4} {task:8}   0  (no readback turns in window)")
        print()
    # Aggregate collapse indicator across tasks per cell (mean top-opener share, weighted by n)
    print("=== COLLAPSE SUMMARY (mean top-opener share across tasks; higher = more robotic/locked) ===")
    for label in ["W03", "W07", "C03", "C07"]:
        ns = [agg.get((label, t), {}).get("n", 0) for t in TASKS]
        shares = [agg.get((label, t), {}).get("top_opener_share", 0) for t in TASKS]
        alrights = [agg.get((label, t), {}).get("alright_pct", 0) for t in TASKS]
        tot = sum(ns)
        if tot:
            w_share = round(sum(s * n for s, n in zip(shares, ns)) / tot)
            w_alr = round(sum(a * n for a, n in zip(alrights, ns)) / tot)
            print(f"  {label}: mean top-opener share = {w_share}%   |  'alright' opener = {w_alr}%   (n={tot})")
    print()
    print("Read: TEMPERATURE effect = W03->W07 and C03->C07 (same prompt).")
    print("      PROMPT effect      = W03->C03 and W07->C07 (same temp).")

if __name__ == "__main__":
    main()
