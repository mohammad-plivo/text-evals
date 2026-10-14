"""Score the TeleCRM collector patterns across simulation reports.

The four patterns from Hunter run a2e04e7d are OMISSIONS as often as they are wrong words, and an
omission is not expressible as a scenario `expect`. So the scenarios carry only the assertions that
are mechanically safe (pattern A's banned code list, and the intent assertions) and everything else
is scored here, off the transcript, position-independently.

    python tally.py <report.json> [report.json ...]
"""
import json
import re
import sys
from collections import defaultdict

CODES = re.compile(r"\bupto ?2\b|\bup to two\b|\b3-5\b|\bthree to five\b|\b6-10\b|\bsix to ten\b"
                   r"|\b11-20\b|\beleven to twenty\b|\b21-50\b|\b51-100\b|\b100 ?plus\b"
                   r"|\bmore than one hundred\b", re.I)
BARE_ACK = re.compile(r"^(understood|okay|ok|got it|alright|sure|thanks?)[.!]*$", re.I)

def _reply_to(turns, needle):
    """The agent's reply to the first caller turn containing `needle`."""
    for t in turns:
        if needle.lower() in (t.get("user") or "").lower():
            return t.get("agent") or ""
    return None

def _addressed(reply, tokens):
    return any(tok in (reply or "").lower() for tok in tokens)

# scenario slug -> (pattern, checker(record) -> (ok, evidence))
def chk_codes(r):
    for t in r["turns"]:
        m = CODES.search(t.get("agent") or "")
        if m:
            return False, "spoke the code %r: %s" % (m.group(0), (t["agent"] or "")[:90])
    return True, ""

def _side_question(needle, tokens):
    def chk(r):
        reply = _reply_to(r["turns"], needle)
        if reply is None:
            return None, "caller never asked it (script drifted)"
        if BARE_ACK.match(reply.strip()):
            return False, "bare acknowledgement: %r" % reply.strip()
        if not _addressed(reply, tokens):
            return False, "did not address it: %s" % reply[:90]
        return True, reply[:70]
    return chk

def chk_pricing(r):
    reply = _reply_to(r["turns"], "what's the pricing")
    if reply is None:
        return None, "caller never asked it (script drifted)"
    low = reply.lower()
    invented = ("analyst will help you by" in low or "pricing is" in low
                or "per month" in low or "costs" in low)
    deferred = any(k in low for k in ("can't", "cannot", "not able", "don't have",
                                      "do not have", "record", "someone from"))
    if invented:
        return False, "answered instead of deferring: %s" % reply[:90]
    return (True, reply[:70]) if deferred else (False, "neither deferred nor answered: %s" % reply[:90])

def chk_missing_date(r):
    reply = _reply_to(r["turns"], "five in the evening")
    if reply is None:
        return None, "caller never said it (script drifted)"
    if _addressed(reply, ("day", "date", "which day", "when would", "tomorrow")):
        return True, reply[:70]
    return False, "never asked for the missing day: %s" % reply[:90]

CHECKS = {
    "a1-team-size-codes-not-spoken": ("A", chk_codes),
    "a2-two-person-team-no-code-echo": ("A", chk_codes),
    "a3-upto-two-no-code-echo": ("A", chk_codes),
    "a4-below-three-no-code-echo": ("A", chk_codes),
    "b1-otp-question-is-answered": ("B", _side_question("otp", ("otp", "card", "no need", "not need", "don't need", "won't need", "never ask"))),
    "b2-pricing-question-is-deferred": ("B", chk_pricing),
    "b3-gst-out-of-scope-redirect": ("B", _side_question("gst", ("gst", "tax", "filing", "can't help", "cannot help", "not something"))),
    "b4-revenue-pushback-is-answered": ("B", _side_question("revenue", ("revenue", "optional", "compulsory", "not required", "skip", "no need"))),
    "b6-wrapup-masking-a-question": ("B", _side_question("will someone actually call me", ("call", "time", "record", "yes", "someone"))),
    "c1-time-without-a-date-is-incomplete": ("C", chk_missing_date),
    # D-005 discriminator: same question as b3, arriving alone instead of bundled with a field answer.
    "b7-out-of-scope-question-alone": ("B", _side_question("gst", ("gst", "tax", "filing", "can't help", "cannot help", "not something"))),
}
# scenarios whose whole assertion is the scenario's own expect block
BY_EXPECT = {"b5-hostile-with-question-exits-hostile": "B",
             "c2-complete-callback-is-captured": "C",
             "c3-consent-without-a-time-is-not-a-callback": "C",
             "d1-refused-field-is-not-re-asked": "D"}

def main(paths):
    per = defaultdict(lambda: [0, 0])          # scenario -> [ok, total]
    pat = defaultdict(lambda: [0, 0])          # pattern  -> [ok, total]
    ev = defaultdict(list)
    for p in paths:
        for r in json.load(open(p)):
            s = r["scenario"]
            if s in CHECKS:
                p_, fn = CHECKS[s]
                ok, why = fn(r)
                if ok is None:
                    continue                    # unevaluable, do not score
            elif s in BY_EXPECT:
                p_, ok, why = BY_EXPECT[s], not r["failures"], "; ".join(r["failures"])[:90]
            else:
                continue
            per[s][0] += bool(ok); per[s][1] += 1
            pat[p_][0] += bool(ok); pat[p_][1] += 1
            if not ok and len(ev[s]) < 2:
                ev[s].append(why)
    print("%-46s %-8s %s" % ("scenario", "pattern", "passed"))
    print("-" * 78)
    for s in sorted(per):
        p_ = (CHECKS.get(s) or (BY_EXPECT.get(s),))[0]
        ok, tot = per[s]
        print("%-46s %-8s %d/%d" % (s, p_, ok, tot))
        for e in ev[s]:
            print("      %s" % e)
    print("\n%-10s %s" % ("PATTERN", "passed"))
    print("-" * 30)
    for p_ in sorted(pat):
        ok, tot = pat[p_]
        print("%-10s %d/%d" % (p_, ok, tot))
    tot_ok = sum(v[0] for v in pat.values()); tot_n = sum(v[1] for v in pat.values())
    print("-" * 30)
    print("%-10s %d/%d" % ("TOTAL", tot_ok, tot_n))

if __name__ == "__main__":
    main(sys.argv[1:])
