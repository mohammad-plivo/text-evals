#!/usr/bin/env python3
"""Validator for the subtle-confirmation training datasets (v2).

v3 datasets are SHORT, MULTI-FIELD (4-5 values), English-only conversations. The point of the
rewrite: a single confirmation can be faked, fifteen in one call cannot. So most
checks here are about variation ACROSS a call, not about one line.

Run:  python3 validate_datasets.py [dir]
"""
import json
import os
import re
import sys
from collections import Counter

DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))

FILES = [
    "choice.json", "boolean.json", "number.json", "currency.json", "text.json",
    "address.json", "datetime.json", "contact_screening.json", "credit_card_expiry.json",
]

MIN_TURNS, MAX_TURNS = 14, 22
MIN_FIELDS, MAX_FIELDS = 4, 5
MIN_UNTAGGED_FIELDS = 2
MAX_TAG_USES = 2
MAX_OPENER_USES = 2

DASH = re.compile(r"[–—]")
PRAISE = re.compile(
    r"\b(great choice|excellent|wonderful|fantastic|awesome|impressive|"
    r"very generous|perfect!|that's perfect|brilliant choice|great!)\b", re.I)
STATUS = re.compile(
    r"\b(has been (recorded|saved|noted|captured|registered|updated|documented|verified|scheduled)|"
    r"i(?:'ve| have) (noted|recorded|saved|captured|registered)|"
    r"(that's|it's|it is) (been )?(noted|recorded|saved|captured|registered)|"
    r"\bnoted\b|on file|in the system|in our records)\b", re.I)
IHEARD = re.compile(r"\bi heard\b", re.I)
CLOSER = re.compile(
    r"(is there anything else|anything else i can (help|assist)|"
    r"thank you for your (time|patience|cooperation)[,.]? (is|do|would)|"
    r"i hope this helps)", re.I)
TELLS = re.compile(
    r"(is that correct|is this correct|just to confirm|to confirm,|i heard|"
    r"you (have )?(selected|chosen|answered|said|provided|indicated|requested|stated)|"
    r"has been (recorded|saved|noted|captured|registered|updated|documented)|"
    r"i(?:'ve| have) (noted|recorded|saved|captured|registered)|"
    r"is there anything else|for verification purposes|to ensure accuracy|"
    r"i will (now )?(read back|proceed|repeat)|kindly (confirm|provide)|"
    r"let me confirm|allow me to confirm|\bnoted\b|great choice|excellent choice|"
    r"perfect!|may i confirm|please confirm)", re.I)
TAGS = re.compile(r"\b(right|correct|yeah|yes|okay|ok)\s*\?", re.I)
NON_ASCII_WORD = re.compile(r"[ऀ-ॿÀ-ɏ]")

GOOD = {"subtle", "strict_required"}


def agent_turns(c, only_subtle_tier=True):
    out = []
    for t in c["turns"]:
        if t["speaker"] != "agent":
            continue
        if only_subtle_tier and t.get("tier") == "strict":
            continue
        out.append(t["text"])
    return out


