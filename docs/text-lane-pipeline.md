# The text lane becomes the first gate: MK's instruction, and how we work from now on

Recorded by the implementing session, 23:30 IST 20 September 2026, so the auditor sees the process
change as well as the findings. This replaces "fix, deploy to dev, run Hunter, read the wreckage".

## 1. What MK instructed, 23:23 IST

> "Is the text-based simulation able to cover all of these failures? If yes, then have we tested on
> text-based? Let's ensure first that our pipeline is foolproof. That means if it fails on text-based,
> it fails on Hunter, and if it passes on text-based, it passes on Hunter. It becomes easy for us to
> reproduce and fix the issues here, and then try on dev instead of trying on dev all the time, which
> will take us a lot of time."

**The honest answer to his first question: no, I did not run the text lane for any of the board-4
fixes.** I went from unit tests to a dev deploy to a 21-call Hunter run. The first thing I did after he
asked was replay one failing scenario in the lane: `18868`, the choice correction, **failed in the text
lane in 57 seconds** with the same shape Hunter reported after three phone calls.

That is the whole argument for this change, in one measurement.

## 2. The lane, as it exists

`v29-revamp/stress-evals/sim-fh/`, already built and in use for earlier rounds:

| Step | Command | What it does |
|---|---|---|
| Build twins | `build_live_twins.py --payloads DIR --passcode X` | One text twin per LIVE Hunter payload: the persona verbatim, the TARGET sentence as the goal, the Hunter criteria verbatim as the rubric, the flow's four custom-code actions run for real against the mock |
| Run | `run_live.py --payloads DIR --env-file F --tree DIR --gemma --repeat N --only SLUG...` | Runs each twin through the sim CLI on a chosen tree, judges with `judge.py` against that scenario's own Hunter rubric, prints a board |
| Judge | `judge.py` | The payload's `evaluationPrompt` verbatim, one verdict per numbered criterion, **score = min accuracy**, threshold 0.8 — Hunter's own rule |

Entry matches Hunter: screening events run at the flow entry, everything else enters at the V2.9 node.
Agent is Gemma, as on dev; persona and judge are GPT, as Hunter does.

## 3. What the lane can and cannot see

This is the part that decides whether "foolproof" is honest.

**Covered** — everything decided by the model, the prompt, the collector tools and the flow's actions:
choice correction and confirmation, answer-beside-a-route, retry and progress budgets, option
presentation, date interpretation from text, screening dispositions, exit routing, and the callback
variables the flow records.

**Not covered — structurally, because there is no audio:**
1. **STT mishearing.** "the twenty-eighth" heard as "the eighth" (`bfe294b4`) cannot occur in text.
2. **TTS/name rendering.** "Mette Larsen" spoken as "MetLife" (`454f581a`) cannot occur in text.
3. **Carrier and call lifecycle.** Dropped calls, silence timeouts, barge-in and interruption timing
   (`e7fd56f2`, `1a8b99c1`).
4. **Real turn-taking latency** and anything that depends on it.
5. **Hunter's own evaluator faults.** The lane uses the same rubric but its own judge run, so an
   evaluator misread like `18992`'s false pass is a property of the Hunter run, not of the lane.

**Therefore the rule we adopt is one-directional and stated as such:**

> **Fails in text ⇒ it will fail on Hunter** (for the covered classes). Fix it in text first.
> **Passes in text ⇏ passes on Hunter.** Audio, carrier and evaluator classes still need live calls.

Claiming the reverse would be the same mistake as claiming offline green proved speech behaviour, which
is exactly what the last two audits caught me doing.

## 4. The working order from now on

1. **Reproduce in the text lane first.** No fix starts without a failing twin. A defect that cannot be
   reproduced in text is labelled audio/carrier/evaluator and goes to the live list explicitly.
2. **Fix, then re-prove in the lane** with repeats (3), on the exact tree.
3. **One changed scenario end-to-end before any bulk authoring change** — the audit's wording, and the
   rule that would have caught my canonical-tuple error after one call instead of twenty-one.
4. **Dev is diagnostic, not clearance.** Deploy, pin the running image and task definition, then run
   three targeted live executions per changed mechanism and read transcript, criterion, producer calls
   and persisted truth for each.
