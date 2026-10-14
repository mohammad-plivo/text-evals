# Stress evals for the V2.9 collectors: a full-time brief

Written 2026-09-14 14:30 IST. Owner of the ask: MK. This is a standalone assignment for one agent. Read `CONTEXT.md` in this directory first for the product, the repos and the working rules; this file adds only what the assignment needs.

## 1. The job in one paragraph

Callers on real calls correct themselves, correct the previous field while the next question is already being asked, answer a question with a question, get angry, give a bare "15th", say two values in one breath, and say "no" at the final confirmation. The 29 Hunter voice scenarios and the 38 text-lane sessions were written one field at a time and do not exercise these. Your job is to build a local, adversarial case pack for every collector type in the text lane, run it, turn every real failure into a root-cause fix in the runner with a failing test first, and then give each case a voice twin in Hunter. Nothing you create is pushed to any remote unless MK says so; the fixes go through MK's normal review.

## 2. What is already known and fixed (do not rediscover)

From dev run 242b6165 on 2026-09-14, three findings:

1. "15th" was recorded as October 15. Two runtime defects, both fixed locally on branch `v29-revamp` (commits bb6beefa and 1c9f22e5): the collectors' own model request did not carry the per-turn date hint, and the hint extractor read a bare ordinal as a month. Two session cases pin it: `mt_date_day_only_still_ahead_this_month`, `mt_date_day_only_already_passed_this_month`.
2. "No. September 15th", a correction of the previous field spoken while the next collector (a choice whose option list contained "September 15") was active, was taken as the choice. Open. This is your first target.
3. "No" at `booking_confirmed` sent the walk to the Declined exit because the node prompt has no branch for a refused booking. Open, a prompt change in the flow (`FHCSD/flows/fhcsd-v29-mock-node-2026-09-14.md`, step 7).

Earlier, from the dev-push review of 09-13: confirmation turns need affirmative evidence (`classify_confirmation_turn`), correction repair backs `_mutates_field`, and the opener boundary (`opening_question_deferred`) attributes a first answer for phone, email, name, dob, address and dtmf but defers on any unanswered question for text, number, currency and choice. That last asymmetry is an accepted ceiling; cases that hit it are labelled, not fixed.

## 3. The text lane, exactly

Location: `v29-revamp/repo/tests/v29_model_eval/`. Runner for sessions: `session_runner.py`; case list: `session_cases.py` (`MULTI_TURN_CASES`, 38 entries); CLI: `live.py`.

Run one or more cases:

```
cd "Agent Runner/v29-revamp/repo"
.venv/bin/python -m tests.v29_model_eval.live \
  --env-file <path to the eval env file, never print it> \
  --ledger <a new ledger json per campaign> \
  --campaign-id <one id per campaign> \
  --output <results jsonl> \
  --repetitions 1 \
  --session-case <id> --session-case <id> \
  --continue-on-oracle-failure
```

The env file lives in the session scratchpad of the previous agent (`scratchpad/v29-eval.env`, mode 600). Ask MK for its path if you cannot find it; never read it into the chat. The ledger enforces a ceiling per campaign; a real GPT-4.1 session costs about 0.02 to 0.05 USD per repetition. Total project spend is near its 200 USD cap. Get a number from MK before a campaign and write it down.

A case is a dict. The keys the runner reads, with the meaning learned the hard way today:

