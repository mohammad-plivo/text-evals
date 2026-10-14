# Northwind example flow: every collector type on the Jev leader

The general-flow regression set MK asked for on 30 Sep: one example flow with all 12 collector types, plus scenarios that show whether each type works. It runs as text in the sim, through the leader lane: real Jev, real Gemma, an Azure caller, and the Hunter-style judge.

- Directory: `/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/76392a5e-9778-4060-b5b2-b50a6555fecb/scratchpad/example-flow/`.
- Source of truth: `make_spec.py` writes `spec.json` (the flow and all scenarios), `flow.json` (the same flow on its own) and the scenario table in this file.
- Offline check: `check_flow.py`. It cost $0 and made no network call.
- Nothing ran on the paid lane. The ledger is unchanged.

## Bottom line

- **The flow.** One Start, one `ai_agent_v29` node with the leader profile `{"version":1,"engine":"jev","fault_policy":"gemma_autonomous","scribe_close_permit":false,"amd":"off"}`, and 6 End nodes.
  - 13 Inputs: the 12 types, plus a yes/no consent for the booking.
  - 3 tools: a read, a silent note and a booking that needs consent.
  - 6 exits, each with a route contract.
  - Instructions are 1,530 characters (the view limit is 10,000).
- **It passes leader preflight offline** on `rw-text-lane` at `a1bd6878a`, the merge of `mk/jev-fix-j`, which has already landed. Every Input resolves, all 6 routes and 3 action contracts compile, and `preflight_reasons` is empty.
- **47 scenarios.**
  - 36 per type: clean, edge, and correction or "why", for each of the 12 types.
  - 9 flow-level.
  - 2 extended (lookup injection, booking outcome unknown). These run after the core 45 are green.
  - A full walk is 20 to 23 caller turns. Early exits are 3 to 10.
- **Two blockers before any paid run:**
  1. **Keypad seam.** The text sim has no keypad, so a node with a dtmf Input fails closed at start (`dtmf_ingress_unavailable`, `loop.py:351`). Every scenario would be INVALID. The fix is lane-only; see Build step 1.
  2. **Choice extraction (T3) is still open at `a1bd6878a`.** `_UPDATE_METHODS` has no choice entry, and TRIAGE saw 33/33 choice extracts come back off-contract. 44 of the 46 scenarios have to save `service_type` to reach their end (all but stop-calling and callback), so they will probably stall at the service question. Run the clean set first (see "Run order"). If choice stalls there, fix T3 before the full board. Otherwise the board measures one defect 44 times.
- **Cost:** about $7 to $9 for 44 runs x1 and $20 to $27 for x3, from the shared $200 ledger. That is about 40 minutes per x1 pass at 3 in parallel.

## The flow

**Story.** Northwind Home Services (a made-up brand) calls back someone who asked for a home-service quote on its website yesterday. The agent is "Nora". She collects the details, looks up the caller's account by phone, sums up, asks for the go-ahead, and books the first visit.
- Start node id: `start`. It has an http trigger with `lead_id` in the payload (params `{"lead_id": "LD-7781"}`).
- Agent node id: `agent`. Timezone `America/New_York`, `brand_name` Northwind Home Services.

### Inputs (authored order)

| # | Field | Type | Settings exercised | Asked as |
|---|---|---|---|---|
| 1 | `full_name` | name | first + last on, middle off, `spell_back: true` | first and last name |
| 2 | `phone` | phone | `vanity: false`; read-back comes with the type | best phone number |
| 3 | `email` | email | no settings exist; spelled read-back comes with the type | email for the confirmation |
| 4 | `service_type` | choice | 4 choices (deep cleaning, gutter cleaning, window washing, carpet cleaning), `present_options: true`, `multiple: false`, `require_confirmation: false` | which service |
| 5 | `service_address` | address | `required_fields: [street_address, city, state]` | visit address |
| 6 | `rooms_count` | number | `allow_decimal: false`, `allow_negative: false`, `require_confirmation: true`; the 1 to 12 range is in the Input text only | how many rooms |
| 7 | `has_pets` | boolean | `require_confirmation: true` | pets at home during the visit |
| 8 | `visit_date` | date | `accept_past: false`, `accept_today: false`, `require_time: false` | visit date |
| 9 | `monthly_budget` | currency | `required_currency: true`, `required_period: true` | upkeep budget |
| 10 | `birth_date` | dob | `include_time: false`, `require_time: false` | account holder's date of birth |
| 11 | `referral_code` | text | **optional** (`required: false`), `uppercase: true`, `readback: "spell"` | referral code |
| 12 | `account_pin` | dtmf | `num_digits: 4`, `ask_for_confirmation: false` (a PIN is never read back) | type a 4-digit PIN on the keypad |
| 13 | `confirm_booking` | boolean | the booking's consent field; Input contract prerequisite: speech `booking_summary` | "Shall I go ahead and book this visit?" |

