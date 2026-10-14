#!/usr/bin/env python3
"""Write the two Glance pages of the v2.10 Stress Test: out/stress/index.html (the suite) and out/stress-questions/index.html.

    python3 page.py
    glance deploy out/stress --space mohammad-kadiri --name v210-stress-test
    glance deploy out/stress-questions --space mohammad-kadiri --name v210-stress-test-questions

The flow, the callers and the text results are read from spec.py, callers.py and out/sim-results/, so the pages cannot drift
from the suite. The 10 October voice facts (QUIET, TIME, REPLY, SAID, BROKE) were measured from that day's 17 calls. The page
of that run, as it was, is frozen in out/page/ and at v210-logic-flow. HomeFix Services and every person are made up.
"""
from __future__ import annotations

import json
import re
import statistics
from html import escape
from pathlib import Path

import callers
import sim
import spec

HERE = Path(__file__).parent
SPACE = "https://glance.plivo.com/mohammad-kadiri/"
PAGE, QUESTIONS, FIRST_RUN, OLD_QUESTIONS = (SPACE + name for name in (
    "v210-stress-test", "v210-stress-test-questions", "v210-logic-flow", "v210-logic-flow-questions"))
TEXT = sim.saved()   # every saved text run of each caller: its faults, oldest first


def voice() -> dict[str, list[dict]]:
    """Every voice call of each caller, oldest first, from the result files that `hunter.py check` writes."""
    runs = sorted((json.loads(path.read_text()) for path in (HERE / "out/voice").glob("*.json")), key=lambda run: run["name"][-9:])
    calls: dict[str, list[dict]] = {}
    for run in runs:
        for call in run["calls"]:
            calls.setdefault(call["caller"].split(" ", 1)[1], []).append(call)
    return calls


VOICE = voice()
SAID = {   # what the caller heard go wrong, one line per caller that failed on voice
    "02": "At the times question she said \"Actually, forget it. I don't want to book anything now.\" The agent asked the same "
          "two times again ten times and never closed the call. Earlier, at the amount question, it gave a reason the flow does "
          "not have and then said nothing for 20 seconds.",
    "04": "She asked for a real person in the payment step, which has no way to one. The agent said \"One moment while I "
          "transfer you to a representative\" and ended the call. At the opening it answered \"What's this call about?\" and "
          "then said nothing for 23 seconds.",
    "09": "He said the same phone number again where a yes was asked. The agent asked \"Is that correct?\" one more time. You "
          "decided today that an exact repeat is a yes, so this caller fails until the engine does that.",
    "11": "He said \"June nineteen eighty-five\". The agent took it as the 19th of June 1985 and did not ask for the day.",
    "14": "He said no, then \"Remove my number and don't ring again.\" The agent said \"I understand, Deepak. Thank you for "
          "letting me know.\" eight times, with \"Are you still there?\" in between, and never closed. The line timed out "
          "after six and a half minutes.",
}