- `id`: unique, prefixed `mt_`.
- `instructions`: the node Task text. Start it with `FREEZE` (the frozen clock sentence) unless the case sets `frozen_time`. Default clock: `2026-09-09T10:00:00+05:30`.
- `fields`: `{name: description}` for every Input.
- `collect_calls`: one `collect(name, task_type, instructions, ...)` per field. The oracle compares the model's tool arguments against this minus `instructions`; so `options`, `choices`, `num_digits`, `spell_back`, `known_value` must be exactly what the model will send. If the model sends no options, author none. `collect_equivalent_default_options` lets you declare defaults that count as equal.
- `caller_steps`: in order. `step(requires_text_any, reply)` sends `reply` once the agent's last speech contains one of the words; `confirm(groups, reply, field, value)` for a read-back plus confirmation turn. Every step needs `active_field` (which collector owns the turn) or `allow_main_reply: True` when the parent node is expected to answer.
- Provenance is mandatory in strict mode: `initial_offers` (values the caller states before the first question, usually `{}`) and per step `offers`: `{field: _offer(value, gate, tool, *argument_alternatives)}`. Gates: `immediate` (stored on the turn), `confirm` (stored only after the caller confirms), `never` (must not be stored). Use `known_value_any` when the parent may pass the value as a seed.
- `expected_values` must equal `submit_arguments`; the walk ends with `submit_details` and `handoff_done`.
- Optional: `collector_result_contains` (substrings the collect tool's return must carry, the receipt directive for example), `forbidden_store`, `lookup_action`, `action_execution_policy`, `required_special`.

Adding a case moves three pins: `tests/units/test_v29_session_eval.py` (count), `tests/v29_model_eval/selection.py` (`CORE_SESSION_COUNT`, `EXTENDED_SESSION_COUNT`), `tests/units/test_v29_benchmark_selection.py` (counts and id totals). Run `tests/v29_model_eval/test_case_shapes.py` first; it catches shape mistakes before any paid call.

How to read a result row: `structural_status` passed or failed with `error.oracle_detail`; `speech_review_status` is `manual_review_required` on every pass, meaning you read the agent's lines in `partial_trace.events` yourself and judge them; `dimensions` carries `safety`, `progress`, `effects`, `speech`, `wire` with invariants such as `collector_asks_its_own_question`. The trace lists every emitted and executed tool call with arguments, the collector stack, and each model call's prompt; that is your ground truth, not the transcript.

Keeping the pack local: write the cases in an untracked file such as `tests/v29_model_eval/local_stress_cases.py` and extend `MULTI_TURN_CASES` from it under a guarded import (`try: from .local_stress_cases import STRESS_CASES except ImportError: STRESS_CASES = []`). The three count pins must then read the base count plus `len(STRESS_CASES)`, or the pins fail. Do not commit the local file. The guarded import and the pin arithmetic are the only repo changes the pack needs, and MK decides when they are pushed.

## 4. The case matrix to build

One row per collector type: name, phone, email, dob, date, number, currency, choice, boolean, text, address, dtmf. Columns, each a case where it applies:

| Column | Caller behaviour | What to assert |
|---|---|---|
| correct after read-back | gives a value, hears it back, says "no, X" | stored value is X, one read-back of X, no re-ask of the original question |
| correct the previous field | while the next collector is active, says "no, <previous field> is X" | previous field becomes X, current field untouched, `change_earlier_value` or the previous collector re-entered, never the current field's update tool |
| overlap trap | as above, where X also matches one of the current field's options or shape | same as above; this is the run 242 shape |
| two corrections | corrects, then corrects again | final value is the last one, exactly two read-backs |
| question instead of answer | "what are the options?", "why do you need that?", "how long will this take?" | one short answer, the question is asked again once, nothing stored, no decline recorded |
| no preference on an optional field | "whatever works", "no preference" | field left empty with the decline path, walk continues |
| refusal on a required field | "I'd rather not" twice | first refusal re-asked once, second halts the step, nothing invented |
| angry caller | "I already told you", "this is ridiculous" plus the value | value stored, one apology at most, no repeat of the question |
| two values in one breath | "the 15th at 9:30" for a date-only field, "yes, next Tuesday" for a boolean then a date | the owning field takes its part, the other value is not lost, no double-ask |
| bare day of month | "15th", "the 3rd", "the 31st" | the date rule: this month while still ahead, else the next month that has it |
| no at the final confirmation | "no" when asked to confirm the whole booking | stored no, the Task's no-branch is taken, never a fabricated success |
| interrupted read-back | caller cuts across the read-back with the correction | same as correct after read-back |

Use the Family Health field names and wording where a case mirrors that flow (`dob_confirmed`, `wants_to_reschedule`, `preferred_start_date`, `selected_slot`, `booking_confirmed`), because those cases become Hunter twins verbatim.

## 5. From a failure to a fix

The loop is fixed and MK insists on it: reproduce in the lane, read the trace to find the exact turn and tool call, decide whether it is the runtime, the prompt or the case (rubrics and cases are wrong sometimes; a wrong case is corrected, never bent to pass), write the failing unit test in the runner, make the smallest change at the point every caller routes through, run the targeted tests, then the full offline suite once (`.venv/bin/python -m pytest -q -p no:cacheprovider tests --ignore=tests/v29_model_eval`, about 80 seconds, 4,962 passing today), then re-run the lane case three times. A fix counts when it passes three of three with the trace read. Commit on `v29-revamp` with a one-line comment style and a dated note in the test; do not push.

Where the mechanics live: `src/units/collect_input.py` (the router, receipts, corrections, declines), `src/units/tasks/collect_*.py` (one collector per type, shared with V2.5, so a change there needs V2.5 thought), `src/units/tasks/turn_evidence.py` (confirmation and correction classification), `src/utils/turn_settle.py` (who owns a turn at a collector boundary), `src/utils/date_hints.py` and `date_hints_legacy.py` (per-turn date hints), `src/preprocessing/hooks.py` (how hints reach the model), `src/prompts/system_prompt_v6.njk` (the collect rules the parent model follows).

## 6. Hunter twins

Read the `hunter` skill for the API. A scenario is `{name, description, category, payload}`; the payload is a `MakeCallRequest` with a `conversationPrompt` (the persona, ending in "TARGET is achieved when …"), an `evaluationPrompt` (numbered criteria, judged `[MET]/[NOT MET]`), `initiationVariables` for the outbound trigger, `expectedCallbackVariables` for the stored values, and `agentConfig`. Hunter's own generator (`POST /api/generate-test-cases`) writes personas from the node graph and covers exits, not collector mechanics; author the twins by hand from your text cases, one persona line per caller step, and give the persona exactly one line to repeat when it must stonewall.

Rules that cost rounds before: create scenarios in a new category (for example `FHCSD v2.9 stress`), never edit the 29; run at most 4 in parallel on dev, check the pod for foreign suites first; the flow's Event Callbacks must point at Hunter's webhook or no variables come back; transcript labels are inverted (`assistant` is the persona); a judge verdict is a claim, read the runner log via `vlogs` (`{aws.ecs.cluster="dev-contacto-agent-runner"} "<flow_run_uuid>"`) before blaming the agent; a fixed scenario must pass three times.

Voice runs need the runner deployed on dev at the commit under test. Dev deploys are MK's to trigger, after the local proof.

## 7. Reporting

Keep a dated ledger in this directory (`stress-evals/progress.md`): per campaign the id, the ledger path, the spend, the case list, structural pass counts, the failures with the exact turn and tool call, and the ruling (runtime defect, prompt gap, case error, accepted ceiling). When a runtime defect is fixed, add the commit and the three-of-three rerun. Report to MK in tables, one row per case, old result to new result, one-line reason; quote the transcript tail and the tool call for every failure; never composite numbers across runs.

## 8. Hard rules

- No pushes, no PRs, no merges, no Jenkins triggers, no Hunter category edits outside your own, without MK's explicit word.
- Secrets never enter the chat: the eval env file, the Hunter cookie, the FHCSD passcode, any API key. Pass paths.
- Say "configuration", never "contract". Comments are one-liners. No em dashes in documents.
- Four concurrent calls machine-wide during any voice work; no pytest while calls are dialling.
- Budget: get the ceiling from MK, put it in the ledger, stop at it.
