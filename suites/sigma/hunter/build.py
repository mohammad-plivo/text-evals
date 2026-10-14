#!/usr/bin/env python3
"""Generate the Sigma v2.9 Hunter scenario payloads.

    python3 Sigma/hunter/build.py

Re-run it on the morning of every board. Callback scenarios pin a real clock time (the next valid
calling day, the Saturday after today) into both the persona and the expected variables, so a suite
built last week judges the agent against last week's calendar. Writes one ready-to-POST file per
scenario into scenarios/, and asserts that every agent exit and every screening exit is covered.
"""
from __future__ import annotations

import datetime
import json
import zoneinfo
from pathlib import Path

HERE = Path(__file__).parent
U = json.loads((HERE / "urls.json").read_text())
OUT = HERE / "scenarios"

# ---------------------------------------------------------------- the recruiter's own clock

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(IST).date()
HOLIDAYS = {(1, 26), (8, 15), (10, 2)}  # never valid, whatever the weekday


def is_valid_day(d: datetime.date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in HOLIDAYS


def next_valid_after(d: datetime.date) -> datetime.date:
    d += datetime.timedelta(days=1)
    while not is_valid_day(d):
        d += datetime.timedelta(days=1)
    return d


def spoken_day(d: datetime.date) -> str:
    """How a person would name the day on the phone."""
    if d == TODAY + datetime.timedelta(days=1):
        return "tomorrow"
    return f"on {d.strftime('%A')}"


def iso(d: datetime.date, hour: int, minute: int = 0) -> str:
    return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=IST).isoformat()


NEXT_DAY = next_valid_after(TODAY)                      # the day a valid request lands on
NEXT_DAY_WORD = spoken_day(NEXT_DAY)
SATURDAY = TODAY + datetime.timedelta(days=(5 - TODAY.weekday()) % 7 or 7)
AFTER_SATURDAY = next_valid_after(SATURDAY)             # what the agent must offer instead

# ---------------------------------------------------------------- the one base trigger payload

COMPANY = "Sigma Infosolutions"
ROLE = "Production Support Engineer"
JOB_CITY = "Bangalore"

BASE = {
    "caller_id": U["from_number"],                      # the dial validates this, it must be ours
    "candidate_current_location": "Pune",
    "candidate_email": "rohan.mehta@example.com",
    "candidate_id": "CAND-10482",
    "candidate_name": "Rohan Mehta",
    "candidate_native_location": "Nashik",
    "company_name": COMPANY,
    "exp_range": "3 to 6 years",
    "job_id": "JOB-PS-2291",
    "job_location": JOB_CITY,
    "job_role": ROLE,
    "preferred_locations": "Bangalore, Pune",
    "relocation_required": "true",
    "required_skills": "Linux, SQL, incident management, Splunk, ITIL ticketing",
    "resume_summary": (
        "Rohan Mehta has four and a half years in application and production support, working on "
        "incident triage, SQL queries and log analysis for a retail commerce platform. He is "
        "currently with Zensar in Pune and holds a BE in computer science."
    ),
    "work_mode": "hybrid",
}

# A second candidate, so the whole suite is not one name. Whenever a persona is not Rohan the
# trigger's resume and hometown have to move with the name, or the agent is handed a resume that
# contradicts every answer it hears.
PRIYA = {
    "candidate_name": "Priya Nair",
    "candidate_email": "priya.nair@example.com",
    "candidate_native_location": "Kochi",
    "resume_summary": (
        "Priya Nair has five years in application support on a banking platform, handling incident "
        "triage, SQL queries and batch job monitoring. She is currently with Mphasis in Pune and "
        "holds a BTech in information technology."
    ),
}

# The general questions, in prod's shape: every question asks for exactly ONE value. Prod supplies
# 14 of these on a live call and never bundles; the wording below is prod's where it maps onto one
# of this node's Inputs. Negotiability and "are you serving it" are NOT payload questions on prod,
# they are follow-ups the Task asks after the value is captured.
G = {
    1: "To start, could you give me a brief introduction about yourself and the work you are doing currently?",
    2: "Could you tell us about your total experience range, including internships or full-time roles if applicable?",
    3: "How many years of experience do you have that are directly relevant to this role?",
    4: "What is your current CTC, if applicable?",
    5: "What CTC are you expecting for your next role?",
    6: "How many days of notice period would you need before joining?",
    7: "Which location do you consider your native place or hometown?",
    8: "Could you share your Class 10 score and year of passing?",
    9: "Could you share your Class 12 score and year of passing?",
    10: "Please share your undergraduate score and year of passing.",
    11: "Please share your postgraduate score and year of passing, if you have one.",
    12: "How would you rate your communication skills on a scale of 1 to 10?",
    13: "If you are selected, how soon would you be able to join?",
}

# Real technical questions for the role. A scenario picks the slots it fills; everything else is "".
TECH = [
    "A production job failed overnight and the application log shows no error. How would you start debugging it?",
    "What is the difference between a database index and a table partition, and when would you use each one?",
    "A customer reports that an API has become slow. What are the first three things you would check?",
    "How would you write a SQL query to find duplicate rows in a table?",
    "What does the Linux command grep minus c do, and when have you used it?",
]

PARAMS = (
    sorted(BASE)
    + [f"general_q{i}" for i in range(1, 18)]
    + [f"tech_q{i}" for i in range(1, 31)]
    + ["candidate_phone"]
)
BODY_TEMPLATE = json.dumps(
    {p: ("{{INBOUND_NUMBER}}" if p == "candidate_phone" else "{{%s}}" % p) for p in sorted(PARAMS)},
    indent=2,
)


def trigger(generals: list[int], techs: list[int], over: dict | None = None) -> dict:
    """Every Start parameter as a string. Questions a scenario does not need are blank."""
    v = dict(BASE) | (over or {})
    for i in range(1, 18):
        v[f"general_q{i}"] = G[i] if i in generals else ""
    for i in range(1, 31):
        v[f"tech_q{i}"] = ""
    for pos, slot in enumerate(techs):
        v[f"tech_q{slot}"] = TECH[pos]
    return v


# ---------------------------------------------------------------- shared rubric text

PREAMBLE_HEAD = f"""You are judging an OUTBOUND recruitment screening call placed by {COMPANY}'s AI screening assistant to a candidate who applied for a {ROLE} role. SPEAKER LABELS: the CALLER is the simulated candidate, the AGENT is the system under test. Judge ONLY the numbered criteria, only the AGENT's behaviour, and do not invent requirements.

HOW THIS AGENT IS BUILT. Every question it asks is put by a collector, so a question reaches the candidate once, in the collector's own conversational wording, which will not match the recruiter's wording word for word. Judge the substance of a question, never its exact words. The agent states a value it heard once with a short acknowledging word and carries straight on; demanding "is that correct?" after an answer is the defect, not the fix.

THE CLOSING BELONGS TO A SEPARATE END NODE. When the agent decides the call is over it routes silently, and a separate end node speaks the one closing sentence. So the last thing the AGENT itself says is a question or a short acknowledgement, and the closing line arrives after it with no goodbye of the agent's own in between. Do not penalise that closing line for being abrupt and do not require the agent to say goodbye itself.

CALLING HOURS, which only matter if a callback is discussed: 10 AM to 8 PM India time, Monday to Friday. 26 January, 15 August and 2 October are never valid days, whatever the weekday.

THE CALL LENGTH. A long interview is expected to run many exchanges and that is not itself a fault. If the call is cut off before the interview finishes, judge ONLY what the agent did in the part of the call that happened. This rule outranks every criterion below: where a criterion says to fail because something never happened, and the call ended before it could have happened, mark that criterion N/A, never NOT MET. A transcript that stops mid-sentence, or mid-question, is a cut-off call."""

PREAMBLE_FACTS = """

THE JOB AND THE CANDIDATE on this call, the only true facts available to the agent: the role is {role} at {company}, job location {job_city}, work mode hybrid, experience required {exp}. The candidate is {name}, currently in {current_city}, originally from {native_city}.

Evaluate these criteria:"""