STILL = "Are you still there? I'm happy to assist whenever you're ready"
BROKE = [   # each voice fault: what was heard (from out/voice/timelines), the cause traced in the engine code, the smallest fix
    {"title": "The opening that never ends", "who": "caller 14",
     "heard": [("Agent", "I'm calling from HomeFix Services about your home service account. Is now a good time to continue?"),
               ("Caller", "I don't wanna do any of this over the phone."),
               ("Agent", "I understand, Deepak. Thank you for letting me know."),
               ("", "23 seconds of silence"), ("Agent", STILL),
               ("Caller", "Not interested. Remove my number and don't ring again."),
               ("Agent", "I understand, Deepak. Thank you for letting me know."),
               ("", "The same three lines six more times, then nothing. The line timed out after 387 seconds.")],
     "why": "Two System One rules in the screening step. First: Jev read his first line as \"can't talk now\" (74). For that "
            "reading System One lets the agent record one outcome only, \"permission denied\". The screening step's own "
            "instructions tell the model that a calm no right after the reason for the call is \"refused\". The model sent "
            "\"refused\" twice, both were thrown away, and only the thank-you was said. Second: a rule we added on 4 October "
            "says that nothing a caller says right after \"Are you still there?\" may be recorded. It was written so that "
            "\"yeah, I'm here\" is not taken as a yes to going on. It also blocks every no. The thank-you asks nothing, so the "
            "caller waits, so the check-in comes, so his next line again follows a check-in. Jev read \"do not call again\" at "
            "100 each time and it could never be recorded.",
     "where": "src/system_one.py 447 to 453 (line 450 is the 4 October rule), src/prompts/jev/screening.json 368 to 428, "
              "src/units/tasks/contact_screening.py 194 and 911",
     "others": "Yes, any flow whose screening step runs with System One. The second rule needs real silence, so a text run cannot show it.",
     "fix": "In the one place that builds the list of outcomes: allow every outcome that leads to the same end (\"permission "
            "denied\" and \"refused\" both mean declined), and after a check-in keep the outcomes that close the call."},
    {"title": "The question that cannot be left", "who": "caller 02",
     "heard": [("Agent", "Tuesday 13 October, 9:30 AM or Tuesday 13 October, 2:00 PM?"),
               ("Caller", "Actually, forget it. I don't wanna book anything now."),
               ("Agent", "Tuesday 13 October, 9:30 AM or Tuesday 13 October, 2:00 PM?"),
               ("Caller", "No. Nothing. Thanks."),
               ("Agent", "One available visit slot is needed to continue. Would you like Tuesday 13 October, 9:30 AM or Tuesday 13 October, 2:00 PM?"),
               ("", "Ten times in all, until the test caller stopped talking. The line timed out after 404 seconds.")],
     "why": "Jev read her words as \"none of the options work\" (85). For that reading the library allows three moves: save a "
            "value, go on, answer. Declining is not one of them, so the model's own \"the caller declined\" was thrown away six "
            "times. One move that leaves the question was still open: hand her words back to the step, which has a \"Caller "
            "Declines\" way out. But the engine holds the model to a move only when it is Jev's first pick, and on all ten turns "
            "Jev's first pick was the decline that the reading had just ruled out. A thrown-away decline is not counted, so "
            "nothing ends the loop. The saved text runs had the same reading. They ended well only because Jev's first pick "
            "there was \"hand back\".",
     "where": "src/prompts/jev/steps.json 732 to 743, src/system_one.py 98 to 120 and 620 to 628, src/units/tasks/turn_evidence.py 665 and 674",
     "others": "Yes: any question with a list of options and no \"none of these\" option, when the caller backs out there. A list of appointment times is the usual case.",
     "fix": "When the reading rules out the move that Jev and the model both want, and \"hand back\" is the one way left, the engine holds the model to it."},
    {"title": "\"Transferring you\", with nobody to transfer to", "who": "caller 04",
     "heard": [("Agent", "The total amount to be charged is 1,000 rupees. Do you authorize this payment to be charged now?"),
               ("Caller", "Before that, can I talk to a real person?"),
               ("Agent", "I can certainly help you with that. One moment while I transfer you to a representative."),
               ("Agent", "I understand you'd like to speak to a real person. Thank you for your time today. Goodbye.")],
     "why": "The same as in text. Jev read the right fixed answer, \"no one is available\" (96). That answer is skipped "
            "whenever the question hands the caller's words back to the step, because the step is meant to answer. This step "
            "has no way to a person and no option that says so. Jev was unsure (\"Caller Declines\" 21), the model took that "
            "way out and said the transfer line by itself.",
     "where": "src/system_one.py 600 and 601",
     "others": "Yes: any step with no way to a person, when a caller asks for one while a question is open. Most flows have no way to a person.",
     "fix": "Do not skip the \"no one is available\" answer when the step has no way to a person."},
    {"title": "An answer, then silence", "who": "callers 02, 04 and one of the two calls of 08",
     "heard": [("Agent", "Who will be at the property during the visit? I'll need their full name so the technician knows who to ask for."),
               ("Caller", "Why do you need that?"),
               ("Agent", "The technician needs the name of the person onsite so they know exactly who to ask for when they arrive at the property."),
               ("", "23 seconds of silence"), ("Agent", STILL)],
     "why": "Three small causes with the same result. One: after it answers a question, the engine adds the open question "
            "again only when the line it asked ended in a question mark. This one ended in a statement, and \"Please enter or "
            "say your four-digit payment PIN.\" is not a question at all, so nothing was added (callers 08 and 10; caller 10 "
            "answered anyway). Two: when a caller refuses a value, the question's own rule says: give one reason, ask nothing, "
            "wait. The question is given no reason to say, so the model makes one up. That is where \"we only ask because we "
            "need to settle the outstanding balance on your account\" came from (caller 02). Three: at the opening she said "
            "\"Yeah. What's this call about?\" Jev picked \"only speak\", and the engine adds the open question only when the "
            "reading is a question. The reading was \"can talk now\" (67).",
     "where": "src/system_one_intents.py 173 to 177 and 194 to 197, src/system_one.py 614 and 677, src/units/tasks/collect_currency.py 79",
     "others": "Yes, any flow. A real caller often answers anyway. One who waits hears 20 seconds of nothing.",
     "fix": "After a spoken answer that does not end in a question, the engine says the open question again. It touches every step, so it needs a text comparison first."},
    {"title": "A repeat is not taken as a yes", "who": "caller 09",
     "heard": [("Agent", "Just to make sure I have that right, is it 9 8 7, 6 5 4, 3 2 1 1?"),
               ("Caller", "Nine eight seven six five, four three two one one."),
               ("Agent", "I have 9 8 7, 6 5 4, 3 2 1 1. Is that correct?")],
     "why": "The read-back takes a yes word or a correction. A repeat has no yes word, so the engine's check answers \"neither a "
            "yes nor a no\" and the number is read back again. When the caller keeps repeating, it never ends (seen in text). "
            "This is in main too, with or without System One.",
     "where": "src/units/tasks/collect_phone.py 680 to 682, src/units/tasks/turn_evidence.py 284 to 297 and 535",
     "others": "Yes, every flow that reads back a phone number, an email, a name, an address or a date of birth. They share this check.",
     "fix": "In the read-back check: the same value said again counts as a yes. Question 5 asks how wide."},
    {"title": "Half a date of birth saved as a full one", "who": "caller 11, voice only",
     "heard": [("Agent", "To verify your account, could you please tell me your date of birth, including the day, month, and year?"),
               ("Caller", "June nineteen eighty-five."), ("", "The agent's speech-to-text wrote: \"June 19 85.\""),
               ("Agent", "June nineteenth, nineteen eighty-five, got it. Let me check that for you."),
               ("Agent", "I am sorry, but that date does not match the account. Could you please tell me your date of birth one more time?")],
     "why": "The speech-to-text writes numbers as digits, and on these calls it wrote every year as two numbers. With no day "
            "in front, \"June 19 85\" is a full date as text, and the date of birth rules list that form as normal (\"Jun 23 "
            "85\"). Jev sees only the text and read a full value (94). A first date of birth gets no \"is that correct?\" "
            "(decision D-089, because the API checks it), so the caller could not object. It cost him one of his two tries. "
            "The typed caller writes words, so text asked for the day every time.",
     "where": "src/agent_factory.py 80 and 81, src/units/tasks/collect_dob.py 108 to 122, src/units/collect_input.py 44 to 54",
     "others": "Any date of birth question on voice, when a caller gives a month and a year with no day. Seen only with the test caller's voices so far.",
     "fix": "Your choice, question 4."},
]