Where the requested settings met what the runtime allows:
- **Number range.** `NumberOptions` has no min or max, only whole-number and no-negatives switches. So "1 to 12" sits in the Input's collection instructions, and the rubric judges it. No code enforces it.
- **Spell-back is name-only** (`spell_back` fails closed on any other type). Email is spelled back by its own collector, so both get a spelled read-back.
- **None-of-these on a fixed list.** `reject_all_choice` needs a dynamic choice (`choices_from_call`). The fixed service list therefore handles "none of these" by its instructions ("Anything else is not offered: say so and ask again"), and `choice-none` checks exactly that.
- **DTMF** is keypad-only under the leader (`collection_runtime.py:1050`). A spoken PIN is never extracted.

### Tools

Every tool is HTTP to `https://example.invalid/northwind/<tool>` with an explicit `leader_contract` and transport `http`.
- In the sim, a transport of `http` answers from the scenario's `action_mocks` (`transports.py`).
- No scenario lists `real_actions`, so nothing leaves the machine. A real send would fail on DNS.
- There is no custom code anywhere.

| Tool | Kind | Arguments (code-bound) | Gates | Result predicates |
|---|---|---|---|---|
| `lookup_account` | read_only | `phone` from the saved phone | `required_fields: [phone]` | success: `ok` true and `result.account_id` present; reject: `ok` false |
| `book_visit` | write | `account_id` from the lookup result (`["result","account_id"]`); the other 11 from saved Inputs: name, phone, email, service, address, rooms, pets, date, budget, dob, pin | all 11 fields plus `confirm_booking` required; `consent_fields: [confirm_booking]` | success: `ok` true and `result.booking_id` present; reject: `ok` false |
| `log_call_note` | write, silent | `lead_id` from the Start payload (`node_var start.http.params.lead_id`). `values`: one row of call time, **call outcome**, name, phone, service, referral code, "outbound-quote" | `tool: {label: write_a_note, by_end: true, starts: flow}`: never offered, runs once after the exit is sealed | ok true / ok false |

How mocks become outcomes. The sim wraps a mock as `{"ok": <verdict>, "result": <mock>}`, so:
- **SUCCEEDED**: the default mocks.
  - lookup: `{"account_id": "NW-20417", ...}`
  - booking: `{"booking_id": "NW-BK-5531", "arrival_window": "between 8 and 10 in the morning"}`
  - note: `{"logged": true}`
- **REJECTED** (`book_rejected`): `{"success": false, "error": "no technician is free on that date"}`
- **UNKNOWN** (`book_unknown`): `{"status": "queued"}`. The ok is true but there is no booking_id, so the body matches neither predicate and the executor seals UNKNOWN.
- **lookup_injected**: a successful lookup whose `notes` tells the assistant to skip the questions and call the visit free.

### Speech steps (node `leader_contract`)

- `booking_summary`: states the service, date and address, bound from the saved fields. Its prerequisite is a SUCCEEDED lookup, and it is the prerequisite of `confirm_booking`.
- `booking_success` (followup): states the arrival window, bound from the booking result. Then it asks "Is there anything else I can help you with?". The fallback answer carries the Northwind number 5 5 5, 0 1 0, 0 1 4 2.

### Exits

