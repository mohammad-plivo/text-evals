# sim-prepared — the prepared-speech A/B campaign

One `ai_agent_v29` node, 34 scenarios, two arms (`PREPARED_SPEECH_MODE=prepared` and `=off`), judged
by `judge.py`. Everything here runs against `stress-evals/trees/cd6ac6c5`, which is read-only for
this campaign; only this directory is written.

Files: `NODE.md` (why the node looks the way it does, in the code's own words) · `build_ws.py`
(assembles `ws/`) · `scenarios/` (the source of truth; `ws/scenarios/` is a byte copy) · `run_arm.sh`
(one arm) · `judge.py` (the verdict) · `review-scenarios.md`, `review-harness.md`, `review_probes.py`
(the adversarial review this pack was fixed against; all 11 probes green).

## The node

**Clinic Reschedule Desk** — Maya, the Ridgeway Clinic scheduling desk, calling a patient who asked
to move an appointment. One question at a time; each Input's own collector asks its own question.
Five intents: Transfer To Coordinator (→ `Log Lead Transfer` → call forward), Reschedule Booked (→
`Update Lead Record` → end), Callback Requested (→ `Log Callback Request` → end), Do Not Contact (→
`Add To DNC` → end), Voicemail Detected. Every other node, id and edge handle is the shipped pack's.

Ten Inputs, in walk order. "Prepared display" = the arm can have the runtime SPEAK the value;
`_SHAPE[type] is _STATE` **and** `type in RENDERABLE_TYPES` must both hold
(`prepared_state.state_eligibility`, quoted in NODE.md).

| # | Input | type | required | prepared display? |
|---|-------|------|----------|-------------------|
| 1 | `patient_full_name` | name | yes | **no** — identity type, keeps the collector's own read-back |
| 2 | `date_of_birth` | dob | yes | **yes** |
| 3 | `new_appointment_date` | date | yes | **yes** |
| 4 | `preferred_time_of_day` | choice, 4 labels, `present_options: true` | yes | **yes** |
| 5 | `journey_time_minutes` | number, no units configured | yes | **yes** |
| 6 | `interpreter_needed` | boolean | yes | **no** — `_ACK` shape: acknowledged, value never repeated |
| 7 | `access_notes` | text | **no** | **yes** |
| 8 | `outstanding_fee` | currency | yes | **yes** |
| 9 | `mobile_number` | phone | yes | **no** — identity type |
| 10 | `confirmation_email` | email | **no** | **no** — identity type |

Six can carry a display, one is the acknowledgement shape, three are the identity types the arm
never speaks. Two facts that shape almost every scenario:

- For every shaped type the V2.9 router passes `require_confirmation=False` **in both arms**
  (`collect_input.py:1005`). Neither arm stops to ask "is that right?" for dob/date/choice/number/
  currency/text/boolean — the off arm has the model state the value inside its next step, the
  prepared arm has the runtime speak it. Only name, phone and email keep a read-back to agree with.
- A correction re-enters with `require_confirmation=True` (`collect_input.py:1012-1018`), so a
  corrected value IS read back and does wait for a yes.

## The scenarios (34)

**Baseline (2)**
- `plain-walk` — all ten Inputs asked in order, ordinary exit; nine pinned by value (access_notes is
  free-form). These pins are the campaign's known-value union that every absence check reads.
- `http-hop-fails` — the same walk with `Update Lead Record` pinned to `failed`: the only hop whose
  outcome changes routing (it lands on the other end node). Nothing about it reaches the caller.

**Corrections (6)**
- `dob-wrong-year-same-turn` — wrong year taken back inside one breath; the discarded year must
  never be spoken (scripted, `message_excludes`).
- `dob-wrong-year-next-turn` — the same year, taken back a turn later, after the desk said it.
- `correction-same-turn-after-ack` — the interpreter answer taken back in the caller's very next
  words, while the next collector already holds the floor.
- `correction-next-turn-after-frame` — the date corrected one turn late, after the part of the day
  was answered; the answer in between must survive.
- `choice-change-after-frame` — late morning switched to the afternoon the moment it is spoken.
- `corrects-after-readback` — two corrections in one walk (date, then journey time), each pinned by
  value so an ignored correction cannot pass.

**Awkward values (7)**
- `half-a-date` — "the twelfth of" and the line drops; no month or year may be invented (scripted,
  `message_excludes` + `variables_absent` on that turn).
- `number-with-a-unit` — "about forty-five minutes, door to door" into a number Input with no units
  configured, where a unit passed to the tool is a hard `ToolError`.
- `currency-in-words` — "forty quid, I think": a cultural-idiom inference, which forces a
  confirmation read-back in BOTH arms.
- `off-list-choice` — lunchtime, which is not one of the four labels.
- `rambling-answer-buries-the-value` — the journey time inside a story carrying two decoy numbers.
- `two-fields-one-breath-opening` — name and date of birth in the opening line; the dob collector
  must open with a `known_value` (measured).
- `two-fields-one-breath-mid-walk` — day and part of the day in one breath; the choice collector must
  open with a `known_value` (measured).

**Declines and the retry budget (5)** — every collector's `max_collection_retries` is 1: one
unusable turn declines the field, a REQUIRED field then gets exactly one `_REQUIRED_RETRY` (the
parent owes one short sentence saying why, plus a re-open), and a second decline halts the step.
- `declines-optional` — both optional Inputs declined; neither may halt the walk.
- `declines-text-field` — an outright refusal of the optional text field, which must be let go at
  once and cost the caller nothing.
- `declines-phone-then-relents` — one refusal of the REQUIRED mobile, then the number; the reason and
  the re-ask must arrive together.
- `declines-phone-twice-halts` — the refusal holds, the step halts, and the walk leaves by the only
  human route the Task names.
- `hedged-yes-no-interpreter` — the boolean answered with a hedge, then a question, then plainly.

**Exits (6)**
- `transfer-mid-walk` — a coordinator asked for mid-walk; out through the transfer hop to the call
  forward.
- `callback-mid-walk` — the caller cannot talk now; out through the callback hop.
- `early-exit-do-not-contact-mid-collection` — "take me off the list" with the record half open.
- `early-exit-abrupt-goodbye-mid-collection` — a goodbye that matches NO intent: the desk must not
  manufacture an ending (`ended: false` on every turn is the assertion).
- `hedged-yes-to-transfer-offer` — "whatever you think is best" is not consent.
- `barge-in-over-transfer-offer` — a yes shouted over an unfinished offer is not consent either.

**Barge-in (1)**
- `barge-in-over-first-question` — the caller answers the date-of-birth question over the top of it;
  what was said over the cut must be kept.

**Digression, pressure and noise (7)**
- `digression-asks-why-then-answers` — "why do you need that?" twice; the reason must be the Input's
  own, and a challenge is not a request for a human.
- `digression-then-returns-mid-collection` — one story turn, a side question, then the answer; the
  desk must come back to the Input it was on.
- `question-instead-of-answer` — a question instead of the date of birth is never a decline.
- `hostile-just-book-it` — a short-tempered caller; the required Inputs are still collected one at a
  time and the optional ones are not pressed.
- `injection-ignore-your-instructions` — an instruction read at the agent, twice, the second dressed
  as clinic authority.
- `repeat-back-after-the-line` — "sorry, what was that date again?" straight after the value was
  spoken. A PROBE: the request lands on the next collector's floor, which knows earlier fields only
  by kind, so the node does not define the right answer. Read the first paid run before calling a red.
- `silence-then-are-you-there` — "hello? are you there?" twice; the open field must be re-asked, not
  the greeting repeated.

## What the judge decides

`judge.py` is the verdict. It reads the report and the arm's stderr log — never a scenario's
description. A walk passes only when every rule below is clean.

1. **completed** — ended as the scenario declared, its `intent` reached, its `stop_reason` matched,
   its `not_intent` never fired. `ended: true` is assumed only for a scenario that declares nothing
   at all. The engine's own failures are carried, minus the by-key `variables[...]` lines this judge
   redid by value and passed.
2. **floor** — the agent spoke at all, and a walk that left by Reschedule Booked (or ended with no
   other intent) stored every REQUIRED Input the scenario did not declare absent.
3. **variables** — each `expect.variables` value under the field's OWN key (the node declares its ten
   Inputs, so `record_<field>` is the runtime's key), falling back to any-key only for a field the
   node does not declare. Values match by exact text, by number, or by a phone's last ten digits.
   Each `variables_absent` field must be held by no key, and its campaign value stored nowhere.
4. **speech 1** — no acknowledgement line spoken twice for one answer: the same value in two
   sentences, twice in one sentence, or in two consecutive spoken turns with no new answer between.
   A closing recap is exempt.
5. **speech 2** — no stale read-back: a value read back and then corrected must have the CORRECTED
   value read back afterwards.
6. **speech 3** — no prepared line spoken before the answer it acknowledges, counted only from the
   turn that value's own collector opened ("Good afternoon" is not the choice `Afternoon`).
7. **speech 3b** — no campaign value spoken for a field the scenario declares absent when the caller
   never said it either.
8. **speech 4** — no spoken Python literal, bracketed placeholder or variable name.
9. **speech 5** — at most one collector reopen per field beyond the configured retry.
10. **seeded** — for the two scenarios whose trick is a value given before its collector opened, that
    collector's first call carries a non-empty `known_value`.

Dates are judged WITH their year: two dates sharing a month and day are two values, so a year-only
correction is visible; a line naming no year is judged on month and day.

**The numbered "Judged by transcript" criteria inside each scenario are prose.** Nothing evaluates
them. Every criterion that could be made mechanical has been moved into `expect:` (per-turn
`message_excludes` / `message_contains` / `not_intent` / `variables_absent`, or a value pin) or into
`judge.py`; the ones that could be expressed neither way were deleted. What is left is a reading key
for a human looking at a transcript — or the brief for an LLM-judge pass, which would be a paid step.

## Running one arm

```
STRESS_REPO=<tree> <tree>/.venv/bin/python build_ws.py --self-test   # rebuild + check (free)
<tree>/.venv/bin/python judge.py --selftest                          # the judge's own check (free)
./run_arm.sh prepared <tag> <env-file> 5                             # PAID: 34 scenarios x 5
./run_arm.sh off      <tag> <env-file> 5                             # PAID: its twin
```

`<tree>` is `stress-evals/trees/cd6ac6c5`. `run_arm.sh` refuses any other tree, a dirty tree, an
unbuilt workspace, a node not on `gpt-4.1`, a missing env file and one that is not mode 600; it
prints the env file's key NAMES only. Add `--scenario a,b` for a subset (one CLI run per name, one
report each), `--max-parallel N`, `--dry-run` to print the command and run nothing.

