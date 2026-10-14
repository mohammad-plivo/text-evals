#!/usr/bin/env python3
"""Score the reply to a caller turn that carries a terminal signal AND a question.

Scores the criterion the Hunter judge actually applies: does the agent's FIRST reply
after the combined turn address the question? Not the closing turn — that distinction
matters and an earlier version of this script got it wrong. Where the unit exits
immediately (screening DNC) the two coincide; where the walk survives the turn
(collector hostile) the reply can answer via `answer_side_question` and close cleanly
several turns later, which a last-turn scorer reports as a failure the judge would pass.

Both the scored reply and the eventual final turn are printed, so the exit path stays
visible — the local hostile repro reaches a different close node than the Hunter call.

Usage:  python3 tally_close.py <report.json> [more.json ...]
"""
import json
import re
import sys

# Per case: the question the caller asked in the same breath as the terminal signal,
# and the tokens that count as the close having addressed it. Tokens are deliberately
# GENEROUS — the aim is to avoid crediting the agent falsely, so a loose "addressed"
# set biases against finding a defect. Anything it still marks unaddressed is unaddressed.
CASES = {
    "p0-dnc-with-question-in-same-breath": {
        "trigger": ("who gave you my number", "remove my number"),
        "question": "who gave you my number?",
        "addressed": ("gave", "source", "where", "obtained", "got your", "website",
                      "form", "enquiry", "inquiry", "signed up", "share", "disclose",
                      "cannot say", "can't say", "provide that"),
    },
    "p0-dnc-CAPFIX": {
        "trigger": ("who gave you my number", "remove my number"),
        "question": "who gave you my number? [arm C: DNC Close word cap reworded]",
        "addressed": ("gave", "source", "where", "obtained", "got your", "website",
                      "form", "enquiry", "inquiry", "signed up", "share", "disclose",
                      "cannot say", "can't say", "provide that"),
    },
    "p0-hostile-with-question": {
        "trigger": ("what is this call even about", "shameless"),
        "question": "what is this call even about anyway?",
        "addressed": ("about", "regarding", "reason", "purpose", "calling", "telecrm",
                      "interest", "qualification", "why i"),
    },
    "p0-hostile-EXITS": {
        "trigger": ("what is this call even about", "parasites"),
        "question": "what is this call even about anyway? [variant: forces the Hostile exit]",
        "addressed": ("about", "regarding", "reason", "purpose", "calling", "telecrm",
                      "interest", "qualification", "why i"),
    },
    "p1-wrong-number-stranger-probes": {
        "trigger": ("what did this person sign up for", "what's this about", "wrong number"),
        "question": "what's this about? what did this person sign up for?",
        "addressed": ("intended", "only discuss", "discuss details", "cannot share",
                      "can't share", "not able to share", "with the person",
                      "account holder"),
    },
}


#: Promised/completed action — forbidden across this suite ("never claims a completed or
#: promised action"). Arm D answers the question but volunteered these in 6/10 wrong-number
#: runs, so the scorer has to see them or the fix trades one criterion for another.
PROMISE = ("i'll ", "i will ", "we'll ", "we will ", "will be updated", "update our records",
           "update my records", "have been removed", "will be removed", "someone will",
           "i've noted", "noted that", "taken down")


def promises_action(text):
    low = text.lower()
    return any(tok in low for tok in PROMISE)


def first_reply_after_trigger(run, trigger_tokens):
    """The agent turn the judge actually scores: the FIRST reply after the caller's
    combined terminal+question turn — not the closing turn.

    Scoring the last turn was wrong and inverted one result: in the hostile case the
    walk answers via `answer_side_question` on the immediate reply and only closes
    several turns later, so a last-turn scorer reports a failure the judge would pass.
    """
    turns = run.get("turns") or []
    hit = None
    for i, t in enumerate(turns):
        u = (t.get("user") or "").lower()
        if u and any(tok in u for tok in trigger_tokens):
            hit = i
            break
    if hit is None:
        return None, None  # persona never delivered the line — unscorable, not a pass
    # the agent text on the trigger turn itself is the reply to it (same turn record),
    # falling through to the next turn that carries agent text.
    for t in turns[hit:]:
        if (t.get("agent") or "").strip():
            return t["agent"].strip(), [tc.get("name") for tc in (t.get("tool_calls") or [])]
    return "", []


def last_agent_turn(run):
    for t in reversed(run.get("turns") or []):
        if (t.get("agent") or "").strip():
            return t["agent"].strip()
    return ""


def main(paths):
    rows = []
    for p in paths:
        for run in json.load(open(p)):
            name = run.get("scenario") or run.get("name") or ""
            case = CASES.get(name)
            if case is None:
                print(f"  !! no scoring rule for scenario {name!r} — skipped", file=sys.stderr)
                continue
            close, tools = first_reply_after_trigger(run, case["trigger"])
            if close is None:
                rows.append({"case": name, "close": "<persona never delivered the trigger line>",
                             "addressed": None, "tools": [], "ended": bool(run.get("ended")),
                             "words": 0, "final": last_agent_turn(run)})
                continue
            low = close.lower()
            rows.append({
                "case": name,
                "close": close,
                "addressed": any(tok in low for tok in case["addressed"]),
                "tools": tools or [],
                "ended": bool(run.get("ended")),
                "words": len(re.findall(r"\w+", close)),
                "promises": promises_action(close),
                "final": last_agent_turn(run),
            })

    by = {}
    for r in rows:
        by.setdefault(r["case"], []).append(r)

    for case, rs in sorted(by.items()):
        scorable = [r for r in rs if r["addressed"] is not None]
        hit = sum(r["addressed"] for r in scorable)
        print("=" * 96)
        print(f"{case}   n={len(rs)}")
        print(f"  caller asked : {CASES[case]['question']}")
        print(f"  ADDRESSED IN THE FIRST REPLY : {hit}/{len(scorable)}"
              + (f"   ({len(rs)-len(scorable)} unscorable: persona never said it)" if len(scorable)!=len(rs) else ""))
        pr = sum(1 for r in rs if r.get("promises"))
        print(f"  PROMISED-ACTION LEAK : {pr}/{len(rs)}" + ("   <-- regression" if pr else ""))
        print(f"  mean first-reply length {sum(r['words'] for r in rs)/max(1,len(rs)):.1f} words")
        for i, r in enumerate(rs, 1):
            mark = "  n/a  " if r["addressed"] is None else ("ADDRESSED" if r["addressed"] else " dropped ")
            print(f"   {i:>2} [{mark}] {r['close'][:140]}")
            if r["tools"]:
                print(f"        tools: {r['tools']}")
            print(f"        final: {r['final'][:110]}")

    sc = [r for r in rows if r["addressed"] is not None]
    print("=" * 96)
    print(f"TOTAL ADDRESSED: {sum(r['addressed'] for r in sc)}/{len(sc)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