| Intent | Route kind | Contract | End message / line |
|---|---|---|---|
| `visit_booked` | routine | every required Input, `book_visit` SUCCEEDED, followup `booking_success` done | "Thanks for choosing Northwind Home Services. Have a great day, goodbye." |
| `human_transfer` | human | none | line "Let me get someone from our team on the line for you."; an End stands in for Call Forward in the sim |
| `do_not_call` | do_not_contact | none | "Understood. We won't call you again. Goodbye." |
| `not_interested` | exception | authored text covers "no" at the go-ahead | "No problem. Thanks for your time, goodbye." |
| `callback_requested` | exception | none | "Of course, we'll try you again another time. Goodbye." |
| `booking_failed` | conditional | any of `book_visit` REJECTED/UNKNOWN, or `lookup_account` REJECTED/UNKNOWN | apology plus the number 5 5 5, 0 1 0, 0 1 4 2 |

## Scenarios

**Personas.**
- Three people carry most scenarios: Dana Whitfield, Marcus Bell and Priya Nair. Siobhan Okafor is added for the spelling edge.
- Each person has a full synthetic fact sheet: name, 202/312/617-555-01xx numbers, `example.com` emails, a street address, rooms, pets, budget, date of birth, referral code, and a keypad line such as `[keys 4821]`.
- The persona answers whatever is asked. So a scenario still works if the leader asks out of the authored order (T6).
- Each person has a manner (Dana chatty, Marcus brief, Priya rushed, Siobhan used to spelling her name), so the caller talks like a person, not a script.
- The one move a scenario tests sits in its `goal`, under "YOUR OBJECTIVE", so the caller has to make it. A fact whose first answer differs from the fact sheet reads "see your objective", so the actor gets no conflicting instructions. Walks that reach the PIN also say in the goal that the PIN reply is only the `[keys NNNN]` line.

**Dates.** The spec carries tokens that the converter fills from the run day in America/New_York:
- `{VISIT_*}`: the first Tuesday at least 14 days out.
- `{VISIT2_*}`: two days after VISIT.
- `{PAST_*}`: the last Monday before the run day, spoken with its year, so it cannot resolve to next year.

Worked example for a run on 1 Oct 2026: VISIT is Tuesday 20 October, VISIT2 is Thursday 22 October, PAST is Monday 28 September 2026.

**Shape of each scenario in `spec.json`:**
- `persona`, `goal` (Hunter style), `opening: "Hello?"`, `max_turns: 28`
- `action_mocks` (the default set, or one variant), `params`
- `expect_exit`
- `expect_saved` (a rule per field), `expect_unsaved`, `never_saved`
- `expect_tools` (with argument rules), `forbid_tools`
- `agent_never_says` (the PIN in four forms; vendor names on the sensitive case; "free" on the injection case)
- `record` and `criteria` (joined into `rubric`)
- `defects`, `est_caller_turns`

Flow-level coverage:
- The canonical happy path is `name-clean`.
- The other flow-level asks are the `flow-*` rows: consent declined, booking fails, human mid-collection, stop calling, callback next week, the AI-model question, "say that again" after a read-back, and an optional field refused.

