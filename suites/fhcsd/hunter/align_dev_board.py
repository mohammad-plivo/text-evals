"""Align the 48 "FHCSD dev test" Hunter scenarios with the deployed V2.9 flow and stamp today's clinic dates.

The flow's step 5 now collects preferred_start_date BEFORE the search, so every persona that reschedules has to
name a date, the criteria that demanded options-before-any-date-ask are inverted, and the slots a call sees are
the first weekdays AFTER the date the persona names. Expected callback variables are set from the same spec, in
the forms the flow stores (ISO dates, "yes"/"no", screening words).

    python3 align_dev_board.py --cookie <file> [--dry-run]

Pulls each scenario live, edits, PUTs and verifies the round trip; never edits from a saved copy. Idempotent:
rerun after the clinic day rolls (12:30 IST) or when the preferred Monday moves on."""
import argparse
import difflib
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://hunter.contactodev.com"
CATEGORY = "FHCSD dev test"
TIMES = ["09:30 AM", "11:00 AM", "03:45 PM"]

# TWO CLOCKS ON PURPOSE. T mirrors the DATA: the mock's clinicToday() is America/Los_Angeles by
# construction ("not the Worker's UTC clock", mock-real/worker.js:303), so the missed appointment and
# the slot dates must be stamped on that clock or the rubric asserts dates the API never returns.
# TOMORROW mirrors the AGENT: it computes "tomorrow" from the flow's Settings timezone, which is
# Asia/Kolkata on the deployed flow. Unifying them broke 26 scenarios on 2026-09-21 (board 6, stopped
# after minutes): the board said the patient missed 21 September, the API said 20 September.
T = datetime.now(ZoneInfo("America/Los_Angeles")).date()          # the mock's clinic day
LATER = T + timedelta(days=14)                                    # the patient's other appointment
PREF = T + timedelta(days=7)                                      # the date most personas ask to look from
PREF += timedelta(days=(7 - PREF.weekday()) % 7)                  # ... always a Monday, 7-13 days out
SAT = PREF - timedelta(days=2)
FRI = PREF + timedelta(days=4)
PREF2 = PREF + timedelta(days=7)
TOMORROW = datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)   # the agent's clock, per MK 20 Sep
SOONEST_ID = None                                                              # filled in once the scenario exists


def weekdays_after(d, n):
    out, x = [], d
    while len(out) < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            out.append(x)
    return out


def spoken(d):
    n = d.day
    suf = "th" if 11 <= n <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{d:%A} the {n}{suf} of {d:%B}"


def long(d):
    return f"{d:%B} {d.day}, {d.year}"


def short(d):
    return f"{d:%B} {d.day}"


DATE_LINE = 'When the agent asks which date you would like to look from, say "from %s".'
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}
SPOKEN = re.compile(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) the (\d{1,2})(?:st|nd|rd|th) of "
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)")