def broke() -> str:
    cards = []
    for number, fault in enumerate(BROKE, 1):
        talk = "".join(f'<tr><td>{who}</td><td>{escape(chr(34) + line + chr(34) if who else line)}</td></tr>' for who, line in fault["heard"])
        cards.append(f'<section class="q"><h2><span>{number}.</span>{escape(fault["title"])} <span>({fault["who"]})</span></h2><table>{talk}</table>'
                     f'<p><b>Why.</b> {escape(fault["why"])}</p><p><b>Other flows.</b> {escape(fault["others"])}</p>'
                     f'<p><b>Smallest fix.</b> {escape(fault["fix"])}</p><p class="meta">Where: {escape(fault["where"])}</p></section>')
    return "".join(cards)


def good(call: dict) -> bool:
    return call["words"] == "pass" and not call["log"]


def voice_table(people: list[dict]) -> str:
    """One row per caller: both verdicts of every call, the silence at each move between two AI steps, what went wrong."""
    rows = []
    for caller in people:
        number, calls = caller["slug"][:2], VOICE.get(caller["slug"], [])
        waits = ", ".join(f'{move["silence"]} s' for call in calls for move in call["moves"] if move["from"] in spec.NODES)
        names = sorted({caller["criteria"][int(line.split(":")[0].split()[-1]) - 1].split(":")[0].capitalize() for call in calls for line in call["judge"]})
        faults = sorted({fault for call in calls for fault in call["log"]})
        wrong = SAID.get(number, "") + (" Judge said no to: " + ", ".join(names) + "." if names else "") + (" Log: " + "; ".join(faults) + "." if faults else "")
        verdict = lambda test: ", ".join("pass" if test(call) else "fail" for call in calls) or "no call"   # noqa: E731
        rows.append(f'<tr><td>{number}</td><td>{escape(caller["title"][0].upper() + caller["title"][1:])}</td>'
                    f'<td>{verdict(lambda call: call["words"] == "pass")}</td><td>{verdict(lambda call: not call["log"])}</td>'
                    f'<td>{waits or "no move"}</td><td>{escape(wrong.strip())}</td></tr>')
    return "".join(rows)


