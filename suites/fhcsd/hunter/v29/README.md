# FHCSD v2.9 — Hunter scenario set

**29 scenarios on the board**, Hunter category **`FHCSD v2.9`**; 17 more parked in
**`FHCSD v2.9 (parked)`** with their ids intact. Ids run 18622–18667, last synced 2026-09-09.
**Nothing has been run.** No `POST /api/runs`, no `/api/calls/trigger`, no retrigger.

MK, 2026-09-09: *"we don't need so many scenarios, keep 25 or 30 at max, cover the most variety and
critical ones."* `KEEP` in `build.py` is the list, by slug; the category in each scenario file
follows from it, and `create.py --sync` touches **only the 29** unless you pass `--all`. Nothing was
deleted: a parked scenario keeps its id, so bringing one back is one line in `KEEP` plus a
`--sync --all`. The **# column below is the file number and is stable** — it does not renumber when
scenarios park.

They target `flows/fhcsd-v29-agent-config.json` — the 2026-09-10 rebuild in the shape of the live
prod V2 flow: **one** V2.9 agent node whose four custom-code actions do auth-plus-request inside
Python, and one End node per exit. 16 nodes, down from the 37-node HTTP-and-Branch graph MK judged
too complex (parked at `FHCSD/parked/build-v29-real-flow.py`).

## The flow these judge, in one paragraph

`Start` (four trigger keys: `date_of_birth`, `first_name`, `last_name`, `phone_number`) → dial +
screening → **FHCSD Rescheduler**, which asks the date of birth and compares it silently against
the one the trigger carried, then calls `fhcsd_match_patient_fresh_auth` →
`fhcsd_get_patient_appointments_fresh_auth` (and names the missed appointment from the result) →
takes the reschedule answer and any date preference → `fhcsd_search_available_appointments_fresh_auth`
→ offers the returned options → takes the one booking confirmation →
`fhcsd_reschedule_appointment_fresh_auth` → reads the booking back and asks "anything else" → one of
eight exits, each with its own End node (Human Requested goes via Transfer to Staff). Every action
authenticates immediately before its own vendor request, so the 30-second token is never reused, and
each retries **once** only when the vendor rejects the token.

**Two consequences for reading a board.** Every scenario now places a real call — the lookups live
inside the agent, so the old "decided before the dial, judged on silence" rubrics were retired with
the graph; 12, 13, 41 and 42 are ordinary conversations judged on what the agent says when a lookup
comes back empty or broken. And the flow *holds* the patient's date of birth before it calls, so
every rubric carries the rule that the agent must never say any part of it first.

## Coverage grid

| MK's row | covered by | note |
|---|---|---|
| **(a) reschedule** — the flow's only business path | 01 02 03 04 36 39 | |
| (a) declines / will not rebook | 08 09 10 21 | |
| (a) no availability | 05 06 07 19 45 46 | |
| (a) verification failed | 11 12 13 25 40 | |
| (a) API failure | 42 44 | a rejected token, and a 409 delivered as HTML |
| (a) transfer to staff | 22 35 | from Agent A, mid-walk and before identity |
| (a) emergency / upset | 23 24 | |
| (a) wrong person / unrelated caller | 34 | screening `wrong_contact` / `unavailable` |
| (a) voicemail / no answer | 32 33 | |
| (a) **book-new / cancel** | 37 38 | **not paths in this flow** — MK confirmed reschedule-only; Cancel and the book-new 409 live in the mock so the flow can grow later |
| (a) lookup | 12 13 41 + every happy path | |
| **(b) dob** — happy / correction / mismatch | 01 14 15 39 / 16 17 29 / **40** | words, digits, partial, corrected, misheard, wrong |
| (b) boolean — happy / correction | 01 39 / 08 09 10 30 | `wants_to_reschedule`, `booking_confirmed` |
| (b) date — happy / edge | 03 04 / 01 19 | `preferred_start_date`, incl. left empty |
| (b) choice — happy / correction | 02 39 46 / 18 | `selected_slot`, and the index that picks the Save node |
| (b) **name / phone / email / address / dtmf** | — | **the flow declares none.** Screening owns identity, the phone arrives in the trigger, there is no keypad step. The read-back-and-wait half of D-089 is not testable here; `acme-v29-local` has all four field types |
| **(c) lookup found / none / ambiguous** | happy / 12 / 13 | |
| (c) appointments found / none | happy / 41 | |
| (c) slots three / two / one / none | happy / 46 / 45 / 07 | |
| (c) save Error 0 / Error 1 / 409 / 409-as-HTML / token rejected | happy / 26 / 43 / 44 / 42 | every outcome `fhcsd_reschedule_appointment_fresh_auth` can return |
| **(d) the closing** — full read-back, success stated, "anything else" waited for | 01 02 18 30 38 39 | 38 forces the follow-up question |
| **(e) interrupts / two-in-one-breath / changes mind / goes silent / human early / wrong-then-right DOB** | 30 / 36 / 17 18 / 31 / 35 / 17 40 | |
| **(f) stated dob-date, no "is that correct?"** | 39 01 14 15 16 29 36 | explicit criterion, not just the preamble |
| (f) boolean acknowledged, never echoed | 39 | explicit criterion |
| (f) one booking confirmation, never two | 39 + 16 others | `ONE BOOKING CONFIRMATION` criterion |
| (f) the recorded DOB is never spoken first | 25 35 40 + every preamble | new obligation created by the rebuild |