5. **The frozen board runs last**, on one pinned candidate, with no mid-run edits.
6. **Every expectation change is proven by a negative control** — a deliberately wrong slot and a
   deliberately missing boolean must fail — before it is trusted.

## 5. Calibration: what we are measuring right now

The seven proof-run scenarios are being replayed in the lane, three times each, on the same tree that
is deployed (`3ca5b326`, image `dev-26.09.20.460`), with Gemma and real actions. The output is a
side-by-side table:

| Scenario | Hunter (live, 3 runs) | Text lane (3 runs) | Reading |
|---|---|---|---|
| per mechanism | pass/fail | pass/fail | **agree-fail** = reproducible here, fix in text; **agree-pass** = lane trustworthy for it; **disagree** = lane blind, live-only |

The table and its disagreements get appended here when the run lands, with the cost comparison
(seconds per text case against minutes per call) so the trade is visible rather than asserted.

## 6. How this plugs into the auditor's gate

The proof-run audit's sequence is "repair offline proof first … replay source counterexamples and model
text … run one changed scenario end-to-end before bulk authoring changes … treat dev as diagnostic".
This lane is the concrete instrument for those steps, and the calibration table is the evidence that it
is fit for them. It does not replace any gate: the three live executions per mechanism, the producer
truth review, and the frozen board all still stand.

---

## 7. Second attempt, 23:40–00:0x IST: what was wrong with the first one, and what I changed

MK, 23:38: *"yes and do not do the same mistake again, now run it properly."* Recorded so the auditor can hold this section to it.

**The first parity attempt (5/21, 1/7 twins) was invalid, and the invalidity was mine.** Three separate configuration faults, each of which alone makes the lane lie:

1. **The lane's flow was stale.** `sim-fh/flow.json` was dated 19 Sep 00:04. It did not contain the step-5 date question, the soonest rule, or the "different provider or location" rule. The twins were judged against rubric text written for the deployed flow, while the agent under test read an older flow. Three of the seven twins failed on exactly that gap, which is an artefact, not a defect.
2. ~~**The pinned tree was not the deployed code.**~~ **Withdrawn — the auditor is right and I was wrong.** I claimed `main-prs/repro-bf020cd1` (head `803415bf`) ran different code than the deployed `3ca5b326`. Their **trees are identical**: `git rev-parse 803415bf^{tree}` and `3ca5b326^{tree}` are both `29e81a05806407489fd850034decce81978cd580`, and `git diff --stat` between them is empty. Different ancestry is not different code, and I asserted the stronger claim without checking the trees. I still pin the lane at `3ca5b326` because the deployed commit is the honest thing to name, but it explains none of the earlier failures. The causes were the stale flow and the missing passcode.
3. **After I refreshed the flow, the twins had no action passcode**, so every action returned `FHCSD_PASSCODE is not configured` and all three runs of the first twin exited `Conflict Or API Failure` at the first tool call. A green-to-red flip caused by the harness, not the agent.

**What I did instead, each step verifiable:**

- **Flow refresh from the deployed truth, not a local copy.** The full `dump_dev_flow.sh` stalls on a `--scan` of the whole dev keyspace, so I read the two node configs directly by key: `PHLO:b363ccd7-60cc-4fca-b451-5f24be67c760:NODE:19b06489-2a83-42a5-bc6b-eada85f2964b:CONFIG` (48,164 bytes) and `…:NODE:67e95d08-92b4-56ce-826f-46673d842a34:CONFIG` (675 bytes). I replaced `instructions`, `actions` and `extract_variables` in `flow.json` with the live values, rewriting `{{uuid.field}}` references to `{{node-name.field}}` the way `build_flow.py` does. Backup of the old file: `scratchpad/flow.json.bak-0920`.
- **The diff proves the staleness claim** — 11 diff lines, three of them substantive: step 5 changed from "Do not ask what dates suit them" to "Collect preferred_start_date… a date, a range or a correction they name is the date, even when they also sound impatient"; step 7 changed to "collect preferred_start_date again"; and the Throughout block gained the different-provider-or-location rule. Those are precisely the rules the three "failures" were scored against.
- **Pinned tree = deployed commit.** New worktree at `3ca5b326` ("Merge pull request #527") with its own venv, confirmed an ancestor of `origin/dev` and two commits behind its tip. The lane now runs the code the pod runs.
- **Passcode restored from the repo's own non-secret constant** (`FHCSD/mock-real/worker.js`, documented in `wrangler.toml` as "not a real secret"), injected through the environment at twin-build time. No secret is written into the repo.
- **48 twins rebuilt** from the refreshed flow, then the same seven scenarios × 3 relaunched against the pinned tree.

