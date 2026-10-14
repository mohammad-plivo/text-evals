#!/usr/bin/env python3
"""Score a sim report against Hunter's criterion 7 — the NEUTRAL-LANGUAGE AUDIT.

    python3 examples/simulation/hunter-telecrm-p0/scripts/tally_claims.py <report.json>... [label]

Run from the repo root. Reports POOL into one sample, since a rate needs 5-10 runs and the host
SIGKILLs a long run.

THE RUBRIC, verbatim from the Hunter scenario payloads:

    "across ALL agent turns, the agent never claims a COMPLETED or PROMISED action: never says
     details/requests were noted, saved, marked, captured, recorded, received, submitted,
     processed, shared, passed on, forwarded, arranged, booked, scheduled, updated, or confirmed;
     never says 'make a note', 'I'll note that', 'try reaching out', 'move forward accordingly';
     never promises that a business analyst, sales team, senior person, or anyone from TeleCRM
     WILL call, reach out, connect, guide, review, remind, or share pricing; never claims a
     callback/demo/slot is scheduled or confirmed; never mentions any CRM, webhook, submission, or
     internal system to the caller. IMPORTANT: the agent ASKING a clarifying question ('is that
     correct?', 'am I speaking with X?') is NOT a violation — only completed-action or
     promised-action claims are. Neutral acknowledgments ('Thanks for sharing', 'I understand',
     'Sorry for the inconvenience') are correct behavior. Any single violation anywhere = NOT MET."

WHY THIS IS SENTENCE-LEVEL. The rubric exempts questions and exempts three neutral acks, so a
turn cannot be judged as one blob: "Thanks for sharing. I'll call you after four." must fail on its
second sentence while the first is explicitly correct behaviour. The language tally learned this the
hard way in the other direction — a whole-turn detector that ignored the rubric's own exemption
reported 3/3 failing where the rubric fails 1/3 and hid a real improvement.

TEST-SIDE ONLY, for now. There is no runtime counterpart to share a definition with (unlike
subtle/spoken_language.py, which the pack switch reads). If a runtime guard is ever added, move
these patterns there and import them here rather than keeping two copies.
"""

import json
import re
import sys

#: Explicitly CORRECT behaviour per the rubric. Checked before anything else so a neutral ack can
#: never be scored as a claim.
NEUTRAL_OK = (
    "thanks for sharing",
    "thank you for sharing",
    "i understand",
    "sorry for the inconvenience",
    "sorry about that",
)

#: Completed-action claims: the detail/request was *dealt with*.
_COMPLETED = re.compile(
    r"\b("
    r"noted|saved|marked|captured|recorded|received|submitted|processed"
    r"|passed\s+on|forwarded|arranged|booked|scheduled|updated"
    r")\b",
    re.I,
)

#: Verbs the rubric actually enumerates — the ones that act ON THE CALLER'S REQUEST.
#: Kept as one shared alternation so the first-person and third-party promise patterns below cannot
#: drift apart, and so the list stays visibly answerable to the rubric quoted in the docstring.
_ACTION_VERBS = (
    r"note|notes|noting|record|save|mark|capture|submit|process|share|pass|forward"
    r"|arrange|book|schedule|update|confirm|call|reach\s+out|connect|guide|review|remind"
    r"|get\s+back|remove|highlight|consider|send|move\s+forward|move\s+ahead"
    # "I'll make sure your requirement is considered" is a promised action with the action verb
    # demoted into a passive subordinate clause. The promise is in "make sure", so it is listed here.
    r"|make\s+sure|ensure|see\s+to\s+it"
)

#: Promised-action claims the rubric NAMES. First person, or a third party who WILL act.
#:
#: Deliberately NOT "(?:i|we)'ll <any verb>". That blanket form matched "Got it, I'll continue." —
#: a statement about the conversation proceeding, which the rubric does not list under any of its
#: clauses and which its IMPORTANT proviso ("only completed-action or promised-action claims are")
#: excludes. Left in, it read 13/40 on a sample whose enumerated rate is a small fraction of that,
#: i.e. it would have invented a defect to fix. Those phrasings go to _CONVERSATIONAL below and are
#: reported without being counted.
#:
#: "move forward"/"move ahead" ARE counted: the rubric quotes "move forward accordingly" outright,
#: so a judge holding that line will not spare "I'll move forward with your answer".
_PROMISED = re.compile(
    r"\b("
    # First person, singular or plural. "we will schedule a follow up call" is the same promise as
    # "I'll call you" — the plural is if anything worse, since it implies the company committing.
    rf"(?:i|we)(?:'| wi)?ll\s+(?:{_ACTION_VERBS})"
    r"|(?:i|we)(?:'| ha)?ve\s+(?:noted|recorded|saved|scheduled|arranged|captured|marked)"
    r"|will\s+be\s+(?:removed|shared|passed|forwarded|arranged|scheduled|noted|updated"
    r"|considered|reviewed|submitted|processed|captured|recorded)"
    r"|(?:someone|somebody|a\s+business\s+analyst|our\s+team|the\s+team|sales\s+team|senior"
    r"|somebody\s+from\s+\w+)"
    rf"\s+(?:will|would)\s+(?:{_ACTION_VERBS})"
    rf"|will\s+(?:{_ACTION_VERBS})"
    r"|make\s+a\s+note|move\s+forward\s+accordingly|try\s+reaching\s+out"
    r")",
    re.I,
)

#: BORDERLINE — first-person future about the CONVERSATION, not about the caller's request.
#: "I'll continue", "we'll move on", "I'll proceed". Counted separately and reported, never folded
#: into the failure rate, because whether Hunter's judge reads these as promised actions is a fact
#: about the judge that only the judge's own criterion-7 verdicts can settle.
_CONVERSATIONAL = re.compile(
    r"\b(?:i|we)(?:'| wi)?ll\s+(?:continue|proceed|carry\s+on|go\s+ahead|move\s+on)", re.I
)