Two subsets of the 29, both asserted `⊆ KEEP` at build time so they cannot drift:
- **lookup failures (4 ids):** 12, 13, 41, 42 — an empty match, an ambiguous match, nothing on file
  to move, and a vendor call that breaks. All four are real conversations.
- **core smoke (12 ids):** 01, 02, 07, 18, 22, 26, 30, 34, 40, 43, 45, 46 — every Save outcome, both
  slot counts, the identity mismatch, the transfer and the corrections.

**Every agent exit has at least one scenario**, and `build.py` asserts the count. Two were added
back for exactly that reason: **11** `dob-refused` (a refusal is not a mismatch — there is no value
to compare, so the agent must stop asking and exit; 40 covers only a *wrong* date) and **24** `upset`
(Patient Upset is its own exit on both agents, and the one most easily confused with Human
Requested).

## Before every board, in order

1. **Re-run `build.py`.** The mock dates the missed appointment from *America/Los_Angeles today*
   and the slots from the next three weekdays, and the rubrics pin those dates as the clinic
   record. A suite built yesterday judges the agent against yesterday's record and fails a correct
   call. Then `create.py --sync` pushes the new dates. It also re-asserts that every persona's
   spoken date of birth still matches the one its own trigger sends — a drift there fails
   verification and takes the whole scenario with it.
2. **`FHCSD_PASSCODE` must exist on the account** the flow runs under (local org
   `<AUTH_ID>`, variable uuid `38bd302f-b6b3-4087-807a-6886e7ea65c9`). Each action reads
   it from its own environment via `os.environ.get("FHCSD_PASSCODE", "")` and refuses before any
   request when it is empty. The lookup is cached per `auth_id` with an empty payload cached on
   failure, so a call made before it existed can keep failing after.
   Prove the actions themselves first, no call needed:
   `FHCSD_PASSCODE=$(cat $SC/fhcsd_passcode) python3 FHCSD/verify_actions.py`.
3. **The mock must be deployed.** `worker.js` has the Druid contract, the 409, the HTML-409 and the
   new steers, but **`wrangler deploy` is MK's click** — until then the live worker serves the old
   contract and scenarios 41–46 cannot pass. Run `node FHCSD/mock/selfcheck-local.mjs` first: it
   exercises the whole contract in-process, no deploy and no network.
4. **The flow must be the one these payloads point at.** `urls.json.flow_uuid` is
   `28bb36dc-b645-4e81-b941-54c976558023`. Paste `flows/fhcsd-v29-real-config.json` into *that*
   flow and save; a different flow means changing `flow_uuid` and re-running build + `--sync`.
5. **Re-check the runner share.** `https://<runner-tunnel-host>` → `127.0.0.1:25003`. A
   re-minted share breaks all 46 at once; one edit in `urls.json` fixes all 46.
6. **Check the dev Hunter pod for foreign traffic** (`GET /api/runs?limit=10`) — another team's
   suite alongside starves calls and voids the board.
7. **`maxParallel: 4`.** MK's rule, 2026-08-31: at 15 the pod starves STT and the re-asks read as
   agent defects. 4 is the number.