**The rule I am adopting, because two of these three faults were silent:** before any parity claim, the lane must print and I must check four facts — the flow dump's source and age, the tree's commit and its relation to the deployed image, that the first action of the first run returned `success: true`, and the judged rubric's provenance. A parity table published without those four is not evidence.

**Still an open gap, named rather than hidden:** the lane judges the rubric only. It does **not** check callback variables, which is why 18996 passed 3/3 in text and failed live on a variable mismatch. Until variable checking is in the lane, "passes in text" cannot imply "passes in Hunter" for any scenario carrying `expectedCallbackVariables`. That work is next, and the calibration table below will mark which rows are variable-blind.

---

## 8. The auditor's review of this lane, 00:21 IST, and what I changed

The auditor read the plan and the builder, runner, judge and simulator code, and reproduced **three false passes locally on stubbed responses, with no model calls**. Its verdict — "the direction is right, but I would not accept it as a reliable gate yet" — is correct, and every item below is now either fixed with a runnable control or recorded as an open limitation.

### 8.1 The guarantee, restated in the auditor's words

MK's framing was "if it fails on text, it fails on Hunter; if it passes on text, it passes on Hunter". That is not achievable: the conversations, the judging, the entry state and the simulator all differ between the lanes. The rule the lane actually enforces from now on:

> **A validated text failure blocks promotion** until it is explained or fixed. **A text pass permits targeted voice testing** — it is never a substitute for it. A text failure that does not reproduce on voice stays **unresolved**; it is never written off as "audio", "carrier" or "evaluator" without evidence naming the cause.

### 8.2 The three false passes, now negative controls

`sim-fh/test_gate_negative.py` runs seven cases against a stubbed model client, so it costs nothing and runs in under a second. Six must fail and one must pass:

| Control | Before | Now |
|---|---|---|
| The simulator reports the wrong exit | judge returned PASS | **FAIL** — the twin's asserted exit is checked in the judge (`--expect-intent`), not only inside the simulator |
| Required screening values skipped | counted as satisfied → PASS | **PARTIAL**, never PASS, and the uncovered keys are printed |
| Judge returns criterion 1 twice, omits 2 | PASS | **FAIL** — the returned numbers must be exactly 1..N |
| Simulator recorded failures | ignored | **FAIL** — `failures` decide the verdict |
| An elicited turn (simulator prompts a silent node) | invisible | **FAIL** — such a run can never prove the agent speaks unprompted |
| An expected variable never recorded | ignored | **FAIL** |
| A clean run (positive control) | PASS | **PASS** |

The runner is hardened the same way: stale `*.judge.json` from an earlier board are deleted before judging, a twin must produce exactly the requested number of judged runs, a non-zero simulator exit is a problem on the board line, and the process now **exits non-zero** unless every twin is green.

### 8.3 What the hardened gate found on the very first pass

This is the evidence that the hardening was not cosmetic. Same seven twins, same deployed commit, judged twice — once with the old rubric-only judge, once with the gate:

