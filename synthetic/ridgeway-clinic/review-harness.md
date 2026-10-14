# Adversarial review: sim-prepared harness (judge.py, build_ws.py, run_arm.sh)

2026-09-17. Read-only against `trees/cd6ac6c5`; no paid call was made. Evidence: `judge.py --selftest` (OK),
`build_ws.py --self-test` (OK), `run_arm.sh --dry-run` on a scratch env file, a real arm log
(`gemma-arms/full-gpt-laneb/run.err`) and real reports (`sim-fh/`, `gemma-arms/ws-gpt/`) for shapes, and
`sim-prepared/review_probes.py` — 11 probes stating the verdict the judge SHOULD give; **11/11 red today**.
A probe going green means its finding is fixed.

**Counts: High 3 · Medium 7 · Low 9. Verdict: the judge is NOT sound as it stands** — a walk that collected
nothing passes the baseline scenario (H2), a value under the wrong field passes (H1), and both
`dob-wrong-year-*` scenarios fail a CORRECT walk with the same verdict a wrong walk gets (H3). The arm
comparison is not bound to the arms (M1, M6). Fix H1–H3 + M1/M2 before the paid pre-flight; the rest can
follow.

## The six questions, answered

| # | Question | Answer |
|---|----------|--------|
| 1 | Does each speech rule fire on bad / stay quiet on good? | Fires on the selftest shapes. Quiet on good: **no** — a correct year correction (H3), a "Good afternoon" greeting (M4) and "True," (L3) are flagged. Misses bad: value twice in one sentence (M7), a corrected fee (M5), values put in the caller's mouth that never reach a tool (L1). |
| 2 | Can a rule pass a walk where the agent never spoke? | **Yes.** All five speech rules and `completed()` pass a silent, tool-less walk with `ended=True` (probe `h2`). Only `expect.variables` would catch it, and 10/35 scenarios — `plain-walk` included — declare none. |
| 3 | Is the value check fooled by a substring or a second field? | Second field: **yes** (H1; `yes` anywhere satisfies `interpreter_needed: yes`). Substring: `says` is word-bounded and `same_value` is exact/numeric/phone-suffix, but a number inside stored free text reads as a leak (L2). |
| 4 | Does the arm comparison compare like with like? | **Not enforced.** No report↔arm binding, no same-file guard, no env digest, the model gate reads a label the sim overrides, and the delta sign follows argument order (M1, M6). |
| 5 | Does run_arm.sh refuse a wrong tree, a missing or world-readable env file, never echo a value? | Wrong HEAD: yes (dirty tree at the same HEAD: no, L5). Missing env: yes. World-readable env: **no** — a 644 file was accepted. Values: never echoed — dry-run output carries key names only, 0 leaks; the CLI's `load_env_file` prints nothing. |
| 6 | Is the LLM-request count real or invented? | **Real.** One `LLM metrics collected` per physical request: 1139 lines == 1139 `LLM HTTP timing collected` (one per POST) in a real arm log; 595 carry a speech_id, 544 are the collectors' (None); 350 main-path `LLM request started`. Per-turn is honestly a walk mean. Caveats: retried attempts double-count under the same call_uuid, and the marker is a substring (M2). |

## High

**H1 — `judge.py:285-288, 376-377` variables judged by value under ANY key, and the engine's by-key verdict is discarded.**
The rule was lifted from `check_report.py`, whose pack declares NO Inputs (`examples/…/flow.json`
extract_variables: 0) so the model named fields freely. This node declares ten (`build_ws.py INPUTS`; ws
flow.json carries all ten names), so `record_<field>` is known. Probe `h1_wrong_key`: wanted date stored
under `access_notes`, wrong date under `new_appointment_date`, engine says
`variables[new_appointment_date]: expected … got …` — judge strips that line and passes the variable.
Probe `h1_yes_anywhere`: `interpreter_needed: "yes"` wanted, stored `no`, `access_notes=yes` → pass.
That is the exact defect `correction-same-turn-after-ack` and `hedged-yes-no-interpreter` exist to catch.
Fix: check `stored.get(slug(field))` first and fall back to any-key only for a field the node does not
declare; stop filtering `variables[`/`variables_absent[` out of the engine's failures.