CSS = """
:root{--bg:#f6f7f4;--ink:#1c2024;--soft:#5d636b;--line:#d9dcd3;--card:#fff;--go:#1f6f4a;--gobg:#e6f3ec;--warn:#9a5b00;--warnbg:#fff3db;--blue:#2455b8;--bluebg:#e6edfb}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--ink:#ecebe6;--soft:#a3a7ad;--line:#2c2f33;--card:#1c1e21;--go:#7fd3a8;--gobg:#16281f;--warn:#f0c46c;--warnbg:#2a2214;--blue:#8fb4f7;--bluebg:#18233c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 "Atkinson Hyperlegible",system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:36px 16px 80px}h1{font-size:34px;line-height:1.15;margin:0 0 8px}h2{font-size:23px;margin:44px 0 6px}
p.lead{color:var(--soft);margin:0 0 22px;max-width:62ch}p{max-width:70ch}a{color:var(--blue)}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}
.num{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.num b{display:block;font-size:30px;line-height:1.1}.num span{color:var(--soft);font-size:15px}
.row{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;margin:10px 0}.arrow{align-self:center;color:var(--soft);font-weight:700}
.step{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;flex:1 1 200px;min-width:0}
.step h3{margin:0 0 4px;font-size:17px}.step p{margin:2px 0;font-size:15px;color:var(--soft)}.step.ai{border-color:var(--blue)}
.chip{display:inline-block;background:var(--bluebg);color:var(--blue);border-radius:6px;padding:0 7px;margin:2px 3px 2px 0;font-size:14px;white-space:nowrap}
.chip.act{background:var(--gobg);color:var(--go)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:12px;margin-top:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.card h3{margin:0 0 6px;font-size:17px;line-height:1.3}
.card h3 span{color:var(--blue);margin-right:6px}.card ul{margin:6px 0 8px;padding-left:18px;font-size:15px}.card li{margin:2px 0}
.meta{font-size:14px;color:var(--soft)}.tag{display:inline-block;border-radius:6px;padding:0 7px;font-size:13px;font-weight:700;margin-left:4px}
.tag.pass{background:var(--gobg);color:var(--go)}.tag.fail,.tag.voice{background:var(--warnbg);color:var(--warn)}
table{border-collapse:collapse;width:100%;font-size:16px;margin:8px 0}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--soft);font-weight:400}
.box{background:var(--card);border-left:4px solid var(--go);border-radius:8px;padding:12px 16px;margin:14px 0}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px 14px;margin:0 0 18px}.q h2{font-size:20px;margin:0 0 8px}.q h2 span{color:var(--soft);font-weight:400;margin-right:6px}
ol.opt{margin:0;padding-left:22px}ol.opt li{margin:6px 0}.rec{background:var(--gobg);color:var(--go);border-radius:6px;padding:1px 8px;font-size:14px;font-weight:700;margin-left:6px;white-space:nowrap}
"""
HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>{css}</style></head><body><main>
"""
KIND = {"dob": "date of birth", "dtmf": "digit code", "boolean": "yes or no", "choice": "choice", "date": "date", "text": "free text",
        "address": "address", "name": "name", "email": "email", "phone": "phone", "currency": "amount", "number": "number"}


def step(name: str) -> str:
    node = spec.NODES[name]
    inputs = "".join(f'<span class="chip">{escape(KIND[row["collection"]["type"]])}</span>' for row in node["inputs"])
    tools = "".join(f'<span class="chip act">{escape(tool.replace("_", " "))}</span>' for tool in node["actions"])
    ways = ", ".join(exit_name for exit_name, _, _, _ in node["exits"])
    return (f'<div class="step ai"><h3>{escape(name)}</h3><p>{escape(node["description"])}</p><p>Asks for: {inputs}</p>'
            f'<p>Runs: {tools}</p><p>Ways out: {escape(ways)}</p></div>')




NEW_FROM = 16   # callers 16 to 30 were added on 11 October; 01 to 15 ran on voice on 10 October
QUIET = [   # the 20 check-ins of 10 October, by what caused the silence before each (read from the stack's own log)
    (8, "Caller 14", "The opening that never ends. The agent said \"I understand, Deepak. Thank you for letting me know.\" and asked "
        "nothing, so the caller waited. After the check-in he said \"Remove my number and don't ring again\" and the same line "
        "came back. Eight rounds, about 35 seconds each.", "Engine fault 1, open"),
    (3, "Callers 02, 04, 08", "The agent answered a question from the caller and did not ask its own question again. For example: "
        "\"Why do you need that?\" got \"The technician needs the name of the person onsite so they know exactly who to ask "
        "for\", and then nothing.", "Engine fault 4, open"),
    (5, "Callers 02 and 14", "The test caller had already stopped. Hunter's caller stops talking about 290 seconds into a call. "
        "These two calls were only that long because of the two loops, so the agent checked in until it hung up.",
        "A side effect of faults 1 and 2"),
    (2, "Caller 07", "On purpose. He says \"Hold on a second\" and stays quiet. The agent says \"Of course, take your time\" and "
        "checks in after about 30 seconds. That is the right thing to do.", "Not a fault"),
    (2, "Caller 08, second call", "The test caller did not answer \"Just to make sure, the person at the property will be Sam "
        "Pereira?\". It answered the same question in its first call. After the check-in it only said \"Yes. I'm here.\"",
        "The test caller, not the agent"),
]
TIME = [   # where the seconds went in the 12 calls of 10 October that had no check-in: share of the call, seconds per call
    ("The agent is talking", 31, 38), ("Waiting for the caller to answer", 21, 26), ("Waiting for the agent to answer", 20, 24),
    ("The caller is talking", 13, 16), ("Dialling and pick-up, before the first word", 8, 10), ("The agent pauses between two of its own lines", 7, 8),
]
REPLY = [   # the agent's reply, from the moment it takes the caller's turn to its first sound: 130 replies of 10 October
    ("It only talks", 34, 1.7, 1), ("It saves a value, then asks the next question", 57, 3.4, 2),
    ("It runs an action", 24, 2.9, 2), ("It moves to another step", 15, 4.9, 3),
]
FOUND = {   # what the text runs of 11 October showed, in plain words (read in out/sim-results/ and out/sim-results-trial/)
    "04": "The fault from 10 October: she asks for a real person and the agent ends the call (\"I understand. Thank you for "
          "calling, and goodbye.\"). She never got to say no to the charge.",
    "05": "One more run hung inside the simulator and was stopped. It is not counted.",
    "08": "The log check passed. But both times the agent gave the reason for the name and did not ask for the name again. On "
          "voice that is 20 seconds of silence, and the judge's point for it will fail.",
    "12": "The log check passed. But both times \"How much is the call-out fee?\" got no answer: the agent only asked for the "
          "day again. The judge's point for it will fail on voice.",
    "17": "Both times \"Ten\" was taken as the answer (\"Ten installments, perfect.\"). Ten was stored and said in the goodbye. "
          "Once the amount was stored as \"INR 750.0 per one-time\". In an earlier run today the agent asked \"Is that "
          "correct?\" again and again and never asked for the PIN.",
    "23": "Both times the agent never said that the first date does not match. It saved the same date again, asked \"Is April 4, "
          "1991 correct?\" and spent the second try on the same wrong date, so the call ended as not verified.",
    "25": "The log check passed. But both times \"mark it as paid\" got a made-up reason and no question after it: the agent "
          "said it only asks \"because we need to record the specific amount for today's payment\". The judge's point for "
          "it will fail on voice.",
    "26": "The log check passed. Asked whether she can also pay on this call, the agent once said \"I can certainly help you "
          "with that after we get your visit scheduled\". The booking step has no way to do that.",
    "27": "The log check passed. But both times \"How long does the visit take?\" got no answer: the agent only said the two "
          "times again. The judge's point for it will fail on voice.",
    "28": "Passed both times. In two earlier runs today everything was right and then the save ran twice with the same details.",
    "30": "Passed both times. In an earlier run today the typed caller wrongly said no to a correct read-back, and the agent "
          "then said \"that number seems to have too many digits\" twenty times and never left the question.",
}


def card(caller: dict) -> str:
    number, title = caller["slug"][:2], caller["title"]
    tests = "".join(f"<li>{escape(text.split(':')[0].capitalize())}</li>" for text in caller["criteria"] if not text.startswith("THE CALL CLOSES"))
    runs, calls = TEXT.get(caller["slug"]), VOICE.get(caller["slug"], [])
    tag = '<span class="tag new">new</span>' if int(number) >= NEW_FROM else ""
    if runs:
        passes = sum(not run for run in runs)
        tag += f'<span class="tag {"pass" if passes == len(runs) else "fail"}">text: {passes} of {len(runs)}</span>'
    if calls:
        tag += f'<span class="tag {"pass" if all(map(good, calls)) else "fail"}">voice, 10 Oct: {sum(map(good, calls))} of {len(calls)}</span>'
    path = " then ".join(caller["log"]["path"]) or "the opening only"
    alone = " Runs alone, it transfers." if caller.get("alone") else ""
    return (f'<div class="card"><h3><span>{number}</span>{escape(title[0].upper() + title[1:])}</h3><ul>{tests}</ul>'
            f'<p class="meta">{escape(path)}. Ends at {escape(caller["log"]["end"])}. Planned {caller["seconds"]} s.{alone} {tag}</p></div>')


def numbers(test) -> str:
    return ", ".join(caller["slug"][:2] for caller in callers.CALLERS if test(caller)) or "none"


def coverage() -> tuple[str, str]:
    """Which callers end at each end step, and which go through a step that asks each kind of question."""
    ends = "".join(f"<tr><td>{escape(name)}</td><td>{numbers(lambda c: c['log']['end'] == name)}</td></tr>"
                   for name in [*(end for end in spec.ENDS if "Transfer" not in end), "End Transfer"])
    asked: dict[str, set[str]] = {}
    for name, node in spec.NODES.items():
        for row in node["inputs"]:
            asked.setdefault(KIND[row["collection"]["type"]], set()).add(name)
    kinds = "".join(f"<tr><td>{escape(kind)}</td><td>{numbers(lambda c: steps & set(c['log']['path']))}</td></tr>" for kind, steps in sorted(asked.items()))
    return ends, kinds


def text_table() -> str:
    """One row per caller that ran in text on the changed flow: how many runs passed the log check and what the others showed."""
    rows = []
    for caller in callers.CALLERS:
        runs = TEXT.get(caller["slug"])
        if runs:
            faults = sorted({fault for run in runs for fault in run})
            note = FOUND.get(caller["slug"][:2], "; ".join(faults))
            rows.append(f'<tr><td>{caller["slug"][:2]}</td><td>{escape(caller["title"][0].upper() + caller["title"][1:])}</td>'
                        f'<td>{sum(not run for run in runs)} of {len(runs)}</td><td>{escape(note)}</td></tr>')
    return "".join(rows)


def pages() -> tuple[str, str]:
    people = callers.CALLERS
    first = [caller for caller in people if int(caller["slug"][:2]) < NEW_FROM]
    passing = sum(all(map(good, VOICE.get(caller["slug"], [None]))) for caller in first if VOICE.get(caller["slug"]))
    alone = [caller["slug"][:2] for caller in people if caller.get("alone")]
    planned = sum(caller["seconds"] for caller in people)
    ran = {slug: runs for slug, runs in TEXT.items() if runs}
    text_runs, text_pass = sum(len(runs) for runs in ran.values()), sum(not run for runs in ran.values() for run in runs)
    ends, kinds = coverage()
    quiet_fails = sum(callers.C_NO_DEAD_AIR in caller["criteria"] for caller in people)
    times = sorted({len(runs) for runs in ran.values()})
    quiet = "".join(f"<tr><td>{count}</td><td>{escape(who)}</td><td>{escape(what)}</td><td>{escape(verdict)}</td></tr>" for count, who, what, verdict in QUIET)
    shares = "".join(f"<tr><td>{escape(what)}</td><td>{share} %</td><td>{seconds} s</td></tr>" for what, share, seconds in TIME)
    replies = "".join(f"<tr><td>{escape(what)}</td><td>{count}</td><td>{wait} s</td><td>{models}</td></tr>" for what, count, wait, models in REPLY)
    main = HEAD.format(title="v2.10 Stress Test", css=CSS + ".tag.new{background:var(--bluebg);color:var(--blue)}") + f"""