| Twin | Rubric-only judge | Hardened gate | What the gate saw |
|---|---|---|---|
| `L-reschedule-callback-later` (18996) | 3/3 PASS | **0/3 FAIL** | `wants_to_reschedule` expected `no`, **never recorded** — the same answer-beside-a-route defect the live call showed (`hand_back value=null`) |
| `L-slot-corrected-after-choosing` (18868) | 3/3 PASS | 2 PARTIAL, **1 FAIL** | run 2 ended with no exit at all: `final: intent: expected 'Rescheduled', got ''` |
| `L-soonest-next-day` (19137) | 3/3 PASS | 2 PARTIAL, **1 FAIL** | run 2 `final: ended: expected True, got False` — the call never ended |
| `L-dob-fished` (18992) | 3/3 PASS | 2 PASS, **1 FAIL** | criterion 3 NOT MET on one run — the prose-loop defect, flaky in text as it is live |
| `L-happy-first-slot` (18879) | 3/3 PASS | 3 PARTIAL | `selected_slot` **matched** the canonical tuple semantically, which independently confirms the auditor's C1: the tuple is not unpassable |
| `L-mildly-annoyed-not-upset` (18998) | 0/3 (variable artefact) | 3 PARTIAL | screening keys are uncovered, not violated |
| `L-two-values-one-breath` (18880) | — | — | the run **stalled** at 0% CPU for 16 minutes and was killed; rerunning |

**The rubric-only lane reported 18/18 green on runs that contain two dead calls, one lost variable and one NOT MET criterion.** That is precisely the misleading green the auditor warned about, and it is why no calibration number from before this section may be quoted.

### 8.4 Accepted and still open

- **Item 4, exact failing-turn replays** — not built yet. Personas can dodge the exchange that breaks the agent; a scripted replay cannot. The four named replays (missing `hand_back.value`, repeated DOB deflection with no decline call, choice correction across separate turns, volunteered answers re-asked) are the next build.
- **Item 5, structured outcome checks** — the lane now checks flattened variables, which is not proof of the delivered callback or a real booking. Selection, action arguments, action result and final recorded values must be validated separately. The five-DOB-requests false pass stays as an evaluator regression case.
- **Item 6, the freeze manifest** — the preflight must hash the whole effective configuration (flow, Inputs, prompts, dependencies, model settings, fixtures, personas, rubrics, harness) plus the date and timezone, and use a dedicated success canary rather than demanding `success: true` from scenarios that deliberately test API failure.
- **Item 1 in §7 stands corrected in place** (the two trees are identical).

### 8.5 Order of work, as the auditor set it

Harness negative controls (**done**) → exact failure replays → repeated persona tests → targeted Hunter runs → frozen full board. No calibration board is interpreted before the false-pass paths are closed.

---

## 9. The exact failing-turn replays, and what they found on the first run (00:30–00:50 IST)

Built as the auditor asked: fixed scripts, not personas, in `sim-fh/ws/replays/scenarios/`. Each asserts the **outcome**, not only the exit — the simulator's `expect` block already supports `variables`, `variables_absent` and `spoke_unprompted`, so the assertions are structural. Run on the deployed commit `3ca5b326`, Gemma, three runs each, serially (parallel runs interleave the verbose log and cannot be read).

| Replay | Result | What it asserts | Finding |
|---|---|---|---|
| `R-callback-later-answer-lost` | **3/3 FAIL** | exit `Declined` **and** `wants_to_reschedule = no` | The exit is right, the answer is never recorded. This is live 18996 / `31f217aa` reproduced **deterministically in text**, for the price of a text run |
| `R-choice-corrected-across-turns` | **3/3 FAIL** | exit `Rescheduled` **and** `booking_confirmed = yes` | Worse than the live symptom: the call ends in `Declined` with no booking at all after the caller corrects their choice in a later turn |
| `R-volunteered-answers-not-reasked` | **3/3 FAIL** | exit `Rescheduled` **and** `preferred_start_date = 2026-09-28` | The run **crashes**: `RuntimeError: cannot schedule new speech, the speech scheduling is draining/pausing`. It happens right after `update_date` applies the volunteered date while a caller turn arrives — the paused-scheduling path PR #527 touched. See the caveat below |
| `R-dob-deflected-six-times` | 3/3 PASS | exit `Verification Failed` | **My assertion is too weak.** The live defect is the *number* of date-of-birth requests (criterion 3), not the exit. This replay does not yet test the defect and must count requests before it is quoted |