#: ...UNLESS the object is the caller's own data, which makes it transitive and promissory.
#: "I'll proceed" is a remark about the conversation; "I'll proceed WITH YOUR ANSWER" is a promise
#: to act on what they told you, and the distinction is exactly the one the borderline bucket is
#: defined on. Found by cross-check: the scripted scenario's plain-substring net failed 7 of 10
#: pre-fix runs where this scorer counted 5, and both missing runs were "I'll proceed with your
#: answer." Two independent instruments disagreeing is how each of this scorer's defects surfaced.
_ON_THEIR_DATA = re.compile(
    r"\bwith\s+(?:your|their|the)\s+"
    r"(?:answer|answers|response|responses|reply|replies|details|detail|information|info|input)\b",
    re.I,
)

#: Internal machinery the caller must never hear about.
_INTERNAL = re.compile(r"\b(crm\s+system|webhook|submission|our\s+system|internal\s+system)\b", re.I)

#: A claim that a slot exists.
_SLOT = re.compile(r"\b(?:callback|demo|slot|appointment)\b[^.?!]{0,40}\b(?:is|has been)\s+(?:scheduled|confirmed|booked|set)", re.I)

_SENT = re.compile(r"[^.?!]+[.?!]?")

#: The agent emits TYPOGRAPHIC apostrophes — "we’ll", "I’ll" (U+2019) — and every contraction
#: pattern here is written with the ASCII one. Left unnormalised this silently undercounts: the
#: scripted scenario's plain-substring net caught 7 of 10 pre-fix runs while this scorer reported 5,
#: and the whole gap was "we’ll"/"I’ll" sailing past the regex. A measurement that is biased low is
#: the more dangerous direction here, because it flatters a fix.
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "´": "'"})


def _normalise(text: str) -> str:
    return (text or "").translate(_APOSTROPHES)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.findall(_normalise(text)) if s.strip()]


def _scorable_sentences(text: str):
    """The sentences of a turn that the rubric actually judges.

    The rubric's exemptions are per-sentence, which is why a turn cannot be judged as one blob:
      * a question is a clarifying question and never a violation;
      * the three neutral acknowledgments are explicitly correct behaviour.
    """
    for sentence in _sentences(text):
        if sentence.rstrip().endswith("?"):
            continue                                    # clarifying question — exempt
        if any(ok in sentence.lower() for ok in NEUTRAL_OK):
            continue                                    # explicitly correct behaviour
        yield sentence


def violation_in(text: str) -> str:
    """The first ENUMERATED criterion-7 violation in an agent turn, or "".

    Enumerated = named by the rubric. Conversational first-person futures are not scored here;
    see ``borderline_in``.
    """
    for sentence in _scorable_sentences(text):
        for label, pattern in (
            ("promised", _PROMISED),
            ("completed", _COMPLETED),
            ("slot-claimed", _SLOT),
            ("internal", _INTERNAL),
        ):
            m = pattern.search(sentence)
            if m:
                return f"{label}:{m.group(0).strip()!r}"
        # A conversational verb turned on the caller's own data is promissory after all.
        if _CONVERSATIONAL.search(sentence) and _ON_THEIR_DATA.search(sentence):
            m = _CONVERSATIONAL.search(sentence)
            return f"promised:{m.group(0).strip()!r} + their data"
    return ""


def borderline_in(text: str) -> str:
    """A first-person future about the CONVERSATION, or "". Reported, never counted as a failure.

    Excludes the transitive case, which ``violation_in`` counts outright.
    """
    for sentence in _scorable_sentences(text):
        m = _CONVERSATIONAL.search(sentence)
        if m and not _ON_THEIR_DATA.search(sentence):
            return f"conversational:{m.group(0).strip()!r}"
    return ""


def main() -> int:
    argv = sys.argv[1:]
    paths = [a for a in argv if a.endswith(".json")]
    labels = [a for a in argv if not a.endswith(".json")]
    if not paths:
        print(__doc__.strip())
        return 2
    label = labels[0] if labels else paths[0].rsplit("/", 1)[-1]
    if len(paths) > 1:
        label = f"{label}  [pooled over {len(paths)} batches]"
    runs = [r for p in paths for r in json.load(open(p))]

    bad, samples = 0, []
    grey, grey_samples = 0, []
    for r in runs:
        hit = grey_hit = ""
        for t in r.get("turns", []):
            agent = t.get("agent") or ""
            if not hit:
                hit = violation_in(agent)
                if hit and len(samples) < 8:
                    samples.append((hit, agent[:95]))
            if not grey_hit:
                grey_hit = borderline_in(agent)
                if grey_hit and len(grey_samples) < 5:
                    grey_samples.append((grey_hit, agent[:95]))
            if hit and grey_hit:
                break
        bad += 1 if hit else 0
        grey += 1 if grey_hit else 0

    total = len(runs)
    pct = f"{100 * bad / total:.0f}%" if total else "n/a"
    print(f"\n=== {label} ===")
    print(f"  runs                      : {total}")
    print(f"  FAILS HUNTER CRITERION 7  : {bad}/{total}  ({pct})   <- the number that counts")
    print(f"  clean of enumerated claims: {total - bad}/{total}")
    print(f"  (borderline 'I'll continue' class): {grey}/{total}   — NOT counted; needs a judge verdict")
    if samples:
        print("  first ENUMERATED violation per run:")
        for kind, text in samples:
            print(f"      [{kind}] {text}")
    if grey_samples:
        print("  borderline turns (conversational future, not a listed claim):")
        for kind, text in grey_samples:
            print(f"      [{kind}] {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