```bash
SC=<scratchpad>            # holds hunter_cookie and fhcsd_local_auth, both mode 600
node FHCSD/mock/selfcheck-local.mjs
python3 FHCSD/build-v29-agent-flow.py                     # the flow, against the mock
python3 FHCSD/hunter/v29/build.py                         # the payloads, with today's dates
python3 FHCSD/hunter/v29/create.py --cookie $SC/hunter_cookie --auth $SC/fhcsd_local_auth --sync
# then, ONLY on MK's go:
#   POST /api/runs {"name":"FHCSD v2.9 board 1","scenarioIds":[...],"maxParallel":4}
```

`--sync` touches the **29 kept** scenarios only. Add `--all` for a pass that also rewrites the 19
parked ones — needed exactly once, when a scenario moves between the two categories.

### Three env vars on the flow builder

`build-v29-real-flow.py` takes its target and its two phone numbers from the environment, so the
prod build is a variable change rather than an edit:

| var | default | effect |
|---|---|---|
| `FHCSD_TARGET` | `mock` | `real` bakes `https://service.fhcsd.org` into every action body **and** writes `flows/fhcsd-v29-agent-prod-config.json` instead, so the mock build is never overwritten |
| `FHCSD_FROM` | `+12813056522` | the outbound caller ID (no `from_number` in the trigger payload any more) |
| `FHCSD_TRANSFER_TO` | `+14582909672` | the Transfer to Staff destination — a Hunter pool number locally, the staff line in prod |

`FHCSD_TARGET=real python3 FHCSD/build-v29-agent-flow.py` validates clean. The validator fails the
build if the real hostname appears while the target is still `mock`, so pointing at the live,
IP-allowlisted host stays a deliberate act. **Nothing has been run against real.**

## The one placeholder

`payload.initiationRequest.headers.Authorization` is `__FROM_SCRATCHPAD__` in every file and the
real Basic header on Hunter. `create.py` substitutes it at POST time from
`scratchpad/fhcsd_local_auth` and applies the same substitution before diffing, so a clean diff
still means "Hunter holds this file". No other field is a placeholder.

## How the mock picks a branch — the patient's LAST NAME, nothing else

`FHCSD/mock/worker.js`, `STEER`/`ALIAS`. Every other surname is the happy path. The endpoints that
never see a name recover the steer from the MasterId, which is a stable hash of it.

| last name | what the mock does | which action sees it |
|---|---|---|
| `Tran` | `GetPatients` → `[]` | match |
| `Delacroix` | `GetPatients` → two rows | match |
| `Achterberg` | patient matches, `GetPatientAppointments` → `[]` | appointments |
| `Kaminski` | every Druid call → 401, even on a token minted a moment earlier | match (success false) |
| `Kowalski` | `GetAvailableAppointments` → `[]` | search |
| `Bergstrom` | availability → exactly one slot | search |
| `Nakamura` | availability → exactly two slots | search |
| `Ferreira` | `SaveAppointment` → 2xx with `Error: 1` | reschedule |
| `Okonkwo` | `SaveAppointment` → HTTP 409 | reschedule |
| `Oyelaran` | `SaveAppointment` → 409 with a `text/html` body | reschedule (409 seen through HTML) |

**The date of birth is no longer validated by the API — by design.** The trigger carries it,
`GetPatients` echoes it back, and the *agent* compares what the patient says against it. So a wrong
date of birth is finally testable (scenario 40), and the mock needs no steer for it.

## The scenarios

Rows marked _parked_ are in `FHCSD v2.9 (parked)` and are not on the board.

