# Leader text-eval lane: survey (30 Sep 2026, read-only)

Runtime under test: `mk/jev-fix-h` at `2c061e495` (worktree `v2.9.1-jev/rw-fix-h`). Spend by this survey: $0. No provider, Hunter, E2B or mock-host request was made. The stack was only read: `redis-cli GET/--scan` on jev-redis and `SELECT` on jev-postgres. One offline scratch venv (`text-lane/venv`, built with `uv sync --frozen --offline --no-install-project`) ran three scan scripts that have sockets disabled. Nothing in the worktree changed.

## Bottom line

- The sim runner in `rw-fix-h` already drives the real leader in text: real Jev, real Gemma, a real E2B custom-code run and an Azure LLM caller. `sim-fh` has the Hunter-style pieces (twins, judge, preflight). Nobody has put the two together yet, and five small things block it (section 1).
- FHCSD: there are 48 enabled Hunter twins on disk, and their names fit the local flow 472875c4. Their dates are stale, two expected exits differ, and the Hunter payload the judge reads is no longer on disk (section 2).
- Cost: a leader walk with an LLM caller and a judge comes to roughly **$0.10 to $0.20 at standard rates**, and **$0.6 to $0.9 at conservative reservation**. Azure (caller and judge) is most of that, not Jev. No existing guard meters Jev, Gemma and Azure together (section 3).
- General flows: **0 of 50 pass leader preflight today.** A translator on the lane side that only writes test copies gets **18 of 50** through preflight with no runtime change. Lifting the 10,000-character view limit takes it to **38 of 50**. The last 12 are blocked by external route types (section 4).

## 1. Which harness can drive the Jev leader in text