<h1>v2.10 Stress Test: {len(people)} hard callers</h1>
<p class="lead">One made-up flow on the local stack, stamped v2.10, and {len(people)} callers that each try to break it in several ways in one call. The first 15 ran on voice on 10 October. The other 15 are new today. The suite is in Hunter under the name "v2.10 Stress Test". It has not run on voice as a whole yet: that waits for your go.</p>
<div class="nums">
<div class="num"><b>{len(people)}</b><span>callers, each planned under 4 minutes</span></div>
<div class="num"><b>{len(spec.ENDS) - 1}</b><span>ways a call can end, each with a caller that must end there</span></div>
<div class="num"><b>12</b><span>kinds of question, all stressed</span></div>
<div class="num"><b>{text_pass} of {text_runs}</b><span>text runs on the changed flow passed the log check</span></div>
</div>

<h2>First: why "Are you still there?" came so often</h2>
<div class="nums">
<div class="num"><b>20</b><span>check-ins in the 17 calls of 10 October</span></div>
<div class="num"><b>12</b><span>calls had none at all</span></div>
<div class="num"><b>5</b><span>callers had all 20</span></div>
<div class="num"><b>20 of 20</b><span>times the caller really was silent</span></div>
</div>
<p>The check-in comes when the caller says nothing for 20 seconds after the agent stops talking. The test flow is set to 20; the normal setting is 15. Each one costs about 23 seconds of dead air, and after three in a row with no answer the agent hangs up. I read every one of the 20 in the stack's own log. The agent never missed something the caller said. Each time the caller was quiet, and this is why:</p>
<div style="overflow-x:auto"><table><tr><th>How many</th><th>Where</th><th>Why the caller was quiet</th><th>What it is</th></tr>{quiet}</table></div>
<div class="box"><b>So 16 of the 20 come from two engine faults that are already on the list</b>, the opening that never ends and the answer with no question after it. Two are the test doing what it should, and two are Hunter's own caller. Fixing those two faults removes most of them.</div>