| # | id | scenario | what it proves |
|---|---|---|---|
| 01 | 18622 | Reschedule — the clean walk, first slot, no date preference | the clean walk end to end: 4 Auth/Druid pairs, one DOB statement, three options, ONE booking confirmation |
| 02 | 18623 | Reschedule — takes the SECOND of three slots | the second option's own ProvScheduleId, FromSlotId and ApptDate must be the ones copied into the save |
| 03 | 18624 | Reschedule — names one specific day as the preference | a named day becomes `StartDate`, formatted MM-DD-YYYY by the agent |
| 04 | 18625 | Reschedule — gives a range, not a day | _parked_ — a range is taken as given; no end date is ever asked for (the node sends EndDate empty) |
| 05 | 18626 | Availability — insists on one specific day | _parked_ — only slots the search returned are offered, however hard the patient pushes |
| 06 | 18627 | Availability — will only take a morning | _parked_ — a constraint the search cannot express is handled honestly, not by inventing a filtered list |
| 07 | 18628 | Availability — nothing comes back at all | an empty availability array reaches `Has Slots` -> End No Slots, with the callback number and no invented slot |
| 08 | 18629 | Reschedule — declines outright, does not want to rebook | the first no ends the call; it is not queried a second time |
| 09 | 18630 | Booking — backs out at the confirmation | _parked_ — alternatives offered once, then Patient Declines, nothing saved |
| 10 | 18631 | Booking — a "maybe" must not book | _parked_ — hesitation is **not** consent: `book` never fires |
| 11 | 18632 | Verification — refuses to give a date of birth | Verification Failed with zero disclosure and no offered workaround |
| 12 | 18633 | Structural — GetPatients finds no patient, so the call is never placed | GetPatients returns [] -> End Verification Failed **without dialling** |
| 13 | 18634 | Structural — two patients match, so the call is never placed | two rows -> `.1.MasterId` exists -> End Verification Failed **without dialling**; no record is read out |
| 14 | 18635 | Verification — date of birth given in words | _parked_ — a spoken-word date is taken, stated once, compared silently |
| 15 | 18636 | Verification — date of birth given as bare digits | _parked_ — digits become a date; month and day are not transposed |
| 16 | 18637 | Verification — partial date of birth, completed on one ask | the year is asked for once and never guessed |
| 17 | 18638 | Verification — date of birth corrected after it was stated | the correction wins, and a read-back **of a correction** is correct, not a defect |
| 18 | 18639 | Booking — changes her mind after choosing a slot | the ids copied into the save are the third option's, not the first's |
| 19 | 18640 | Availability — volunteers a day before anything is offered | _parked_ — an unchecked day is never confirmed as available; it becomes `StartDate` |
| 20 | 18641 | Out of scope — asks what the visit will cost | _parked_ — no price, no insurance position, the main number instead, then back to the flow |
| 21 | 18642 | Out of scope — asks to be called back later | _parked_ — a mid-call bad time is accepted and closed without saving (lands on Patient Declines — see the note below) |
| 22 | 18643 | Transfer — asks for a person mid-walk | Transfer to Staff from Agent A, announced once, not treated as anger |
| 23 | 18644 | Emergency — chest pain mid-walk | 911, no medical advice, the reschedule abandoned |
| 24 | 18645 | Upset — angry about being called by a machine | one apology and close; not routed as a transfer |
| 25 | 18646 | Verification — demands the details before verifying | _parked_ — the one rule that outranks everything, under three pushes — and the agent holds a DOB it must not leak |
| 26 | 18647 | Booking — the save comes back Error 1 and must not be claimed | 2xx with Error 1 -> `Save Result` slot-taken -> End Slot Taken; never claimed as booked |
| 27 | 18648 | Disclosure — patient insists there were two appointments | _parked_ — anti-fabrication: only the one appointment GetPatientAppointments returned |
| 28 | 18649 | Side question — "who is this?" right after screening | _parked_ — answered once, briefly, with no detail, then back to the question |
| 29 | 18650 | STT — heavy background noise over the date of birth | _parked_ — asks for a repeat instead of proceeding on a value it did not hear |
| 30 | 18651 | Booking — caller cuts across the read-back | the interruption is the answer; the read-back is not restarted |
| 31 | 18652 | Abandoned — goes silent after the disclosure | nothing saved, and the agent does not talk into silence forever |
| 32 | 18653 | Screening — answering machine picks up | the generic message only — a machine is not a verified patient |
| 33 | 18654 | Screening — the patient never picks up | _parked_ — the screening no-answer branch; nothing disclosed |
| 34 | 18655 | Screening — a family member answers, the patient is out | nothing disclosed to a third party, and no verification attempted with them |
| 35 | 18656 | Transfer — asks for a person before verifying anything | _parked_ — the transfer fires before identity, and the recorded DOB does not leak on the way out |
| 36 | 18657 | Reschedule — two values given in one breath | both values captured from one answer; neither is asked for again |
| 37 | 18658 | Out of scope — wants to cancel, not reschedule | _parked_ — a cancellation is out of scope: handed to the clinic number, never claimed (Cancel exists in the mock, not in the flow) |
| 38 | 18659 | Out of scope — asks to book a second, different appointment | the extra request is never invented, and the follow-up question is actually asked |
| 39 | 18660 | Subtlety — the three confirmation shapes in one call | the confirmation contract: stated dob, acknowledged yes, stated slot, ONE booking confirmation |
| 40 | 18661 | Verification — the date of birth does not match the record | **the new identity test**: a wrong date ends the call, and the agent never says the date it holds |
| 41 | 18662 | Structural — the patient has no appointment, so the call is never placed | a patient with no appointments -> End No Appointment **without dialling** |
| 42 | 18663 | Structural — a Druid call rejects the token, so the call is never placed | a rejected token is a breakdown, not 'no patient' and not 'no availability' — **no dial** |
| 43 | 18664 | Booking — the save returns HTTP 409, the patient already has one | HTTP 409 -> `Save Failure Kind` -> End Already Has Appointment, never a claimed booking |
| 44 | 18665 | Booking — the save answers 409 as HTML, which the platform cannot parse | a text/html 409 loses its status to phlo's rewrite; the flow must degrade to the generic failure, still never claiming a booking |
| 45 | 18666 | Availability — exactly one slot comes back | one slot comes back: one option offered, no blank option, nothing invented |
| 46 | 18667 | Availability — exactly two slots come back | two slots come back: two options offered, and option 2 books the second slot |