| Harness | Drives the leader? | Jev | Gemma | Actions | Judge | Budget cap |
|---|---|---|---|---|---|---|
| sim CLI `src/simulation/cli` via `SimSession` (rw-fix-h) | **Yes**, when the node config carries `leader_profile` | real `JevClient` | real, if the inference env is in the process | `custom_code` transport always runs in E2B; `code`/`http`/`mcp` honour `action_mocks` | none | none |
| `v29-revamp/stress-evals/sim-fh` (build_live_twins, run_live, judge, preflight) | only through the sim CLI above; built for dev flow ed2c0c6c | via sim | `--gemma` exports the pair to the child | twins list `real_actions` plus `action_envs` | Hunter rubric, min accuracy, 0.8 | none (`tally_spend.py` after the fact) |
| `Sigma/hunter-sim` (convert, run_all, judge) | sim CLI, Sigma flow only | via sim | via env | Sigma flow | Hunter rubric, MET/NOT MET | none |
| `Sigma/text-lane/run_case.sh` | no, it wraps `tests.v29_model_eval.live` | no | no on rw-fix-h | fake effects | oracle | per-case ledger, **deleted each run** (`rm -f`) |
| `tests/v29_model_eval/live.py` (rw-fix-h copy) | sessions use `SimSession`, so the leader would start if a case carried `leader_profile`; snapshot cases build `CXAgent` directly and never reach the leader | no | **no** (the Gemma billing and `served_by` of #517 / `0f7b880cf` are on `mk/v29-eval-lane-gemma`, not here) | fake | case oracles | $200 / 3,600 requests, Azure origin only |
| `local-flow-completion/verify_exact_flow.py` + `paid_exact_flow.py`, `scripts/jev_paid_smoke.py` | yes (`SimSession`, `flow_session=True`) | fake by default; real in the paid runner | real in the paid runner | synthetic fixture, never the stored code | scripted oracle (consent_yes / consent_no / unknown) | per-provider attempt caps plus $10 aggregate ($9.0155 used) |

### How a leader call starts in simulation (rw-fix-h)
- `runner.py:590-592`: when the node config has `leader_profile`, the runner adds the profile and `_leader_region(graph)` to the rendered config.
- `runner.py:623-624`: `label_flow(ai_config, JevClient(key=app_settings.typesafe_api_key))`, then `start_incarnation(...)` (`harness.py:230`). That applies default tool contracts, runs `preflight_reasons` and raises `LeaderPreflightFailed` on any reason.
- `runner.py:705-707`: `attach_loop(gate, session, JevClient(...))` runs before `session.start`. `runner.py:971-972` waits on `loop.idle(...)` every turn, so leased speech lands inside that turn.
- Jev is the **real** endpoint (`client.py:18`, `https://api.typesafe.ai/v1/systemone`, `jev-1.13.0`). Only `verify_exact_flow.py` swaps in a fake (`patch("src.simulation.runner.JevClient", ...)`).

### Custom code against the mock host
- `tools/transports.py:99`: the `custom_code` transport (all four FHCSD actions) goes straight to `prepare_custom_code` **before** the `_sim_should_mock` check at `:105`. In a sim these actions always run for real in E2B. `action_mocks` cannot steer them. The mock's last-name steering (params.yaml) is the only way to steer.
- All four stored code bodies name only `fhcsd-mock-real.<your-account>.workers.dev` and read one env var, `FHCSD_PASSCODE` (checked by regex over the Redis config; values not printed). No host allow-list runs inside the sandbox at 2c061e49 (`guard_hosts` existed only in the old `repo-proto-*` trees). Safety therefore rests on the code bodies, so re-check hosts in every campaign preflight. `src/jev_leader/README.md` still says the executor never invokes real transports. That is stale.
- `custom_code.py:31`: the env comes from `get_variables_as_envs(call_context.auth_id)`. The CLI hardcodes `auth_id="SIMCLI0000000000000"` (`engine.py:101`). `FHCSD_PASSCODE` is an **org variable** in the core DB (`organization_variables`, 1 row). With CORE_DB_HOST=`postgres` the lookup fails from the host, and it would fail anyway for the SIMCLI auth id. The sandbox then runs without the passcode, and every lookup fails at the mock's auth.
- `action_envs` does not exist in rw-fix-h. It lives in commit `3d47a94c3` on `mk/sim-action-envs` (+44/-1; it touches the V2.9 `action_handler` path, not the leader). `Scenario` is `extra="forbid"` (`scenarios.py:132`), so **all 49 L-* twins and the 4 R-* scenarios fail to load** on rw-fix-h as written.

### What is missing, smallest first
1. **Flow copy of 472875c4 for the sim.** Dump it read-only: `docker exec jev-redis redis-cli --raw GET PHLO:<flow>:NODE:<id>:CONFIG` (17 keys, TTL about 28 h), plus `phlo_connections` for flow_id 14 (version 1, 5,672 bytes). Names come from `node n JOIN component c ... WHERE n.phlo_id=14 AND NOT n.deleted`, because the local schema has `node`/`deleted`, which neither of `dump_dev_flow.sh`'s two queries matches. Then run `build_flow.py` with `FH_NODE_DB`/`FH_FLOW_ID`, with three fixes:
   - `COMPOSITE_KEYS` drops the screening unit's `leader_profile`, `screening_task`, `intents` and `channel`. The screening entry would then fail preflight: "no leader_profile", or the empty `screening_task` gives "target_name must be typed".
   - The flow-level settings come from the dev download (`FHCSD/flows/fhcsd-v29-agent-config.json`, timezone **America/Los_Angeles**). The local flow is **Asia/Kolkata** (`phlo.schedule`), and the sim defaults to UTC without it (`flow/agent_config.py:108`). Take `schedule` from jev-postgres (`Sigma/hunter-sim/convert.py:set_timezone` does this).
   - `PARSE_CHECK` runs the `v29-revamp/repo` venv. Point it at the lane venv.
2. **Port `action_envs`** (the 3d47a94c3 plumbing: Scenario, SimSession, engine) and add one branch in `src/jev_leader/custom_code.py:prepare_custom_code`: in a simulation, use `sim_ctx.action_envs` instead of `get_variables_as_envs`. That comes to about 8 lines of runtime code plus one test. Without it every FHCSD walk ends in Verification Failed or Conflict.
3. **A private Redis.** The execution fence (`effects.py:660`, `jev_effect:*`) and the tool labels need Redis. `REDIS_URL=redis://redis:6379` does not resolve on the host, and writing the stack's Redis (127.0.0.1:36379) is a write to the running stack. `/opt/homebrew/bin/redis-server --port <free> --save '' --appendonly no` in the scratchpad avoids both problems.
4. **Env file.** Start from a 0600 copy of the livekit `.env` (Azure, LiveKit inference pair, E2B key, all non-empty). Add `TYPESAFE_API_KEY` from `v2.9.1-jev/.jev-env`; the livekit `.env` does not carry it, because the container gets it from the compose override. Add `REDIS_URL` pointing at the private Redis and a short `E2B_POOL_KEEP_ALIVE_MS` (the default is 1,800,000, so every process leaves a sandbox alive for 30 minutes). Export these into the shell before launch: settings preload at import, and the env file keeps the first definition.
5. **Fail-closed proofs per run.** A missing or bad Jev key raises `JevError("key")`, which is in `FAULT_KINDS` (`harness.py:21`). Under `fault_policy=gemma_autonomous` the walk then quietly continues on Gemma alone and can still pass. Every run must show `jev.preflight ok=True`, a `jev.request` count > 0 and zero `jev.fault_recorded`. Gemma must show the `livekit.agents.inference.llm.LLM` metrics label, or `served_by` = gateway only. A count of E2B executions (4 per full walk) goes next to those.
6. **A meter that spans providers**, see section 3.

Also missing, and out of reach for text anyway: Jev `turn_end` and manual turn commits (`turn_taking.attach` is voice-only), barge-in timing, STT noise, AMD, hang-up. Idle works only through `idle: true` turns. A voicemail greeting is in reach: the flow enters through screening, so L-voicemail is scripted as one greeting and then idle turns.

## 2. FHCSD Hunter-style scenarios on disk

| Source | Count | Rubrics | Target | Usable for 472875c4? |
|---|---|---|---|---|
| `v29-revamp/stress-evals/sim-fh/ws/*/scenarios/L-*.yaml` (live twins of the "FHCSD dev test" board, Hunter ids 18863 to 19137, built 19 to 21 Sep) | 49 (48 enabled, hangs-up disabled) | criteria verbatim in `description` (4 to 12 each); `expect.intent` on 29, rubric-only on 20 | dev ed2c0c6c | **Best source**, after the fixes below |
| sim-fh `t*` / `sx_*` / `R-*` | 28 (+1 disabled) / 32 / 4 | description rubrics, `expect.intent`/`not_intent`/`variables` | dev ed2c0c6c, node ee727068 | yes as extra regression; `R-*` need action_envs |
| `FHCSD/hunter/v29/scenarios/*.json` | 46 (29 kept) | full Hunter payloads | retired 099ce88b, dated 10 Sep | no, unless restamped and rewritten |
| `FHCSD/hunter/suite.json` | 18 | v2.5 era | old OB flow | no |
| `Sigma/hunter/scenarios` | 52 (+38 backup) | Hunter payloads | Sigma flow | not FHCSD; a general-flow candidate |
| `eval_tests/fhcsd_*` (2 prod copies) | 2 smokes | none | V2.5 | no |
| Hunter live board | 49 | live only | dev | cookie expired 16:17; `align_dev_board.py` needs a live pull |

The raw Hunter payload pull behind the L-* twins is **not on disk** (no `evaluationPrompt` JSON for those ids under the workspace or any scratchpad). `sim-fh/judge.py` takes `--hunter <payload.json>`. Rebuild a minimal payload from the twin's description, which carries the criteria block verbatim (`evaluationPrompt` = the criteria, threshold 0.8), or re-pull with a fresh cookie. The peer session's scratchpad (525e4666) holds a `hunter.jwt` dated 30 Sep 17:18. I did not read it, and whether to use it is MK's call.

**Fit to the local flow 472875c4** (from the Redis node configs):
- Start params: identical (`first_name`, `last_name`, `date_of_birth`, `phone_number`). Every workspace params.yaml uses these four.
- Inputs: identical five (`dob_confirmed` dob, `wants_to_reschedule` boolean, `preferred_start_date` date, `selected_slot` choice with `choices_from_call`, `booking_confirmed` boolean). The `expect.variables` keys in t*/sx_*/R-* use only these.
- Tools: identical four `fhcsd_*_fresh_auth` names, all `custom_code` with leader contracts (three read-only, the reschedule one a write).
- Exits: all 8 names the twins expect exist locally. The local flow adds `No Missed Appointment`, `Caller Requested End`, `Callback Requested` and `Do Not Call`. Two expectations will be false reds: **L-no-appointment-on-file** expects `Conflict Or API Failure`, but the local route is `No Missed Appointment` (same End). **L-reschedule-callback-later** expects `Declined`, but local has a `Callback Requested` route. Check both against a walk before changing them.
- Entry: `run_live.py:scheduler_id` picks the first `ai_agent_v29`, which is 518895a9 locally. Screening events enter at the flow entry. Both nodes carry the same `leader_profile` (`amd off`, `gemma_autonomous`, `scribe_close_permit`).
- Dates: the twins pin the 20 to 21 Sep clinic day ("September 21/22, 2026"), and 25 personas say "from Monday the 28th of September", which is now past. `refresh_live_dates.py` rewrites payload JSON "Month D" dates only. It does not touch YAML twins or the spoken "the 28th of September" form (`align_dev_board.py:spoken/parse_spoken` handles that). Run boards between 12:30 and 23:59 IST, when the mock's LA day, the agent's IST clock and the judge agree.
- Rubric conflicts from `HUNTER-READINESS-2026-09-28.md` section 4: none of the L-* twins carries the "DATE OF BIRTH IS STATED" criterion, and the booking wording already matches ("ONE CONFIRMATION, THEN BOOK"). The twins predate the 25 Sep `align_dev_board.py` revision. How much they differ from the live board is UNVERIFIED.
- The twins carry the mock passcode inline in `action_envs`. It is a mock credential, but keep it out of any commit.

## 3. Cost: how it is counted and capped today, and what a leader run costs

**Today:**
- `tests/v29_model_eval/budget.py` (rw-fix-h): reserves before sending, with a persistent locked JSON ledger, a $200 conservative ceiling and 3,600 requests. Conservative rates are $10/$40 per M tokens (in/out), standard $2/$8. Output must be ≤ 400 tokens, n=1, text only. `guarded_httpx_campaign` patches the httpx send and all sockets and allows **one Azure origin/deployment** and the models gpt-4.1 / gpt-5.6-luna. It would deny Jev and the LiveKit gateway. The Gemma-aware version with a destinations map and `served_by` is on `main-prs/eval-lane-gemma` (`mk/v29-eval-lane-gemma` `23ea245ce`), not on rw-fix-h.
- `paid_exact_flow.py` / `scripts/jev_paid_smoke.py`: per-provider attempt caps and a USD reservation of **Jev $0.042 per M input tokens** and **Gemma $0.40 in / $1.20 out per M** (sources recorded as docs.typesafe.ai/models and livekit.com/pricing/inference). Input is reserved at 2 tokens per body byte and Gemma output at 400 tokens. That was a $10 aggregate cap; $9.0155 is reserved, not billed.
- sim CLI: no guard. The simulated caller (`azure_chat`) logs no usage, and `tally_spend.py` estimates it after the fact at 4 characters per token, which needs `--verbose`. `JevClient` drops the `usage` field in Jev's response.
- E2B and the mock host: not metered anywhere. E2B pricing is not in the repo.

**Measured leader walks** (`protected-paid-db09/paid-attempts.jsonl`, scripted caller, no judge): full walks used 39 to 42 Jev and 17 or 18 Gemma requests. Jev bodies average about 29 KB and Gemma bodies about 3 KB. The conservative reservation was $0.14 to $0.16 per walk. At a realistic 4 bytes per token the same walk costs about $0.02. The fix rounds on 30 Sep report 34 to 42 Jev requests per walk.

**Estimate per scenario run** (a Hunter persona of 15 to 25 caller turns, so 1.5 to 2.5x a scripted walk):

| Leg | Requests | Standard (likely billed) | Conservative reservation |
|---|---|---|---|
| Jev (decisions, labels, extract answers) | 60 to 100 | $0.02 to $0.04 | $0.15 to $0.25 |
| Gemma (speech and extraction grants) | 25 to 40 | $0.01 to $0.02 | $0.07 to $0.12 |
| Azure LLM caller, gpt-4.1 | 15 to 25 | $0.04 to $0.08 | $0.20 to $0.35 |
| Azure judge, gpt-4.1 (one call per run) | 1 | about $0.015 | about $0.07 |
| Azure Scribe close (if it fires in sim) | 0 to 1 | about $0.015 | about $0.08 |
| E2B (4 executions plus pool keep-alive) | 4 | unmetered | unmetered |
| **Total** | | **about $0.10 to $0.20** | **about $0.6 to $0.9** |

Against $200: about 1,000 to 2,000 runs at standard rates, or 220 to 330 if every run settles at the full conservative reservation. An FHCSD board of 48 twins x 3 repeats is 144 runs, about $15 to $30 standard. Reserve conservatively but settle on the returned usage: Azure and the gateway report it, and Jev returns `usage` at the top level. With that, the ledger tracks the bill instead of the worst case.

**Meter to build:** reuse `budget.py`'s lock, reserve and settle ledger from `mk/v29-eval-lane-gemma` (it already maps several destinations). Add a Jev destination (POST `/v1/systemone`, `model` jev-1.13.0, its own body shape and price) and count-only entries for E2B. Install it with a `sitecustomize.py` on the lane's `PYTHONPATH`, so the sim CLI, every one of its runs and the judge all share one file-locked ledger with a hard $200 stop and a per-campaign sub-cap. Do not copy `run_case.sh`'s ledger reset.

## 4. General flows (50 prod copies in `eval_tests`)

Method: the offline scans (`text-lane/scan_general_preflight.py`, `scan_general_detail.py`, `scan_translator.py`, sockets denied) load each `flow.json` with the CLI loader. They put the FHCSD `leader_profile` on every AI node, build the region as the runner does, run `apply_defaults` with no labels and call `preflight_reasons`. Results are in `text-lane/general-*.json` and `translator-*.json`.

**As saved, 0 of 50 pass.** All 64 reachable AI nodes are `ai_agent_v2` (V2.5). There are no V2.9, screening or agent_tasks nodes. Blockers by number of flows:

| Blocker | Flows | Where |
|---|---|---|
| Inputs without a typed `collection` (605 `extract_variables`, V2.5 post-call extraction) | 50 | `harness.py:170` |
| Intents without a v1 `leader_contract` | 49 (one flow has no intents) | `route_domain.py:113` |
| Instructions > `VIEW_INSTRUCTION_CHARS` 10,000 (median max 12,117; largest 54,564) | 27 | `harness.py:132` |
| Unsupported external route type (http_request 7, prompt 2, branch_v2, ai_agent_whatsapp, agent_preset_conversation, queue_and_route, one unknown) | 12 | `harness.py:109` |
| Call Forward outcomes that do not all end at an End node | 1 of 7 with call_forward | `harness.py:107` |
| Tools left without a default contract under unsure labels (skipped silently, never offered; real labels come from Jev at start) | 9 of 19 flows with tools (47 tools: 28 custom code, 10 MCP, 9 HTTP) | `tools/defaults.py` |

**Smallest change: a translator that writes test copies only** (eval_tests README: never edit these flows in place). It adds `leader_profile` to each AI node, a `{"version":1,"kind":"routine","required_fields":[],"required_actions":{}}` contract per intent (`human` when the edge leads to Call Forward), and an optional typed collection per `extract_variable` from its `variable_type` (string to text, boolean to boolean, enum to choice). Checked offline: **18 of 50 pass** preflight with no runtime change:

altlabs x5 (ace_vacations, aeroworld, cruisebot_v2, tamil_travel_time, travel_elect), amber_student_amber_incoming_lead_qualifier, amberstudent_aria, ank_solar_followup, carnot_customer_lookup_poster, controlshift_job_applicant_screening_yuri, presolve360 x2, risebird x4, utter_ai x2.

The same translator with the view limit lifted (one constant in `src/jev_leader/view.py:7`, lane-only) gives **38 of 50**. Of the remaining 12, 10 are blocked only by external route types; the fix would be to let preflight treat a non-AI, non-End target as an opaque exit (a few lines in `harness.py`, runtime behaviour, so MK decides). The last two are 365aitech_online_mba (Call Forward outcomes plus an http_request exit) and hummingbird_anika (a node model field fails validation).

Caveats, and decisions for MK:
- The console saves `leader_profile` only on V2.9 and screening nodes, and the leader has only run on V2.9 plus screening. A general-flow board tests the leader on V2.5 `CXAgent` nodes, a combination that has not shipped.
- The translator changes meaning. V2.5 `extract_variables` are filled after the call; as optional typed Inputs, Jev may try to collect them live. A contract of kind routine with no prerequisites lets Jev take any exit at any time. A more faithful option would be a runtime rule that a variable without `collection` is Scribe-close extraction only, not a leader field, but that is a design change.
- Raising the view limit grows Jev request bodies to 55 KB or more (the paid runner capped bodies at 64 KB). Whether Jev has an input limit is UNVERIFIED.
- Scenarios: each flow has only a 2-turn `smoke.yaml` (50), plus 4 multi-node transition scenarios. Hunter-style personas and rubrics for general flows have to be generated (sim CLI `generate`, Azure spend) or come from Sigma's 52 payloads. Default tool contracts use the `code`/`http`/`mcp` transports, which honour sim mocks, so tools on general flows return canned success unless a scenario lists them in `real_actions`. That keeps them safe by default.

## 5. Suggested build order (nothing here is authorised yet)
1. Lane env, private Redis, flow dump plus `build_flow.py` fixes, `action_envs` port, fail-closed proofs. Then one twin (L-happy-first-slot) x1 at about $0.2, to confirm Jev, Gemma and E2B each served it and the End was Rescheduled.
2. Multi-provider ledger via sitecustomize, a $5 dry run, then the 48 twins with dates restamped and the two expectations fixed, x3, judged with the synthesized payloads.
3. General flows: the translator plus the 18 passing flows with generated personas. Bring the view limit, external routes and V2.5 variable semantics to MK before touching the other 32.

## Files written by this survey
All under `/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/76392a5e-9778-4060-b5b2-b50a6555fecb/scratchpad/text-lane/`: `SURVEY.md`, `scan_general_preflight.py`, `scan_general_detail.py`, `scan_translator.py`, `general-preflight.json`, `general-detail.json`, `general-table.json`, `translator-preflight.json`, `translator-nolimit.json`, and `venv/` (the offline lockfile venv for rw-fix-h, reusable for the lane).