**H2 — `judge.py` has no floor on what a completed walk collected or said.**
Probe `h2_silent_walk`: two turns, agent text empty, no tool calls, `ended=True` → PASS on
`plain-walk`; one greeting + `Reschedule Booked` + zero records → PASS. `check_report.py:206` had
`only N collect calls: stalled or ran as plain V2`; nothing equivalent survived. Fix: `incomplete: agent
never spoke` when `spoke_turns` is empty; and for a walk that leaves by `Reschedule Booked` /
`end_conversation`, every `required: True` Input (read from `ws/flow.json`) not in `variables_absent`
must be stored.

**H3 — `judge.py:113-122` dates are year-blind, so a year correction cannot be judged.**
`spoken_forms` drops the year (`_ = y`) and judges a date by month+day words only. `1926-06-09` and
`1962-06-09` therefore match the same speech. Probe `h3_year_correction`: the CORRECT walk (wrong year read
back, corrected, corrected year read back) fails with two `double acknowledgement` lines; the WRONG walk
(old year read back again) gets the identical verdict, and rule 2 never fires on it. Both
`dob-wrong-year-*` scenarios are unjudgeable, and any correction that changes only the year is invisible.
Fix: add year needles (`1962`, `nineteen sixty two`) to date forms and require the year in `says` when
the text carries any year-shaped token; dedupe `candidate_values` by spoken forms, not by `same_value`.

## Medium

**M1 — arm comparison is not bound to the arms (`run_arm.sh:52,69`, `judge.py:452-472, 549-552`).**
Both arms append `ws/reports/<stamp>.jsonl` with no arm marker; run_arm.sh records no stamp (only
"newest .jsonl"), though the CLI prints `  report: …<stamp>.json` into `run-<label>.out`
(`cli/__main__.py:108`). `judge.py prepared=X off=X` compares a file with itself silently; the arm name is
whatever the user types (a bare jsonl path yields arm `20260917-….jsonl`); the "prepared vs off" delta is
`vals[0]-vals[1]` in argument order. Fix: run_arm.sh parses the `report:` line and copies
`<stamp>.jsonl` into `$OUT/reports/` (then `resolve()` on the arm dir works and the name carries the arm);
judge refuses two specs resolving to one file, orders columns prepared-then-off, and proves the arm from
the log: `prepared.ready|fallback|skip|cancel` event lines exist only under mode `prepared`
(`prepared_speech.py:555/606/638`; `prepared_entry.py:327` "off … logs nothing").

**M2 — LLM count: retried attempts double-count; marker is a substring (`judge.py:421-449, 584`).**
`engine.run_suite:481-489` reruns a throttled attempt with the same `run_idx`, so the discarded attempt's
requests land under the same `sim-cli-<name>-<run>` call_uuid and the report never says `attempts`
(not emitted). `"LLM metrics collected" in line` also matches `Scribe LLM metrics collected` /
`AMD LLM metrics collected` (0 in the log checked; latent). Fix: count
`call.lifecycle phase=simulation_agent_` per call_uuid (exactly one per attempt; 45/45 in the real log)
and warn or divide; match `message.startswith("LLM metrics collected")`.

**M3 — `judge.py:263-265` invents `ended: true` when a scenario declares only `not_intent`/`variables_absent`.**
`declines-phone-twice-halts` and `hedged-yes-to-transfer-offer` are such scenarios; a walk that halts
at `max_turns` passes the engine and fails the judge (probe `m3`). Fix: default `want_end` only when
`expect` is empty.

**M4 — rule 3 fires on a choice label that is an ordinary word (`judge.py:343-348`).**
"Good afternoon, this is Maya…" then the caller picks `Afternoon` → `prepared line spoke 'Afternoon'
before the answer` (probe `m4`). `choice-change-after-frame` and `off-list-choice` expect `Afternoon`.
Fix: only count speech of a value from the turn its field's `collect_*` first opened.

**M5 — the currency update is misread (`judge.py:45` SKIP_ARG_KEYS vs `collect_currency.py:326`).**
`update_currency_value(min_amount, max_amount, currency, period)` carries the amount as `min_amount`,
which SKIP_ARG_KEYS drops (it is a constraint on `collect_*`, a value on `update_*`). Probe `m5`: the
timeline for `outstanding_fee` becomes `["GBP"]` — rule 2 is blind to a corrected fee and "GBP" becomes a
bogus candidate. Fix: for `update_currency_value`, value = `min_amount` (range: `min–max`).