def parse_spoken(m):
    """The persona writes dates with no year; they are always within a few weeks of the clinic day.
    Roll the YEAR, never 365 days: a February date either side of a leap year would otherwise shift by a day."""
    day, month = int(m.group(1)), MONTHS[m.group(2)]
    for year in (T.year, T.year + 1, T.year - 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if -180 <= (d - T).days <= 185:
            return d
    return date(T.year, month, day)


def restamp(text, delta):
    """Move every spoken date by a whole number of weeks, so weekday names stay true."""
    return SPOKEN.sub(lambda m: spoken(parse_spoken(m) + timedelta(days=delta)), text)

# --- personas ------------------------------------------------------------------------------------------------
# Wordings of "no date preference" across the board; each becomes the one date line.
GENERIC = [
    (r'You want to reschedule\. You have no date preference: say "whatever is soonest works"\.', "You want to reschedule. {D}"),
    (r'You want to reschedule and have no date preference: say "whatever is soonest works"\.', "You want to reschedule. {D}"),
    (r'You have no date preference: say "whatever is soonest works"\.', "{D}"),
    (r'You want to reschedule\. You have no date preference\.', "You want to reschedule. {D}"),
    (r'You want to reschedule, no date preference\.', "You want to reschedule. {D}"),
    (r'You want to reschedule and have no date preference\.', "You want to reschedule. {D}"),
    (r'You want to reschedule, no preference: "whatever you have is fine"\.', "You want to reschedule. {D}"),
    (r'You want to reschedule, no preference\.', "You want to reschedule. {D}"),
    (r'If (?:the agent|it) asks what dates suit you BEFORE reading any options, say "no preference, whatever you have" and wait(?: for the options)?\.', "{D}"),
]
SPECIFIC = {
    "18886": [("you want to reschedule, no date preference, take the first option offered",
               "you want to reschedule. {D} Take the first option offered")],
    "18887": [("you want to reschedule, no date preference, take the first option offered",
               "you want to reschedule. {D} Take the first option offered")],
    "18880": [("and yes, I do want to reschedule, ideally next week",
               "and yes, I do want to reschedule, from {PREF} if you can")],
    "18999": [('If asked which date or which Friday to look from, or whether to look from another date, say "yes, a week from today onwards".',
               'If asked which date or which Friday to look from, or whether to look from another date, say "from {FRI}".')],
    "19000": [('If it asks which date to look from, say "from tomorrow onwards" and take the first option it reads next.',
               'If it asks for another date to look from, say "from {PREF2}" and take the first option it reads next.')],
    "19002": [('When the agent then asks which date to look from, say "the Monday after next, onwards"; if it asks you to pin that down, say "the Monday a bit under two weeks from today"; if it asks whether it has the right date, say "yes, that one".',
               'When the agent then asks which date to look from, say "from {PREF2}"; if it asks whether it has the right date, say "yes, that one".')],
    "19003": [('When the agent asks which date to look from, say "a week from today"; if it asks whether it has the right date, say "yes, that\'s it".',
               'When the agent asks for another date to look from, say "from {PREF2}"; if it asks whether it has the right date, say "yes, that\'s it".')],
    "19004": [('If the agent asks what dates suit you BEFORE reading any options, say "no preference, whatever you have" and wait for the options. When the FIRST options are read out, say "none of those suit me". When the agent asks which date to look from, say "this coming Saturday".',
               'When the agent asks which date you would like to look from, name the Saturday: say "from {SAT}".')],
    "19005": [('If the agent asks what dates suit you BEFORE reading any options, say "no preference, whatever you have" and wait for the options. When it reads out its first set of options, turn them all down: "none of those work for me". If it asks whether you would like it to look at other dates, say yes. When it asks which date you would like, say "last Monday". If it tells you that day has already passed, or asks you again for a date, say "oh — then a week from today". If you have already said that and it asks once more, do not repeat it word for word; say "seven days from now, that\'s fine".',
               'When the agent asks which date you would like to look from, say "last Monday" — a day that has already gone. If it tells you that day has already passed, or asks you again for a date, say "oh — then from {PREF}". If you have already said that and it asks once more, do not repeat it word for word; say "the Monday I just gave you, that\'s fine".'),
              ("Never name a calendar date yourself. ", "")],
}

# --- rubrics -------------------------------------------------------------------------------------------------
# scenario -> what the call sees: how many slots the search returns, and which date the persona asks to look from.
WALKS = {"18864": ("one", PREF), "18865": ("two", PREF), "18866": ("none", PREF), "18867": ("three", PREF),
         "18868": ("three", PREF), "18869": ("three", PREF), "18870": ("three", PREF), "18871": ("three", PREF),
         "18875": ("three", PREF), "18878": ("three", PREF), "18879": ("three", PREF), "18880": ("three", PREF),
         "18886": ("three", PREF), "18887": ("three", PREF)}
NOAPPT = {"18872"}                     # the patient has no appointment on file
NO_SEARCH = {"18863", "18873", "18874", "18876", "18881", "18882", "18884", "18885", "18888", "18889", "18890", "18891"}
TAIL = "Treat phonetic renderings"     # the block ends where the phonetics sentence begins
PATIENT_DATE = ("THE PATIENT'S DATE. The clinic's search starts from the date the patient asks the agent to look from and "
                "returns weekdays only, so every option in a read-out that follows it falls on or after that date, and an "
                "option dated before it is invented. The agent asking for that date, and restating it once as it goes to "
                "look, are both correct; naming a date the patient did not give is not.")
LOOK_FROM = ("ASKS WHICH DATE TO LOOK FROM, THEN SEARCHES FROM IT: after the patient says yes to rescheduling, and before "
             "reading out any option, the agent asks once which date the patient would like to look from, and waits for the "
             "answer. Every option it then reads out falls on or after the date the patient gave. NOT MET if it reads out "
             "options before asking for that date, if it asks for the date again after the patient gave one clearly, or if it "
             "reads out an option dated before that date. Stating the date back once as it goes to look is correct.")
ADD_LOOK_FROM = ["18878", "18879", "18993", "18994", "18997", "18998", "19001", "19006", "19007"]
CRITERIA = {
    "19002": [("4. OPTIONS BEFORE ANY DATE ASK: after the patient says yes to rescheduling, the agent reads out a first set of options, at most three, each with a date and a time, and no agent turn before that first read-out asks what date or dates suit the patient, which day they would like, or when they are free; the caller volunteering \"no preference\" does not excuse such a question. If the caller never says yes to rescheduling, or no first set of options is ever read out in the transcript, this criterion is NOT MET.",
               "4. THE DATE FIRST, THEN THE OPTIONS: after the patient says yes to rescheduling the agent asks, once, which date they would like to look from, waits for the answer, and only then reads out a first set of options, at most three, each with a date and a time, every one of them on or after the date the patient gave. If the caller never says yes to rescheduling, if no first set of options is ever read out, or if options are read out before the patient gives a date, this criterion is NOT MET."),
              ("5. ASKS THE DATE ONLY AFTER NONE OF THESE: the agent first asks which date the patient would like to look from only AFTER the caller has turned down the first set, and it does ask then: its next substantive move after the rejection is that question (a short acknowledgement, or one \"shall I look at other dates?\" before it, is fine), not guessing a period, offering to \"check next week\" as though it knew what was open, reading the same options out again, or reading a new set without asking. If the caller never turns down the first set, or the agent never asks for a date after that rejection, this criterion is NOT MET.",
               "5. ASKS FOR ANOTHER DATE AFTER NONE OF THESE: after the caller turns the first set down, the agent's next substantive move is to ask which other date they would like to look from (a short acknowledgement, or one \"shall I look at other dates?\" before it, is fine), not guessing a period, offering to \"check next week\" as though it knew what was open, reading the same options out again, or reading a new set without asking. If the caller never turns down the first set, or the agent never asks for another date after that rejection, this criterion is NOT MET.")],
    "19003": [("4. AT MOST THREE PER READ-OUT: every read-out of options has at most three, each with a date and a time, and the first read-out comes before any agent question about what dates suit the patient. If no options are ever read out in the transcript, this criterion is NOT MET.",
               "4. AT MOST THREE PER READ-OUT, AFTER THE DATE IS ASKED: the agent asks which date to look from before it reads out any option, and every read-out has at most three options, each with a date and a time, all on or after the date the patient last gave. If no options are ever read out in the transcript, this criterion is NOT MET."),
              ("5. SECOND SEARCH HAPPENS: after the caller turns down the first set of options, the agent asks which date the patient would like to look from, the caller names one, and the agent then reads out a second set of options",
               "5. SECOND SEARCH HAPPENS: after the caller turns down the first set of options, the agent asks which other date the patient would like to look from, the caller names one, and the agent then reads out a second set of options")],
    "19004": [("4. AT MOST THREE PER READ-OUT: every read-out of options has at most three, each with a date and a time, and the first read-out comes before any agent question about what dates suit the patient. If no options are ever read out in the transcript, this criterion is NOT MET.",
               "4. AT MOST THREE PER READ-OUT, AFTER THE DATE IS ASKED: the agent asks which date to look from before it reads out any option, and every read-out has at most three options, each with a date and a time, all on or after the Saturday the patient gave. If no options are ever read out in the transcript, this criterion is NOT MET."),
              ("5. NO WEEKEND SLOT INVENTED: the caller asks to look from \"this coming Saturday\".",
               "5. NO WEEKEND SLOT INVENTED: the caller asks to look from a Saturday.")],
    "19005": [("3. DOES NOT ACCEPT A PAST DATE: after the patient turns down the first read-out and names \"last Monday\" as the date they would like, the agent does not take that day",
               "3. DOES NOT ACCEPT A PAST DATE: asked which date to look from, the patient names \"last Monday\", and the agent does not take that day"),
              ("Once the patient gives a future date (\"a week from today\"), the agent goes straight on to read out options",
               "Once the patient gives a future date, the agent goes straight on to read out options")],
}

# 2026-09-25 criteria review of run 431ec723 (FHCSD/evidence/CRITERIA-REVIEW-2026-09-25.md). Each pair survived three
# independent refutations; the ground is D-022's: a date the generator never re-stamps (checkability), or a demand that
# contradicts contract step 8 (one booking read-back, then a yes) or step 10 (no details restated after booking).
REVISED = {
    "18864": [("the agent reads out one appointment time, September 21, 2026 at 09:30 AM, and no others.",
               "the agent reads out one appointment time, the single slot in THE CLINIC RECORD above (09:30 AM on the date the record gives for it), and no others.")],
    "18865": [("the agent reads out September 21, 2026 at 09:30 AM and September 22, 2026 at 11:00 AM, and no third one.",
               "the agent reads out the two slots in THE CLINIC RECORD above (09:30 AM and 11:00 AM, each on the date the record gives for it), and no third one."),
              ("BOOKS THE SECOND: the appointment stated after booking is September 22, 2026 at 11:00 AM.",
               "BOOKS THE SECOND: the booking the agent reads back and gets the patient's yes on immediately before it books is option 2 in THE CLINIC RECORD above (11:00 AM on the date the record gives for option 2), and any appointment it states after booking is that one too.")],
    "18868": [("the appointment the agent states after booking is the THIRD slot in the clinic record (option 3, September 23, 2026 at 03:45 PM).",
               "the booking the agent reads back and gets the patient's yes on immediately before it books, and any appointment it states after booking, is the THIRD slot in the clinic record (option 3, 03:45 PM on the date the record gives for option 3).")],
    "18878": [("the appointment the agent states after booking is the SECOND slot in the clinic record (option 2, September 22, 2026 at 11:00 AM).",
               "the booking the agent reads back and gets the patient's yes on immediately before it books, and any appointment it states after booking, is the SECOND slot in the clinic record (option 2, 11:00 AM on the date the record gives for option 2).")],
    "19005": [("the new appointment the agent states after booking is exactly the FIRST option",
               "the booking the agent reads back and gets the patient's yes on immediately before it books, and any appointment it states after booking, is exactly the FIRST option"),
              ("or the agent never states a new appointment, this criterion is NOT MET.",
               "or the agent never reads a booking back for the patient's yes, this criterion is NOT MET.")],
    "19007": [("and both match the appointment it stated as booked:",
               "and both match the booking the agent read back and the patient said yes to:"),
              ("the time is the same clock time as in its success statement, however naturally worded",
               "the time is the same clock time as in the booking the agent read back and the patient said yes to, however naturally worded"),
              ("or the agent never stated a new appointment as booked, this criterion is NOT MET.",
               "or the agent never read a booking back and got the patient's yes, this criterion is NOT MET.")],
    "19006": [("Because this agent books right after a choice, the retraction may land before or after the save went through.",
               "This agent reads the chosen booking back and asks for a yes before it saves, so a retraction given in place of that yes means nothing was booked; only if the patient had already said yes to the read-back can the retraction land after the save went through."),
              ("One exception, because the save can complete in the moment between the choice and the retraction:",
               "One exception, which applies only if the patient said yes to the read-back before retracting, because the save can complete in the moment between that yes and the retraction:")],
    "18997": [("the new appointment the agent states after booking is the one the agent had most recently identified as the second option",
               "the booking the agent reads back and gets the patient's yes on immediately before it books, and any appointment it states after booking, is the one the agent had most recently identified as the second option"),
              ("If no new appointment is ever stated as booked, NOT MET.",
               "If the agent never reads a booking back for the patient's yes, NOT MET.")],
    "19002": [("the appointment the agent then states as booked is exactly that option",
               "the booking the agent then reads back and gets the patient's yes on immediately before it books, and any appointment it states after booking, is exactly that option"),
              ("or the agent never states a booked appointment, this criterion is NOT MET.",
               "or the agent never reads a booking back for the patient's yes, this criterion is NOT MET.")],
    "18881": [("CLOSES POLITELY: the agent says it will try again another time, or asks for nothing further, and ends the call.",
               "CLOSES POLITELY: the agent says it will try again another time, or asks for nothing further, and ends the call. The closing "
               "message the platform speaks in the agent's voice when the agent selects an exit (on this path a brief apology saying "
               "details will not be shared) is the agent's close and satisfies this criterion if it asks for nothing further.")],
    "18870": [("unless it gives the number to call.",
               "unless the patient is also given the number to call, in that turn or in the closing line that follows it.")],
    "19001": [("explains a second time unprompted,",
               "explains a second time unprompted (a further apology or restatement that it cannot help with cost or insurance, in a later agent turn with no caller question in between, is a second explanation even when the reschedule question follows it in that same turn),")],
}
# The confirmation bullet 21 scenarios already carry; the other 24 still said the agent books right after the choice.
STALE_CONFIRM = ("NOTHING in this call is put to the patient for agreement: the agent states each value once, books right after "
                 "the slot is chosen, and then states the new appointment once. Any question asking the patient to agree to a "
                 "value or to the booking is a defect.")
ALIGNED_CONFIRM = ("Only the booking read-back is put to the patient: after the slot is chosen the agent reads the chosen "
                   "appointment back once and asks a single yes/no, which may be phrased as a question. Every other value is "
                   "stated once and never put to the patient for agreement, and after the booking the agent gives one short "
                   "success statement without repeating the details.")

# --- expected callback variables ------------------------------------------------------------------------------
SCREENED = {"screening_status": "permission_granted", "screening_disposition": "reached", "screening_relationship": "self"}
DOB = {"18863": "1996-07-07", "18864": "1990-05-05", "18865": "1991-06-06", "18866": "1969-08-07", "18867": "1980-09-09",
       "18868": "1983-07-21", "18869": "1979-04-04", "18870": "1964-06-28", "18871": "1968-07-12", "18872": "1982-02-02",
       "18873": "1960-12-12", "18874": "2002-01-01", "18875": "1980-08-08", "18876": "1984-10-19", "18878": "1971-07-03",
       "18879": "1977-02-18", "18880": "1986-10-27", "18884": "1966-05-02", "18885": "1975-09-01", "18886": "1959-01-08",
       "18887": "1991-03-12", "18889": "1968-03-02", "18890": "1980-02-11", "18891": "1986-09-25", "18993": "1981-03-09",
       "18994": "1980-06-22", "18996": "1991-03-22", "18997": "1968-11-09", "18998": "1982-06-03", "18999": "1991-03-09",
       "19000": "1968-08-22", "19001": "1981-10-03", "19002": "1988-11-14", "19003": "1981-03-09", "19004": "1979-06-23",
       "19005": "1971-03-09", "19006": "1991-08-23", "19007": "1961-11-02"}
WANTS_NO = {"18876", "18996"}
BOOKED = {"18864", "18865", "18867", "18868", "18869", "18870", "18871", "18875", "18878", "18879", "18880", "18886",
          "18887", "18993", "18994", "18997", "18998", "19000", "19001", "19002", "19004", "19005", "19007"}
START = {**{s: PREF for s in WALKS}, **{s: PREF for s in ("18993", "18994", "18997", "18998", "18999", "19000", "19001", "19006", "19007")},
         "19002": PREF2, "19003": PREF2, "19004": SAT, "19005": PREF}
# which option the persona takes, by index into the slots the search returns from START[sid]
BRANCHING = {"18999", "19000"}   # a second search is in scope, so the final date/slot is branch-dependent
SLOT = {"18864": 0, "18865": 1, "18867": 0, "18868": 2, "18869": 0, "18870": 0, "18871": 0, "18875": 0, "18878": 1,
        "18879": 0, "18880": 0, "18886": 0, "18887": 0, "18993": 0, "18994": 0, "18997": 1, "18998": 0, "19000": 0,
        "19001": 0, "19002": 0, "19004": 0, "19005": 0, "19006": 0, "19007": 0}
EXTRA = {"18882": {"voicemail_detected": "True"}, "18987": {"screening_status": "callback_requested"},
         "18988": {"screening_status": "do_not_call", "screening_disposition": "do_not_call"},
         "18989": {"screening_status": "wrong_number"}}


NODE_ENTRY = ("NODE ENTRY. Two different units speak on this call. The screening unit runs first and hands over; this node "
              "then runs and its FIRST turn is the one in which the agent first asks the patient for their date of birth. "
              "Judge only from that turn onwards. Everything before it - a greeting, naming the clinic, confirming who is "
              "speaking, asking whether now is a good time or whether it may continue - belongs to screening and is outside "
              "these criteria, however it is worded. This is a boundary in the call, not a licence to ignore words: the SAME "
              "moves after entry are defects, so a greeting, an identity question or a permission question that appears once "
              "the date of birth has been asked for is NOT MET, and a repetition of the date-of-birth question itself is "
              "judged normally. The line \"Are you still there? I'm happy to assist whenever you're ready.\" is the platform's idle "
              "reminder rather than a sentence the agent chose; do not read it as the agent speaking, but a call that keeps "
              "eliciting it has not ended when it should have.")
SCREENING_OWN_ENTRY = {"18987", "18988", "18989", "18991"}   # their rubric already says screening is under test
SCREENING_ENTRY_IDS = {"18881", "18882"}
SCREENING_ENTRY = ("SCREENING IS THE UNIT UNDER TEST. Judge every agent turn from the first word; there is no later entry turn. "
                   "The call is expected to end inside screening: the rescheduling step, with its date-of-birth question, should "
                   "never be reached, and no one is connected or transferred. The line \"Are you still there? I'm happy to assist "
                   "whenever you're ready.\" is the platform's idle reminder rather than a sentence the agent chose; do not read it "
                   "as the agent speaking, but a call that keeps eliciting it has not ended when it should have.")
ONE_LIST = ("ONE OPTION LIST UNLESS ASKED: the agent reads the list of options once. A second complete list, in the same turn "
            "or a later one, is NOT MET unless the patient asked to hear the options again. Reading back only the option the "
            "patient chose, or repeating a single option they asked about, is not a second list.")
ADD_ONE_LIST = set(WALKS) | {"18993", "18994", "18997", "18998", "19000", "19001", "19002", "19005", "19006", "19007"}
TARGETS = {
    "18870": ("TARGET is achieved when the agent has told the patient the time was not held and that someone will follow up.",
              "TARGET is achieved when the agent has told the patient the time was not held, has given the clinic's number or "
              "the call has closed after it, and you have heard the closing line."),
    "18993": ("TARGET is achieved when the agent has stated the new appointment once and closed the call.",
              "TARGET is achieved when the agent has confirmed the booking and closed the call."),
    "18994": ("TARGET is achieved when the agent has stated the new appointment once and closed the call.",
              "TARGET is achieved when the agent has confirmed the booking and closed the call."),
    "19005": ("TARGET is achieved when the agent has stated your new appointment and closed the call.",
              "TARGET is achieved when the agent has confirmed the booking and closed the call."),
    "19007": ("TARGET is achieved when the agent has stated your new appointment, answered your clinic-and-time question, and closed the call.",
              "TARGET is achieved when the agent has confirmed the booking, answered your clinic-and-time question, and closed the call."),
}
REFUSAL_CRITERION = (
    "2. EXPLAINS AND STOPS: the agent says it cannot discuss appointment information without verifying identity. After the "
    "first refusal it may ask once more, rephrased - that is the one retry a required field is given - and after the second "
    "refusal it stops asking and ends the call. A third request for the date of birth, or any pressure after the second "
    "refusal, is NOT MET.")


def slot_text(start, i):
    """The chosen option as a canonical tuple. The collector stores the agent's own prose, which varies run to run,
    so the expectation states the facts (date, time, provider, facility) rather than one rendering of them."""
    d = weekdays_after(start, i + 1)[i]
    return f"{d:%Y-%m-%d} {TIMES[i]} | Dr. Rismiller | Logan Heights Family Health Center"


def record_block(sid):
    """The pinned clinic record for the first-batch rubrics: what the mock will actually serve this call."""
    head = ("THE CLINIC RECORD. These are the only true facts on this call; any other date, time, provider or facility the "
            "agent states is invented:\n")
    if sid in NOAPPT:
        body = ("- the clinic has NO appointment on file for this patient: there is nothing to move, and any appointment, date, "
                "time, provider, facility or slot the agent states as this patient's is invented.\n")
        days = []
    else:
        body = (f"- the ONE appointment the patient missed: {long(T)} at 10:30 AM with Dr. Rismiller at Logan Heights Family "
                f"Health Center. The patient also has a later appointment on file, {long(LATER)} at 02:15 PM with Dr. Williams; "
                "that is NOT the appointment they missed and must never be presented as it.\n")
        days = [T]
        if sid in NO_SEARCH:
            body += ("- no appointment slots are looked up on this call, so any slot, day or time the agent states as open or "
                     "available is invented.\n")
        else:
            n = {"one": 1, "two": 2, "three": 3, "none": 0}[WALKS[sid][0]]
            start = WALKS[sid][1]
            body += f"- the date the patient asks the agent to look from: {long(start)}.\n"
            if n == 0:
                body += ("- the search from that date returns NO slots at all: nothing is open, and any option the agent reads "
                         "out is invented.\n")
            else:
                slots = weekdays_after(start, n)
                opts = "; ".join(f"option {i + 1}, {long(d)} at {TIMES[i]}" for i, d in enumerate(slots))
                only = "the ONLY appointment slot that exists" if n == 1 else "the ONLY appointment slots that exist"
                tail = (" The search returned that one slot and nothing else; there is no second and no third option to offer."
                        if n == 1 else " The search returned those two slots and nothing else; there is no third option to offer."
                        if n == 2 else "")
                body += (f"- {only}: {opts}, all with Dr. Rismiller at Logan Heights Family Health Center. The clinic books "
                         f"weekdays only, so the first option is the next weekday after the patient's date.{tail}\n")
                days += [start] + slots
    wd = ", ".join(f"{short(d)} is a {d:%A}" if i == 0 else f"{short(d)} a {d:%A}" for i, d in enumerate(days))
    note = ("The record gives each date with no weekday, so a date said without a weekday is complete and correct, and stating "
            "the year is optional.")
    if days:
        note += f" {wd}: a weekday the agent names that matches its date is not an invented date."
    return head + body + note + "\n"


NAMES = {"18879": "FHCSD dev test — Reschedule — the clean walk, first slot"}  # the persona now names a date


def edit(d):
    sid, p = d["id"], d["payload"]
    d["name"] = NAMES.get(sid, d["name"])
    cp, ep = p["conversationPrompt"], p["evaluationPrompt"]
    subs = {"{D}": DATE_LINE % spoken(PREF), "{PREF}": spoken(PREF), "{PREF2}": spoken(PREF2), "{SAT}": spoken(SAT),
            "{FRI}": spoken(FRI)}

    def fill(s):
        for k, v in subs.items():
            s = s.replace(k, v)
        return s

    reschedules = sid in WALKS or sid in START
    if reschedules:
        first = SPOKEN.search(cp)
        if first:                                                # a rerun: move the dates on, keeping the wording
            delta = ((SAT if sid == "19004" else PREF) - parse_spoken(first)).days   # the FIRST date a persona names
            cp = restamp(cp, delta)
        else:
            hits = 0
            for old, new in SPECIFIC.get(sid, []):      # scenario wording first: the generic rules would eat part of it
                if old in cp:
                    cp = cp.replace(old, fill(new), 1)
                    hits += 1
            for pat, rep in GENERIC:                    # one date line per persona, so stop at the first wording that matches
                cp, n = re.subn(pat, fill(rep).replace("\\", "\\\\"), cp, count=1)
                hits += n
                if n:
                    break
            cp = re.sub(GENERIC[-1][0], "", cp).replace("  ", " ")   # drop any other "no preference" sentence
            assert hits, f"{sid}: no place found for the date line"
    if "THE CLINIC RECORD." in ep:
        start = ep.index("THE CLINIC RECORD.")
        end = ep.index(TAIL, start)
        ep = ep[:start] + record_block(sid) + ep[end:]
    elif reschedules and PATIENT_DATE[:30] not in ep:
        ep = ep.replace("\n\nEvaluate these criteria:", "\n\n" + PATIENT_DATE + "\n\nEvaluate these criteria:", 1)
    if sid in SCREENING_OWN_ENTRY or sid in SCREENING_ENTRY_IDS:   # screening is under test: no node boundary to judge from
        ep = ep.replace("\n\n" + NODE_ENTRY, "", 1)
        if sid in SCREENING_ENTRY_IDS and "SCREENING IS THE UNIT UNDER TEST." not in ep:
            ep = ep.replace("\n\nEvaluate these criteria:", "\n\n" + SCREENING_ENTRY + "\n\nEvaluate these criteria:", 1)
    elif "NODE ENTRY." not in ep:                                 # boundary, not a text exemption (audit section 3, F1)
        ep = ep.replace("\n\nEvaluate these criteria:", "\n\n" + NODE_ENTRY + "\n\nEvaluate these criteria:", 1)
    for old, new in CRITERIA.get(sid, []) + REVISED.get(sid, []):
        if old in ep and new not in ep:                        # a new text may extend its old one; apply it once
            ep = ep.replace(old, new, 1)
    ep = ep.replace(STALE_CONFIRM, ALIGNED_CONFIRM, 1)
    if sid == "18888":                                           # one rephrased retry is the authored field policy, not a defect
        ep = ep.replace("2. EXPLAINS AND STOPS: the agent says it cannot discuss appointment information without verifying "
                        "identity, and stops asking after the refusal is clear.", REFUSAL_CRITERION, 1)
    if sid in ADD_ONE_LIST and "ONE OPTION LIST UNLESS ASKED" not in ep:   # the duplicate read-out the board used to forgive
        n = max(int(m) for m in re.findall(r"(?m)^(\d+)\. ", ep)) + 1
        ep = ep.rstrip() + f"\n{n}. {ONE_LIST}\n"
    for old, new in TARGETS.get(sid, ()) and [TARGETS[sid]] or []:
        if old in cp:
            cp = cp.replace(old, new, 1)
    if sid in ADD_LOOK_FROM and "ASKS WHICH DATE TO LOOK FROM" not in ep:
        n = max(int(m) for m in re.findall(r"(?m)^(\d+)\. ", ep)) + 1
        ep = ep.rstrip() + f"\n{n}. {LOOK_FROM}\n"

    ecv = {}
    if sid in DOB:
        ecv["dob_confirmed"] = DOB[sid]
    if sid in START or sid in WANTS_NO:
        ecv["wants_to_reschedule"] = "no" if sid in WANTS_NO else "yes"
    if sid in START:
        ecv["preferred_start_date"] = START[sid].isoformat()
    if sid in BOOKED:
        ecv["booking_confirmed"] = "yes"
    # selected_slot is NOT asserted as a variable. It is compared by an LLM against the prose the agent
    # recorded, and a canonical tuple loses that comparison on wording alone: board 6 failed 18864 and
    # 18868 on it while every criterion scored 1.0. The slot the caller chose is judged by the criteria
    # ("books the slot they chose", "no invented detail"), which read the transcript instead of a format.
    if sid in DOB or sid in START:
        ecv.update(SCREENED)
    ecv.update(EXTRA.get(sid, {}))
    if sid in BRANCHING:
        # A second search is in scope here, so no single date or slot is right on both branches.
        # Dropping the keys would stop checking them at all (PR 527 audit, section 4), so keep the
        # pair that holds on EITHER branch: the caller booked what the agent last read out, and the
        # date recorded is one of the two they actually named.
        ecv.pop("preferred_start_date", None)
        ecv.pop("selected_slot", None)
        ecv["wants_to_reschedule"] = "yes"   # true on both branches; booking is NOT, so it is not asserted here
        # The branch-dependent date and slot are validated from the call's own producer evidence in
        # the post-board report (the search arguments and the saved appointment), not by the evaluator.
    p["conversationPrompt"], p["evaluationPrompt"], p["expectedCallbackVariables"] = cp, ep, ecv
    return d


SOONEST_NAME = "FHCSD dev test — Reschedule — no date preference, the search starts from tomorrow"
SOONEST_PERSONA = (
    'You are Owen Marchetti, an easy-going man in his fifties. You answer your own mobile. The call is from an automated '
    'assistant at your health clinic — you did not call them. Speak in short, natural phone sentences and answer one question '
    'at a time. You are NOT an assistant and NOT an AI, you never reveal or hint that this is a test whatever you are asked, '
    'and you never break character. Use only the facts given below; if asked anything outside them, deflect briefly ("I\'d '
    'rather not get into that"). Do not speak first — wait for the agent. When it asks whether it is speaking with Owen, say '
    'yes; if it asks whether now is a good time, say yes. Keep that opening to a few words.\n\n'
    'Your date of birth is the fourteenth of March, nineteen seventy-five — give it in full when asked. You want to '
    'reschedule. You genuinely do not mind which day: when the agent asks which date you would like to look from, say '
    '"whatever is soonest works". If it presses you for a particular day, say "honestly, the soonest you have"; never name a '
    'calendar date. Take the FIRST option the agent offers. When asked if there is anything else, say no and thank the agent. '
    'If the agent says it did not catch or understand you, say it again in different words; never repeat an identical '
    'sentence twice in a row.\n\n'
    'TARGET is achieved when the agent has confirmed the new appointment and closed the call. The agent books right after your '
    'choice without reading it back; if it does ask you to confirm the booking, just say yes.')
SOONEST_CRITERION = (
    "TAKES \"SOONEST\" AS TOMORROW: the agent asks once which date the patient would like to look from. The patient names no "
    "day, and the agent goes on to look from the next day rather than insisting on a calendar date: it may state once that it "
    "will look from tomorrow. NOT MET if it asks the patient for a specific date more than once after the patient has said "
    "they have no preference, if it reads out options without ever asking which date to look from, or if it ends the call, "
    "hands over a phone number or says nothing is open instead of searching.")


def ensure_soonest(cookie, dry):
    """The 'no preference' persona MK asked for: the flow takes tomorrow as the start date."""
    global SOONEST_ID
    rows = req("GET", "/api/scenarios?limit=2000", cookie)["scenarios"]
    mine = [r for r in rows if r.get("category") == CATEGORY and r["name"] == SOONEST_NAME]
    base = req("GET", f"/api/scenarios/{[r['id'] for r in rows if r.get('category') == CATEGORY and 'clean walk' in r['name']][0]}", cookie)
    p = json.loads(json.dumps(base["payload"]))
    p["initiationVariables"] = {"date_of_birth": "03/14/1975", "first_name": "Owen", "last_name": "Marchetti"}
    p["conversationPrompt"] = SOONEST_PERSONA
    p["testId"] = "voice-fhcsd29-soonest-next-day"
    p["event"] = "soonest-next-day"
    ep = p["evaluationPrompt"]
    ep = ep[:ep.index("THE CLINIC RECORD.")] + soonest_record() + ep[ep.index(TAIL):]
    ep = re.sub(r"\n\d+\. ASKS WHICH DATE TO LOOK FROM.*?(?=\n\d+\. |\Z)", "", ep, flags=re.S).rstrip()
    nxt = max(int(m) for m in re.findall(r"(?m)^(\d+)\. ", ep)) + 1
    ep += "\n%d. %s\n" % (nxt, SOONEST_CRITERION)
    p["evaluationPrompt"] = ep
    p["expectedCallbackVariables"] = {"dob_confirmed": "1975-03-14", "wants_to_reschedule": "yes",
                                      "preferred_start_date": TOMORROW.isoformat(), "booking_confirmed": "yes",
                                      **SCREENED}
    body = {"name": SOONEST_NAME, "description": "The patient names no day at all. Per MK, the flow takes tomorrow as the "
            "date to look from, so the agent must search rather than press for a calendar date.",
            "category": CATEGORY, "tier": base.get("tier"), "payload": p}
    if mine:
        SOONEST_ID = mine[0]["id"]
        live = req("GET", f"/api/scenarios/{SOONEST_ID}", cookie)
        if json.dumps(live["payload"], sort_keys=True) == json.dumps(p, sort_keys=True):
            print(f"soonest scenario {SOONEST_ID}: unchanged")
            return
        if dry:
            print(f"soonest scenario {SOONEST_ID}: would update (start {TOMORROW})")
            return
        req("PUT", f"/api/scenarios/{SOONEST_ID}", cookie, body)
        print(f"soonest scenario {SOONEST_ID}: updated (start {TOMORROW})")
    elif dry:
        print(f"soonest scenario: would create (start {TOMORROW})")
    else:
        SOONEST_ID = req("POST", "/api/scenarios", cookie, body)["id"]
        print(f"soonest scenario {SOONEST_ID}: created (start {TOMORROW})")


def soonest_record():
    slots = weekdays_after(TOMORROW, 3)
    opts = "; ".join(f"option {i + 1}, {long(d)} at {TIMES[i]}" for i, d in enumerate(slots))
    days = [T, TOMORROW] + slots
    wd = ", ".join(f"{short(d)} is a {d:%A}" if i == 0 else f"{short(d)} a {d:%A}" for i, d in enumerate(days))
    return ("THE CLINIC RECORD. These are the only true facts on this call; any other date, time, provider or facility the "
            "agent states is invented:\n"
            f"- the ONE appointment the patient missed: {long(T)} at 10:30 AM with Dr. Rismiller at Logan Heights Family "
            f"Health Center. The patient also has a later appointment on file, {long(LATER)} at 02:15 PM with Dr. Williams; "
            "that is NOT the appointment they missed and must never be presented as it.\n"
            f"- the patient names no date, so the agent looks from tomorrow, {long(TOMORROW)}.\n"
            f"- the ONLY appointment slots that exist: {opts}, all with Dr. Rismiller at Logan Heights Family Health Center. "
            "The clinic books weekdays only, so the first option is the next weekday after tomorrow.\n"
            "The record gives each date with no weekday, so a date said without a weekday is complete and correct, and stating "
            f"the year is optional. {wd}: a weekday the agent names that matches its date is not an invented date.\n")


def req(method, path, cookie, body=None):
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                               headers={"Cookie": cookie, **({"Content-Type": "application/json"} if body else {})})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    cookie = open(a.cookie).read().strip()
    cookie = cookie if cookie.startswith("hunter_session=") else "hunter_session=" + cookie
    print(f"clinic day {T:%A %d %B %Y} | preferred {PREF:%A %d %B} | saturday {SAT:%d %b} | second {PREF2:%d %b} | friday {FRI:%d %b}")
    ensure_soonest(cookie, a.dry_run)
    ids = [s["id"] for s in req("GET", "/api/scenarios?limit=2000", cookie)["scenarios"] if s.get("category") == CATEGORY and str(s["id"]) != str(SOONEST_ID)]
    if a.only:
        ids = [i for i in ids if str(i) in a.only.split(",")]
    changed = 0
    for sid in ids:
        live = req("GET", f"/api/scenarios/{sid}", cookie)
        was = json.loads(json.dumps(live["payload"]))
        after = edit(json.loads(json.dumps(live)))["payload"]
        if json.dumps(was, sort_keys=True) == json.dumps(after, sort_keys=True):
            continue
        changed += 1
        if a.dry_run:
            print(f"\n===== {sid} {live['name']}")
            for f in ("conversationPrompt", "evaluationPrompt"):
                a1 = re.split(r"(?<=[.!?]) (?=[A-Z0-9])|\n", was.get(f, "") or "")
                b1 = re.split(r"(?<=[.!?]) (?=[A-Z0-9])|\n", after.get(f, "") or "")
                for l in difflib.unified_diff(a1, b1, lineterm="", n=0):
                    if l[:1] in "+-" and l[:3] not in ("---", "+++") and l.strip() not in ("+", "-"):
                        print(("  " + l)[:520])
            if was.get("expectedCallbackVariables") != after.get("expectedCallbackVariables"):
                print("  ECV:", json.dumps(after.get("expectedCallbackVariables"), sort_keys=True))
            continue
        d = edit(live)
        req("PUT", f"/api/scenarios/{sid}", cookie, {k: d[k] for k in ("name", "description", "category", "tier", "payload")})
        back = req("GET", f"/api/scenarios/{sid}", cookie)
        ok = json.dumps(back["payload"], sort_keys=True) == json.dumps(d["payload"], sort_keys=True) and back.get("tier") == d.get("tier")
        print(f"  PUT {sid} {'verified' if ok else 'ROUND-TRIP DIFFERS'}")
        assert ok, sid
    print(f"\n{'would change' if a.dry_run else 'changed'} {changed} of {len(ids)}")


if __name__ == "__main__":
    main()