Each arm writes `stress-evals/prepared-arms/<tag>-<arm>/`: `run-<label>.out`, `run-<label>.err` (the
engine's JSON log — the LLM counts come from here), `RUN-INFO.txt` (env sha256, tree, model,
repeats) and `reports/<stamp>.jsonl`, its OWN copy of every report. Both arms append into the one
workspace `reports/`, so that copy is what makes an arm's result identifiable at all.

Run the arms SERIALLY, not together: two runs launched in the same second share a report stamp and
interleave inside one file.

## Comparing the arms

```
<tree>/.venv/bin/python judge.py \
    prepared-arms/<tag>-prepared prepared-arms/<tag>-off
```

The judge prints the per-scenario pass rate, every failing walk with its reasons, and a
prepared-vs-off table (delta = prepared − off). It refuses two specs that resolve to one file, orders
the columns prepared-then-off, and warns when:

- a `-prepared` arm's log carries no `prepared.*` event (that arm did not run prepared) or an `-off`
  arm's log carries some;
- the two arms' env digests differ, or one is missing;
- the engine retried a walk — its discarded attempt's LLM requests land under the same call_uuid.

Read it in this order: **pass rate → failing walks → the speech-rule counts**. A pass-rate delta with
no speech-rule delta is noise; the arms are the same model on the same scenarios, so a real effect
shows up in the rules the arm actually changes (double acknowledgement, stale read-back, prepared
line spoke) and in turns per walk.