def check_file(path):
    errs, warns = [], []
    with open(path) as f:
        d = json.load(f)

    for k in ("task", "tier", "description", "style_rules", "conversations"):
        if k not in d:
            errs.append(f"missing top-level key: {k}")
    if errs:
        return errs, warns

    convs = d["conversations"]
    if len(convs) != 20:
        errs.append(f"expected 20 conversations, got {len(convs)}")

    labels = Counter(c["label"] for c in convs)
    good_label = "strict_required" if "strict_required" in labels else "subtle"
    bad_label = "non_subtle"
    if good_label == "strict_required":
        # credit-card file: both labels are correct behaviour
        if labels.get("subtle") != 10 or labels.get("strict_required") != 10:
            errs.append(f"expected 10/10 subtle/strict_required, got {dict(labels)}")
        correct_labels = {"subtle", "strict_required"}
    else:
        if labels.get("subtle") != 10 or labels.get("non_subtle") != 10:
            errs.append(f"expected 10/10 subtle/non_subtle, got {dict(labels)}")
        correct_labels = {"subtle"}

    ids = [c["id"] for c in convs]
    if len(set(ids)) != len(ids):
        errs.append("duplicate conversation ids")

    pairs = {}
    for c in convs:
        pairs.setdefault(c["pair_id"], []).append(c)
    for pid, members in pairs.items():
        if len(members) != 2:
            errs.append(f"{pid}: expected 2 conversations, got {len(members)}")
        elif len({m["label"] for m in members}) != 2:
            errs.append(f"{pid}: both members share a label")

    for c in convs:
        cid, label = c["id"], c["label"]
        turns = c["turns"]

        if c.get("language") != "en":
            errs.append(f"{cid}: language must be 'en' (v2 is English only)")
        if not (MIN_TURNS <= len(turns) <= MAX_TURNS):
            errs.append(f"{cid}: {len(turns)} turns, want {MIN_TURNS}-{MAX_TURNS}")
        speakers = {t["speaker"] for t in turns}
        if speakers != {"agent", "caller"}:
            errs.append(f"{cid}: speakers = {speakers}")

        joined = " ".join(t["text"] for t in turns)
        if NON_ASCII_WORD.search(joined):
            errs.append(f"{cid}: non-English script detected")

        if label in correct_labels:
            flds = c.get("fields")
            if not flds:
                errs.append(f"{cid}: correct-label conversation needs a 'fields' array")
            elif not (MIN_FIELDS <= len(flds) <= MAX_FIELDS):
                errs.append(f"{cid}: {len(flds)} fields, want {MIN_FIELDS}-{MAX_FIELDS}")

            ats = agent_turns(c)
            for txt in ats:
                if DASH.search(txt):
                    errs.append(f"{cid}: em/en dash: {txt[:60]}")
                if PRAISE.search(txt):
                    errs.append(f"{cid}: praise slop: {txt[:60]}")
                if STATUS.search(txt):
                    errs.append(f"{cid}: status phrase: {txt[:60]}")
                if IHEARD.search(txt):
                    errs.append(f"{cid}: 'I heard': {txt[:60]}")
                if CLOSER.search(txt):
                    errs.append(f"{cid}: chatbot closer: {txt[:60]}")

            openers = [re.sub(r"[^a-z']", "", t.split()[0].lower()) for t in ats if t.split()]
            for w, n in Counter(openers).items():
                if n > MAX_OPENER_USES:
                    errs.append(f"{cid}: opener '{w}' used {n}x (max {MAX_OPENER_USES})")
            for a, b in zip(openers, openers[1:]):
                if a == b:
                    errs.append(f"{cid}: consecutive agent turns both open with '{a}'")

            tagged = [t for t in ats if TAGS.search(t)]
            tag_words = Counter(TAGS.search(t).group(1).lower() for t in tagged)
            for w, n in tag_words.items():
                if n > MAX_TAG_USES:
                    errs.append(f"{cid}: check tag '{w}?' used {n}x (max {MAX_TAG_USES})")
            untagged = len(ats) - len(tagged)
            if untagged < MIN_UNTAGGED_FIELDS:
                errs.append(f"{cid}: only {untagged} untagged agent turns, "
                            f"want >= {MIN_UNTAGGED_FIELDS}")

        elif label == bad_label:
            note = (c.get("notes") or "").lower()
            wrong_direction = "wrong-direction" in note or "wrong direction" in note
            if not wrong_direction:
                hits = sum(1 for t in agent_turns(c, only_subtle_tier=True) if TELLS.search(t))
                if hits < 3:
                    errs.append(f"{cid}: robotic twin shows only {hits} tells, want >= 3 "
                                f"(the repetition is the lesson)")

    # pair parity on caller turns
    for pid, members in pairs.items():
        if len(members) != 2:
            continue
        a, b = members
        ca = [t["text"] for t in a["turns"] if t["speaker"] == "caller"]
        cb = [t["text"] for t in b["turns"] if t["speaker"] == "caller"]
        shared = sum(1 for x in ca if x in cb)
        ratio = shared / max(len(ca), len(cb)) if ca and cb else 0
        if ratio < 0.6:
            warns.append(f"{pid}: only {ratio:.0%} of caller turns shared across the pair")

    return errs, warns


def main():
    total, failed = 0, 0
    for name in FILES:
        path = os.path.join(DIR, name)
        if not os.path.exists(path):
            print(f"MISSING {name}")
            failed += 1
            continue
        errs, warns = check_file(path)
        with open(path) as f:
            n = len(json.load(f)["conversations"])
        total += n
        if errs:
            failed += 1
            print(f"FAIL {name} ({n} conversations)")
            for e in errs[:40]:
                print(f"   - {e}")
            if len(errs) > 40:
                print(f"   ... and {len(errs) - 40} more")
        else:
            print(f"ok   {name} ({n} conversations)")
        for w in warns[:10]:
            print(f"   ~ {w}")
    print(f"\n{total} conversations across {len(FILES)} files; {failed} file(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
