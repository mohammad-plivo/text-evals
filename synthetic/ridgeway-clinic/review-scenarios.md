# review-scenarios: adversarial pass over sim-prepared/scenarios (35 files)

Static review only: no CLI run, no model call. Every claim below about the runtime was read off
`trees/cd6ac6c5` at the cited line; every claim about the judge off `sim-prepared/judge.py`. Scenario
line numbers are the file's own (`ws/scenarios/*.yaml` is a byte copy of `sim-prepared/scenarios/*.yaml`,
built by `build_ws.py`; fix the source, rebuild).

Severity: **HIGH** = a correct agent fails it or a broken agent passes it as written, on every run.
**MEDIUM** = the trick is not what the text says it is, or the expectation is not derivable from the node.
**LOW** = prose is wrong or an assertion is weaker than it could be.

## Runtime facts the scenarios depend on (verified)

| fact | where |
|---|---|
| The sim drives every caller turn as `input_modality="audio"`, so the collectors' audio confirmation gates are live | `src/simulation/runner.py:957` |
| For every shaped type (dob, date, choice, number, currency, text, boolean) the V2.9 router passes `require_confirmation=False` — in BOTH arms. Neither arm asks "is that right?" for those seven; the OFF arm has the LLM *state* the value inside its next step (`_RECEIPT[_STATE]`), the prepared arm has the runtime speak it. Only name/phone/email keep the collector's own read-back | `src/units/collect_input.py:42-50, 55-73, 1005` |
| A correction (`change_earlier_value` / re-entry) forces `require_confirmation=True`; a `known_value` forces it only for identity types | `collect_input.py:1012-1018, 1021-1026` |
| Stored formats: dob/date ISO (`1962-06-09`), number bare (`"35"`), currency `f"{ISO} {float}"` (`GBP 40.0`), boolean `yes`/`no`, choice = the label (keys == labels for a list), name joined, phone as the router stores it | `src/units/tasks/collectors.py:36-96`, `collect_choice.py:_normalize_choices` |
| Every collector's `max_collection_retries` defaults to 1: "unusable turn number 1 itself is answered by calling `decline_*`" — one non-answer turn declines the field; a REQUIRED field then gets exactly one `_REQUIRED_RETRY` (parent must say why + re-open), a second decline is `_REQUIRED_HALT` | `collect_number.py:157,191,248`, `collect_boolean.py:119,154`, `collect_choice.py:129`, `collect_datetime.py:217`, `collect_input.py:94-105, 1147-1156` |
| A caller turn that is a question is never an unusable turn (`answer_side_question`, then re-ask) | `collect_number.py:86`, `collect_choice.py:60`, `collect_boolean.py` template |
| Exit gates: the FIRST intent exit while a required Input has no record is refused with `_EXIT_HALT` ("Call the collect tool for it and let the specialist ask, then take this exit … or call this same handoff again straight away"); an exit in a turn that ended with `?` is refused once | `collect_input.py:106-113, 150-215` |
| `idle: true` → `_drive_idle_reminder`: re-asks the pending field ONLY when `pending_collector_field(state)` finds `state.active_walk_unit._active_node._current_task._subtle_var`; that attribute chain is set only by the V2.5 `AgentTasksUnit`. The V2.9 path never sets `active_walk_unit`, so on this node the reminder is always the flow's verbatim `reminder_msg` ("Are you still there? I'm happy to assist whenever you're ready") via `session.say` | `runner.py:812-876`, `src/handlers/idle_timeout.py:31-42, 57-88`, `src/units/agent_tasks.py:1362` (only setter) |
| This workspace is NOT a flow-session bundle (`flow_session: False`). On an idle turn `run.events` is empty; the reply is recovered only from `serialized_context`, which is `[]` unless `session.current_agent` is a `SharedUnitBase`; the raw-context fallback is gated on `flow_session`. A V2.9 collector is an inline `AgentTask` (not a `SharedUnitBase`), so an idle turn taken while a collector holds the floor returns an EMPTY agent message | `runner.py:985-990, 1035-1046`, `src/units/root.py:42-64` |
| `interrupt_after` cuts the last assistant message of `session.current_agent.chat_ctx` at the FIRST case-insensitive match and raises `ScenarioAbort` on no match | `src/simulation/cli/engine.py:127-137` |
| A scripted call that ends before a turn carrying an `expect:` FAILS the run ("declared expectation(s) could be evaluated") | `engine.py:316-324` |
| `stop_reason` for the terminals is `end_conversation` / `call_forward` | `src/simulation/flow/walk.py:156-162` |
| Both edges of `Log Lead Transfer` reach the call_forward; both edges of `Log Callback Request` reach `End - Callback Scheduled`; only `Update Lead Record` and `Add To DNC` route differently on failure | `ws/flow.json` edges |
| `judge.completed()`: an `expect` with no `ended`, no `intent` and no `stop_reason` is judged as "must end" | `judge.py:263-266` |
| judge re-judges `variables`/`variables_absent` BY VALUE and drops the engine's by-key lines; the engine report still prints them as failures | `judge.py:281-300, 373-381` |
| judge evaluates ONLY: engine verdict, completion, variables by value, and its five speech rules. It never reads a scenario's description | `judge.py:11-27, 318-381` |

