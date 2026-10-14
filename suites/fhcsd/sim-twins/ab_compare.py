"""Compare two run_live.py arms twin by twin: judge pass rate, plus two direct transcript metrics that do not
depend on the judge — confirmation questions asked per run, and whether the callback number was spoken after an
out-of-scope ask.  ab_compare.py --base DIR --fix DIR
"""
import argparse
import glob
import json
import os
import re
NUMBER = re.compile(r"6\s*1\s*9\D{0,4}5\s*1\s*5\D{0,4}3\s*9\s*9\s*9")
CONFIRM = re.compile(r"is your booking confirmed|is that booking confirmed|booking confirmed\?|confirm (?:the|your|this) booking|shall i (?:go ahead and )?book", re.I)


def runs(arm_dir):
    board = json.load(open(os.path.join(arm_dir, "board.json")))
    out = {}
    for slug, res in board.items():
        if not res.get("report"):
            out[slug] = []; continue
        reps = json.load(open(res["report"]))
        judged = {j["run"]: j for j in (json.load(open(f)) for f in glob.glob(os.path.join(arm_dir, f"{slug}-run*.judge.json")))}
        rows = []
        for r in reps:
            agent_lines = [ln for t in r["turns"] for ln in (t.get("agent") or "").split("\n") if ln.strip()]
            confirms = sum(1 for ln in agent_lines if CONFIRM.search(ln))
            number = any(NUMBER.search(ln) for ln in agent_lines[:-2])  # not the closing line
            j = judged.get(r["run"], {})
            rows.append({"run": r["run"], "pass": bool(j.get("pass")), "score": j.get("score"),
                         "notmet": [c.get("n") for c in j.get("criteria", []) if not c.get("met")],
                         "confirms": confirms, "number": number,
                         "intent": next((t["intent"] for t in reversed(r["turns"]) if t.get("intent")), "")})
        out[slug] = rows
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--fix", required=True)
    a = ap.parse_args(); base, fix = runs(a.base), runs(a.fix)
    print(f"| twin | base pass | fix pass | base ≥2 confirms | fix ≥2 confirms | base number | fix number | base not met | fix not met |")
    print("|---|---|---|---|---|---|---|---|---|")
    for slug in sorted(set(base) | set(fix)):
        b, f = base.get(slug, []), fix.get(slug, [])
        def frac(rows, key): return f"{sum(1 for r in rows if r[key])}/{len(rows)}"
        def multi(rows): return f"{sum(1 for r in rows if r['confirms'] >= 2)}/{len(rows)}"
        def nm(rows):
            from collections import Counter
            c = Counter(n for r in rows for n in r["notmet"]); return ",".join(f"{k}×{v}" for k, v in sorted(c.items()))
        print(f"| {slug} | {frac(b,'pass')} | {frac(f,'pass')} | {multi(b)} | {multi(f)} | {frac(b,'number')} | {frac(f,'number')} | {nm(b)} | {nm(f)} |")
    tb, tf = [r for v in base.values() for r in v], [r for v in fix.values() for r in v]
    print(f"\ntotal: base {sum(r['pass'] for r in tb)}/{len(tb)} pass, fix {sum(r['pass'] for r in tf)}/{len(tf)} pass; "
          f"double confirmations base {sum(r['confirms']>=2 for r in tb)}, fix {sum(r['confirms']>=2 for r in tf)}")


if __name__ == "__main__":
    main()
