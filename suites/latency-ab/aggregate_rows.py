#!/usr/bin/env python3
"""Aggregate LATENCY_ROWS_PATH jsonl files into the A/B latency budget table.

Usage: python3 aggregate_rows.py rows/tasksflow-<stamp>.jsonl rows/v2flow-<stamp>.jsonl
"""
import json
import sys
from collections import defaultdict


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def load(path, kind="llm"):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return [r for r in rows if r.get("kind") == kind]


def report_turns(name, turns):
    """kind=='turn' rows from the sim engine: agent-side wall time per logical
    turn. Silent turns (spoke=False) are what a caller hears as extra dead air
    before the next spoken reply — merge each silent stretch into the next
    spoken turn."""
    if not turns:
        return
    merged, carry, silent = [], 0.0, 0
    for t in turns:
        felt = t.get("felt_s") or 0
        if not t.get("spoke") and not t.get("ended"):
            carry += felt
            silent += 1
            continue
        merged.append(carry + felt)
        carry = 0.0
    print(f"TURN rows ({name}): spoken-turn felt p50 {pct(merged,.5):.3f} / p90 {pct(merged,.9):.3f} s "
          f"(spoken={len(merged)}, silent-merged={silent}, raw-turns={len(turns)})")


def report(name, rows):
    print(f"\n### {name} — {len(rows)} LLM requests")
    if not rows:
        return
    ttfts = [r["ttft"] for r in rows if r.get("ttft") and r["ttft"] > 0]
    prompts = [r["prompt_tokens"] for r in rows if r.get("prompt_tokens")]
    cached = sum(r.get("cached_tokens") or 0 for r in rows)
    ptotal = sum(r.get("prompt_tokens") or 0 for r in rows)
    cache_hit_reqs = sum(1 for r in rows if (r.get("cached_tokens") or 0) > 0)
    print(f"TTFT p50/p90/p99: {pct(ttfts,.5):.3f} / {pct(ttfts,.9):.3f} / {pct(ttfts,.99):.3f} s  (n={len(ttfts)})")
    print(f"prompt tokens p50/p90: {pct(prompts,.5):.0f} / {pct(prompts,.9):.0f}")
    print(f"cached-token share: {cached}/{ptotal} = {cached/ptotal*100 if ptotal else 0:.1f}%  | reqs with any cache hit: {cache_hit_reqs}/{len(rows)} = {cache_hit_reqs/len(rows)*100:.1f}%")
    # Per-turn felt latency: group pipeline requests by speech_id; the caller
    # waits through every request in the speech serially — full duration of
    # each non-final request plus TTFT of the final (speaking) one.
    speeches = defaultdict(list)
    for r in rows:
        if r.get("speech_id"):
            speeches[r["speech_id"]].append(r)
    felts, multi = [], 0
    for sid, rs in speeches.items():
        rs = sorted(rs, key=lambda r: r.get("t_start") or 0)
        felt = sum(r.get("duration") or 0 for r in rs[:-1]) + (rs[-1].get("ttft") or 0)
        if felt > 0:
            felts.append(felt)
        if len(rs) > 1:
            multi += 1
    if felts:
        print(f"FELT per-turn (speech-grouped): p50 {pct(felts,.5):.3f} / p90 {pct(felts,.9):.3f} s  "
              f"(turns={len(felts)}, multi-request turns={multi}, reqs/turn={sum(len(v) for v in speeches.values())/len(speeches):.2f})")
    direct = [r for r in rows if not r.get("speech_id")]
    if direct:
        print(f"direct (no speech_id — pick/scribe/etc): {len(direct)} reqs, "
              f"sum-duration p50 {pct([r.get('duration') or 0 for r in direct],.5):.3f}s")

    by = defaultdict(list)
    for r in rows:
        by[r.get("purpose") or "?"].append(r)
    print(f"{'purpose':28s} {'n':>5s} {'ttft_p50':>9s} {'ttft_p90':>9s} {'prompt_p50':>10s} {'cached%':>8s}")
    for purpose, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        t = [r["ttft"] for r in rs if r.get("ttft") and r["ttft"] > 0]
        pr = [r["prompt_tokens"] for r in rs if r.get("prompt_tokens")]
        ca = sum(r.get("cached_tokens") or 0 for r in rs)
        pt = sum(r.get("prompt_tokens") or 0 for r in rs)
        print(f"{purpose:28s} {len(rs):5d} {pct(t,.5):9.3f} {pct(t,.9):9.3f} {pct(pr,.5):10.0f} {ca/pt*100 if pt else 0:7.1f}%")


def main():
    sets = {p: load(p) for p in sys.argv[1:]}
    for path, rows in sets.items():
        report(path.split("/")[-1], rows)
        report_turns(path.split("/")[-1], load(path, kind="turn"))
    if len(sets) == 2:
        (n1, r1), (n2, r2) = sets.items()
        t1 = [r["ttft"] for r in r1 if r.get("ttft") and r["ttft"] > 0]
        t2 = [r["ttft"] for r in r2 if r.get("ttft") and r["ttft"] > 0]
        print(f"\n### DELTA ({n1.split('/')[-1]} - {n2.split('/')[-1]})")
        print(f"TTFT p50: {pct(t1,.5)-pct(t2,.5):+.3f}s   p90: {pct(t1,.9)-pct(t2,.9):+.3f}s")
        print(f"reqs: {len(r1)} vs {len(r2)}  ({len(r1)/max(len(r2),1):.2f}x)")


if __name__ == "__main__":
    main()