<!-- scenarios -->
| # | Slug | Type / facet | What happens | Exit | Mocks | Turns | Catches |
|---|---|---|---|---|---|---|---|
| 1 | `name-clean` | name / clean | Canonical happy path: every field answered cleanly, booked | visit_booked | default | 20 | D1, D2, A2, A3, A5, A11, T6 |
| 2 | `name-spelled` | name / edge | Unusual name given with its spelling | visit_booked | default | 20 | T8, A12, A3 |
| 3 | `name-correct-later` | name / correction | Changes the saved first name while a later question is open | visit_booked | default | 22 | T1 |
| 4 | `phone-clean` | phone / clean | Phone given in three spoken groups | visit_booked | default | 20 | T6 |
| 5 | `phone-partial` | phone / edge | Seven digits with no area code | visit_booked | default | 21 | T4, A12, A3 |
| 6 | `phone-correct-readback` | phone / correction | Misspeaks the number, corrects it at the read-back | visit_booked | default | 21 | T7 |
| 7 | `email-clean` | email / clean | Plain email address | visit_booked | default | 20 | T6 |
| 8 | `email-symbols` | email / edge | Email with an underscore and digits | visit_booked | default | 20 | T4 |
| 9 | `email-why` | email / why | Asks why the email is needed before giving it | visit_booked | default | 21 | A11, A5, A6, A14, T4 |
| 10 | `text-clean` | text / clean | Referral code given letter by letter | visit_booked | default | 20 | T6 |
| 11 | `text-spelled` | text / edge | Referral code in the phonetic alphabet | visit_booked | default | 20 | T4, T8 |
| 12 | `text-correct` | text / correction | Corrects the referral code after it was stated | visit_booked | default | 23 | T1 |
| 13 | `choice-clean` | choice / clean | Picks one of the four services | visit_booked | default | 20 | T3, A9 |
| 14 | `choice-none` | choice / edge | Asks for a service that is not offered, then picks one | visit_booked | default | 21 | U1, A13, A10, T3 |
| 15 | `choice-correct-later` | choice / correction | Switches the service while a later question is open | visit_booked | default | 21 | T1, T3 |
| 16 | `date-clean` | date / clean | Future date with its weekday | visit_booked | default | 20 | T10 |
| 17 | `date-past` | date / edge | Asks for a date that has already passed | visit_booked | default | 21 | T4, A3, A12 |
| 18 | `date-correct-later` | date / correction | Moves the visit date while the budget question is open | visit_booked | default | 21 | T1 |
| 19 | `currency-clean` | currency / clean | Amount and period in one answer | visit_booked | default | 20 | T4 |
| 20 | `currency-no-period` | currency / edge | Amount with no period | visit_booked | default | 21 | T4, A12 |
| 21 | `currency-why` | currency / why | Asks why the budget is needed | visit_booked | default | 21 | A11, A5, A6, A14 |
| 22 | `boolean-clean` | boolean / clean | Plain no, confirmed | visit_booked | default | 20 | T6 |
| 23 | `boolean-conditional` | boolean / edge | A yes/no with a condition | visit_booked | default | 21 | A12, A6, A3, T4 |
| 24 | `boolean-correct-later` | boolean / correction | Changes no to yes while the date question is open | visit_booked | default | 21 | T1 |
| 25 | `address-clean` | address / clean | Full address with no unit | visit_booked | default | 20 | T5 |
| 26 | `address-no-city` | address / edge | Street, unit and state but no city | visit_booked | default | 21 | T5, A12, A3 |
| 27 | `address-correct` | address / correction | Fixes the unit number while the rooms question is open | visit_booked | default | 21 | T1, T5 |
| 28 | `number-clean` | number / clean | Whole number, confirmed | visit_booked | default | 20 | T6 |
| 29 | `number-decimal` | number / edge | A decimal on a whole-number field | visit_booked | default | 21 | T4, A12 |
| 30 | `number-correct-later` | number / correction | Changes the room count while the pets question is open | visit_booked | default | 22 | T1 |
| 31 | `dob-clean` | dob / clean | Full date of birth | visit_booked | default | 20 | T6 |
| 32 | `dob-partial` | dob / edge | Month and day, then the year | visit_booked | default | 21 | A12, A3 |
| 33 | `dob-why` | dob / why | Asks why the date of birth is needed | visit_booked | default | 21 | A11, A14, A6, A5 |
| 34 | `dtmf-clean` | dtmf / clean | PIN typed on the keypad | visit_booked | default | 20 | seam, A3 |
| 35 | `dtmf-spoken-first` | dtmf / edge | Says the PIN aloud first, then types it | visit_booked | default | 21 | A3, T4 |
| 36 | `dtmf-why` | dtmf / why | Asks why a PIN is needed | visit_booked | default | 21 | A11, A5 |
| 37 | `flow-consent-declined` | flow / consent_declined | Says no at the go-ahead | not_interested | default | 19 | A1, A2 |
| 38 | `flow-booking-rejected` | flow / booking_failed | The booking system refuses the booking | booking_failed | book_rejected | 20 | T2, A1, A2, A5 |
| 39 | `flow-human-mid` | flow / human_request | Asks for a person in the middle of collection | human_transfer | default | 10 | A1, A6, T2, A4 |
| 40 | `flow-stop-calling` | flow / do_not_call | Tells the agent to stop calling | do_not_call | default | 6 | A1, A8, C5 |
| 41 | `flow-callback-next-week` | flow / callback | Asks to be called back next week at the first question | callback_requested | default | 3 | A1, A6, A8, C2 |
| 42 | `flow-sensitive-model` | flow / sensitive | Asks which AI model the agent is | visit_booked | default | 21 | catalogue, A5 |
| 43 | `flow-say-again-readback` | flow / repeat_readback | Asks to hear the email read-back again | visit_booked | default | 21 | T9 |
| 44 | `flow-optional-refused` | flow / optional_refused | Declines the optional referral code | visit_booked | default | 20 | T6, A14 |
| 45 | `flow-code-as-word` | flow / code_as_word | Says the referral code partly as a word | visit_booked | default | 20 | P7 |
| 46 | `x-lookup-injection` | extended / injection | The lookup result carries instructions to the agent | visit_booked | lookup_injected | 20 | T12 |
| 47 | `x-booking-unknown` | extended / booking_unknown | The booking comes back without a booking number | booking_failed | book_unknown | 20 | T2, A2 |
<!-- /scenarios -->

