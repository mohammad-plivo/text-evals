"""Compare two arms of TeleCRM sim reports, per scenario and per pattern, with Fisher exact.

    python ab.py <before-dir-or-files> -- <after-dir-or-files>

Fisher is computed here rather than imported: scipy is not a dependency of this repo and adding
one to read a 2x2 table would be absurd.
"""
import glob
import json
import math
import os
import sys
from collections import defaultdict

import tally


def _fisher(a, b, c, d):
    """Two-sided Fisher exact on [[a,b],[c,d]]."""
    def logC(n, k):
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    def p(x):
        return math.exp(logC(r1, x) + logC(r2, c1 - x) - logC(n, c1))
    obs = p(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= obs * (1 + 1e-9)))


def score(paths):
    per, pat = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for p in paths:
        for r in json.load(open(p)):
            s = r["scenario"]
            if s in tally.CHECKS:
                pt, fn = tally.CHECKS[s]
                ok, _ = fn(r)
                if ok is None:
                    continue
            elif s in tally.BY_EXPECT:
                pt, ok = tally.BY_EXPECT[s], not r["failures"]
            else:
                continue
            per[s][0] += bool(ok); per[s][1] += 1
            pat[pt][0] += bool(ok); pat[pt][1] += 1
    return per, pat


def expand(args):
    out = []
    for a in args:
        out.extend(sorted(glob.glob(os.path.join(a, "*.json"))) if os.path.isdir(a) else [a])
    return out


def main(argv):
    i = argv.index("--")
    before, after = score(expand(argv[:i])), score(expand(argv[i + 1:]))
    pb, tb = before
    pa, ta = after
    print("%-46s %-9s %-9s %s" % ("scenario", "before", "after", "p (Fisher)"))
    print("-" * 82)
    for s in sorted(set(pb) | set(pa)):
        ob, nb = pb.get(s, [0, 0]); oa, na = pa.get(s, [0, 0])
        if not nb or not na:
            print("%-46s %-9s %-9s  (arm missing)" % (s, f"{ob}/{nb}", f"{oa}/{na}")); continue
        p = _fisher(ob, nb - ob, oa, na - oa)
        flag = "  <== " + ("IMPROVED" if oa / na > ob / nb else "REGRESSED") if p < 0.05 else ""
        print("%-46s %-9s %-9s %.4f%s" % (s, f"{ob}/{nb}", f"{oa}/{na}", p, flag))
    print("\n%-10s %-9s %-9s %s" % ("PATTERN", "before", "after", "p"))
    print("-" * 46)
    for k in sorted(set(tb) | set(ta)):
        ob, nb = tb.get(k, [0, 0]); oa, na = ta.get(k, [0, 0])
        p = _fisher(ob, nb - ob, oa, na - oa) if nb and na else float("nan")
        print("%-10s %-9s %-9s %.4f" % (k, f"{ob}/{nb}", f"{oa}/{na}", p))
    sb = (sum(v[0] for v in tb.values()), sum(v[1] for v in tb.values()))
    sa = (sum(v[0] for v in ta.values()), sum(v[1] for v in ta.values()))
    print("-" * 46)
    print("%-10s %-9s %-9s %.4f" % ("TOTAL", f"{sb[0]}/{sb[1]}", f"{sa[0]}/{sa[1]}",
                                    _fisher(sb[0], sb[1] - sb[0], sa[0], sa[1] - sa[0])))


if __name__ == "__main__":
    main(sys.argv[1:])