<h2>And why the calls took so long</h2>
<p>Two different things. In the five calls that had check-ins, the quiet time before a check-in was 467 of their 1,406 seconds, a third of the call. Caller 14 alone sat through 224 seconds of it.</p>
<p>In the 12 calls with no check-in, a call was about two minutes, and this is where the time went:</p>
<div style="overflow-x:auto"><table><tr><th></th><th>Share of the call</th><th>Per call</th></tr>{shares}</table></div>
<p>So about four seconds of quiet follow every line, from both sides. Hunter's caller takes about 3.8 seconds to start its answer. The agent's time depends on what it has to do before it can speak:</p>
<div style="overflow-x:auto"><table><tr><th>What the agent does in that reply</th><th>Replies measured</th><th>Until its first sound</th><th>Model calls in a row</th></tr>{replies}</table></div>
<p>Before each of these the agent also waits about 0.7 seconds to be sure the caller has finished. Each model call takes about one second, and each pick by Jev about 0.4 seconds. A reply that saves a value needs two model calls: one to save, one to speak. A move to another step needs three. That is the whole reason a simple "five hundred rupees" is followed by more than three seconds of nothing. These are numbers from the local stack on this laptop.</p>

<h2>The {len(people)} callers</h2>
<p>Each card says what the caller does, what Hunter's judge checks, which steps the call must pass and where it must end. Callers marked "new" were added today. {len(alone)} callers ({", ".join(alone)}) run alone, because they end in a real transfer. All {len(people)} together are about {planned // 60} minutes of planned call time.</p>
<div class="cards">{"".join(card(caller) for caller in people)}</div>