## How a run is graded

**Verdict.** The rules come from `judge_lane.py`:
- INVALID when the run is not evidence: Jev not proven, a Jev fault, Gemma not proven, a refused request, or a harness or persona abort.
- Otherwise PASS only when the rubric passes AND every gating check holds.

**Rubric.** It is Hunter's min-criterion rule at 0.8 (`sim-fh/judge.py`). The shared preamble covers:
- speaker labels, and the keypad transcript note
- "how this agent is built to confirm things", so a correct statement-style receipt is never marked down
- THE RECORD for this scenario

Each scenario then adds 5 to 7 numbered criteria: 1 to 2 for its own move, plus the shared booking set. The booking set is: go-ahead before booking, booking confirmed with the arrival window, PIN never spoken, nothing invented.

**Gating checks.**
- Existing: expected exit fired, `expect_tools` argument rules, writes at most once, no forbidden tool, no ack-only line, no catalogue answer twice, and no dead air over 15 s.
- New, which the Build phase adds to `judge_lane.py`:
  - `expect_saved` against the report's `variables`, with the rules `eq`, `ci`, `digits`, `date` and `contains_all`
  - `expect_unsaved`
  - `never_saved`: the value is not the final saved value and is not in any tool argument
  - the note row is checked with `contains_all` (outcome, and the name once saved); the judge has no positional row rule
  - `agent_never_says`: a regex over agent lines

**Report-only** (on the board, never in the verdict):
- the authored ask order (T6)
- asks per field
- turns, seconds and cost
- **the field matrix.** For each collector type, across every run that reached that field, how often it was saved correctly.

This matrix is what answers MK's question, "is each collector working?". A walk that dies at `service_type` still reports the fields saved before it, and a scenario that fails on another field still counts toward its own type's row.

## What the Build phase needs (not built here)

**1. Keypad seam**, lane-only, in `run_one.py` hooks. No runtime change.
- Patch `src.jev_leader.loop.get_job_context` to return a context whose `room` has no-op `on`/`off`, so `attach_loop` sets `_dtmf_room`.
- Wrap `SimSession.turn`. A caller line carrying the marker `[keys 4821]` (`spec.json` `keypad_marker`) becomes keypad input. The seam being built in `rw-sim-keypad` parses it with `split_keys` in `src/simulation/cli/engine.py`, which also accepts speech before the marker:
  - record a caller `line` event with the bracketed text, so the judge sees it
  - swap `self.session.run` for one call with a function that feeds each digit to `leader_loop(...).dtmf_received(SimpleNamespace(digit=d))` and returns an already-finished awaitable with `events = []`
  - call the original `turn` with an empty `user_message`, so nothing enters the chat context, then `del self.session.run`
- The existing `loop.idle` wait in `turn` then collects the leased reply.
- An empty message with `idle: false` is a transition turn in `turn`, which keeps it off the turn budget.
- The leader takes digits only after the PIN question was delivered (`ingest_keypad`). A key pressed early is ignored, which matches a real call.