**Caveat, stated because the mistake is mine and it matters:** in the volunteered-answers replay the caller's line "The first one works." arrives before any slots are offered, because I wrote the script from the wrong question order. The crash is still real — a caller can speak at any moment, and a `RuntimeError` that ends the call is never an acceptable response to an ill-timed turn — but the script needs re-timing before this is called a clean reproduction of 18880.

**A second, separate defect: the walk stalls.** `L-two-values-one-breath` hung **twice**, on two independent launches, in the same place: immediately after the agent says it will check availability, i.e. inside `fhcsd_search_available_appointments_fresh_auth`. The process sat at 0% CPU for 16 and 8 minutes with no further log line, and had to be killed both times. On a live call this is dead air, so it is worth its own investigation rather than a retry.

**What this says about the lane.** Before tonight the text lane reported these same mechanisms as green. With the evidence gate and the replays it produces, in one pass and for a few dollars, two deterministic reproductions of live defects, one crash and one reproducible hang. That is the gate doing its job. It is still **not** a substitute for voice: the promotion rule in §8.1 stands.

**Immediately next:** count the date-of-birth requests in the deflection replay; re-time the volunteered-answers script; then fix the two reproduced defects against these replays, since a deterministic 3/3 failure is the cheapest possible fix-verification loop.

---

## 10. Fixes made tonight against the replays (01:00–02:00 IST)

MK, 00:40: *"nothing is happening in the morning, we will do everything here and right now and then pass on to dev for testing."*

Branch `mk/v29-fhcsd-replay-fixes`, cut from the deployed commit `3ca5b326` (not from `main`, because the code these fix is only on dev; noted rather than assumed).

### 10.1 A yes/no field lost the answer the caller gave beside a route (live 18996)

**Root cause, and it was ours, not the model's.** Every collector's frame carries this rule: *"A caller who asks to be called back is not declining this field and is not answering it… the request they made is never itself that answer."* That is right for an email address and wrong for a yes/no. When what the caller is putting off **is the thing the field asks about**, their turn has answered it. The model was told not to pass the answer, so it passed `value: null` and the answer was lost — which is why the live call exited correctly and recorded nothing.

**Fix:** only a boolean field is told the other half of the rule — a deferral of the very thing it asks about is its answer, and the answer is no. No other field is told that, so a callback request can never be recorded as an email address.

**Proof:** `wants_to_reschedule` is now recorded as `no` on 3 of 3 runs of the twin, against 0 of 3 before.

### 10.2 A model that called a completion tool twice killed the call

`hand_back` raised `RuntimeError: CollectBoolean is already done` straight out of the tool when the model repeated itself. A model repeating itself is not a reason to hang up on a caller. `hand_back`, `answer_side_question` and `change_earlier_value` are now no-ops once the collector has completed. This is what the `RuntimeError: cannot schedule new speech` crash in §9 was standing on.

### 10.3 An activity swap read as the call ending

`session_closing` reports True while no activity is mounted. That is correct for muting speech and wrong for telling the walk the call is over: a collector that hands back unmounts its activity for an instant, and on that instant the record path reported **"call ended"** to the parent while the caller was still on the line. `session_terminating` asks the strict question (`_closing is True`), and the record path now asks that one. The log line proving the change: `recorded beside the route; no receipt and no continuation on a route`, where it used to say `stored while the call was closing`.

### 10.4 What the fixes do to the board

| Twin | Before | After |
|---|---|---|
| `L-reschedule-callback-later` (18996) | 0/3, `wants_to_reschedule` never recorded | exit `Declined` and the variable recorded `no` on 3/3; **one criterion still fails** — see below |
| `L-slot-corrected-after-choosing` (18868) | 2 PARTIAL, 1 FAIL (a run with no exit at all) | **3/3 `Rescheduled`, every criterion 1.00**, PARTIAL only for the screening keys the lane cannot cover |

**Still failing, stated plainly:** on 18996 the agent asks the rescheduling question **once more** after the caller defers, then routes correctly. The variables and the exit are right; criterion 4 counts that repeat as a violation. It is a single-turn adherence miss by the model after it has been told, first thing in the tool result, that the field is answered and must not be asked about again. It is not fixed by more prose, and the next lever is structural.