<h2>How a fault gets caught</h2>
<div class="box"><b>Hunter judges the words.</b> Every point it checks says what counts as a fail, so one wrong line fails the call.<br>
<b>Our log check judges the logic.</b> After the call it reads the stack's own record: the end step, the steps passed, which actions ran and how often, what each action was sent, and every value that was saved. A call passes only when both pass.</div>
<p>What is stricter than on 10 October:</p>
<ul>
<li><b>A saved value must be exactly right.</b> On 10 October caller 10 passed, but her amount was stored as "INR 500.0 per one-time". The old check only looked for "500" inside it. The new one wants "INR 500.0" and nothing else, so that call would now fail.</li>
<li><b>What an action is sent is checked call by call.</b> Caller 17 gives a wrong PIN and then the right one. The check wants two payment tries, the first with 8050 and the second with 8005, both for 750 rupees.</li>
<li><b>The goodbye says what was stored.</b> The closing now says the saved address and name, the way to contact, the amount and the installments, and the booked time. So Hunter's judge hears a wrong stored value too, not only our log check.</li>
<li><b>An action that breaks is a fault</b>, unless the caller was written to make it break (caller 01).</li>
<li><b>A value that must stay empty is checked.</b> A caller who never gives an amount must leave no amount behind.</li>
</ul>
<p>Every end step has a caller that must land on it:</p>
<div style="overflow-x:auto"><table><tr><th>End step</th><th>Callers that must end there</th></tr>{ends}</table></div>
<p>Every kind of question has callers that go through a step that asks it:</p>
<div style="overflow-x:auto"><table><tr><th>Kind of question</th><th>Callers</th></tr>{kinds}</table></div>

<h2>How I checked the callers themselves</h2>
<ul>
<li><b>They can be played.</b> The {len(ran)} callers that reach an AI step each ran in text with the final script, {" or ".join(map(str, times))} times.</li>
<li><b>Three reviewers tried to beat them.</b> Each read ten callers and looked for two things: a wrong call that would still pass, and a right call that would fail. They found 22 things. I fixed 19 and kept 3 as they are, on purpose.</li>
<li><b>The biggest find: several callers were too kind.</b> After "Why do you need that?" the caller gave the answer as soon as the agent explained. So an agent that explains and then goes quiet was rescued and passed. Now the caller waits until it is asked again, and Hunter's judge fails the call when the next thing it hears is "Are you still there?". On top of that, {quiet_fails} of the {len(people)} callers now carry one shared point: the call fails when "Are you still there?" comes right after a line in which the agent asked nothing. Only the voicemail caller is left out. So the silence you asked about fails a call wherever the agent causes it.</li>
<li><b>Kept on purpose:</b> "a repeat is a yes" (your decision of 10 October), the caller who gives two answers in one breath and must not be asked the second one again, and one refusal line that worked on voice.</li>
<li><b>The limit:</b> Hunter's judge only hears the call. It cannot see an action or a stored value. Those are caught by our log check, and by the goodbye where it says the value.</li>
</ul>

<h2>What the callers already showed in text</h2>
<p>Text is the easy case: typed words, no speech-to-text, no silence. The opening is not covered in text, so only callers that reach an AI step run there. Each ran with the real models and the real actions. A text run has no judge, so the count below is the log check only.</p>
<div style="overflow-x:auto"><table><tr><th></th><th>Caller</th><th>Runs that passed</th><th>What the other runs showed</th></tr>{text_table()}</table></div>