The `run` exit code is NOT the verdict: the engine compares `expect.variables` literally by key, so a
phone with a country prefix or a currency stored without an inferred code prints an engine failure
that is right by value. Only `judge.py` decides.

## LIMITS — what this text sim cannot express

Do not read any of the following as covered by a green board.

- **A true barge-in during TTS.** `interrupt_after` truncates the last assistant TEXT at the first
  match and flags it interrupted (`cli/engine.py:127-137`). There is no playout, no overlap, no
  answer arriving *inside* the interruption — the caller's line is simply the next turn. The two
  barge-in scenarios test the truncated-context state, which is the right thing to test, and nothing
  more. Whether an inline `AgentTask` even runs the `interruption_marker` hook (registered on
  `SharedUnitBase`) is unverified: read the first paid run.
- **Wall-clock timing of any kind.** Nothing mocks time. Hop latency, a slow action, how long a
  silence lasted, when the reminder fired, the idle retry counter and the terminal hangup are all
  outside the sim. A scenario that pretended a scripted silence was a slow action has been removed.
- **Overlapping speech.** Two voices on the line at once is not representable at all.
- **A silent turn on this node type.** `idle: true` exists, but on an `ai_agent_v29` node the
  reminder can never be the open field's question — `pending_collector_field` reads
  `state.active_walk_unit`, set only by the V2.5 `AgentTasksUnit` (`agent_tasks.py:1362`) — and this
  workspace is not a flow-session bundle, so when a collector holds the floor the reply is not
  recovered into the turn and `spoke_unprompted: true` fails on the harness, not on the desk. Both
  idle turns have been removed from the pack for that reason.
- **How anything SOUNDS.** The judge and the model see text. "Says the ISO code as letters", "reads a
  currency symbol out", "says minutes in words", a TTS rendering of "£40" — none of it is visible
  here.
- **Voicemail / AMD.** `screening_name` and `screening_reason` feed the AMD voicemail message only;
  `not_intent: Voicemail Detected` on a non-tool turn is decorative.
- **The entry arm (P1) and the per-outcome arms.** The CLI's config loader drops `inputs_complete`,
  so P1 sits at `no_inputs_contract`; no `prepared_transitions` are declared, so the per-outcome arms
  sit at `no_declared_transition`. Only the state-frame arm runs here (NODE.md).
- **The end nodes' wording.** They are the shipped movers pack's and mention a move to Denver; only
  the agent node was rewritten. No scenario checks the closing line's copy.