**Tests:** `tests/units/test_route_answer_and_idempotence.py` pins all three fixes (a repeated completion tool, the boolean-only frame rule, and the swap-vs-teardown distinction). Full unit suite **3254 passed, 3 xfailed**.

### 10.5 The preflight earned its place immediately

The first verification run was **refused** by the preflight because the tree was dirty — my uncommitted fixes. That is the gate doing exactly what §8 built it for: a board run on an unrecorded tree is not evidence.

---

## 11. The PR-531 audit, answered (02:00–02:50 IST)

The auditor requested changes on `07485d51` and was right on all three counts. Each is corrected in `00e6c5ed`, with tests written at the level it asked for rather than as string assertions.

### 11.1 The correction tool was not a no-op after completion

The audit reproduced it: on a completed task the guard sat **after** validation, so a late `change_earlier_value` still ran `_change_refused` (which can raise `ToolError` into a call that has moved on) and still added the field to `action_pending_fields`, which `src/tools/action_policy.py` reads when deciding whether a later action may run. The guard is now the first statement in all three completion tools. Tests cover the same field and a distinct late field, assert no staging and no raise, and a monkeypatched always-refuse guard proves the refusal reaches a live collector and never a completed one.

### 11.2 The lifecycle check missed a queued close

`_close_soon` creates `_closing_task` synchronously and sets `_closing` only inside it, which is why the SDK's own `_is_closing` reads the task first. `session_terminating` now calls that predicate when it exists and reads both fields otherwise, and a rename of either degrades to "not terminating" — a live call keeps running rather than being muted. The audit also caught a second call site I had missed: the earlier-value **resume** at `collect_input.py:1167` still asked the lenient guard, so an activity swap between a correction and its resume could drop the interrupted field. It asks the strict one now. The test builds the real `AgentSession` class and moves it through the states rather than asserting on hand-made booleans.

### 11.3 The boolean guidance was two rules in disagreement

The frame carried a blanket rule plus a boolean exception, while `hand_back`'s own contract still carried only the blanket rule — the model was reading both. They are one field-aware rule now, and the tool description is built from the collector's kind, so a yes/no field and an email field are told different, self-consistent things. The three meanings the audit named are asserted separately: a now-question plus "not now" is **no**; a callback-later question plus "please call back" is **yes**; an unrelated field plus a callback request is **no value**. A confirmation-owed boolean is never finalised unasked (`_records_a_seed_unasked` refuses it).

### 11.4 The most important finding: the transcript accused the agent of something it did not do

The audit's log reading is correct, and my §10 claim of a "single-turn adherence miss" was **not established**. On `fix-board7` run 2 the model's three responses after the deferral were an empty text with `handoff_declined` and a closing line. None of them asked the rescheduling question, yet the report showed it after the caller's deferral, and the judge failed the run on it.