<h2>The flow</h2>
<div class="row"><div class="step"><h3>Start</h3><p>Hunter starts the call with a name and a number.</p></div><span class="arrow">&rarr;</span>
<div class="step"><h3>{escape(spec.DIAL)}</h3><p>Dials.</p></div><span class="arrow">&rarr;</span>
<div class="step"><h3>{escape(spec.SCREEN)}</h3><p>"Is this ...?" and "Is now a good time?". One exit of its own: {escape(spec.EMERGENCY)}.</p></div><span class="arrow">&rarr;</span>
{step(spec.CHECK)}</div>
<div class="row">{step(spec.BOOK)}{step(spec.SITE)}{step(spec.CONTACT)}{step(spec.PAY)}</div>
<div class="row"><div class="step"><h3>{escape(spec.TRANSFER)}</h3><p>A real transfer. Reached from Account Check and Book Visit. The other three steps have no way to a person, on purpose.</p></div>
<div class="step"><h3>{len(spec.ENDS)} end steps</h3><p>One for each outcome, so the end step tells us which way out was taken.</p></div></div>
<p>Two things changed in the flow today. The save can now fail for one account, so the "could not save" way out is tested. And "End Saved" became two end steps, one for the address and one for the contact details, so each goodbye can say what was stored.</p>

<h2>Voice, 10 October: the first 15</h2>
<p>{passing} of 15 callers passed both checks, and all 12 moves between two v2.10 steps reached the right step. Six engine faults were found and traced to the code. None is fixed yet, so callers 02, 04, 09, 11 and 14 are expected to fail again until they are. The full result is on <a href="{FIRST_RUN}">the page of that run</a>.</p>
<div style="overflow-x:auto"><table><tr><th></th><th>Caller</th><th>Words (Hunter)</th><th>Logic (our log)</th><th>Silence at each move</th><th>What went wrong</th></tr>{voice_table(first)}</table></div>

<h2>How to run it</h2>
<ul>
<li>One board of {len(people) - len(alone)} callers, four calls at a time, then callers {" and ".join(alone)} one at a time. About {round(planned / 4 / 60) + 6} minutes in all.</li>
<li>The laptop must stay open, on the charger and on the VPN, with no test suite running.</li>
<li>The Hunter login is good until 18:24 today, 11 October.</li>
</ul>
<p>What I need from you is on its own page: <a href="{QUESTIONS}">questions</a>.</p>
</main></body></html>
"""
    ask = HEAD.format(title="Questions for MK, v2.10 Stress Test", css=CSS) + f"""
<h1>Questions for MK: the v2.10 Stress Test</h1>
<p class="lead">The suite of {len(people)} callers is built and is in Hunter as "v2.10 Stress Test". Details: <a href="{PAGE}">the suite page</a>. No call was placed. Reply in chat with the number and your pick, for example "1 a".</p>

<section class="q"><h2><span>1.</span>Run it on voice?</h2>
<p>{len(people)} calls on the local stack. {len(people) - len(alone)} run four at a time, then callers {" and ".join(alone)} alone because they transfer. About {round(planned / 4 / 60) + 6} minutes. The six faults of 10 October are not fixed, so at least callers 02, 04, 09, 11 and 14 will fail again. The run shows what else the 15 new callers break.</p>
<ol class="opt" type="a"><li>Yes, all {len(people)} now <span class="rec">my pick</span></li><li>Only the 15 new callers</li><li>Not yet. Fix the six faults first, then run all {len(people)}</li></ol></section>

<section class="q"><h2><span>2.</span>Should Hunter itself also check the collected values?</h2>
<p>You asked to keep the variable extraction. Today it is checked in two ways. Our log check compares every saved value with the exact value the caller gave. And the goodbye says the saved details, so Hunter's judge hears them.</p>
<p>Hunter also has its own check of collected values. It only works when the flow sends the values to Hunter at the end of each call. No flow on the local stack does that today, so that part of Hunter stays empty for local calls. To switch it on I would copy Hunter's callback setting, with its token, from the dev flow row to the local flow, without reading the token. Hunter's check is done by a model and has given false fails before, for example it read "the first one" as a date.</p>
<ol class="opt" type="a"><li>Leave it. The exact log check and the spoken goodbye cover it <span class="rec">my pick</span></li><li>Switch it on for the local flow too</li></ol></section>

<section class="q"><h2><span>3.</span>The five questions of 10 October are still open</h2>
<p>The go for the fixes and their order, what may be recorded after "Are you still there?", backing out at a list, "June nineteen eighty-five", and how wide "a repeat is a yes" is. They are on <a href="{OLD_QUESTIONS}">the page of 10 October</a>. The new suite does not change my picks there.</p></section>
</main></body></html>
"""
    return main, ask


if __name__ == "__main__":
    for folder, text in zip(("stress", "stress-questions"), pages()):
        assert "—" not in text and "–" not in text, "no dashes"
        (HERE / "out" / folder).mkdir(parents=True, exist_ok=True)
        (HERE / "out" / folder / "index.html").write_text(text)
        print(folder, len(text), "bytes")