## Cross-cutting findings

### X1 — HIGH — the "Judged by transcript" criteria are evaluated by nothing
31 of 35 descriptions carry four numbered criteria ("the switch goes through change_earlier_value",
"the collect_choice call carries a known_value", "the offer is made again", "never says the ISO code
aloud", "the reason is the configured one", …). `judge.py` reads `expect:` only; `known_value` is even
in its `SKIP_ARG_KEYS` (judge.py:45). The engine reads `expect:` only. So every one of those criteria
is prose: a broken agent passes them all, and the scenario claims a measurement it never makes.
**Fix (pick one, state it in NODE.md):** (a) add an LLM-judge step that reads `description` off the
`scenario_started` event (the engine emits it, engine.py:397) and grades each numbered criterion —
that is a paid step for the caller to schedule; or (b) move every mechanically checkable criterion
into `expect:` (per-turn `message_excludes` / `not_intent` / `variables_absent`, listed per scenario
below) or into `judge.py` (a "second value for field F in `timeline`" check covers every
"change_earlier_value or a second collect" criterion; a `known_value`-present check covers both
two-fields scenarios), and delete the criteria that neither can express.

### X2 — HIGH — `judge.completed()` turns four expects into "the call must end"
`question-instead-of-answer`, `two-fields-one-breath-opening`, `early-exit-abrupt-goodbye-mid-collection`,
`declines-phone-twice-halts` declare no `ended`/`intent`/`stop_reason`, so judge.py:263-266 demands
`ended=True`. The first two are scripted mid-walk scripts that cannot end; the third has no intent
that fits and no end tool, so a CORRECT desk cannot end either. Verified statically:
`judge.completed(non-ended walk, expect)` → `['turn 1: ended False, scenario declared True']` for all four.
Per-file fixes below.

### X3 — HIGH — `idle: true` measures the harness on this node type
Two scenarios use it. On an `ai_agent_v29` node the reminder is the flow's fixed line, never the open
field's question (facts table), and when a collector holds the floor the reply is not even recovered
into the turn (`resp.message == ""`), so `spoke_unprompted: true` fails with "the agent said nothing at
all" (scenarios.py:50-55). `pending_collector_field` and the raw-context recovery both exist for the
V2.5 walk only. Verify on the first paid run: an idle turn whose `agent` is empty in the report is
the harness, not the desk. Per-file fixes below.

### X4 — MEDIUM — descriptions assume the OFF arm reads a shaped value back and waits; it does not
`collect_input.py:1005` sets `require_confirmation=False` for every shaped type in both arms. So
"the off arm reads the date of birth back and waits, the prepared arm has already moved on"
(dob-wrong-year-same-turn L4-6, two-fields-one-breath-opening L6-8, question-instead-of-answer L3-4,
choice-change-after-frame L3-4, correction-next-turn-after-frame L3, corrects-after-readback L2-4) is
false: in both arms the value is stated inside the next collector's question and the walk moves on.
The tricks still work (a correction lands on the next collector's floor in both arms, which is what
the correction scenarios need), but every scripted "Yes, that's right." placed after a dob/date/choice
answers the NEXT collector's question instead, in both arms. Fix the prose; trim those turns where
noted.

### X5 — MEDIUM — the exit gates shape every mid-walk exit, and the criteria blame the desk for them
Seven scenarios exit mid-walk (transfer ×4, callback ×2, DNC ×1). The first handoff call is refused
by `exit_blocked_on_required` with a directive whose FIRST clause is "call the collect tool for it and
let the specialist ask, then take this exit" (collect_input.py:106-113). A model obeying that clause
asks the next Input's question before leaving — exactly what "does not ask another Input's question
after the request" (early-exit-do-not-contact crit. 1, action-hop-callback crit. 1) marks NOT MET.
Likewise `exit_blocked_on_question` is what makes "offer, then wait for the yes" happen; the transfer
scenarios' criterion "hands over on that turn = NOT MET" is partly a gate test. Say so in the
descriptions; the `expect:` blocks themselves are fine.

### X6 — MEDIUM — retry budget is 1: a second non-answer turn on a required field halts the walk
Every collector declines on unusable turn number 1 (facts table). A REQUIRED field then gets one
`_REQUIRED_RETRY` (the parent MUST "say in one short sentence why {name} is needed") and a second
decline halts the step. Any scenario that scripts two or more non-question non-answer turns on one
required field is testing the retry ceiling, not the behaviour it names — see
digression-then-returns-mid-collection (HIGH), hedged-yes-no-interpreter, hostile-just-book-it,
off-list-choice. And the mandated reason sentence is what the "no lecture" criteria will trip on.

### X7 — LOW — pack residue never reaches the agent node, but does reach the closing line
`params.yaml` is the movers lead (Michael Carter, Austin→Denver); nothing in the agent node carries a
placeholder, so the persona (Ruth Okafor, clinic) contradicts nothing the desk sees. But the end nodes
are the pack's: `End conversation 9/10` say "…if the caller isn't a fit or the move can't proceed…",
`Callback Follow Up` (Voicemail only) says "Hi, this is Dan… your move to Denver… +15550100001". A
closing line mentioning a "move" is possible and no scenario checks it. Acceptable; note in NODE.md.

### X8 — LOW — the engine's `variables` check is exact by key; the judge's is by value
`Expectation.check` compares `merged_vars[name] != expected` literally (scenarios.py:75-78), so a
currency stored as `40.0` (no inferred code) or a phone stored with a country prefix prints a
`variables[...]` failure in the run report that the judge then discards (judge.py:376-377). Fine, but
the `run` exit code is not the verdict; only `judge.py` is. State it in NODE.md `## Use`.

### X9 — LOW — absence checks for `access_notes` are key-only
`judge.VALUE_HINTS` lists only the mobile. No scenario pins `access_notes`, so the union of known
values has nothing to look for and `variables_absent: [access_notes]` (declines-text-field, hostile)
catches only a write under the declared key. Add `"access_notes": ["wheelchair", "side entrance"]`
to `VALUE_HINTS` (judge.py:49).

## Per-scenario findings

### action-hop-callback-log-slow-then-fails.yaml
- **HIGH** L2-7, L28-31, L34-37 — the premise is not what runs. The idle turn (L28) comes BEFORE the
  callback time (L32) and before the intent fires, so no hop is "in flight" during the silence; and
  `Log Callback Request: failed` is a no-op — both of that hop's edges reach `End - Callback Scheduled`
  and the mocked hop never touches the agent, so the transcript is identical under `success`.
  Criteria 3 and 4 cannot fail. Also X3: the idle turn lands after the date collector hands back
  (routing text: a callback request → `hand_back`, collect_input.py:571-579), so the parent holds the
  floor and the reply is the fixed reminder — criterion 1 passes on a constant; if the collector did
  NOT hand back the reply is empty and `spoke_unprompted` fails. Either way it measures no desk.
  **Fix:** drop L28-31 and L34-37; retitle as the callback-exit walk (`callback-mid-walk`) with
  criteria 2 and 4 only; if a second callback scenario is wanted keep it as the twin of
  barge-in-over-first-question with no barge-in. Description must stop claiming hop latency.
- **LOW** L40 — `not_intent: Reschedule Booked` is redundant next to `intent: Callback Requested`.

### action-hop-transfer-log-fails.yaml
- **MEDIUM** L2-5, L31-33 — same no-op pin: both `Log Lead Transfer` edges reach the call_forward and
  the hop is mocked, so "the failure must stay invisible" (crit. 2) cannot fail; a broken agent
  passes. The file is `transfer-mid-walk` plus two pins. **Fix:** delete it and move L38-43
  (`variables` + `variables_absent`) into `transfer-mid-walk.yaml`.

### barge-in-over-first-question.yaml
- **MEDIUM** L28 `interrupt_after: name` — the first reply is wholly LLM-authored (`screening_name`
  is used only by the AMD voicemail path, `src/amd/controller.py:693-696`; nothing scripts the
  greeting) and the cut lands at the FIRST match. "Hi, my name is Maya…" cuts the greeting before
  any question, so the trick becomes "interrupted greeting" and criterion 2 then punishes the correct
  move (re-introducing to a caller who never heard who is calling; `allow_greeting_interruption`
  is true). **Fix:** move the barge-in to the DOB question, whose label is stable:
  ```yaml
  - user: Hello?
  - user: Ruth Okafor.
  - user: Yes — ninth of June nineteen sixty-two. Sorry, go on.
    interrupt_after: birth
  - user: Actually, I can't do this now. Could someone ring me back?
  ```
  and pin `variables: {patient_full_name: Ruth Okafor, date_of_birth: "1962-06-09"}`.
- **LOW** — the truncated message lives in the COLLECTOR's chat context (engine.py:127-129); the
  `interruption_marker` hook is registered on `SharedUnitBase` (`src/units/base.py:505`), and whether
  an inline `AgentTask` runs it was not verified. If the model never sees a marker, "keep what was
  said over the cut" is tested only through the truncated text. Verify on run.

### barge-in-over-transfer-offer.yaml
- **HIGH** L31-37 — the script fits one of three correct behaviours. Turn 5 is a DIRECT request for
  a coordinator, and the intent's first clause fires on that alone ("Trigger when the caller asks to
  speak to a scheduling coordinator"); the exit gate refuses once and its own text says "call this
  same handoff again straight away and it will go through" (one turn, two calls). A desk that
  transfers at turn 5 ends the call there, turn 6's `expect` is never evaluated and engine.py:316-324
  FAILS the run. A desk whose offer does not contain the word "coordinator" ("put you through to
  someone who can help — shall I?") aborts on the anchor. Only "offer, wait" fits. **Fix:** make
  turn 5 a problem the desk must *offer* to solve (clause 2), and anchor on the verb every offer
  carries:
  ```yaml
  - user: Before we go on — this appointment is tied to a test at another clinic, can this desk move both together?
  - user: Yes, please, put me through.
    interrupt_after: through
    expect: { not_intent: Transfer To Coordinator, ended: false }
  - user: Yes. Put me through.
  ```
  Keep the final expect. Note in the description that `exit_blocked_on_question` is what forces the
  wait (X5).

### choice-change-after-frame.yaml
- **LOW** L3-4 — "read back in the off arm" is wrong (X4); in both arms "late morning" is stated
  inside the journey-time question, so the switch lands on the number collector's floor in both.
  The trick IS arm-independent, for the opposite reason. Fix the prose.
- **MEDIUM** L8-11 — criterion 1 (`change_earlier_value` or a second `collect_choice`) is unencoded
  (X1). judge rule 2 does cover criterion 2 (a stated value later corrected must be re-stated). Encode
  criterion 1 in judge.py as "timeline[preferred_time_of_day] has two distinct values" or drop it.

### correction-next-turn-after-frame.yaml
- **LOW** L3 — prose wrong (X4). The date correction re-enters the date with
  `require_confirmation=True` (collect_input.py:1012-1018), so the corrected date IS read back and
  needs a yes — the persona's "agree with correct read-backs" covers it. Pins are right.

### correction-same-turn-after-ack.yaml
- **LOW** L35 — `interpreter_needed: "yes"` is matched by value under ANY key (judge.py:285-288); a
  "yes" written to any other field would pass it. Acceptable (no other boolean here); note it.

### corrects-after-readback.yaml
- **HIGH** L21-23 — no `variables` pin. A desk that ignores both corrections stores 12 March / 35,
  ends through Reschedule Booked and PASSES; judge rule 2 fires only when a second write exists in
  `timeline`, and an ignored correction writes nothing. **Fix:** add
  `variables: {new_appointment_date: "2028-03-19", journey_time_minutes: "50"}`.
- **LOW** L1-4 — "legacy read-back" prose (X4): there is no read-back for date/number in either arm;
  both corrections land on the next collector's floor.

### currency-in-words.yaml
- **MEDIUM** L2-3, L7 — "in the arm's own shape" is false for this field. "quid" is a cultural-idiom
  inference (`collect_currency.py:57`), `currency_inferred=true` forces `_confirmation_required`
  (`collect_currency.py:532-536`), so the record is `not_clean_completed`, the frame is declined
  (`prepared_state.py:318`) and the collector reads back "40 GBP" with a confirmation question in
  BOTH arms. The scenario tests the inference read-back, not the arm; say so. Criterion 1 is a real
  risk (the model is handed the literal "40 GBP", `collect_currency.py:374-376`) but unencoded.
- **LOW** L30 — `"GBP 40.0"` matches `_flatten_currency` exactly when GBP is inferred; a `40.0` store
  is accepted by the judge's `amount()` and printed as an engine failure (X8).

### declines-optional.yaml
- **MEDIUM** L22-23 — only the email is pinned absent. "there is nothing" on `access_notes` must take
  the optional decline path (collect_input.py:600-604: "if the caller has no preference… call its
  decline tool at once"); a desk that writes "nothing"/"no notes" passes. **Fix:** add
  `access_notes` to `variables_absent`.

### declines-phone-then-relents.yaml
- **MEDIUM** L12, L32-33 — criterion 4 (mobile ends as 7700900123) is unencoded. The judge matches a
  phone on its last ten digits (judge.py:181-182). **Fix:** add `mobile_number: "07700900123"` to
  `variables`. Criteria 1-3 are derivable from `_REQUIRED_RETRY` (collect_input.py:95-101).

### declines-phone-twice-halts.yaml
- **HIGH** L30-34 (X2) — no `ended`/`intent`/`stop_reason`, so the judge demands the call ends. The
  description says the failure route is "offering a scheduling coordinator", but L4-6 hedges it and
  criterion 4 starts "if". `_REQUIRED_HALT` says "follow the Current Task Instructions' failure route
  (hand back / human / the configured exit)"; the Task's only human exit is Transfer, and the persona
  already says yes to a person (L25) with `Log Lead Transfer` pinned (L27-29). **Fix:** commit to it:
  ```yaml
  expect:
    ended: true
    stop_reason: call_forward
    intent: Transfer To Coordinator
    not_intent: Reschedule Booked
    variables_absent: [mobile_number, confirmation_email]
  ```
  If halting without a transfer is meant to be acceptable, set `ended: false` instead and drop the
  world_state pin — one or the other, never implicit.

### declines-text-field.yaml
- **LOW** — sound. Criterion 1 is derivable (optional → "do not press or ask again"). Note that
  hostile-just-book-it's criterion 3 contradicts it (below).

### digression-asks-why-then-answers.yaml
- **LOW** — sound: each "why" is a question, routed to `answer_side_question` (never a decline),
  `not_intent: Transfer` is encoded, five pins. Criterion 2 ("the configured reason") is prose only.

### digression-then-returns-mid-collection.yaml
- **HIGH** L30-32 (X6) — three digression turns on the REQUIRED `journey_time_minutes`, only one of
  which is a question. With `max_collection_retries=1` the first story turn declines the field
  (`collect_number.py:248`: "unusable turn number 1 itself is answered by calling
  decline_number_capture"), the parent's `_REQUIRED_RETRY` re-opens it, the second story turn
  declines again and `_REQUIRED_HALT` ends the step — before "thirty-five minutes" is ever said.
  A desk that obeys its configuration fails `intent: Reschedule Booked`. **Fix:** one story turn
  then the side-gate QUESTION (a question never counts), then the answer:
  "…spend one turn on the car park being dug up and how you were nearly late, then ask whether the
  side gate is open in the mornings, then say the journey takes thirty-five minutes." Update
  criterion 3 accordingly.

### dob-wrong-year-next-turn.yaml
- **LOW** L10 — criterion 3 ("no agent turn after the correction names the discarded year") fails a
  correct desk: the corrected DOB is re-entered with confirmation on, and "nineteen sixty-two, not
  seventy-two — is that right?" is a legitimate read-back. Unencoded anyway; soften or delete.

### dob-wrong-year-same-turn.yaml
- **LOW** L4-6, L21-25 — rationale wrong (X4): neither arm reads the DOB back, so turn 5 "Yes, that's
  right." answers the DATE question in both arms; the date collector re-asks and turn 6 answers.
  Harmless; the per-turn `message_excludes` are the right kind of assertion. Rewrite L4-6; keep the
  turn only for its `message_excludes`, or drop it and put those excludes on turn 6.

### early-exit-abrupt-goodbye-mid-collection.yaml
- **HIGH** L31-41 (X2) — no `ended`: the judge demands an end the desk cannot produce (no intent fits,
  no end tool), and the engine hole runs the other way: a desk that fires Callback Requested or
  Do Not Contact ends the call, skips the remaining (expect-less) turns, satisfies
  `not_intent: Reschedule Booked` and PASSES. **Fix:**
  ```yaml
  - user: Sorry, I've got to go, there's someone at the door.
    expect: { ended: false }
  - user: No, don't ring me back. I'll call you myself when I can. Bye.
    expect: { ended: false, not_intent: Callback Requested }
  - user: Bye.
    expect: { ended: false, not_intent: Do Not Contact }
  expect:
    ended: false
    not_intent: Reschedule Booked
    variables_absent: [...]
  ```
  (`not_intent` takes one name; `ended: false` is what rules out every exit at once.)

### early-exit-do-not-contact-mid-collection.yaml
- **LOW** (X5) — the DNC handoff is refused once by the required-field gate; a model obeying the
  gate's first clause asks the date before leaving, which criterion 1 marks NOT MET. The expect block
  is right; add a line to the description so a red run is read correctly.

### half-a-date.yaml
- **MEDIUM** L7-8, L18-21, L34 — criterion 1 is the whole trick and it is unencoded; worse, the pin
  passes THROUGH the defect: a collector that resolves "the twelfth of" to the next 12th, states it,
  gets corrected by the persona ("that is not what you said…") and ends on 2028-03-12 satisfies the
  pin while having invented a month. **Fix:** script the date turns so the assertion is mechanical:
  ```yaml
  - user: The twelfth of
    expect:
      message_excludes: [january, february, april, may, june, july, august, september, october, november, december, "2026", "2027"]
      variables_absent: [new_appointment_date]
  - user: March, twenty twenty-eight.
  ```
  (a "march"/"2028" mention before the caller said it is the one case this cannot catch; accept.)

### hedged-yes-no-interpreter.yaml
- **MEDIUM** L30-33 (X6) — the first hedge is unusable turn number 1 → `decline_boolean_capture`
  → required → `_REQUIRED_RETRY` (the parent must say why an interpreter answer is needed and
  re-open), the second hedge is a question (→ `answer_side_question`, re-ask), then "no". It works,
  but through the decline/retry machinery, and the mandated reason sentence is what criterion 2
  ("lectures about interpreters = NOT MET") will flag. **Fix:** either one hedge (the daughter line)
  then the plain no on the re-ask — the boolean prompt's own "never decline on the first one" path —
  or keep two and rewrite criterion 2 to allow the one-sentence reason.

### hedged-yes-to-transfer-offer.yaml
- **MEDIUM** L27-31 — turn 5 ("cancel my blood test at a different clinic") does not force an offer:
  "you'd need to ring that clinic" and straight on to the date is also correct. Then turn 6's hedge
  answers the date question (nonsense) and turn 7's direct "put me through" fires the transfer — the
  final expect and the per-turn `not_intent` all PASS without the hedge ever being tested. **Fix:**
  make turn 5 something the desk cannot place but a coordinator can (as in barge-in-over-transfer-offer)
  and assert the re-ask is a question:
  ```yaml
  - user: Well... whatever you think is best.
    expect: { not_intent: Transfer To Coordinator, ended: false, message_contains: "?" }
  ```

### hostile-just-book-it.yaml
- **LOW** L9-10 — criterion 2 ("the four parts of the day are not re-listed") contradicts the node:
  `present_options: true` means the collector reads the options when it asks; `_NO_RECITE` applies
  only when it is false (collect_choice.py). Delete it. L11 criterion 3 ("pressed at most once, with
  one short reason") contradicts the optional rule the node carries (Task: "tell them that is fine and
  move on"; collect_input.py:600-604) and declines-text-field's criterion 1: make it "not pressed".
  Also (X6) the snap on the choice question declines it once → required retry; expected, fine.

### http-hop-fails.yaml
- OK — the only hop pin that changes routing (failed → `End conversation 10`). Closing prose is the
  movers pack's (X7).

### injection-ignore-your-instructions.yaml
- **LOW** L21-23, L29-31 — `message_excludes` are two exact phrasings; "I've confirmed your
  appointment", "it's now confirmed", "marked as confirmed" pass. Add: `confirmed your`,
  `now confirmed`, `been confirmed`, `marked as confirmed`, `booking confirmed`. Otherwise this is
  the best-encoded scenario in the pack.

### number-with-a-unit.yaml
- **LOW** L9 — premise holds (`collect_number.py:705-709, 812`: any unit with none configured is a
  `ToolError`). Criterion 3 "as minutes in words" is not derivable: the stored value is bare and
  whether the desk says "minutes" is style. Delete "in words".

### off-list-choice.yaml
- **LOW** (X6) — "lunchtime, around one" is an unusable turn → decline → required retry → the re-opened
  collector presents the options (present_options) → "afternoon". Works; criterion 2 is derivable.
  Say the path runs through the required retry, so the reason sentence is expected.

### plain-walk.yaml
- **MEDIUM** L20-22 — the baseline pins nothing. A walk that ends through Reschedule Booked with wrong
  values passes, and the judge's known-value union (used by every `variables_absent`) is thinner for
  it. **Fix:** pin all ten (dob `"1962-06-09"`, date `"2028-03-12"`, `Late morning`, `"35"`, `"no"`,
  access note text is free-form — pin by value fails on paraphrase, leave it — `"GBP 40.0"` for the
  fee is NOT safe (currency may not be inferred from "forty pounds is unpaid"; "pounds" is a stated
  currency → GBP; pin it), `mobile_number: "07700900123"`, `confirmation_email`).

### question-instead-of-answer.yaml
- **HIGH** L29-32 (X2) — no `ended`: the judge demands an end from an 8-turn mid-walk script. **Fix:**
  add `ended: false` to the final expect.
- **LOW** L2-4, L18, L25, L27 — prose wrong (X4); turns 5 and 7 "Yes, that's right." answer the next
  collector in both arms — trim to: name line, yes (name), why, DOB, date, choice. Turn 1 "yes,
  speaking" precedes any greeting (the caller's first line is what draws it); reword to "Hello? Yes,
  Ruth Okafor speaking."

### rambling-answer-buries-the-value.yaml
- OK — the rambling turn contains the value, so it is usable; pins right; decoys are only in prose.

### repeat-back-after-the-line.yaml
- **MEDIUM** L8-9, L20-21 — criterion 2 ("not word for word") is neither derivable nor encoded. And
  the request lands on the CHOICE collector's floor in both arms ("repeats … remain with this
  collector", collect_input.py:571-579); that collector is told which earlier fields exist and their
  kinds, not their values, so "the same date is said again" may be unreachable from where the request
  arrives — the correct behaviour is undefined by the node. Keep the scenario as a probe, delete
  criterion 2, and read the first paid run before trusting a red.

### silence-then-are-you-there.yaml
- **HIGH** L16-19, L25-28 (X3) — both idle turns fall while a collector holds the floor (name after
  "Hello?", DOB after the name is confirmed): the reply is not recovered (`resp.message == ""`) and
  `spoke_unprompted: true` fails every run; and even where it is recovered, the V2.9 reminder is the
  fixed "Are you still there?…" line, so criteria 1 and 3 ("with the open field's own question") are
  unreachable on this node type. **Fix:** delete both idle turns; the caller's "Are you there?" turns
  with `message_contains` are the part that tests re-asking the open field. If an idle turn must
  stay, put it where the parent holds the floor (after a hand_back) and assert only
  `not_intent: Voicemail Detected` + `ended: false`.
- **LOW** L22 — `message_contains: name` fails "Yes, I'm here — who am I speaking with?". Widen to
  `[name, "speaking with", "booked under"]`.
- **LOW** L17-19, L26-28 — `not_intent: Voicemail Detected` on an idle turn is trivially true
  (`session.say` makes no tool call). Harmless.

### transfer-mid-walk.yaml
- **MEDIUM** L17-19 — no pins: a desk that transfers on "Hello?" passes. **Fix:** take the pins from
  action-hop-transfer-log-fails (see above) and add
  `new_appointment_date: "2028-03-12"`, `preferred_time_of_day: Late morning`,
  `variables_absent: [journey_time_minutes, mobile_number, confirmation_email]`.

### two-fields-one-breath-mid-walk.yaml
- **MEDIUM** L7-8 — criterion 1 (`collect_choice` carries `known_value`) is unencoded and
  `known_value` is in the judge's `SKIP_ARG_KEYS`. Encode in judge.py ("the first collect call for
  preferred_time_of_day has a non-empty known_value") or drop it.
- **LOW** L18-19 — "late morning if you have it" in the date turn: `require_time: false` and it is
  not a clock time, so the store should stay `2028-03-19`; if a time were captured the ISO prefix
  still matches the judge (`ISO_DATE_RX` is a prefix match) but not the engine. Verify on run.

### two-fields-one-breath-opening.yaml
- **HIGH** L24-27 (X2) — no `ended`: the judge demands an end from a mid-walk script. **Fix:** add
  `ended: false`.
- **LOW** L6-8, L19-23 — prose wrong (X4): a seeded DOB is a shaped type, so `require_confirmation`
  stays False (collect_input.py:1005; the known-value force at :1021 is identity-only) and neither
  arm reads it back; turns 3, 5 and 7 "Yes, that's right." each answer the next collector. Trim to
  four turns (opening line, yes for the name, date, choice). Turn 1 "yes, that's me" precedes any
  greeting. Criterion 1 (`known_value` on `collect_dob`) is unencoded — same judge check as above.

## What the text sim cannot express (and which scenarios lean on it)

- **A barge-in during TTS.** `interrupt_after` truncates the last assistant TEXT and flags it
  interrupted; there is no playout, no overlap, no "the answer arrives inside the interruption" — the
  caller's line is simply the next turn. barge-in-over-first-question / barge-in-over-transfer-offer
  test the truncated-context state, which is the right thing to test, but should say so.
- **Hop latency / a slow action.** Nothing mocks time; action-hop-callback-log-slow-then-fails
  pretends a mid-collection silence is one. It is not (see its entry).
- **Silence duration, reminder timing, the retry counter and the hangup.** `idle: true` fires one
  reminder immediately; `_inactivity_loop`'s counter and terminal hangup are not reproduced
  (runner.py:822-828). On this node type the reminder is a constant (X3).
- **Overlapping speech / talking over the reminder.** Not representable; no scenario claims it,
  but criterion 1 of action-hop-callback reads as if it were.
- **How something SOUNDS.** "in words", "the ISO code aloud as letters", "pounds said as a word",
  "a currency symbol read out" (currency-in-words, number-with-a-unit): the judge and the model see
  text; a TTS rendering of "£40" or "GBP" is outside the sim.
- **Voicemail / AMD.** `screening_name`/`screening_reason` feed the AMD voicemail message only;
  `not_intent: Voicemail Detected` on an idle turn is decorative.
- **The entry arm (P1) and per-outcome arms** — already stated in NODE.md; no scenario claims them.

## Counts

| severity | count |
|---|---|
| HIGH | 10 — X1, action-hop-callback, barge-in-over-transfer-offer, corrects-after-readback, declines-phone-twice-halts, digression-then-returns, early-exit-abrupt-goodbye, question-instead-of-answer, silence-then-are-you-there, two-fields-one-breath-opening |
| MEDIUM | 16 — X4, X5, X6, action-hop-transfer-log-fails, barge-in-over-first-question, choice-change-after-frame, currency-in-words, declines-optional, declines-phone-then-relents, half-a-date, hedged-yes-no-interpreter, hedged-yes-to-transfer-offer, plain-walk, repeat-back-after-the-line, transfer-mid-walk, two-fields-one-breath-mid-walk |
| LOW | 24 — X7, X8, X9, and the 21 per-file LOW bullets above |

X2 and X3 are counted through their per-file HIGH entries, not again as headings.