**M6 — `run_arm.sh` cannot prove both arms ran the same env or the same model.**
No permission check (a 644 env file passes; `stat -f %Lp` = 600 should gate). No env digest in
RUN-INFO. The `"model": "gpt-4.1"` grep (L38) is not bound to the campaign node and is not what runs:
`agent_factory.py:370-371` swaps the model for `AZURE_OPENAI_SIM_DEPLOYMENT` when set. Fix: refuse a
non-600 env file; write `shasum -a 256` of the env file and whether `AZURE_OPENAI_SIM_DEPLOYMENT` is
among its keys into RUN-INFO.txt; judge compares the two arms' digests.

**M7 — rule 1 misses a value repeated inside ONE sentence (`judge.py:334`).**
`sentences()` splits on `.!?` only; "The twelfth of March, yes, the twelfth of March it is, …" is one
sentence and passes (probe `m7`). Fix: count matches of the spoken form in the turn text instead.

## Low

- **L1** rule 3 only judges values that reached a tool (`candidate_values`); a date and time of day put in
  the caller's mouth and never stored pass (probe `l1`) — `early-exit-do-not-contact` criterion 2 is
  unenforced. Pass `known` into `speech_failures` for `variables_absent` fields.
- **L2** `same_value` numeric path matches a number inside stored free text: `access_notes="it takes me 35
  minutes…"` reads as a leak of a declined `journey_time_minutes` (probe `l2`). Gate `amount()` on a
  number-shaped string.
- **L3** rule 4 `\bTrue\b` flags "True, that is the case." (probe `l3`). Drop True/False or require an
  adjacent `=`/`:`/bracket.
- **L4** `run_arm.sh:28` `[0-9]*)` accepts `3x` as repeats; the CLI's argparse then dies after the
  pre-flight. Use `''|*[!0-9]*) refuse`.
- **L5** `run_arm.sh:34` compares `git rev-parse --short HEAD` to a literal (length is auto, grows with
  ambiguity) and a dirty tree at the same HEAD passes. Use `case "$(git rev-parse HEAD)" in cd6ac6c5*)`
  plus `[ -z "$(git status --porcelain)" ]` (clean today).
- **L6** two arms launched in the same second share a stamp; `RunRecorder` opens `reports/<stamp>.jsonl`
  in append mode, so the files interleave. M1's per-arm copy plus serial arms covers it.
- **L7** `--scenario a,b` runs the CLI once per name → one jsonl each; `resolve()` keeps only the newest,
  so all but the last scenario are dropped unless every jsonl is listed. Judge every jsonl in tiers[0].
- **L8** `main()` warns a walk with no YAML is "judged on the speech rules only" — `completed()` still
  demands `ended=True` for it.
- **L9** `stats["completion"]` counts any failure containing `exit` (L521-522), e.g. an engine
  `error: …exit…` line. Cosmetic.

## What holds up

- `build_ws.py --self-test` is a real check: builds twice (idempotent), resolves every Input through the
  runtime's own resolver with no stale/errored configuration, asserts the 6/1/3 display split against
  `_SHAPE`/`RENDERABLE_TYPES`, no digit/`@` in any tool-backed prose, both exits route through an
  `http_request` hop, every rendered placeholder resolves, 35/35 scenarios load. NODE.md matches the code.
- Real reports do carry `update_*`/`confirm_*`/`change_earlier_value` calls (arguments as a JSON string),
  so rules 1–3 and the timeline have data; `update_number.value`, `update_text.value`,
  `update_choice.choice`, `update_phone_number.phone_number`, `update_email_address.email`,
  `update_name.first/last_name`, `update_dob/date.year/month/day` all reach `primary_value` correctly
  (currency is the exception, M5). `record_*` uses `value`; `RETRIES_DEFAULT=1` matches the tasks'
  `max_collection_retries: int = 1`.
- `after_end` turns are excluded; a walk with no `scenario_finished` is `incomplete`; the caller-hang-up
  synthetic turn (`ended=False, stop_reason=caller_hung_up`) fails `ended: true` correctly.
- run_arm.sh exports `PREPARED_SPEECH_MODE` for the CLI process only, and `load_env_file` uses
  `os.environ.setdefault`, so an env file cannot override the arm. Unknown flags and a bad arm are
  refused before anything runs. With `--verbose` the engine's JSON log lands on stderr, so
  `run-<label>.err` is the right input for `llm_requests`.