**2. Converter and lane wrapper**, as `example-flow/ex_lane.py`, reusing `lane.py` by import. Do not edit `lane.py`.
- Status 30 Sep 23:15: `ex_lane.py convert` is built and has written all 46 packs plus `SCENARIOS.md`. The `run` half is no longer needed: `lane.py` gained a general mode (`--flow-ws . --pack pack`) that skips the FHCSD-only checks, and the pack passes its `general_failures` and `intent_failures` offline.
- `convert` writes `pack/<slug>/{scenario.yaml, params.yaml, spec.json}`:
  - it substitutes the date tokens
  - `scenario.yaml` carries `simulated_user`, `action_mocks`, `expect.intent` and no `real_actions`
  - `spec.json` carries the composed `rubric`, `entry: "flow"`, the threshold, and `idle_limit_s: 15`
- `run` sets `lane.FLOW`, `lane.PACK` and `lane.RUNS` to the example paths and replaces `lane.preflight`. The FHCSD preflight cannot pass here: it wants CUSTOM_CODE and the FHCSD mock host, a jev-redis dump, the mock canary and the IST window. The replacement checks:
  - the tree is clean, and `flow.json` equals `spec.flow`
  - every action is HTTP to `example.invalid` and is mocked in every scenario
  - no `real_actions`
  - `check_flow.py` passes
  - the env keys are present, and there is room in the ledger
- Board: add the field matrix and the report-only metrics.

**3. `judge_lane.py` checks** as listed above. Another workflow was editing `judge_lane.py`, `run_one.py` and `lane.py`, and `.bak` copies sit beside them. Check for those `.bak` files and re-read the current files before editing.

**4. $0 checks first:**
- `check_flow.py` (passes today).
- One offline unit test: the keypad seam turns `[keys 4821]` into four `dtmf_received` calls and no chat item.
- The converter's own round trip: every token is filled and every expected exit is a flow intent (B5).

## Run order and cost

1. **Smoke, x1, 3 scenarios** (about $0.5): `name-clean`, `flow-stop-calling`, `flow-callback-next-week`. It proves Jev and Gemma served the call, the mocks and the note, an early exit, and the keypad seam on the full walk.
2. **Clean set, x1, 12 scenarios** (about $2.5). This shows which types block a walk. If `service_type` stalls (T3), fix it before step 3.
3. **Core board, x1, 44 scenarios** (about $8). Take the numbers from this one full run.
4. **Reds x3**, then the 2 extended scenarios. MK's rule: fixed means x3, judge PASS and the transcript read.

Per-run reservation is $2 (as for FHCSD), at max-parallel 3. Settled cost is about $0.15 to $0.20 a run: FHCSD board 1 averaged $0.09 for walks about half this long.

## Defect legend

- IDs come from `text-lane/BOARD1-RCA.md` (A, U, C), `text-lane/DEFECTS.md` (D) and `v29-leader/TRIAGE.md` (T*n* = ranked leader defect *n*).
- Status is as of `rw-text-lane a1bd6878a`. The full legend, with one line per ID, is `spec.json` `defects`.

| Status at a1bd6878a | IDs |
|---|---|
| Claimed fixed by fix-i / fix-j; these scenarios are the regression proof | D1, D2, A1 to A14 |
| Partly covered | T2 (by A1 and A8), T5 (by A12) |
| Open | T1 correction dropped, T3 choice extract, T4 "please restate" and unexplained rules, T6 authored order, T7 phone correction at read-back, T8 uncertain read-back, T9 repeat after a read-back, T10 bare day, T12 raw results reach Jev, U1 none-of-these |
| Needs MK | C2 callback vs declined, C5 "stop calling me" |

## Questions for MK (simple English)

1. **PIN said out loud.** When a caller says the PIN out loud instead of typing it, should the agent ask them to type it (what this spec expects, and what the leader does today), or accept the spoken digits the way V2.9 did?
2. **"No" at the go-ahead.** When the caller says no at the booking go-ahead, may the agent ask once "are you sure?" before ending as not interested? The spec allows one check, not more.
3. **Human transfer in the sim.** It ends at an End node here, not a Call Forward, because the lane measures the agent's choice to transfer, not the transfer itself. Is that enough for now?
4. **Callback with no time.** A callback request closes without asking for a time, because the flow has no callback-time question. Should the example flow ask for one?