## What the rubrics assume about V2.9 — read this before calling a red real

Every `evaluationPrompt` carries the same preamble, verbatim, because a rule the judge is not given
is one it invents the opposite of (the TeleCRM "Noted" lesson). It states that:

- the agent **never says any part of the date of birth before the patient has** — new, and the most
  important one: the flow now holds it, so leaking it would hand the answer to whoever answered.
- a value is **stated once with a short acknowledging word** and not queried — "November sixth,
  two thousand three, got it". Demanding "is that correct?" is wrong. This covers **dob, date, text
  and address** as well as choice, currency and number (D-089, tree `229f0285d`).
- a **yes or no is acknowledged without being repeated**. "So that's a yes to rescheduling,
  correct?" is the defect, not the fix.
- **exactly one** thing is put to the patient for agreement: the whole booking, read back with
  date, time, provider and facility, before it is saved.
- a **corrected** value may be read back and agreed to — the correction floor restores it.
- the **clinic record** is pinned with today's dates, and anything else the agent says is invented;
  the slot times are fifteen-minute windows, and speaking either the window or its start is fine,
  while reading digits or hyphens aloud is a defect.

If the rig is rolled back to a tree where `dob` is not in `_SHAPE`
(`V2.9-Agent-Node/repo/src/units/collect_input.py`), scenarios 14, 15, 16, 29, 36 and the
`DATE OF BIRTH IS STATED, NOT QUERIED` criterion elsewhere will false-fail: the fix is one
`create.py --sync` after editing `C_STATE_DOB` in `build.py`. And never compare a rubric on Hunter
with the one in a file by memory — `create.py --diff` does it field by field.

## Deliberately not covered, and why

- **The `name`, `phone`, `email`, `address` and `dtmf` collectors.** This flow declares none of
  them, so the "read back and wait" half of the D-089 table cannot be exercised here at all. It
  needs a different flow; `acme-v29-local` has all five field types.
- **Booking a new appointment, and cancelling one.** MK confirmed the flow stays reschedule-only.
  `CancelAppointment` and the book-new 409 are in the mock so the flow can grow without another
  mock change; scenarios 37 and 38 test the refusal, which is the only correct behaviour today.
- **A mid-call callback request has no exit of its own.** Spec §6 leaves Bad Time to the screening
  node, so a patient who asks to be called back *after* screening lands on `Patient Declines`
  (scenario 21). That records the wrong reason and schedules no retry — a spec question, in GAPS.
- **`EndDate`, and any date arithmetic.** The agent supplies `start_date` already formatted, and
  both dates are nullable, so "no preference" sends neither and the vendor's own window applies. MK has asked FHCSD
  whether `GetAvailableAppointments` requires one (question 7).
- **The patient-scoped `AuthenticationToken`.** Both header names carry the vendor token, as prod
  does. If FHCSD confirm the per-patient token is required, it is one line in the shared prelude.
  See GAPS N3.
- **The real host.** `service.fhcsd.org` is IP-allowlisted and 403s from here; the builder's
  validator fails the build if that hostname ever appears in the config.
- **The `Transfer to Staff` leg actually being answered.** `to` is a Hunter pool number, so 22 and
  35 prove the announcement and the routing, not a connected human.
- **`answerBehavior`** (scenario 33) is a payload shape we have never used. Read the run item's
  `error_message`, not a judge verdict, and expect to adjust it once.