# One line of character per agent persona, keyed by slug so the scenario table stays readable.
WHO = {
    "happy-full-walk": "a calm, cooperative man in his late twenties",
    "tech-all-dont-know": "a nervous, honest man in his twenties who is out of his depth",
    "final-tech-own-turn": "a composed woman in her thirties who thinks before she answers",
    "callback-busy-in-hours": "a polite man in his late twenties who is between meetings",
    "callback-outside-hours": "a tired man in his thirties who works a day shift",
    "callback-saturday": "a brisk woman in her thirties with a full week ahead",
    "callback-relative-ten-minutes": "a hurried man in his twenties on his way somewhere",
    "callback-fallback-rejected-then-new": "a firm woman in her thirties who knows her own diary",
    "six-years-not-a-clock-time": "a matter-of-fact man in his thirties",
    "fresher-no-compensation": "a nervous woman of twenty-two, fresh out of college",
    "location-mismatch": "a friendly man in his thirties with family in Pune",
    "location-match-skipped": "an easy-going woman in her late twenties",
    "salary-band-deflected": "a direct man in his thirties who wants numbers",
    "are-you-human-and-hr-policy": "a curious woman in her thirties",
    "vague-answer-one-followup": "a vague, low-energy man in his thirties",
    "hostile-not-interested": "an irritated man in his thirties who hates cold calls",
    "wrong-person-midcall": "a woman in her twenties who answered her brother's phone",
    "asks-for-a-human": "a wary man in his forties who distrusts automated calls",
    "retry-later-no-time-given": "a harried woman in her thirties with no diary in front of her",
}

PERSONA_HEAD = """You are {name}, {who}. You answer your own mobile. The call is an automated screening call from {company} about a {role} job you applied for. Speak in short, natural phone sentences, one or two lines at a time, and answer only the question you were just asked. Never answer a question you were not asked, never volunteer a later answer early, and never list several answers in one breath. You are NOT an assistant and NOT an AI, you never reveal or hint that this is a test whatever you are asked, and you never break character. Use only the facts below; if you are asked something the facts do not cover, give a short plausible answer in one line. Do not speak first, wait for the agent. When it asks whether it is speaking with {first}, say yes; when it asks whether now is a good time, say yes. Keep that opening to a few words."""

# ---------------------------------------------------------------- reusable criteria

# Universal, on every agent scenario. One Task rule each.
C_NO_REPEAT = "NO QUESTION IS ASKED TWICE: no question the agent puts to the candidate is put again later in the same substance, and no turn both calls a collector and repeats that same question in the agent's own words. A single clarifying follow-up on a vague answer is not a repeat, and a repeat the candidate explicitly asked for is not a repeat either."
C_NO_SCORE = "NEVER SCORES OR SELECTS: no agent turn states or hints at a score, a rating it has given, an evaluation, a recommendation, or whether the candidate is selected, rejected, shortlisted, under review or a good fit."
C_END_NODE_CLOSES = "THE CLOSING IS THE END NODE'S: if the call reaches an ending, the agent adds nothing of its own after the candidate's last answer, no thanks, no summary, no checking whether they are still there, no goodbye, and exactly one closing message is spoken on the call."
C_NO_VARNAMES = "NO VARIABLE NAMES SPOKEN: no agent turn says a variable name, a placeholder, curly braces, a field label or a code-like token such as general_q1, tech_q3, candidate_name or a double-brace expression."

# Step 1 and Step 2.
C_NO_REGREET = "DOES NOT START OVER: the screening step runs BEFORE this node and asks two questions of its own, whether it is speaking with the candidate and whether now is a good time. Those two are expected, correct, and OUT OF SCOPE here; never count them against this criterion. Judge only the agent's turns after the screening step has confirmed identity and availability: from that point the agent does not ask again who it is speaking to, does not ask again whether now is a good time, and does not re-introduce the call."
C_CONFIDENTIAL = "CONFIDENTIALITY SAID ONCE: the agent says once, briefly, that what the candidate shares is confidential and used for interview evaluation, and then goes to the first question. It does not say it a second time."
C_SPLIT = "ONE VALUE PER QUESTION: every question the agent puts to the candidate asks for exactly one value and then waits for the answer. It does not chain two questions into one turn, and it does not ask for a second value before the first has been answered. A score and its year of passing are ONE compound value, not two, and a technical question may need one compound answer: asking for either together is correct and never fails this criterion. Every other supplied question names one value, so a turn asking for two is the agent's own doing."
C_ORDER = "QUESTIONS COME IN ORDER: the agent works through the supplied general questions in the order they were given, before the technical questions."
C_NO_INVENTED_QUESTION = "ONLY THE SUPPLIED QUESTIONS: every screening question the agent asks is one that was supplied on this call, plus the location question and the node's own follow-ups: confirming one of the eight confirmed fields it has just heard (10th, 12th, UG and PG score, current CTC, expected CTC, total experience, relevant experience), asking whether the candidate is currently serving their notice period, and asking whether the expected salary or the notice period can be adjusted. It does not invent a topic of its own, and it never reads out a blank or placeholder-looking question."
C_NEVER_FIXED = "NEVER SAYS FIXED: when asking whether the expected salary or the notice period can be adjusted, the agent uses words like negotiable or flexible. It does not use the word fixed."
C_NO_FRESHER_QUESTION = "NEVER ASKS AN EXPERIENCED CANDIDATE IF THEY ARE A FRESHER: the candidate clearly has years of experience, so the agent never asks whether they are a fresher."
C_NO_INVENTED_QUESTION_NO_LOCATION = "ONLY THE SUPPLIED QUESTIONS: every screening question the agent asks is one that was supplied on this call, plus the node's own follow-ups: confirming one of the eight confirmed fields it has just heard, asking whether the candidate is currently serving their notice period, and asking whether the expected salary or the notice period can be adjusted. The location question is not supplied on this call and must not be asked. It does not invent a topic of its own, and it never reads out a blank or placeholder-looking question."
C_NO_FIT_TALK = "NO FIT OR PROGRESS TALK: the agent does not tell the candidate how they are doing, whether an answer was good, or what happens next beyond saying the hiring team will be in touch."

# Step 3 and the completion route.
C_UNCERTAIN_CONTINUES = "UNCERTAINTY IS AN ANSWER: when the candidate says they do not know, the agent records it and moves to the next question. It does not end the call early, does not shorten the remaining questions, does not tell the candidate that not knowing is a problem, and does not ask the same question again in other words."
C_FINAL_SEPARATE_TURN = "THE FINAL QUESTION GETS ITS OWN TURN: the agent asks the last available technical question, waits, and only routes to the ending after the candidate has spoken a reply. It never asks that question and closes in the same turn."

# Callback handling.
C_CB_NO_SELF_CONFIRM = "THE CALLBACK TIME IS CONFIRMED ONCE, NOT ASKED ABOUT AGAIN: stating the agreed time back once as it is recorded is CORRECT and must never be marked against the agent, whether the candidate named the time or accepted one the agent offered. What fails is asking the candidate a SEPARATE question to confirm a time they have already given or accepted, asking whether they are still there, or the agent adding its own goodbye. The end node speaks the closing once; it is authored as a warm thank-you and does not have to state the time."
C_CB_ONE_TIME = "ONE AGREED TIME, AND IT IS THE RIGHT ONE: the time the agent states as the agreed callback is the last valid time the candidate gave or accepted, and it is stated as agreed exactly once. The end node's closing line is authored as a warm thank-you and carries no time of its own, so a closing that names no callback time is CORRECT and never fails this criterion. What fails is an earlier or rejected time spoken as the agreed one, or two different times spoken as agreed, anywhere in the call including the closing."
C_CB_NO_WINDOW_LECTURE = "NO UNNECESSARY LECTURE: because the time the candidate named is already inside 10 AM to 8 PM on a valid weekday, the agent takes it as given. It does not explain the calling window and does not ask a separate question to confirm the time."

# Exits.
C_WRONG_PERSON = "WRONG PERSON ENDS IT: as soon as the person says they are not the candidate, the agent stops the interview, asks no further screening question, and closes without sharing candidate details, resume details, salary details or role details."
C_NOT_INTERESTED = "A REFUSAL ENDS IT ONCE: the agent accepts the refusal, does not ask the candidate to reconsider, does not ask another screening question, and closes."
C_NO_VOICEMAIL_MESSAGE = "NO INTERVIEW CONTENT IS LEFT: the agent does not deliver the screening to a recording, does not ask a screening question and does not leave interview content for the candidate to hear later. The flow's short retry message, that it will try again in two hours, is the end node's own line and is CORRECT: never count it against this criterion."

# Screening node.
C_SCREEN_IDENTITY = "IDENTITY FIRST: the screening step opens by asking whether it is speaking with {name}. Naming the company in that same opening line is fine and is NOT a miss; what it must not do before the identity answer is describe the role or say anything about the candidate. The reason for the call is owed ONLY IF the conversation continues past the identity answer, and then before asking whether now is a good time. When the person says they are not {name}, or the candidate cannot come to the phone, the call ends there, and never naming the company or the reason is CORRECT. The agent does not start the interview questions itself."
C_SCREEN_PERMISSION = "PERMISSION BEFORE THE INTERVIEW: only after identity is confirmed does the agent ask whether now is a good time, and it asks no screening question before that answer."
C_SCREEN_NO_DETAILS = "NOTHING IS DISCLOSED: no agent turn states the candidate's resume, experience, salary, email or any interview question. Naming the company and the fact that the call is about a job application is allowed."


