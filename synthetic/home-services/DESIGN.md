# V2.9 Hunter example: flow and suite design (approved by MK 2026-09-24)

## Goal
A small outbound V2.9 flow and a 14-scenario Hunter suite to stress-test the V2.9 collectors: every Input type once,
values handed node to node, and the edge cases each type is meant to handle. The flow and its paste file are described
in `README.md`; `build_flow.py` is the source.

## Suite
| # | Scenario | Stresses | Exit |
|---|---|---|---|
| 1 | happy-full-walk | all 15 values cleanly; the upstream name used in Service Request; the read-back in Booking Confirmation | Booking Complete End |
| 2 | volunteers-ahead | service, rooms and date given in one breath and never re-asked | Booking Complete End |
| 3 | corrections | visit date and email changed after they are given; the corrected values are stored | Booking Complete End |
| 4 | optional-skips | no gate code, no alternate phone, no reminder; the agent moves on without pressing | Booking Complete End |
| 5 | date-and-dob | today refused (accept_today false), then "next Friday"; an impossible birth date, then a valid one | Booking Complete End |
| 6 | number-and-currency | "two and a half" rooms (whole numbers only); a budget said loosely | Booking Complete End |
| 7 | choice-and-boolean | an unlisted service, then a paraphrased pick; an ambiguous pets answer | Booking Complete End |
| 8 | contact-details | a spelled email, a phone with a country code, an unusual name spelled out, an address without its city | Booking Complete End |
| 9 | digit-code | three digits given, then corrected to four | Booking Complete End |
| 10 | name-corrected-upstream | a different name at Caller Check, then used downstream and never re-asked | Booking Complete End |
| 11 | wrong-person | not the account holder: no service question, nothing disclosed | Wrong Person End |
| 12 | declines-mid-walk | stops wanting the service after a few answers | Declined End |
| 13 | human-requested | asks for a person mid-walk | Human Followup End |
| 14 | not-confirmed | says no at the read-back; the reminder is never asked | Not Confirmed End |

Every scenario is also judged on: no question repeated, one value per question, no variable name or braces spoken, the
right exit, no invented detail, and the closing being the End node's own line.

## Method (from `General Instructions/v2.9 procedure.md` §3.4 and `HUNTER-PROTOCOL.md`)
1. `hunter/build.py` writes the scenarios. It recomputes every date in IST the morning of a board, because Hunter judges in UTC.
2. One happy-path smoke call → read the stored form of every callback variable (ISO dates, choice values, yes/no) →
   author `expectedCallbackVariables` in that stored form only.
3. One full board at `maxParallel 4`, pre-flighted in the launch command (cookie, no foreign run, numbers free), from ONE run id.
4. Per fail: HangupSource/HangupCause → the judge's own words → the runtime's tool-call lines.

## Known risk
Hunter's persona hangs up at about 300 s (a pipecat idle default on Hunter's side). Screening plus 15 values may run close
to that, so the full walks can be cut off. The smoke call measures the walk time before the board is spent.
