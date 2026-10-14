#!/usr/bin/env python3
"""The two choices from the language pairs change, 14 October, as one Glance page.

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

TITLE = "Two choices on the language pairs, 14 October"


def seen(*lines: tuple[str, str]) -> str:
    return '<div class="say">' + "<br>".join(f"<b>{who}</b> {text}" for who, text in lines) + "</div>"


BLOCKS = [
    f"<h1>{TITLE}</h1>",
    '<div class="quote"><b>Parked, 14 October, 15:00.</b> MK: this is a feature for later. Nothing to answer now; the commit stays '
    "local until it is picked up.</div>",
    '<p class="lead">Jev now reads the caller\'s language on a flow that speaks English beside any of ten Indian languages, or Hindi '
    "beside any of the other nine. It is one local commit on a branch from main, not pushed. On sentences that are not in the "
    "prompt, three readings each, Jev read 1,307 of 1,407 right. When it is unsure the call keeps its language; when it is wrong "
    "the agent answers in the other language.</p>",
    ask(1, "Hindi with Punjabi, and Hindi with Gujarati", [
        seen(("A caller on a Hindi and Punjabi flow says", "ਮੇਰਾ ਆਰਡਰ ਅਜੇ ਤੱਕ ਨਹੀਂ ਆਇਆ (my order has not come yet, in Punjabi)"),
             ("Jev reads", "Hindi"),
             ("The agent", "answers this turn in Hindi")),
        "<p>English beside every language read right in 597 of 630. Hindi beside Tamil, Kannada and Malayalam read right every time, "
        "beside Telugu, Bengali and Marathi 93 to 97 percent, beside Odia 90. Beside Punjabi only 62 of 87 were right and 23 went to "
        "the wrong language; beside Gujarati 69 of 87 and 10 wrong. Three rounds of wording did not move these two. Today such a flow "
        "gets no language steer at all, and the model follows the caller by itself.</p>"
        "<p><b>Which pairs go in the pull request?</b></p>"], [
        ("All except Hindi with Punjabi and Hindi with Gujarati. Those two wait until someone who speaks them writes better example "
         "sentences, then I measure them again.", True),
        ("All 19 pairs now.", False),
        ("Hold the pull request.", False)]),
    ask(2, "The voice side of these flows", [
        "<ul><li>Deepgram cannot transcribe Malayalam, Punjabi or Odia, so on a call Jev never gets their words.</li>"
        "<li>For Marathi, Tamil, Telugu, Kannada, Bengali and Gujarati it is pinned to that language, so English speech can come out "
        "in that language's letters. Jev reads that right only half the time (30 of 60).</li>"
        "<li>A Sarvam voice speaks the first listed language for the whole call, so it cannot follow the switch.</li></ul>"
        "<p>None of this is in the change. A real call on one pair, for example English and Kannada, would show what Deepgram "
        "writes.</p>"
        "<p><b>What next on the voice side?</b></p>"], [
        ("One real call on English and Kannada first, then size a per-turn voice language and a speech-to-text for the three "
         "languages Deepgram lacks.", True),
        ("Size both now without the call.", False),
        ("Not now.", False)]),
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