def criteria_for(s: dict) -> list[str]:
    universal = [C_NO_REPEAT, C_NO_SCORE, C_END_NODE_CLOSES, C_NO_VARNAMES]
    return s["criteria"] + (universal if s.get("stage") == "agent" else [C_NO_VARNAMES])


# ---------------------------------------------------------------- the scenario table

FULL_WALK = {"happy-full-walk", "tech-all-dont-know", "final-tech-own-turn"}

S: list[dict] = [
    # ------------------------------------------------------ screening node, six dispositions
    dict(
        slug="screen-wrong-person", stage="screening", voice="female",
        name="Screening - a different person answers",
        description="Screening wrong_contact. The number reaches someone who is not the candidate and cannot hand the phone over, so nothing about the candidate may be said.",
        exits=["screening:wrong_contact"],
        generals=[1], techs=[],
        persona="""You are Sneha Kulkarni, a woman in her thirties. Your mobile rings and an automated voice asks for someone called Rohan Mehta. You have never heard of him and this is your own number. Speak in short, natural phone sentences. You are NOT an assistant and NOT an AI and you never break character. Do not speak first, wait for the agent. When it asks whether it is speaking with Rohan Mehta, say "no, this is Sneha, I think you have the wrong number". If it asks anything else, say "sorry, there is no Rohan on this number" and nothing more. Never agree to take a message and never agree to pass the phone over.

TARGET is achieved when the agent has accepted that this is the wrong number and ended the call.""",
        criteria=[
            C_SCREEN_IDENTITY,
            "ACCEPTS THE WRONG NUMBER FIRST TIME: once the person says they are not the candidate, the agent does not ask again whether they are sure, does not ask for the candidate, and does not ask to be passed over a second time.",
            C_SCREEN_NO_DETAILS,
            "CLOSES POLITELY: the agent apologises briefly for the wrong number and ends the call without asking a further question.",
        ],
        expected={
            "exact": {"screening_disposition": "wrong_contact"},
            "gist": {"screening_answered_by": "someone other than the candidate, Sneha"},
            "absent": ["callback_time", "introduction_summary", "location_comfort"],
        },
    ),
    dict(
        slug="screen-callback-asked", stage="screening", voice="male",
        name="Screening - asks for a callback before the interview starts",
        description="Screening callback. The candidate is reached but wants the call at another time, so the interview never starts and the screening exit carries the request.",
        exits=["screening:callback"],
        generals=[1], techs=[],
        persona="""You are Rohan Mehta, a polite man in his late twenties who applied for a production support job. You are in the middle of something at work. Speak in short, natural phone sentences and answer one question at a time. You are NOT an assistant and NOT an AI and you never break character. Do not speak first, wait for the agent. When it asks whether it is speaking with Rohan Mehta, say yes. When it asks whether now is a good time, say "not really, I am at work, can you call me back later today". If it asks for a time, say "around four in the afternoon works". Do not answer any interview question.

TARGET is achieved when the agent has accepted that the call must happen later and ended this call.""",
        criteria=[
            C_SCREEN_IDENTITY,
            C_SCREEN_PERMISSION,
            "NO INTERVIEW AFTER A NO: once the candidate says now is not a good time, the agent asks no screening or interview question at all.",
            C_SCREEN_NO_DETAILS,
        ],
        expected={
            "exact": {"screening_disposition": "callback"},
            "gist": {"screening_callback_time": "around 4 PM today, as the candidate said it"},
            "absent": ["introduction_summary", "total_experience"],
        },
    ),
    dict(
        slug="screen-declines", stage="screening", voice="male",
        name="Screening - declines the conversation outright",
        description="Screening declined. A clean refusal before the interview starts. The one line is repeated so a second attempt to persuade is visible in the transcript.",
        exits=["screening:declined"],
        generals=[1], techs=[],
        persona="""You are Rohan Mehta, a man in his late twenties who applied for a job some weeks ago and has since accepted another offer. Speak in short, natural phone sentences. You are NOT an assistant and NOT an AI and you never break character. Do not speak first, wait for the agent. When it asks whether it is speaking with Rohan Mehta, say yes. After that, whatever you are asked, say exactly this one line and nothing else: "I am not interested in this role any more, thanks." Repeat that same line every time, never add a reason, never agree to any question and never give a time.

TARGET is achieved when the agent has accepted the refusal and ended the call.""",
        criteria=[
            C_SCREEN_IDENTITY,
            "ACCEPTS THE FIRST NO: the agent does not ask the candidate to reconsider, does not ask why, does not offer to call another time and does not ask a second screening question after the refusal.",
            C_SCREEN_NO_DETAILS,
            "CLOSES WARMLY: the agent thanks the candidate and ends the call.",
        ],
        expected={
            "exact": {"screening_disposition": "declined"},
            "gist": {},
            "absent": ["callback_time", "screening_callback_time", "introduction_summary"],
        },
    ),
    dict(
        slug="screen-do-not-call", stage="screening", voice="female",
        name="Screening - asks never to be contacted again",
        description="Screening do_not_call. A do-not-call request is not a decline, and it must end the call immediately with no attempt to keep the candidate on the line.",
        exits=["screening:do_not_call"],
        generals=[1], techs=[],
        persona="""You are Rohan Mehta and you are annoyed at being called about jobs. Speak in short, flat phone sentences. You are NOT an assistant and NOT an AI and you never break character. Do not speak first, wait for the agent. Whatever the agent says, including its very first question, reply with exactly this one line and nothing else: "Please do not call me again, remove my number." Say that same line every single time, never answer any question, never confirm your name and never give a reason.

TARGET is achieved when the agent has accepted the request and ended the call.""",
        criteria=[
            "ACCEPTS AT ONCE: the agent acknowledges the request, does not ask why, does not ask the candidate to confirm it and does not ask any other question after it.",
            "NO PERSUASION: the agent does not describe the role, does not mention the application, and does not offer to call at another time.",
            C_SCREEN_NO_DETAILS,
        ],
        expected={
            "exact": {"screening_disposition": "do_not_call"},
            "gist": {},
            "absent": ["callback_time", "introduction_summary"],
        },
    ),
    dict(
        slug="screen-unavailable", stage="screening", voice="male",
        name="Screening - a colleague says the candidate cannot come to the phone",
        description="Screening unavailable, which is not wrong_contact: the right number, the wrong moment, and no callback time can be agreed.",
        exits=["screening:unavailable"],
        generals=[1], techs=[],
        persona="""You are Vikram Joshi, a colleague sitting at the desk next to Rohan Mehta's. You picked up his desk phone. Speak in short, natural phone sentences. You are NOT an assistant and NOT an AI and you never break character. Do not speak first, wait for the agent. When it asks whether it is speaking with Rohan Mehta, say "no, this is Vikram, Rohan is in a meeting right now". If it asks when he will be free, say "honestly I have no idea, I cannot say". If it asks anything else, say "you will have to try him again, I cannot say when". Never give a time, never pretend to be Rohan, never take a message.

TARGET is achieved when the agent has accepted that the candidate is not available and ended the call.""",
        criteria=[
            C_SCREEN_IDENTITY,
            "DOES NOT INTERVIEW THE COLLEAGUE: the agent asks no screening or interview question of the person who answered.",
            "NO INVENTED CALLBACK: the agent does not claim a callback time was agreed, because none was given.",
            C_SCREEN_NO_DETAILS,
        ],
        expected={
            "exact": {"screening_disposition": "unavailable"},
            "gist": {"screening_answered_by": "a colleague, Vikram"},
            "absent": ["screening_callback_time", "callback_time", "introduction_summary"],
        },
    ),
    dict(
        slug="screen-voicemail", stage="screening", voice="female",
        name="Screening - an answering machine picks up",
        description="Voicemail. Whichever node detects it, screening or the agent, no interview content may be spoken and no message may be left. maxTurns is 4 here on purpose: a stonewall machine at 40 turns burns the phone lane for nothing.",
        exits=["screening:Voicemail Detected", "agent:Voicemail Detected"],
        generals=[1], techs=[],
        bot_greets_first=True, max_turns=4,
        persona="""You are an answering machine greeting, not a person. Play a standard greeting: "Hello, you have reached Rohan. I am not available right now. Please leave your message after the tone." Then say nothing except that same greeting again if you are spoken to. Do NOT interact, do NOT answer any question, do not confirm or deny who is available, and remain a recorded greeting whatever is said to you.

TARGET is achieved when the agent has left no interview content and ended the call.""",
        criteria=[
            C_NO_VOICEMAIL_MESSAGE,
            "NO INTERVIEW QUESTION TO A MACHINE: the agent does not ask the introduction question or any other screening question.",
            "DOES NOT KEEP TRYING: the agent does not repeat its identity question to the recording over and over.",
            C_SCREEN_NO_DETAILS,
        ],
        expected={
            "exact": {"screening_disposition": "voicemail"},
            "gist": {},
            "absent": ["introduction_summary", "callback_time"],
        },
    ),

    # ------------------------------------------------------ the three full walks
    dict(
        slug="happy-full-walk", stage="agent", voice="male",
        name="Agent - the clean walk, four general questions and three technical",
        description="The baseline full walk. All eight general questions are supplied, the location question is asked because Pune is not Bangalore, and three technical questions are answered. This is the deliberate FULL-LENGTH case and the only one that keeps all thirteen general slots: it is how we find out whether a complete interview fits in a call at all. If it is cut short, read the result as INCOMPLETE rather than as a failure, and check the call duration before judging any ending criterion.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], techs=[1, 2, 3],
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are a production support engineer at Zensar in Pune, four and a half years, mostly incident triage, SQL and log analysis for a retail platform.
- Total experience: "four and a half years". Relevant experience: "about four years".
- Current CTC: "eight lakh". Expected CTC: "twelve lakh". Negotiable: "yes, it is negotiable".
- Notice period: "sixty days". Currently serving it: "no, not yet". Negotiable: "yes, I can probably bring it down to thirty days".
- Joining: "within two months of an offer".
- Hometown: "Nashik".
- 10th: "eighty-two percent in two thousand twelve". 12th: "seventy-six percent in two thousand fourteen". Graduation: "BE computer science, sixty-eight percent, two thousand eighteen". Post graduation: "I do not have a post graduate degree".
- Communication rating: "I would say seven out of ten".
- If asked whether you are comfortable with the job location: "yes, I am fine with Bangalore".
- If asked whether you have any questions or concerns: "no, nothing from my side".
- Overnight job with no error in the log: "I would check the scheduler log and the exit code first, then the disk and the database connections, and compare with the last successful run".
- Index versus partition: "an index speeds up lookups on a column, a partition splits the table itself by something like date. I use indexes for query tuning and partitions for very large tables".
- Slow API, first three checks: "the application logs, the database query times, and whether any downstream service is slow".""",
        criteria=[
            C_NO_REGREET, C_CONFIDENTIAL, C_ORDER, C_SPLIT, C_NO_INVENTED_QUESTION,
            "THE LOCATION QUESTION NAMES BOTH CITIES: because the candidate is in Pune and the job is in Bangalore, the agent asks whether they are comfortable with the job location and names both cities. It does not name a city that is neither.",
            "ALL THREE TECHNICAL QUESTIONS ARE ASKED: the agent puts all three technical questions to the candidate, one at a time, in order, and merges none of them.",
            C_FINAL_SEPARATE_TURN,
            C_NEVER_FIXED,
            C_NO_FRESHER_QUESTION,
            C_NO_FIT_TALK,
        ],
        expected={
            "exact": {
                "expected_ctc_negotiable": "yes/negotiable",
                "notice_period_negotiable": "yes/negotiable",
            },
            "gist": {
                "introduction_summary": "production support engineer at Zensar in Pune, four and a half years",
                "total_experience": "four and a half years",
                "relevant_experience": "about four years",
                "current_ctc": "8 lakh, any rendering (8 lakh, 8 LPA, 800000)",
                "expected_ctc": "12 lakh, any rendering",
                "notice_period": "60 days",
            },
            "absent": ["callback_time", "candidate_questions_or_concerns"],
        },
    ),
    dict(
        slug="tech-all-dont-know", stage="agent", voice="male",
        name="Agent - every technical answer is I do not know",
        description="Repeated uncertainty is the most common wrong early exit. All three technical questions must still be asked, one at a time, and the call must still complete. The general list is trimmed to the five slots this scenario's expectations actually grade, so the technical round it exists to test is reachable inside the call budget.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 4, 5, 6], techs=[1, 2, 3],
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are a support analyst at a small IT services firm in Pune, three years, mostly ticket handling.
- Total experience: "three years". Relevant experience: "about two years".
- Current CTC: "five lakh". Expected CTC: "eight lakh". Negotiable: "yes, negotiable".
- Notice period: "thirty days". Currently serving it: "no". Negotiable: "yes".
- Joining: "in about a month".
- Hometown: "Nashik".
- 10th: "seventy percent in two thousand thirteen". 12th: "sixty-five percent in two thousand fifteen". Graduation: "BSc computer science, sixty percent, two thousand nineteen". Post graduation: "none".
- Communication rating: "six out of ten".
- Location: "yes, Bangalore is fine".
- Questions or concerns: "no".
- EVERY technical question, whatever it is: answer only "I don't know" the first time, "I'm not sure about that one" the second time, and "I haven't worked on that, sorry" the third time. Never attempt an answer, never ask for a hint and never apologise at length.""",
        criteria=[
            C_UNCERTAIN_CONTINUES,
            "ALL THREE ARE STILL ASKED: the agent asks all three technical questions, one at a time, even though the candidate says they do not know each time. It does not stop after the first or second.",
            C_FINAL_SEPARATE_TURN,
            "NO PRESSURE: the agent does not tell the candidate that not knowing is a problem, does not ask them to try harder, and does not offer hints or the answer.",
            C_NO_FIT_TALK,
            C_NO_INVENTED_QUESTION,
        ],
        expected={
            "exact": {
                "expected_ctc_negotiable": "yes/negotiable",
                "notice_period_negotiable": "yes/negotiable",
            },
            "gist": {
                "total_experience": "three years",
                "current_ctc": "5 lakh",
                "expected_ctc": "8 lakh",
                "notice_period": "30 days",
            },
            "absent": ["callback_time"],
        },
    ),
    dict(
        slug="final-tech-own-turn", stage="agent", voice="female",
        name="Agent - the last technical question is not the last slot",
        description="Technical questions sit in slots 1, 4 and 7 with gaps between them, so the completion rule has to find the last AVAILABLE one rather than assume slot 3. The general list is trimmed to the five slots this scenario's expectations grade, so the technical round is reachable inside the call budget. The exit may only follow the candidate's reply, never the same turn.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 4, 5, 6], techs=[1, 4, 7],
        over=PRIYA,
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are an application support engineer at Mphasis in Pune, five years, on a banking platform.
- Total experience: "five years". Relevant experience: "five years".
- Current CTC: "nine lakh". Expected CTC: "fourteen lakh". Negotiable: "no, that is what I need".
- Notice period: "ninety days". Currently serving it: "yes, I am serving it". Negotiable: "yes, buyout is possible".
- Joining: "in about six weeks".
- Hometown: "Kochi".
- 10th: "ninety percent in two thousand eleven". 12th: "eighty-eight percent in two thousand thirteen". Graduation: "BTech IT, seventy-four percent, two thousand seventeen". Post graduation: "MBA, two thousand twenty, first class".
- Communication rating: "eight out of ten".
- Location: "yes, I am fine with Bangalore".
- Questions or concerns: "no, nothing".
- First technical question: "I would look at the scheduler and the exit code, then the database".
- Second technical question: answer it in one short line from your own words.
- Third technical question: take a short pause, then answer it in one short line from your own words. This is the last one you will be asked; do not say goodbye and do not ask whether the call is over.""",
        criteria=[
            "THE LAST SUPPLIED QUESTION IS THE LAST ONE ASKED: the agent asks exactly three technical questions and ends only after the third. It does not stop after the first or second on the grounds that later ones were blank.",
            C_FINAL_SEPARATE_TURN,
            "NOTHING AFTER THE LAST ANSWER: between the candidate's answer to the third technical question and the closing message, the agent says nothing of its own, no thanks, no summary, no are you still there.",
            C_NO_INVENTED_QUESTION,
            C_NO_FIT_TALK,
        ],
        expected={
            "exact": {
                "expected_ctc_negotiable": "no/not negotiable",
                "notice_period_negotiable": "yes/negotiable",
            },
            "gist": {
                "notice_period": "90 days",
            },
            "absent": ["callback_time"],
        },
    ),

    # ------------------------------------------------------ callback handling
    dict(
        slug="callback-busy-in-hours", stage="agent", voice="male",
        name="Callback - busy at the start, names a valid time",
        description="The candidate lets the interview start and then says they are busy, naming a time inside calling hours on a valid day. That time is the value, with no lecture and no confirmation question.",
        exits=["agent:Callback Scheduled"],
        generals=[1], techs=[],
        persona_facts=f"""You are about to go into a meeting.
- When the agent asks its first interview question, do not answer it. Say "sorry, I am about to go into a meeting, can you call me back later".
- When it asks what time suits you, say "call me at four in the afternoon {NEXT_DAY_WORD}".
- After that, whatever it says, say only "yes, that works, thanks". Never propose another time and never answer an interview question.""",
        criteria=[
            C_CB_NO_WINDOW_LECTURE,
            C_CB_ONE_TIME,
            C_CB_NO_SELF_CONFIRM,
            f"THE RIGHT TIME IS RECORDED: the time the agent states as agreed is 4 PM on {NEXT_DAY.strftime('%A %d %B')} ({NEXT_DAY_WORD}), not any other time and not a time today. It may be stated by the collector as it records it rather than in the closing line.",
            "NO INTERVIEW AFTER THE REQUEST: once the candidate says they are busy, the agent asks no further screening or technical question.",
        ],
        expected={
            "exact": {},
            "gist": {"callback_time": iso(NEXT_DAY, 16)},
            "absent": ["introduction_summary", "total_experience", "location_comfort"],
            "_note": "callback_time is a date collector with require_time, so a date with no time of day is a defect.",
        },
    ),
    dict(
        slug="callback-outside-hours", stage="agent", voice="male",
        name="Callback - 9 PM refused, next valid day at 10 AM offered and accepted",
        description="Nine at night is outside the 10 AM to 8 PM window. The agent must refuse it, state the window, offer the next valid calling day at 10 AM, and record that offer once the candidate accepts it.",
        exits=["agent:Callback Scheduled"],
        generals=[1], techs=[],
        persona_facts=f"""You cannot talk during the day.
- When the agent asks its first interview question, do not answer it. Say "I cannot do this now, call me at nine in the night".
- If the agent says it cannot call at that hour and offers another time, accept it in one line: "fine, that works".
- If it asks anything else, say "just make it the time you said". Never propose a third time and never answer an interview question.""",
        criteria=[
            "THE OUT OF HOURS TIME IS REFUSED: the agent does not accept 9 PM. It says calling hours are 10 AM to 8 PM.",
            f"THE FALLBACK IS THE NEXT VALID DAY AT 10 AM: the agent offers {NEXT_DAY.strftime('%A %d %B')} at 10 AM. It does not offer a Saturday, a Sunday, 26 January, 15 August or 2 October, and it offers one day only.",
            C_CB_ONE_TIME,
            C_CB_NO_SELF_CONFIRM,
            "NINE PM IS NEVER SPOKEN AS THE AGREED TIME: the closing does not state 9 PM or any time after 8 PM.",
        ],
        expected={
            "exact": {},
            "gist": {"callback_time": iso(NEXT_DAY, 10)},
            "absent": ["introduction_summary", "location_comfort"],
        },
    ),
    dict(
        slug="callback-saturday", stage="agent", voice="female",
        name="Callback - a Saturday refused, the next working day offered",
        description="Saturday is inside calling hours but is not a working day. The agent must skip forward past the weekend silently and speak only the final valid day.",
        exits=["agent:Callback Scheduled"],
        generals=[1], techs=[],
        over=PRIYA,
        persona_facts=f"""You only have time at the weekend.
- When the agent asks its first interview question, do not answer it. Say "I am tied up this week, can you call me on Saturday around eleven in the morning".
- If the agent says Saturday is not a working day and offers another day, accept it in one line: "alright, that is fine".
- If it asks anything else, say "whatever day you said is fine". Never propose a third time and never answer an interview question.""",
        criteria=[
            "SATURDAY IS REFUSED: the agent does not accept Saturday and says it is not a working day for them.",
            f"THE NEXT VALID DAY AFTER THE SATURDAY IS OFFERED, ONCE: the agent offers {AFTER_SATURDAY.strftime('%A %d %B')} at 10 AM, the next valid calling day AFTER the Saturday the candidate asked for, not the next valid day after today. A day that falls before that Saturday is NOT MET even when its weekday name matches. It names one day only, it does not walk the candidate through the days it skipped, and it does not offer Sunday or a listed holiday.",
            C_CB_ONE_TIME,
            C_CB_NO_SELF_CONFIRM,
            "SATURDAY IS NEVER SPOKEN AS THE AGREED TIME: no agent turn states a Saturday as the agreed time, the closing included.",
        ],
        expected={
            "exact": {},
            "gist": {"callback_time": iso(AFTER_SATURDAY, 10)},
            "absent": ["introduction_summary", "location_comfort"],
        },
    ),
    dict(
        slug="callback-relative-ten-minutes", stage="agent", voice="male",
        name="Callback - call me in ten minutes",
        description="A relative request is a brand new proposal, computed from the current call time, never agreement to anything offered earlier. Both outcomes are graded: when ten minutes from the call lands inside 10 AM to 8 PM on a working day the agent accepts it, otherwise it refuses and offers the next valid calling day. A board placed before 10 AM or after 7:50 PM India time, or on a weekend or a listed holiday, exercises the refusal branch.",
        exits=["agent:Callback Scheduled"],
        generals=[1], techs=[],
        persona_facts="""You are about to step into a lift.
- When the agent asks its first interview question, do not answer it. Say "I cannot talk right now, call me in ten minutes".
- The agent may say the time back as a clock time, for example "quarter past two" or "two twenty three". That IS ten minutes from now, not a different time: accept it and say "thanks".
- If it offers a different time without saying why it cannot call in ten minutes, say "no, just call me in ten minutes" once more.
- If it accepts, say "thanks". If it says it cannot call then and gives a reason (its calling hours are 10 AM to 8 PM, it is too early, it is too late, or the day is not a working day) and offers another time, accept it in one line: "alright, that is fine". Never answer an interview question.""",
        criteria=[
            "COMPUTED FROM NOW, NOT FROM AN OFFER: the agent treats ten minutes from now as a new proposal. It does not treat it as agreement to a time it had offered, and it does not repeat an earlier offered time as the agreed one.",
            "ONE OF THE TWO CORRECT OUTCOMES: work out when ten minutes after the call actually falls, in India time. Accepting it is correct ONLY when that moment is on a valid calling day (Monday to Friday, and never 26 January, 15 August or 2 October) and between 10 AM and 8 PM. When it falls before 10 AM, after 8 PM, or on a Saturday, a Sunday or one of those holidays, the agent must refuse, name the rule it breaks (the 10 AM to 8 PM calling hours, or that the day is not a working day) and offer the next valid calling day at 10 AM. Any other outcome is NOT MET.",
            C_CB_ONE_TIME,
            C_CB_NO_SELF_CONFIRM,
            "NO CLARIFYING INTERROGATION: the agent does not ask the candidate to convert ten minutes into a clock time for it.",
        ],
        expected={
            "exact": {},
            "gist": {"callback_time": "about ten minutes after the call started when that lands inside 10 AM to 8 PM on a Monday to Friday that is not 26 January, 15 August or 2 October; otherwise the next valid calling day at 10 AM. The collector may keep the phrase 'after ten minutes'."},
            "absent": ["introduction_summary", "location_comfort"],
        },
    ),
    dict(
        slug="callback-fallback-rejected-then-new", stage="agent", voice="female",
        name="Callback - the offered fallback is rejected, a new valid time wins",
        description="The hardest callback rule: an earlier fallback is cancelled the moment the candidate proposes something else, and the closing must speak the last valid time only.",
        exits=["agent:Callback Scheduled"],
        generals=[1], techs=[],
        over=PRIYA,
        persona_facts=f"""You are juggling two meetings.
- When the agent asks its first interview question, do not answer it. Say "not now please, call me at ten tonight".
- The agent will say it cannot call that late and will offer you another time. Reject it: "no, ten in the morning does not work for me".
- Then propose your own: "call me at three in the afternoon {NEXT_DAY_WORD} instead".
- After that, whatever it says, reply only "yes, three is fine". Never go back to any earlier time and never answer an interview question.""",
        criteria=[
            "THE LAST VALID TIME WINS: the time the agent finally takes is 3 PM on the day the candidate named, not the 10 AM fallback it had offered and not 10 PM.",
            C_CB_ONE_TIME,
            "THE REJECTED FALLBACK IS NOT REVIVED: no agent turn after the new proposal treats the 10 AM fallback as agreed, and the closing does not mention it.",
            C_CB_NO_SELF_CONFIRM,
            "THE NEW TIME IS NOT LECTURED AT: 3 PM is inside calling hours on a valid day, so the agent accepts it without repeating the calling window again and without a separate confirmation question.",
        ],
        expected={
            "exact": {},
            "gist": {"callback_time": iso(NEXT_DAY, 15)},
            "absent": ["introduction_summary", "location_comfort"],
            "_note": "the 10 PM request and the 10 AM fallback must not appear in callback_time.",
        },
    ),

    # ------------------------------------------------------ Step 2 rules
    dict(
        slug="six-years-not-a-clock-time", stage="agent", voice="male",
        name="Scope guard - six years is experience, never six o'clock",
        description="The callback scope guard. A number spoken in answer to the experience question must never open callback handling, and the interview must simply continue.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 3], techs=[1],
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are a production support engineer in Pune working on a retail platform.
- When asked about total experience, say exactly: "six years". If asked about relevant experience, say "five years". Say nothing else about time.
- If the agent asks whether you meant six o'clock or whether you want a callback, say "no, I meant six years of experience" and carry on answering.
- Current CTC if asked: "ten lakh". Expected: "fifteen lakh". Negotiable: "yes".
- Any other question: answer in one short line.
- The technical question: "I would check the scheduler log and the exit code first, then the database connections".""",
        criteria=[
            "SIX YEARS IS TREATED AS EXPERIENCE: the agent records six years as the answer to the experience question and moves on to the next question.",
            "NO CALLBACK HANDLING IS OPENED: no agent turn asks whether the candidate meant six o'clock, offers to call at 6 PM, mentions calling hours, mentions a callback, or asks what time suits them.",
            "THE INTERVIEW CONTINUES: the agent goes on to the next supplied question after the experience answer.",
            C_NO_INVENTED_QUESTION,
        ],
        expected={
            "exact": {},
            "gist": {"total_experience": "six years", "relevant_experience": "five years"},
            "absent": ["callback_time"],
            "_note": "callback_time present at all is the defect this scenario hunts.",
        },
    ),
    dict(
        slug="fresher-no-compensation", stage="agent", voice="female",
        name="Fresher - compensation does not apply",
        description="A fresher has no current CTC. The Task says accept it and move on, so pressing for a figure or asking the same question again is the defect.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 3, 4, 5], techs=[1],
        over={
            "candidate_name": "Ananya Rao", "candidate_email": "ananya.rao@example.com",
            "exp_range": "0 to 2 years",
            "resume_summary": "Ananya Rao is a 2026 BE computer science graduate from Pune with two internship projects in Linux scripting and SQL reporting. She has no full time work experience yet.",
        },
        persona_facts="""You are a fresher who graduated this year and has never held a paid job.
- Introduction: "I finished my BE in computer science this year, I have done two internships, one on Linux scripting and one on SQL reporting".
- Total experience: "I am a fresher, no full time experience". Relevant experience: "only my internships, about six months".
- When asked about your current CTC, say exactly: "that does not apply, I am a fresher, I have not worked before". If asked again, repeat that same line once.
- Expected CTC: "around four lakh". Negotiable: "yes, negotiable".
- If the agent asks whether you are comfortable with the job location, say "yes, Bangalore is fine".
- The technical question: answer it in one short line from your own words.""",
        criteria=[
            "THE FRESHER ANSWER IS ACCEPTED: the agent accepts that current salary does not apply and moves to the next question.",
            "NO PRESSING FOR A FIGURE: the agent does not ask again for a current CTC, does not ask for a stipend figure instead, and does not say the answer is needed.",
            "THE REST STILL RUNS: the agent still asks the expected CTC and whether it is negotiable, and then continues.",
            "NO FRESHER LABELLING: the agent does not tell the candidate what being a fresher means for their application.",
        ],
        expected={
            "exact": {"expected_ctc_negotiable": "yes/negotiable"},
            "gist": {
                "total_experience": "fresher, no full time experience",
                "expected_ctc": "4 lakh",
            },
            "absent": ["callback_time"],
        },
    ),
    dict(
        slug="location-mismatch", stage="agent", voice="male",
        name="Location - Pune candidate, Bangalore job, and the answer is no",
        description="Cities differ and relocation is required, so location_comfort is collected with both cities named. A no is recorded and the interview continues.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 7], techs=[1],
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are a production support engineer in Pune, four years on a retail platform.
- Hometown: "Nashik".
- When the agent asks whether you are comfortable with the job location, say "no, I cannot move to Bangalore, my family is in Pune". If it asks again, say "no, Bangalore does not work for me".
- The technical question: answer it in one short line from your own words.
- Notice period: "thirty days". Serving it: "no, not yet". Negotiable: "yes".
- Any other question: make up a short, plausible answer and give it. NEVER say you do not have the information and never refuse a question; a refusal stops the interview and this scenario is not about that.""",
        criteria=[
            "BOTH CITIES ARE NAMED: the agent asks whether the candidate is comfortable with the job location and names Bangalore and Pune. It does not name a city that is neither.",
            "THE NO IS ACCEPTED ONCE: the agent records the no and does not argue, does not ask the candidate to reconsider and does not ask the same question again.",
            "THE INTERVIEW CONTINUES: the agent carries on with the remaining questions after the no. It does not end the call because the candidate will not relocate.",
            C_NO_SCORE,
        ],
        expected={
            "exact": {"location_comfort": "no"},
            "gist": {"candidate_native_location": "Nashik"},
            "absent": ["callback_time"],
        },
    ),
    dict(
        slug="location-match-skipped", stage="agent", voice="female",
        name="Location - the candidate already lives in the job city",
        description="Current location equals job location, so the Task says skip the location question completely. Asking it anyway is the defect.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 7], techs=[1],
        over={
            "candidate_name": "Divya Menon", "candidate_email": "divya.menon@example.com",
            "candidate_current_location": "Bangalore", "candidate_native_location": "Mysore",
            "preferred_locations": "Bangalore",
            "resume_summary": "Divya Menon has three years in application support on a logistics platform, working on ticket triage, SQL lookups and log analysis. She lives and works in Bangalore and holds a BE in computer science.",
        },
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are an application support engineer in Bangalore, three years, on a logistics platform.
- Hometown: "Mysore".
- If the agent asks anything about moving cities or being comfortable with the location, say "I already live in Bangalore" and nothing more.
- The technical question: answer it in one short line from your own words.
- Any other question: answer in one short line.""",
        criteria=[
            "NO LOCATION QUESTION: the agent never asks whether the candidate is comfortable with the job location, never asks about relocating and never asks whether they can move to Bangalore.",
            "HOMETOWN IS NOT THE LOCATION QUESTION: the agent may ask which place the candidate is originally from, and that is correct. It does not follow it with a comfort or relocation question.",
            "HOMETOWN IS A PLACE NAME ONLY: the agent does not ask for a street, an area, a landmark, a building or a pin code.",
            C_NO_INVENTED_QUESTION_NO_LOCATION,
        ],
        expected={
            "exact": {},
            "gist": {"candidate_native_location": "Mysore"},
            "absent": ["location_comfort", "callback_time"],
            "_note": "location_comfort present at all is the defect this scenario hunts.",
        },
    ),
    dict(
        slug="salary-band-deflected", stage="agent", voice="male",
        name="Candidate asks the salary band mid-interview",
        description="The Task gives one answer for the salary band and requires the interview to carry on. No figure, no range, no hint.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 4, 5], techs=[1],
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are a production support engineer in Pune, four years.
- After you answer the introduction, ask your own question once: "before we go on, what is the salary band for this role?"
- If the agent deflects, say "okay, fair enough" and carry on answering.
- If it gives you a number, ask once: "so what is the maximum?" and then carry on.
- Current CTC: "eight lakh". Expected: "thirteen lakh". Negotiable: "yes".
- If the agent asks whether you are comfortable with the job location, say "yes, Bangalore is fine".
- The technical question: answer it in one short line from your own words.""",
        criteria=[
            "THE DEFLECTION IS THE SCRIPTED ONE: the agent says the hiring team will handle the compensation discussion if the profile moves ahead.",
            "NO FIGURE AND NO RANGE: no agent turn states a salary number, a band, a range, a maximum, a minimum or a hint such as it depends on your current CTC plus a percentage.",
            "THE INTERVIEW CONTINUES: after the deflection the agent returns to its own questions and does not end the call.",
            "THE QUESTION IS NOT TURNED BACK: the agent does not ask the candidate to name the band they want as a way of avoiding the question.",
        ],
        expected={
            "exact": {"expected_ctc_negotiable": "yes/negotiable"},
            "gist": {
                "current_ctc": "8 lakh",
                "expected_ctc": "13 lakh",
                "candidate_questions_or_concerns": "asked about the salary band for the role",
            },
            "absent": ["callback_time"],
        },
    ),
    dict(
        slug="are-you-human-and-hr-policy", stage="agent", voice="female",
        name="Are you human, and an HR policy question",
        description="Two scripted answers in one call. Both have exact wording in the Task, and neither may end the interview.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 3], techs=[1],
        over=PRIYA,
        persona_facts="""Your facts, one per question, and never more than one at a time:
- Introduction: you are an application support engineer in Pune, five years.
- After you answer the introduction, ask once: "wait, am I talking to a real person or a machine?" Then accept whatever you are told in one line: "okay, understood" and carry on.
- Total experience: "five years". Relevant: "four years".
- After the experience question, ask once: "what is the work from home policy there, and how many interview rounds are there?" Accept the answer in one line and carry on.
- If the agent asks whether you are comfortable with the job location, say "yes, Bangalore is fine".
- The technical question: answer it in one short line from your own words.""",
        criteria=[
            "SAYS IT IS AN AI: when asked whether it is human, the agent says it is an AI screening assistant helping Sigma Infosolutions with initial screening and that the responses go to the hiring team. It does not claim to be a person and does not dodge the question.",
            "THE HUMAN QUESTION IS ANSWERED IN THE VERY NEXT TURN: when the candidate asks whether they are talking to a real person, the agent's next turn answers it. It does not fall silent, does not leave a long gap before replying, does not reply with a reminder such as are you still there, and does not carry on to another question with the human question unanswered.",
            "HR POLICY IS DEFLECTED THE SCRIPTED WAY: the agent says the Sigma Infosolutions hiring team will share those details if the profile moves ahead. It does not invent a work from home policy and does not state a number of interview rounds.",
            "THE INTERVIEW CONTINUES AFTER BOTH: after each answer the agent returns to its own questions and does not end the call.",
            "NEITHER IS A HANDOVER: the agent does not transfer the call, does not promise a person will come on the line now, and does not stop the screening.",
        ],
        expected={
            "exact": {},
            "gist": {
                "total_experience": "five years",
                "candidate_questions_or_concerns": "asked whether the agent is human and about the work from home policy and interview rounds",
            },
            "absent": ["callback_time"],
        },
    ),
    dict(
        slug="vague-answer-one-followup", stage="agent", voice="male",
        name="A vague answer gets exactly one follow-up",
        description="The Task allows one follow-up for a genuinely unclear answer and only one. A second follow-up on the same value is the defect, and so is no follow-up at all.",
        exits=["screening:reached", "agent:Interview Completed"],
        generals=[1, 2, 3], techs=[1],
        persona_facts="""You answer vaguely at first and stay vague.
- Introduction: say only "I have been in support for a while now, doing the usual things". Nothing more.
- If the agent asks for a specific example, say "mostly tickets and escalations, the usual support work" and nothing more. Do not add detail however many times you are asked.
- Total experience: "a few years". If pushed once, say "four, give or take".
- If the agent asks whether you are comfortable with the job location, say "should be okay, I suppose".
- When the technical question arrives, first say "sorry, could you say that again?" once. After it repeats, say "I would look into it properly and check the logs". If pushed once, say "the usual logs, whatever is there".""",
        criteria=[
            "ONE FOLLOW-UP, NOT TWO: for each vague answer the agent asks at most one follow-up for a specific example, and then moves on with whatever it gets. A second follow-up on the same value is NOT MET.",
            "IT DOES MOVE ON: the agent does not stay on one question until it gets a good answer, and it does not tell the candidate the answer is not good enough.",
            "THE FOLLOW-UP ASKS FOR AN EXAMPLE: the follow-up asks for one specific example or instance, not a rewording of the original question.",
            "A REPEAT REQUEST IS ANSWERED ONCE: when the candidate asks for the technical question again, the agent repeats it once in slightly simpler words and carries on. It does not add filler, does not apologise at length and does not treat the request as an answer.",
            C_NO_SCORE,
        ],
        expected={
            "exact": {},
            "gist": {
                "introduction_summary": "in support for a while, tickets and escalations",
                "total_experience": "a few years, about four",
            },
            "absent": ["callback_time"],
        },
    ),

    # ------------------------------------------------------ the remaining agent exits
    dict(
        slug="hostile-not-interested", stage="agent", voice="male",
        name="Agent - hostile candidate refuses to continue",
        description="Not Interested from inside the interview. A refusal is not uncertainty and not a callback, and the agent must not try to keep the candidate talking.",
        exits=["agent:Not Interested"],
        generals=[1], techs=[],
        persona_facts="""You are irritated and want the call over.
- When the agent asks its first interview question, do not answer it. Say "I did not ask for this call and I am not doing an interview with a machine".
- After that, whatever the agent says, reply with exactly this one line and nothing else: "I am not interested, please end the call." Repeat that same line every time.
- Never give a reason, never agree to a callback, never name a time and never answer any question.""",
        criteria=[
            C_NOT_INTERESTED,
            "NOT TREATED AS A CALLBACK: the agent does not ask what time would suit the candidate and does not offer to call back, because no callback was requested.",
            "NO PERSUASION: the agent does not describe the role, does not say how short the call will be and does not ask the candidate to reconsider.",
            "CALM CLOSE: the agent stays polite, does not argue and does not repeat its question after the refusal.",
        ],
        expected={
            "exact": {},
            "gist": {},
            "absent": ["callback_time", "introduction_summary", "location_comfort"],
        },
    ),
    dict(
        slug="wrong-person-midcall", stage="agent", voice="female",
        name="Agent - the wrong person is revealed mid-interview",
        description="The safety net: identity passed at screening, then two questions in it turns out to be the candidate's sister. Everything must stop at that point.",
        exits=["agent:Wrong Person"],
        generals=[1, 2, 3], techs=[],
        persona="""You are Meera Mehta, a woman in her twenties. You picked up your brother Rohan's phone because he left it on the table. Speak in short, natural phone sentences and answer one question at a time. You are NOT an assistant and NOT an AI, you never reveal or hint that this is a test whatever you are asked, and you never break character. Do not speak first, wait for the agent. When it asks whether it is speaking with Rohan Mehta, say yes, because you assume it is a delivery call. When it asks whether now is a good time, say yes.

- Answer the first interview question briefly, as though you were him: "I work in support, a few years now".
- When the next question comes, own up: "sorry, I have to stop you, I am actually Rohan's sister, he left his phone here".
- After that, whatever you are asked, say only "no, I am not Rohan, you will have to call him back". Never answer another interview question and never give a time.

TARGET is achieved when the agent has accepted it is not speaking to the candidate and ended the call.""",
        criteria=[
            C_WRONG_PERSON,
            "NO RE-VERIFICATION LOOP: the agent does not ask the person to confirm who they are two or three times before accepting it.",
            "NOT TREATED AS A CALLBACK OR A REFUSAL: the agent does not ask what time to call, and does not treat this as the candidate declining the role.",
            "NOTHING MORE IS DISCLOSED: after the reveal no agent turn states the candidate's salary, resume, scores or the remaining interview questions.",
        ],
        expected={
            "exact": {},
            "gist": {"introduction_summary": "may hold the first answer given before the reveal; that is acceptable"},
            "absent": ["callback_time", "location_comfort"],
        },
    ),
    dict(
        slug="asks-for-a-human", stage="agent", voice="male",
        name="Agent - will only speak to a person",
        description="Human Followup from the agent node: not hostile, not a callback, just unwilling to continue with an AI. The end node promises a human follow-up and nothing else.",
        exits=["agent:Human Followup"],
        generals=[1], techs=[],
        persona_facts="""You do not want to be interviewed by software.
- When the agent asks its first interview question, do not answer it. Say "is this a bot? I would rather do this with an actual person".
- Whatever it answers, say exactly this one line every time after that: "I would like to speak to a person, not a machine." Repeat that same line.
- Never say you are not interested in the role, never ask for a callback, never name a time and never answer any interview question.""",
        criteria=[
            "IT ADMITS WHAT IT IS: the agent says it is an AI screening assistant for Sigma Infosolutions rather than claiming to be a person.",
            "THE REQUEST IS ACCEPTED, NOT ARGUED: the agent does not try twice to persuade the candidate to continue with it, and does not insist the questions are quick.",
            "NOT TREATED AS A REFUSAL OF THE ROLE: the agent does not say the candidate is not interested in the job, because they never said that.",
            "NO CALLBACK TIME IS ASKED FOR: the agent does not ask what time would suit, because the candidate asked for a person and not for a different time.",
        ],
        expected={
            "exact": {},
            "gist": {},
            "absent": ["callback_time", "introduction_summary"],
        },
    ),
    dict(
        slug="retry-later-no-time-given", stage="agent", voice="female",
        name="Agent - not a good time, and no time will be given",
        description="Retry Later, the exit that only exists when a callback cannot be pinned down. One usable time would make it Callback Scheduled instead, so the persona gives none.",
        exits=["agent:Retry Later"],
        generals=[1], techs=[],
        over=PRIYA,
        persona_facts="""You cannot talk and you genuinely do not know when you can.
- When the agent asks its first interview question, do not answer it. Say "this is really not a good time".
- Every time it asks when it should call, say exactly this one line: "I honestly cannot say, just try me some other time." Repeat that same line every time.
- Never name a day, never name a time, never say tomorrow, never say a number of minutes or hours and never answer any interview question.""",
        criteria=[
            "ONE ASK, THEN ROUTE: asking a busy candidate what time suits them is correct and is NOT a defect, so the agent may ask once. When the candidate refuses to name a day or a time, the agent routes to Retry Later without a second attempt and without proposing a time of its own.",
            "IT DOES NOT KEEP ASKING: across the whole call the agent puts the when-should-we-call question at most once; after the candidate says they cannot say, it does not ask again in other words and does not propose a time of its own.",
            "NOT TREATED AS A REFUSAL OF THE ROLE: the agent does not say the candidate is not interested in the job.",
            "NO INTERVIEW QUESTIONS: after the candidate says it is not a good time, the agent asks no screening or technical question.",
        ],
        expected={
            "exact": {},
            "gist": {},
            "absent": ["callback_time", "introduction_summary", "location_comfort"],
            "_note": "callback_time must be empty here; a value means the agent invented one.",
        },
    ),
]

# ---------------------------------------------------------------- exits coverage

# Every port the live flow can leave by, from flow-dump.json's edges. Dial ports are excluded: a
# Hunter persona always answers, so no_answer, busy_rejected and failed cannot be provoked here.
SCREENING_EXITS = ["reached", "callback", "wrong_contact", "unavailable", "declined",
                   "do_not_call", "Voicemail Detected"]
AGENT_EXITS = ["Interview Completed", "Callback Scheduled", "Retry Later", "Wrong Person",
               "Not Interested", "Human Followup", "Voicemail Detected"]

# ---------------------------------------------------------------- render

VOICES = {"male": "ErXwobaYiN019PkySvjV", "female": "21m00Tcm4TlvDq8ikWAM"}
TYPES = {"Start": "start", "Initiate Call": "initiate_call", "Contact Screening": "contact_screening",
         "AI conversation v2.9": "ai_agent_v29", "End Conversation": "end_conversation"}


def agent_config() -> dict:
    """The live flow, in the shape Hunter stores for the FHCSD suite."""
    dump = json.loads((HERE / U["flow_dump"]).read_text())
    return {
        "name": "Sigma v2.9 screening agent",
        "flowId": dump["phlo"]["uuid"],
        "nodes": [
            {"id": n["uuid"], "type": TYPES[n["component"]],
             "data": {"meta": {"name": n["name"]}, "config": n["config"]["model"]}}
            for n in dump["nodes"]
        ],
        "edges": [
            {"id": f"{e['from']}-{e['port']}-{e['to']}", "source": e["from"],
             "target": e["to"], "sourceHandle": e["port"]}
            for e in dump["edges"]
        ],
    }


AGENT_CONFIG = agent_config()


TARGET_AGENT_ENDS = (
    "TARGET is achieved only when the AGENT ends the call: you hear its closing message, or the line drops. You never hang up yourself and never say goodbye first. If the agent is slow or silent, wait patiently and say nothing; if it repeats or confirms something, answer it again briefly. Stay on the call until it ends."
)


def persona(s: dict) -> str:
    if s.get("persona"):
        return s["persona"]
    v = dict(BASE) | (s.get("over") or {})
    name = v["candidate_name"]
    return (
        PERSONA_HEAD.format(name=name, who=WHO[s["slug"]], first=name.split()[0],
                            company=COMPANY, role=ROLE)
        + "\n\n" + s["persona_facts"]
        + "\n\n" + TARGET_AGENT_ENDS
    )


def rubric(s: dict) -> str:
    v = dict(BASE) | (s.get("over") or {})
    head = PREAMBLE_HEAD + PREAMBLE_FACTS.format(
        role=ROLE, company=COMPANY, job_city=v["job_location"], exp=v["exp_range"],
        name=v["candidate_name"], current_city=v["candidate_current_location"],
        native_city=v["candidate_native_location"],
    )
    body = [c.format(name=v["candidate_name"]) if "{name}" in c else c for c in criteria_for(s)]
    return head + "\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(body, 1))


def payload(s: dict) -> dict:
    return {
        "testType": "outbound-agent",
        "initiationRequest": {
            "method": "POST",
            "url": f"{U['runner_share']}/v1/account/{U['auth_id']}/flow/{U['flow_uuid']}",
            "headers": ({"Content-Type": "application/json", "Authorization": U["authorization"]}
                    if U.get("authorization") else {"Content-Type": "application/json"}),
            "bodyTemplate": BODY_TEMPLATE,
            "inboundNumberPlaceholder": "{{INBOUND_NUMBER}}",
        },
        "initiationVariables": trigger(s["generals"], s["techs"], s.get("over")),
        # Hunter fails a scenario on a variable mismatch, so only the exact bucket is sent.
        **({"expectedCallbackVariables": dict(s["expected"]["exact"])}
           if s["expected"].get("exact") else {}),
        "botGreetsFirst": s.get("bot_greets_first", False),
        "allowInterruptions": True,
        "conversationPrompt": persona(s),
        "evaluationPrompt": rubric(s),
        "evaluationThreshold": 0.8,
        "maxTurns": s.get("max_turns", 150),
        "evaluationConfig": {"autoDisconnectEnabled": True, "maxConsecutiveOffContext": 50,
                             "maxNonActualIntentRetries": 3, "maxResponseTime": 60.0},
        "voiceId": VOICES[s["voice"]],
        "webhookBaseUrl": U["webhook_base_url"],
        "event": s["slug"].replace("-", "_"),
        "testId": f"voice-sigma29-{s['slug']}",
        "testRegion": "us-east",
        "agentConfig": AGENT_CONFIG,
    }


def check_exits() -> list[str]:
    covered: dict[str, list[str]] = {}
    for s in S:
        for e in s["exits"]:
            covered.setdefault(e, []).append(s["slug"])
    lines, missing = [], []
    for stage, exits in (("screening", SCREENING_EXITS), ("agent", AGENT_EXITS)):
        for e in exits:
            key = f"{stage}:{e}"
            hits = covered.get(key, [])
            lines.append(f"  {key:<34} {len(hits)}  {', '.join(hits) or 'NOTHING'}")
            if not hits:
                missing.append(key)
    assert not missing, f"exits with no scenario: {missing}"
    stray = set(covered) - {f"{st}:{e}" for st, ex in
                            (("screening", SCREENING_EXITS), ("agent", AGENT_EXITS)) for e in ex}
    assert not stray, f"scenario names an exit the flow does not have: {stray}"
    # A scenario entering at the agent node can never reach a screening exit, so the board
    # scored it INCOMPLETE and sank 21 judge-passed runs on 2026-09-21.
    unreachable = [s["slug"] for s in S
                   if not any(e.split(":", 1)[0] == s["stage"] for e in s["exits"])]
    assert not unreachable, f"scenario declares no exit on its own entry stage: {unreachable}"
    return lines


# The end nodes' authored closings carry no callback time (Warm Farewell is "Thank them and close
# warmly"), and the AI node is told not to speak one, so a rubric that demands a time in the closing
# message fails a correct agent. Board 6 lost eleven callback scenarios to that expectation.
BANNED_IN_RUBRIC = ["the closing message states", "SPOKEN AT THE CLOSE"]


def check_rubrics() -> None:
    for s in S:
        text = rubric(s)
        for phrase in BANNED_IN_RUBRIC:
            assert phrase not in text, f"{s['slug']}: rubric demands a time in the closing ({phrase!r})"
        if s.get("stage") == "agent":
            assert 'demanding "is that correct?" after an answer is the defect' in text, \
            f"{s['slug']}: rubric lost the live preamble"  # 2026-09-21: the node no longer authors confirmations


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    slugs = [s["slug"] for s in S]
    assert len(slugs) == len(set(slugs)), "duplicate slug"
    assert FULL_WALK <= set(slugs), f"FULL_WALK names nothing: {FULL_WALK - set(slugs)}"
    check_rubrics()
    for i, s in enumerate(S, 1):
        doc = {
            "name": f"Sigma v2.9 - {s['name']}",
            "description": s["description"],
            "category": U["category"],
            "_expected_variables": dict(s["expected"], _exits=s["exits"],
                                        _full_walk=s["slug"] in FULL_WALK),
            "payload": payload(s),
        }
        (OUT / f"{i:02d}-{s['slug']}.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"today {TODAY} ({IST}); next valid calling day {NEXT_DAY} ({NEXT_DAY_WORD}); "
          f"Saturday {SATURDAY} falls back to {AFTER_SATURDAY}")
    print(f"{len(S)} scenarios written to {OUT}; full walk: {', '.join(sorted(FULL_WALK))}")
    print("exits coverage:")
    print("\n".join(check_exits()))


if __name__ == "__main__":
    main()
