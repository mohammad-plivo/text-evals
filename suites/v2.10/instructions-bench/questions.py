#!/usr/bin/env python3
"""The decisions that came out of the v2.10 instructions guide, 14 October, as one Glance page.

    python3 questions.py        # writes out/questions/index.html
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT / "night-2026-10-11"), str(ROOT / "fails-2026-10-11")]
from build import MORE  # noqa: E402
from notes import ask  # noqa: E402
from report import CSS, HEAD  # noqa: E402

GUIDE = "https://glance.plivo.com/mohammad-kadiri/v210-vibe-guide"
TITLE = "Four choices from the instructions guide, 14 October"


def seen(*lines: tuple[str, str]) -> str:
    return '<div class="say">' + "<br>".join(f"<b>{who}</b> {text}" for who, text in lines) + "</div>"


BLOCKS = [
    f"<h1>{TITLE}</h1>",
    '<p class="lead">The guide is done and checked on dev with real Jev and gpt-5.6-luna. Writing the instructions by its rules took '
    "the first fill from 36 of 72 runs right to 61 of 69. Four things are yours to decide. The facts behind them are in "
    f'<a href="{GUIDE}">the guide</a>.</p>',
    ask(1, "How the Vibe agent fills a node's variables", [
        seen(("The Vibe agent writes", "STEP 2: PHONE, \"Ask for the best phone number to reach the patient.\", and a variable "
              "contact_phone with one line and no type"),
             ("You open the node in the builder", "the Variables tab adds patient_contact_phone (Phone) next to contact_phone"),
             ("On a call", "the agent asks for the phone number twice"),
             ("The Vibe agent edits the node later", "the Phone type and its settings are wiped from every variable")),
        "<p>The Vibe agent can only write a variable's name and one line. Every time it edits a node it rebuilds it from a fixed list, "
        "and that drops the type and settings the builder filled. This was read in the aiassist code, not seen on a live flow.</p>"
        "<p><b>What should the Vibe agent do?</b></p>"], [
        ("Give it a tool that asks the runner to fill and describe the variables, the same request the builder makes, and let its "
         "rebuild keep the type and settings. Code in aiassist. I would size it first and show you.", True),
        ("Only the guide's way for now: it leaves the variables empty, you open each node once so Jev and Luna fill them, and "
         "instruction edits on v2.10 nodes are made in the builder.", False),
        ("Leave it as it is for now.", False)]),
    ask(2, "Luna mixes up a value", [
        seen(("The instructions say", "Ask how many tablets they have left. It must be a whole number."),
             ("Luna writes", "prescription_number: \"Ask the caller to key in the 7-digit prescription number.\""),
             ("On a call", "the agent asks for the prescription number twice and never asks about the tablets")),
        "<p>This happened in 3 of 3 runs, and something like it in 6 more of the 23 flows: a balance the agent reads out taken as "
        "the amount the caller will pay, a company described as the person's name, a time of day taken as the fee question. Each "
        "variable is described by its own Luna call, which sees the others only by name.</p>"
        "<p>Describing the clear types first (name, phone, date and so on) and then the others with those in view fixed 2 of the 7 "
        "on dev. On 12 October you also asked that the description call write a choice's options, which today nobody writes.</p>"
        "<p>One Luna call per node could do both: it sees every variable at once, so two variables cannot take the same value, and "
        "it can return a choice's options with its name and description. That is not tested. Testing it needs the change on the dev "
        "runner, since gpt-5.6-luna is only there.</p>"
        "<p><b>How do you want this fixed?</b></p>"], [
        ("Build the one-call version on a branch (names, descriptions and a choice's options together). You put it on dev, I rerun "
         "the 23 flows and show you the numbers before any main pull request.", True),
        ("Only the two passes, which are measured: fixed 2 of the 7.", False),
        ("Not now.", False)]),
    ask(3, "Five smaller fixes the test found", [
        "<ul>"
        "<li>A second value of one type is added only when Jev can point at the line that asks for it. Today a phone question next "
        "to an account number makes two phone variables.</li>"
        "<li>When the new instructions ask for no value of a type at all, the one variable of that type is removed even if Jev is "
        "unsure. Today deleting the vehicle question removed nothing in 0 of 3 runs.</li>"
        "<li>Luna always replaces names like <b>name</b> and <b>text</b>. Today <b>name</b> stayed in 8 of 69 runs.</li>"
        "<li>Two values of one type get their own settings, for example a missed visit's date that may be in the past and a new "
        "date that must be in the future. Today both get the same rule.</li>"
        "<li>The builder keeps \"read it back character by character\" when it saves. Today it drops it.</li>"
        "</ul>"
        "<p><b>Which of these do you want?</b></p>"], [
        ("The three small ones now: the names, the read-back, and the removal rule. The other two after question 2 is measured.", True),
        ("All five.", False),
        ("None for now.", False)]),
    ask(4, "Where the guide goes", [
        "<p>The Vibe agent reads its builder prompt on every turn. A skill it reads only when it asks for it, and the builder prompt "
        "has to name the skill for that to happen reliably.</p>"
        "<p><b>Where should the Vibe agent get these rules from?</b></p>"], [
        ("A short skill of about 100 lines (the 13 writing rules and the edit rules) in the prompts repo, named in the builder prompt, "
         "with the full guide as its reference. One pull request to the prompts repo.", True),
        ("A section inside the builder prompt, so it is always read. About 600 more words on every turn.", False),
        ("Keep it as a document for now.", False)]),
]


def main() -> None:
    text = "\n".join([HEAD.format(title=TITLE, css=CSS + MORE), *BLOCKS, "</main></body></html>"])
    banned = re.findall(r"(?i)rapido|fhcsd|family health|san diego|/Users/|—|–", text)
    assert not banned, banned[:5]
    out = HERE / "out" / "questions"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(text)
    print(len(text), "characters,", sum(block.startswith('<div class="q">') for block in BLOCKS), "questions")


if __name__ == "__main__":
    main()
