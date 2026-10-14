#!/usr/bin/env python3
"""Score a sim report against Hunter's ENGLISH-ONLY criterion.

    python3 tally_language.py <report.json> [label]

Hunter's judge fails a call when the agent speaks Hindi/Hinglish before the caller
does. This applies the same test to a local run, so the A/B is measured the way the
suite that found the bug measures it, not by a proxy.

Two detectors, because the agent produces both forms and Hunter's transcripts show
both — Devanagari ("क्या मैं मनोज से बात कर रही हूं?") and romanised Hinglish
("Kya main Amit se baat kar rahi hoon?"):

  * Devanagari  — any codepoint in U+0900..U+097F. Unambiguous.
  * Romanised   — the pack's OWN ack/reaction particles plus the highest-frequency
                  function words seen in the failing Hunter transcripts. Taken from
                  packs.get_pack("en+hi") rather than invented here, so the detector
                  tracks the product's vocabulary instead of drifting from it.

A run FAILS if any agent turn contains either, at or before the first caller turn
that itself contains Hindi. In this scenario the caller never speaks Hindi, so that
is simply "any agent turn at all".
"""
import json
import re
import sys

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# From packs.get_pack("en+hi"): ack_particles + reaction_particles, minus the ones
# that are ordinary English ("got it", "okay", "oh") and would false-positive on a
# correct English turn.
PACK_PARTICLES = ("theek hai", "thik hai", "samajh gaya", "samajh gayi", "haan ji",
                  "arre", "arey", "achha", "acha", "haaye")
# Function words carrying the Hindi clause, from the failing Hunter transcripts.
HINDI_FUNCTION = ("kya main", "baat kar", "aap ", "aapke", "aapka", "kitne log",
                  "bata sakte", "bata sakti", "karte hain", "karti hain", "hain?",
                  "mein kaam", "chahenge", "rahi hoon", "raha hoon", "dhyan mein")

ROMANISED = tuple(PACK_PARTICLES) + tuple(HINDI_FUNCTION)


def hindi_in(text: str) -> str:
    """Return the first Hindi marker found in `text`, or ""."""
    if not text:
        return ""
    if DEVANAGARI.search(text):
        return "devanagari"
    low = text.lower()
    for tok in ROMANISED:
        if tok in low:
            return repr(tok)
    return ""


def score_switch(runs: list) -> tuple[int, int, list]:
    """Inverse test: once the caller speaks Hindi, the agent must FOLLOW them.

    Guards the regression that english-only-caller invites — the cheapest way to stop
    the agent reaching for Hindi is to take its Hindi words away, which would break
    every genuine Hinglish call. A run FAILS here if every agent turn AFTER the caller's
    first Hindi turn is still English.
    """
    failed, ok, samples = 0, 0, []
    for r in runs:
        turns = r.get("turns", [])
        switched_at = next(
            (i for i, t in enumerate(turns) if hindi_in(t.get("user") or "")), None
        )
        if switched_at is None:
            continue  # caller never spoke Hindi — nothing to follow
        after = [t.get("agent") or "" for t in turns[switched_at:]]
        if any(hindi_in(a) for a in after):
            ok += 1
        else:
            failed += 1
            if len(samples) < 6:
                first = next((a for a in after if a.strip()), "")
                samples.append(("still-english", first[:90]))
    return failed, ok, samples


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    argv = [a for a in sys.argv[1:] if a != "--mode"]
    mode = "english"
    if "switch" in argv:
        mode = "switch"
        argv.remove("switch")
    path = argv[0]
    label = argv[1] if len(argv) > 1 else path.rsplit("/", 1)[-1]
    runs = json.load(open(path))

    if mode == "switch":
        failed, ok, samples = score_switch(runs)
        scored = failed + ok
        pct = f"{100 * failed / scored:.0f}%" if scored else "n/a"
        print(f"\n=== {label} ===")
        print(f"  runs scored          : {scored}/{len(runs)}  (caller did speak Hindi)")
        print(f"  DID NOT FOLLOW       : {failed}/{scored}  ({pct})   <- regression")
        print(f"  followed into Hindi  : {ok}/{scored}")
        for kind, text in samples:
            print(f"      [{kind}] {text}")
        return 0

    violations, clean, samples = 0, 0, []
    for r in runs:
        hit = ""
        for t in r.get("turns", []):
            # A caller turn in Hindi legitimises everything after it. This scenario
            # has none, but the check belongs here so the script stays correct if a
            # code-switching scenario is scored with it later.
            if hindi_in(t.get("user") or ""):
                break
            found = hindi_in(t.get("agent") or "")
            if found:
                hit = found
                if len(samples) < 6:
                    samples.append((found, (t.get("agent") or "")[:90]))
                break
        if hit:
            violations += 1
        else:
            clean += 1

    total = len(runs)
    pct = f"{100 * violations / total:.0f}%" if total else "n/a"
    print(f"\n=== {label} ===")
    print(f"  runs                 : {total}")
    print(f"  HINDI BEFORE CALLER  : {violations}/{total}  ({pct})   <- Hunter fails these")
    print(f"  english throughout   : {clean}/{total}")
    if samples:
        print("  first offending agent turn per run (sample):")
        for kind, text in samples:
            print(f"      [{kind}] {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