**One real harness defect found and fixed (PR #532).** Raw-message recovery reports whichever assistant line it finds unreported in the live context, so a line generated on an earlier turn but missed by that turn's capture was indistinguishable from one spoken now, and landed after the caller's next turn. Each turn now snapshots the context's assistant lines before driving anything; a recovered line already in that snapshot is marked reported and logged instead of being counted as this turn's speech.

**And one real product defect it does NOT explain, now identified.** With #532 applied to the same twin, the question still appears after the deferral and the new "earlier line" log stays silent — so in that run the line is genuinely **generated during the deferral turn**. The mechanism: `CollectBoolean.on_enter` fires `generate_reply(instructions=self._question)` directly, and nothing cancels it when the collector completes by handing back a moment later. The deferred path already guards exactly this — `rearm_entry_question._still_owed` drops an opener when the collector is done, the caller has spoken, or the call is closing — but the immediate path has no such guard and keeps no handle to interrupt.

**Not fixed tonight, deliberately.** The shape of the fix is clear (the immediate entry question must answer `_still_owed` too, or the collector must hold its speech handle and interrupt it on completion), but it is speech-scheduling code at 02:50 and it deserves the same verification the other three got. It is the first item of the next session, and it is the real cause of the 18996 criterion-4 failure.

### 11.5 Status against the audit's verification gate

Done: root-fix tests for the early guard and a distinct late field (1); queued-close and real-SDK lifecycle tests (2); positive and negative boolean cases per field, polarity and meaning (3); the capture repair (5, in part — #532 fixes one mechanism, §11.4 names the other). Outstanding: real-collector integration coverage (4), the clock freeze and coherent fixture refresh (6), hash archiving (7, the preflight manifest now emits them per board), the three-then-voice-then-board sequence (9). No fresh board is quoted here, and the two 3/3 results above are named as what they are: targeted proof of two mechanisms, not clearance.

---

## 12. The repeated question, chased to the end (03:00–04:15 IST)

MK asked for the §11.4 fix and a text proof before pushing. The fix is built and pinned by tests; **the text lane cannot prove or disprove it**, and the reason is worth more than the fix.

### 12.1 The fix

`fire_entry_question` parks the opener's speech handle on the collector, and the shared `complete()` in `LanguageHintTask` — which already cancelled a pending re-arm — now drops the pending opener too. Force-interrupt on purpose: once the collector has finished, the question is moot whether or not it had started. A question already spoken is left alone, and a handle that refuses interruption never fails the completion. Every immediate entry question goes through the helper (boolean, choice, currency, text) and so does the re-armed path, so it is one rule for every collector rather than a patch on the one that showed it. Four tests, and `6310 passed, 160 skipped` outside e2e.

### 12.2 Why the twin still shows the repeat, and what that proves

Four runs, each ruling something out:

1. **With the fix, the twin is unchanged** and the "dropped" log never fires.
2. **A probe log proved the opener IS asked through the helper** (`entry_question: asked by CollectBoolean`) on the turn *before* the deferral, and that the handle was already `done()` when the collector handed back — so there was nothing left to cancel.
3. **The model's own request payloads put the question BEFORE the caller's deferral** on every request of that turn. The agent asked first; the caller answered it.
4. **Neither capture guard fires**, because at the turn's start the line is in no context yet (it was scheduled, not landed), and the copy that later appears carries a fresh id and a fresh `created_at` — the code's own comment warns that context copies re-id items, which is why text is the stable key. Attributing by creation time was tried and reverted: the copy's timestamp is not the original's.

**What this means.** In the text lane a scheduled opener completes instantly, so the window the fix exists for — a question still playing when the collector finishes — never opens. The lane cannot demonstrate the defect **or** the fix. This is a class the text lane does not cover, and it belongs in §3 of this document alongside the others.

**And the transcript is still wrong.** The question is delivered across the turn boundary, so the report shows it after the caller's reply to it, and a judge reads that as the agent asking twice. Two doors were closed (PR #532: raw recovery, the context-item union, and the collector's own context in the snapshot) and this case goes through neither. The remaining honest statement: **the sim cannot currently place a line that was generated before the caller's turn and delivered after it.** Until it can, criterion-4-style "asked again" failures on 18996 are not evidence about the agent, in either direction.

### 12.3 What I am NOT claiming

Not that the repeat is a model-adherence failure (withdrawn in §11.4, and the request-payload ordering argues against it). Not that the opener fix repairs 18996 — the only thing that can settle it is a **voice** call on dev, where the question takes real time to play. Not that the board is ready: §11.5's outstanding items stand.

### 12.4 Pushed

| Branch | PR | What |
|---|---|---|
| `mk/v29-fhcsd-replay-fixes` @ `7a72706f` | [#531](https://github.com/contacto-io/agent-runner/pull/531) | the three route/lifecycle fixes, the audit's three corrections, and the opener cancel |
| `mk/v29-sim-turn-attribution` @ `edf23195` | [#532](https://github.com/contacto-io/agent-runner/pull/532) | harness only: turn attribution through both doors, and the collector's own context in the snapshot |

---

## 13. Filed for after prod (MK, 2026-09-21 11:29 IST: "file for after prod")

Two findings from the PR #533 review, same class as findings 1 and 2 of the audit, deferred by MK. Miller CX
currently requests changes on both, so the PR's `code-review/codex` status is red until they are fixed or the
decision is overridden by a human review.

**Update 2026-09-21 16:10 IST — items 1 and 2 are closed at the root, not deferred.** MK (11:52) refused the patch-and-re-review loop and (12:56) took the auditor's design; both fixes are in PR #533 (main `8fe6e1f6`, on prod as `26.09.21.126`). Item 1: `_asked_again_by_an_action` is gone (`e67f82e5`); an action can only reject a candidate through its own `execution_policy.on_reject` rule, so an unrelated lookup never pops a carried answer. Item 2: `collect_email` classifies through `evidenced_decline` (`795fd724`), same as name — the caller's turn decides refusal vs inability, and a paused turn is refused with `refuse_deferred_turn`. Pinned by `tests/units/test_rejected_candidates.py`, `tests/units/test_carried_answer_confirmation.py`, `tests/units/test_unresolved_declines.py`. Items 3 and 4 remain open.

1. **The carried-answer drop is field-blind** (`src/units/collect_input.py`, the `_asked_again_by_an_action`
   check on the carry, ~line 499). A caller gives this field's value beside a side question; the parent runs
   an UNRELATED lookup; that output is the newest history item, so the helper returns true and the caller's
   answer is popped and discarded before the collector resumes — the caller is asked again for a value they
   already gave. The correction path was fixed in `38cd34aa` by requiring no caller turn since the field's own
   record; the carry has no record yet, so that stamp does not discriminate here. The carry's policy check
   (options/settings changed) already covers a genuine re-ask of THIS field; the fix is to drop the action
   clause for carries, or scope it to an action whose output changed the field's policy. Pin: value +
   side-question + unrelated-action sequence.

2. **`collect_email`'s decline can never be a refusal** (`src/units/tasks/collect_email.py:333`). The tool's
   `Literal` permits only `input_not_provided` and `spelling_not_provided`, and the prompt sends a firm refuser
   to `input_not_provided`, so `refused=reason == "refused"` is always false: a required email the caller
   refuses outright is recorded as inability and the walk continues. Fix as `collect_name` was fixed in
   `38cd34aa`: `refused=evidenced_decline(self, UNABLE) == REFUSED`, so the caller's own turn decides. Pin
   refusal and genuine inability end to end.

3. **`execution_policy.on_reject` has no production author** (found while closing the PR #533 review, 13:25 IST).
   The runtime contract landed in `e67f82e5`: an action's `execution_policy.on_reject` rule names the collected
   field and the argument that carried its candidate, and a matching result marks that candidate rejected so the
   collector never seeds or returns it. But on the deployed FHCSD node none of the four actions carries an
   `execution_policy` at all, and neither the console nor phlo-core has a producer for it — `on_success` had none
   before this PR either. So the rule ships inert: nothing is ever rejected, carries and records are kept, which is
   the auditor's safe default. To make it live: (a) console authors `on_reject` for the availability search and the
   save (rejects `preferred_start_date` / `selected_slot` on `success: false` or `slots_available: 0`); (b) prove
   the config-service GET projection preserves `execution_policy` end to end — the projection that erased node keys
   on 09-17 (`node-model-keys-erased-by-get-projection`) — by round-tripping a node through the console and reading
   the Redis `:CONFIG` back. **Update 13:50 IST:** Miller CX read PHLO-core and reports that PHLO passes
   `execution_policy` through whole (no key filtering in `phlo/components/utils.py`), so preservation is not
   the gap; authoring is. Only (a) remains.

4. **The screening exception exit (#527) is inert in production** (Miller CX on `e67f82e5`). `_exception_intents()`
   intersects the screening config's `exception_intents` with `agent_config.intents`; PHLO-core's
   `phlo/components/contact_screening/views.py` emits `intents: []` deliberately and a `screening_task` of only
   `extra_instructions` / `ask_permission`, and nothing in agent-runner assigns `intents`, so on a real call both
   sides are empty, the exit tool is never built and the escape route cannot fire. It runs only in the text lane,
   whose `src/simulation/flow/agent_config.py` synthesises its own config. Safe default: screening behaves exactly
   as before #527. To make it live, PHLO-core must emit the node's `intents` and the allowlisted
   `exception_intents` on the screening `agent_config`; no PHLO-core PR exists yet. Runtime side needs no change.
