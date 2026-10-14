# Text evals

The text-based test lanes and Hunter-style test scenarios we built while testing Plivo CX voice agents (agent-runner V2.5, V2.9, System One with Jev, and v2.10). This file explains how the scenarios are made, how to run them, how to score them, and the rules that kept the numbers honest.

Two kinds of material live here:

- `synthetic/` holds made-up businesses and made-up callers. Start here. Every file can be read and shared.
- `suites/` holds the test sets we built for real customer flows. The scenarios, generators and scorers are here. The customer flows themselves, run outputs and anything with real call data are not.

## Contents

- [What is in this repo](#what-is-in-this-repo)
- [The two kinds of test](#the-two-kinds-of-test)
- [Set up once](#set-up-once)
- [Make sim scenarios](#make-sim-scenarios)
- [Make Hunter scenarios](#make-hunter-scenarios)
- [Run](#run)
- [Score and judge](#score-and-judge)
- [Rules that kept results honest](#rules-that-kept-results-honest)
- [Traps](#traps)
- [Not in this repo](#not-in-this-repo)

## What is in this repo

### Start with these (synthetic)

| Folder | What it is | Start with |
|---|---|---|
| `synthetic/northwind` | A made-up home services booking flow (one V2.9 node, 13 Inputs over all 12 collector types, 3 tools, 6 exits) and 47 scenarios: a clean case, an edge case and a correction or "why" case per collector type (eight types get a correction; email, currency, dob and dtmf get "why"), plus flow-level cases such as consent declined, stop calling, a human mid-call and a booking rejected. One Python file writes the flow and every scenario. The flow runs on the Jev leader (see [Make sim scenarios](#generate-them)). | `SPEC.md`, `SCENARIOS.md`, `make_spec.py` |
| `synthetic/homefix` | The v2.10 stress test: one made-up flow (every collector type, actions, AI-to-AI moves, a transfer) and 30 hard callers, built into sim workspaces and Hunter payloads from one source. A call passes only when Hunter's judge and our own log check both pass. | `README.md`, `callers.py` |
| `synthetic/ridgeway-clinic` | A 34-scenario A/B on one V2.9 node (a clinic reschedule desk with ten Inputs), with a deterministic judge and probes that test the judge itself. | `README.md`, `review-scenarios.md` |
| `synthetic/acme-claims` | 26 Hunter coverage scenarios for an insurance claims line, a sim workspace for the same flow (`sim/`, three scenarios) and the prompt that builds the flow. | `hunter/scenarios.py` |
| `synthetic/home-services` | The cleanest Hunter example: a flow builder, 14 Hunter payloads with their generator, create and run scripts, a Hunter-to-sim converter and a judge that grades sim runs with each scenario's own Hunter rubric. | `README.md`, `hunter/build.py` |

### Suites built for customer flows

| Folder | Flow | What is there |
|---|---|---|
| `suites/fhcsd` | Clinic appointment rebooking | Hunter boards for V2.5 and V2.9 (`hunter/`, `hunter/v29/`), a steerable clinic API mock (`mock/`, `mock-real/`), a sim A/B kit (`sim/`), Hunter-to-text twins with a Hunter-style judge (`sim-twins/`), the 48-caller text lane with spend control (`text-lane/`), guarded single-node probes (`probes/`) |
| `suites/sigma` | Recruitment screening | A Hunter generator and 14 hand-written scenarios (`hunter/`), the Hunter-to-sim lane with an audited judge and negative controls (`hunter-sim/`), a text-lane classifier (`text-lane/`) |
| `suites/rapido` | Driver reactivation in Hindi and Kannada | Language-following A/B builders and scorers, 11 scenario sets |
| `suites/telecrm` | Lead qualification, English and Hindi | Scripted and persona scenarios, transcript tallies, a Fisher-test A/B, a safe Hunter rubric editor |
| `suites/carnot` | Tractor welcome call, several Indian languages | 19 Hunter payloads |
| `suites/vapi-clinic` | Pulmonology clinic | A stdlib mock of the clinic API and a sim rig with scorers |
| `suites/system-one-lane` | System One (Jev leads) on the clinic flow | The System One text lane, board readers, A/B tables and cheap replay repros |
| `suites/v29-stress` | V2.9 collectors | The Lane A stress pack (collector edge cases) and its launchers |
| `suites/v2.10` | v2.10 | Before and after text checks, a wording lab for Jev, board tools, an instructions-to-Inputs bench, a caller-language bench |
| `suites/latency-ab` | Agent node latency | A three-arm latency A/B over six small sim workspaces |
| `suites/subtle-confirmations` | Collector read-backs | A cx-skills runner, a humanness scorer and labelled contrastive conversations |
| `suites/cx-skills-gemma` | Gemma 31B on the cx-skills task suites | Sharded sweeps, a recheck loop and a cross-model regression check |

### Shared tools and docs

| Path | What it does |
|---|---|
| `tools/launch.py` | Runs the sim CLI on one agent-runner tree with `--verbose --no-open`, the env file named in its `ENV_FILE` line exported only to the child, and Gemma switched on. The log starts with the tree's commit and a dirty flag; any uncommitted diff is saved beside it as `<ws>/logs/<label>.diff` |
| `tools/run_suite.sh` | Runs every scenario of a workspace in parallel, one CLI process per scenario, resumable (see [Run](#sim) before using it) |
| `tools/show_report.py`, `tools/said.py` | Print a sim report's turns and tool calls, or everything the agent said in one run of a verbose log |
| `tools/scenarios_to_cli.py` | Turns console-generated scenarios into sim CLI YAML |
| `tools/internal_to_export.py` | Turns the console's internal flow JSON into the export shape the sim CLI reads |
| `tools/sim-watchdog.sh` | While a `rerun.sh` campaign is running, kills any sim run on a `sim-fh/ws/<name>` workspace whose newest `campaign-*/lane-b/` log has been silent for 60 seconds. Its paths are the old stress-evals layout; adapt them first |
| `docs/hunter-api.md` | Hunter API recipes: auth, endpoints, payload anatomy, failure triage |
| `docs/hunter-protocol.md` | The rules for Hunter voice boards |
| `docs/hunter-rubric-idiom.md` | How to write a persona and a rubric the way Hunter judges them |
| `docs/v29-test-ladder.md` | The full V2.9 test ladder: unit tests, text lane, local stack, dev Hunter board, and the fix loop |
| `docs/text-lane-pipeline.md` | Why the text lane runs first and what it can and cannot see |
| `docs/stress-evals-brief.md`, `docs/stress-evals-plan.md` | How Lane A cases are written, the 12 collector types by 12 caller behaviours matrix, and how Hunter scenarios become text twins |
| `docs/scenario-stability.md` | Pass rates per scenario across six boards, the reason one board is not a pass rate |
| `docs/local-harness.md` | Running one agent node locally, text only |
| `docs/subtle-confirmations-method.md` | The method behind the subtle confirmation rules |

## The two kinds of test

**Text sim.** agent-runner's simulation CLI runs the real agent code (the same prompts, tools, collectors and routing) and feeds it typed caller lines instead of speech. A scripted caller says fixed lines; a simulated caller is an LLM playing a persona. There is no phone, so a run takes seconds per turn and costs cents. It shows logic, collectors, routing, saved values and language.

**Hunter.** Hunter (`https://hunter.contactodev.com`) places a real phone call. An LLM persona talks to the agent, and an LLM judge scores the call against numbered criteria. It is slower and costs more, and it is the only way to see voice faults: speech-to-text mishearing, text-to-speech, barge-in, latency, idle timers and dead air.

**Text twins** are the same scenario run both ways: the Hunter persona becomes a simulated caller and the Hunter rubric becomes the text judge. The rule goes one way only. A fail in text will fail on a call too, for the things text can see. A pass in text proves nothing about voice.

The order we used for every fix: find the root cause, reproduce it in text, A/B it in text, batch the fixes, then one dev deploy and one Hunter board.

## Set up once

1. **An agent-runner tree with its own venv.** The sim CLI lives in agent-runner (`src/simulation/cli`). Each worktree needs its own `.venv`; run `uv sync --frozen` in it. Most scripts here take the tree path as an argument or run from inside it.
2. **An env file with the keys, outside this repo.** The sim CLI reads `--env-file` (Azure OpenAI endpoint, key and deployments, the LiveKit inference key pair, and so on). Keep it at `chmod 600`. Never commit it; `.gitignore` blocks `.env` files.
3. **Gemma.** The CLI's env file keeps the first definition of each key, and settings load when the code is imported, so put `LIVEKIT_INFERENCE_ENABLED=true` and the LiveKit inference key pair in the shell environment too. `tools/launch.py` does this for the child process. Check the log: `runs on Gemma by default` and the metrics label `livekit.agents.inference.llm.LLM` mean Gemma; `livekit.plugins.openai.llm.LLM` means Azure GPT carried the run.
4. **The Hunter cookie.** Every Hunter call needs the `hunter_session` cookie (Google sign-in, about 24 hours). Copy it from the browser's devtools and save it in a file outside the repo. Most scripts take the file with `--cookie`; `synthetic/acme-claims/hunter/hunter_cov.py` takes it as its first argument, and `suites/fhcsd/hunter/add_provenance.py` and `suites/telecrm/changes/apply_hunter_criteria.py` read the cookie itself from `HUNTER_COOKIE`. `GET /api/auth/me` tells you whether it still works.
5. **Paths.** The scripts were written inside one workspace on one laptop, and the folders were renamed for this repo. Many still point at the laptop (`/Users/mohammad.kadiri/...`), mostly near the top of the file, and some use relative paths from the old folder names. Fix them before running. The old names:

   | Old folder | Here |
   |---|---|
   | `V29-Hunter-Example/` | `synthetic/home-services/` |
   | `v2.9.1-jev/text-evals/example-flow/` | `synthetic/northwind/` |
   | `v2.9.1-jev/text-evals/text-lane/` | `suites/fhcsd/text-lane/` |
   | `v2.9.1-jev/s1-thin-audit/lane/` | `suites/system-one-lane/` |
   | `v2.10/logic-flow/` | `synthetic/homefix/` |
   | `v29-revamp/stress-evals/sim-prepared/` | `synthetic/ridgeway-clinic/` |
   | `v29-revamp/stress-evals/sim-fh/` | `suites/fhcsd/sim-twins/` |
   | `FHCSD/hunter/`, `FHCSD/sim/`, `FHCSD/mock*/` | `suites/fhcsd/hunter/`, `sim/`, `mock*/` |
   | `Sigma/hunter/`, `Sigma/hunter-sim/` | `suites/sigma/hunter/`, `hunter-sim/` |

   The biggest group is `suites/fhcsd/text-lane`: `lane.py` takes the tree from the `LANE_TREE` environment variable, and its `ROOT`, `SIMFH_WS`, `OLD_PAYLOAD`, `WORKER_JS`, `LIVEKIT_ENV` and `JEV_ENV` lines are laptop paths. `synthetic/northwind/ex_lane.py` and `suites/system-one-lane/s1_lane.py` import `lane`; `PYTHONPATH=<repo>/suites/fhcsd/text-lane` is enough for that.
6. **Hunter generators** read `urls.json` next to them. Copy `urls.example.json` to `urls.json` and fill in the runner URL, account auth id, flow uuid, webhook base URL, caller number and category. `urls.json` is git-ignored.
7. **PyYAML.** `synthetic/northwind/build_ws.py` and `ex_lane.py`, `suites/fhcsd/text-lane/lane.py` and `rerun.py`, `suites/rapido/lang_switch_ab.py` and `tools/scenarios_to_cli.py` import `yaml`. Run them with the agent-runner tree's `.venv/bin/python`, or install PyYAML for `python3`.

## Make sim scenarios

### A workspace

```
<workspace>/
  flow.json        the flow, in the console's "Download config" format
  params.yaml      the Start node's http params, shared by every scenario in this workspace
  scenarios/*.yaml one file per scenario
  reports/         written by each run (git-ignored)
```

Ways to get `flow.json`: the console's Download config button; `tools/internal_to_export.py` on the internal flow JSON; or, for a flow you can only read from the database, adapt `suites/fhcsd/booking-ab/build_flow.py`, which rebuilt one FHCSD dev flow (`ed2c0c6c`) that way. `python -m src.simulation.cli init <ws> --flow <export.json>` scaffolds a workspace and writes a `params.yaml` with every `{{Start.*}}` placeholder the flow uses.

Because `params.yaml` is shared by the whole workspace, give a persona its own workspace when it needs its own identity. A shared name once made the screening step exit as wrong contact.

### A scripted caller

```yaml
description: >-
  Caller corrects the date after the read-back. Judged by transcript: the agent keeps the
  corrected date and does not ask for the time again.
turns:
  - user: "Hello?"
  - user: "Yes, this is Dana."
  - user: "Next Tuesday at 10."
  - user: "No, sorry, Wednesday at 10."
    expect: { message_contains: "Wednesday" }
expect: { ended: true }
```

Use scripted turns for regressions and for barge-in: `interrupt_after: "<phrase>"` cuts the previous agent reply right after that phrase and marks it interrupted, which is the state a real barge-in leaves. Pick a phrase the agent always says, not filler. A scripted caller derails when the agent asks something the script did not expect (for example an extra read-back), so write complete lines.

### A simulated caller

```yaml
description: Busy caller who wants a callback tomorrow afternoon.
simulated_user:
  persona: "You are Dana Whitfield. You answer your own mobile. Short answers, one at a time."
  goal: "You cannot talk now. Get a callback tomorrow around 3 PM, confirm it, then end the call."
  opening: "Hello?"
  max_turns: 12
expect: { intent: Callback Requested, ended: true }
```

Write the goal as directions to an actor: what they want and how to behave turn by turn. Make sure the goal leads to the exit you expect.

### What `expect` can check

`intent`, `not_intent`, `ended`, `stop_reason`, `node`, `variables`, `variables_absent`, `message_contains`, per turn or for the whole run. `action_mocks` (tool name to its output) can be set per scenario and per turn; use `real_actions` instead when the action code itself is what you are testing. Branches of the jev and v2.10 work also take `idle: true` for a silent turn and `dtmf:` for keypad turns.

Put only checks that cannot be wrong in `expect`. An omission ("the agent never asked twice") cannot be written as an expect, so score it from the report afterwards (see [Score and judge](#score-and-judge)). Many scenarios here list what the transcript must show under "Judged by transcript:" in the description.

### Generate them

- **With the CLI's LLM:** `python -m src.simulation.cli generate <ws> --count 5 --env-file <env>`. Read every `expect:` it writes; it sometimes pairs a goal with the wrong exit.
- **From one source in code (what we did most).** Keep every scenario as one entry in a Python table, and let a script write the YAML, the params and the flow. Rebuild instead of hand-editing. Examples:
  - `synthetic/northwind/make_spec.py`: one `add(slug, group, type, facet, title, person, special, criteria, defects, turns)` call per scenario. The flow runs on the Jev leader, so the check and the lane need an agent-runner tree that has `src/jev_leader` (`SPEC.md` names the commit); main does not. From `synthetic/northwind`, run `python3 make_spec.py`, then either `PYTHONPATH=../../suites/fhcsd/text-lane python3 ex_lane.py convert --day YYYY-MM-DD` (lane packs) or `python3 build_ws.py --day YYYY-MM-DD` (a plain sim workspace in `ws/`). Run the packs with the lane's general mode: `LANE_TREE=<tree> python3 <repo>/suites/fhcsd/text-lane/lane.py preflight --flow-ws <repo>/synthetic/northwind --pack <repo>/synthetic/northwind/pack`, then `lane.py run` with the same two flags plus `--campaign NAME --campaign-cap USD --only <slug>`. Check offline before any paid run: from that tree, `.venv/bin/python <repo>/synthetic/northwind/check_flow.py <flow.json or ws dir>`.
  - `synthetic/homefix/callers.py` and `spec.py`: each caller holds who they are, the persona's facts, Hunter's criteria and what our own log must show. `python3 build.py` writes the flow, the sim workspaces and the Hunter payloads, with every date computed from today. It needs the local v2.10 stack: it reads the runner tunnel from a tunnels file of a stack run, queries the `v210-postgres` container, and reads Hunter's webhook base and account id from `V29-Hunter-Example/hunter/urls.json` (`synthetic/home-services/hunter/urls.json` here). Fix those paths at the top of `build.py` first. `sim.py` runs inside the `v210-agent-runner` container.
  - `suites/rapido/lang_switch_ab.py`: callers whose every line is tagged with the language the next reply must use, built into one workspace per arm and scored by the same file.
  - `suites/fhcsd/sim/build_arms.py`: Hunter failures turned one by one into simulated callers, with A/B flow arms.
  - `suites/system-one-lane/make_flow_exit_callers.py`: clones existing callers and adds one scripted line each, for targeted variants.
- **From Hunter scenarios (text twins).** Pull the payloads (`GET /api/scenarios/<id>`), then map: `conversationPrompt` without its TARGET sentence becomes `simulated_user.persona`, the TARGET sentence becomes the goal, `initiationVariables` becomes `params.yaml` unchanged (empty fields matter, because the flow branches on what it already knows), and the rubric goes with the scenario for the judge. Converters: `synthetic/home-services/hunter-sim/convert.py`, `suites/sigma/hunter-sim/convert.py`, `suites/fhcsd/sim-twins/build_live_twins.py`. Hunter's `agentConfig` and console exports can miss parts of the node config; the FHCSD lane built `flow.json` from the live node configs for that reason.
- **From console-generated scenarios:** `tools/scenarios_to_cli.py` (its speech-noise persona texts are reusable wherever text has to imitate mishearing).

## Make Hunter scenarios

### The payload

```
testType            outbound-agent (the flow calls Hunter) or inbound-agent (Hunter calls the flow)
initiationRequest   for outbound: the flow's trigger URL, headers, and a bodyTemplate with {{VARS}}
                    plus {{INBOUND_NUMBER}}, where Hunter puts the pool number the flow must call
initiationVariables the values for the {{VARS}} in the bodyTemplate (the Start params)
conversationPrompt  the persona, ending with "TARGET is achieved when ..."
evaluationPrompt    a preamble plus numbered criteria
evaluationThreshold 0.8
maxTurns, voiceId, language, botGreetsFirst, allowInterruptions
webhookBaseUrl      copy it from any existing QA scenario
agentConfig         the flow export; Hunter only stores it for its dashboards
```

`docs/hunter-api.md` has the full field list and every endpoint.

### Persona and rubric

The persona is written in the second person ("You are ..."), gives one answer at a time and ends with the TARGET sentence. The rubric preamble says who is the CALLER and who is the AGENT, says to judge ONLY the numbered criteria, states the facts of the domain and says what must NOT be penalised. Each criterion is one line: a short title, the test, and what makes it NOT MET. Hunter passes a call at 0.8, and the score is the lowest criterion, not the average. See `docs/hunter-rubric-idiom.md`.

Hunter's judge never sees tool outputs. A "no invented detail" criterion must name the mock's fixtures so the judge can check it (`suites/fhcsd/hunter/add_provenance.py` does this).

### Generate, push, run

The pattern used for every board: one spec entry per scenario in `build.py`, a script that pushes and reads back, and a script that runs one board.

```bash
python3 synthetic/home-services/hunter/build.py                    # writes hunter/scenarios/*.json
python3 synthetic/home-services/hunter/create.py --cookie <file> --sync   # POST/PUT, then read each back and diff it
python3 synthetic/home-services/hunter/run_board.py --cookie <file> --name "board name" --all --parallel 4 --interval 5
```

- A PUT that returns 200 says nothing about what was stored, so always read back and diff. A PUT without the full object (including `tier`) silently reset `tier` on 33 TeleCRM scenarios. `suites/telecrm/changes/apply_hunter_criteria.py` shows the safe way to edit live scenarios: back up first, send the full object, diff the round trip.
- Never hand-edit a generated scenario on Hunter. Change the generator and rebuild. Pull the live copies first, because rubrics also get edited on Hunter.
- `POST /api/generate-test-cases` can draft scenarios from an `agentConfig`. Treat them as drafts.
- Hunter has no field for expected variables. Our generators write `_expected_variables` and strip it before pushing; after a run, compare it with `GET /api/calls/{id}` (`callback_var_evaluation`), or use `suites/sigma/hunter/grade_variables.py` on a local stack.

Other generators: `suites/fhcsd/hunter/v29/build.py` (46 clinic scenarios, mock branches picked by the patient's last name), `suites/sigma/hunter/build.py` (asserts that every exit has a scenario), `synthetic/acme-claims/hunter/hunter_cov.py`, `synthetic/homefix/hunter.py`.

### Before the flow can be tested

- The flow must dial `{{Start.http.params.<phone field>}}`, not a fixed number, or every test fails with an empty transcript.
- The Start node's Require Authentication must be off, or the payload must carry the account's Basic header (the Carnot payloads here had it removed). Otherwise every item fails at trigger time with a 401.
- For variables to come back, the flow's Event Callbacks must send HANGUP and RECORDING to Hunter's webhooks. The runner caches the flow for about 29 hours after a callback change.
- Save each V2.9 node once before Publish.

### Dates and clocks

Rebuild date-based scenarios on the morning of the board. Hunter judges "today" in UTC, the agent uses the flow's timezone, and the clinic mocks use the clinic's own day (America/Los_Angeles), so keep these clocks apart in the generator. Unifying them broke 26 scenarios once. Run no relative-date scenarios between 18:30 and 00:00 UTC. The clinic mock lanes only run between 12:30 and 23:59 IST.

## Run

### Sim

```bash
cd <agent-runner tree>
.venv/bin/python -m src.simulation.cli run <ws> --env-file <env> --verbose --no-open \
    --node <V2.9 node id> --repeat 10 --max-parallel 4 --stagger 2 [--scenario <name>]
```

- `--node` starts at that AI node. The sim cannot carry a call from screening into the next node, so score the screening opening and the node in separate workspaces.
- `--verbose`: without it the CLI turns INFO logs off, and most of what you need to read is INFO.
- One process per workspace at a time; two runs on one workspace overwrite each other's reports. For parallel arms, copy the workspace.
- `tools/launch.py <tree> <ws> <label> [cli args]` writes `<ws>/logs/<label>-<HHMMSS>.log`, headed by the tree's commit, and saves any uncommitted diff as `<ws>/logs/<label>.diff`, so every arm is "base plus exactly this patch". Set its `ENV_FILE` line to your env file first.
- `tools/run_suite.sh <ws> <jobs> <outdir> [modality]` runs one process per scenario with `uv run` in the tree set by `SUITE_REPO`, using the env file in `SUITE_ENV`; both are fixed at the top of the script. It passes `--modality`, which the current CLI's `run` does not accept, so remove that flag first. A scenario counts as done once it has a line in `<outdir>/exits.txt`, whatever its exit code, so delete the failed lines before a rerun. Three jobs was stable on the laptop; six ran out of memory.
- Long campaigns: start them detached (a new session), stop them by PID, never with `pkill -f`. `tools/sim-watchdog.sh` only watches `rerun.sh` campaigns in the old stress-evals layout and exits at once when none is running, so adapt it before relying on it.

### Text lanes with a budget

`suites/fhcsd/text-lane/lane.py` (and `suites/system-one-lane/s1_lane.py` for System One) wrap the CLI for whole boards: convert the pack for today, a fail-closed preflight, a one-scenario canary, then the board. Every run reserves money in a locked ledger before it starts (`meter.py`) and settles after; a run is INVALID unless the model was proven on the wire.

```bash
python3 lane.py convert                 # rebuild pack/ for today from the sim-fh twins at SIMFH_WS (not in this repo; without them nothing is written and pack/ keeps its old dates)
python3 lane.py preflight
python3 lane.py run --campaign NAME --campaign-cap 10 --only <slug> ...  --repeat 3 --max-parallel 4
python3 lane.py board runs/NAME
python3 rerun.py --campaign NAME --campaign-cap 10 --not-valid
```

A happy clinic call cost about $0.20, and the 48-caller board about $6.50 and 15 minutes at 4 in parallel. Stop a board by reserving the rest of its cap, not by killing it. Read `suites/system-one-lane/README.md` and `suites/fhcsd/text-lane/PEER-NOTES.md` before running a lane.

### Hunter

Smoke one scenario before a batch. Run dev boards at `maxParallel` 4 with `intervalSeconds` 5; at 15 the shared pod starved speech-to-text (10/20 against 17/20 on the same build). Check `GET /api/runs?limit=12` for another team's run before starting, because the dev pod is shared. Never compare boards run at different parallelism. `docs/v29-test-ladder.md` has the full board checklist, and `docs/hunter-protocol.md` the rules behind it.

## Score and judge

### From the report, without a judge

Each run writes `reports/<stamp>.jsonl`: `scenario_started`, one `turn` record per turn (`user`, `agent`, `node`, `tool_calls`) and `scenario_finished`. Small tally scripts read it:

- `suites/rapido/score.py`, `lang_switch_ab.py score`: reply language by script, saved answers and declines by tool name
- `suites/telecrm/sim/tally.py` with `ab.py` (a two-sided Fisher exact test, no scipy) for before and after
- `suites/fhcsd/sim/tally.py`: the Hunter rubric's checks done in code, position-independent, with a Fisher test
- `synthetic/home-services/hunter-sim/audit_loops.py`, `suites/sigma/hunter-sim/compare_runs.py`, `suites/sigma/text-lane/classify_campaign.py`: structural checks that need no model

A tool call is not a success. The runtime can refuse a tool call and only the verbose log shows it; check the log before trusting a column that counts calls.

### A Hunter-style judge on text

Apply the scenario's own rubric word for word, one MET or NOT MET with an accuracy per criterion, score = the lowest accuracy, pass at the scenario's threshold (0.8), temperature 0. Then add hard gates in code: the declared exit, one clean close, the expected variables, no tags or snake_case in agent speech.

- `synthetic/home-services/hunter-sim/judge.py`: the quick version (met over total)
- `suites/sigma/hunter-sim/board.py` with `audited/`: the board of record, with a contradiction pass and negative controls (`test_gate_negative.py`) that every known false-pass shape must fail
- `suites/fhcsd/text-lane/judge_lane.py`: validity first, then deterministic checks, then the rubric
- `synthetic/ridgeway-clinic/judge.py`: fully deterministic, value-first

Check a scorer against verdicts you already know before trusting it: `suites/fhcsd/sim/tally_replay.py --validate` replays 13 known Hunter failures, and `suites/vapi-clinic/sim-rig/hunter-telecrm-p0/scripts/validate_claims.py` checks a claim detector against 42 cases. One past scorer judged the last turn instead of the first reply after the trigger and failed calls the judge would pass.

### Reading Hunter results

- In Hunter's transcript, `assistant` is the persona and `user` is the agent under test. Relabel before showing anyone.
- A fail is a claim. Read the transcript and `eval_breakdown.criteria`, then our own runner log for the same moment, before blaming the agent. "Evaluation error" with no NOT MET line means the judge gave up.
- A booking judged 1.0 with zero tool call events is a false pass.
- Before blaming the agent for a red call, rule out a void board: another suite on the shared pod, a dead mock tunnel, items with null turns (a 402 or the IP whitelist), USER_BUSY at 0 seconds, the persona's five-minute stop.
- Pair calls by first utterance or by start time plus pool number, never by persona name.

## Rules that kept results honest

- **Repeats.** An A/B needs 5 runs per arm, 10 when the arms look close; three is noise. Run them as two batches of five, because a killed long run writes no report. Report the rate and the n.
- **One change per arm.** Arms differ by one commit or one switched flag, never by editing code between runs.
- **"Fixed" means:** the scenario passes 3 times out of 3 on the corrected build, the judge says PASS each time, a person has read the transcript, and a unit test fails without the fix.
- **A board number comes from one fresh full run id.** No mixing re-dials or re-judges into it, and no rubric edits mid-run.
- **One board is not a pass rate.** The same build scored anywhere from 13/18 to 17/18 across boards (`docs/scenario-stability.md`).
- **Prove the model** from the metrics label or the host it was served by, never from the config. A Gemma failure is fixed on Gemma.
- **Freeze before a board.** A preflight checks that the flow, the payloads, the tree and the converted workspaces are the ones you mean to test (`suites/sigma/hunter/preflight.py`, `suites/fhcsd/sim-twins/preflight.py`). One board was graded against a four-day-old flow.

## Traps

**Sim**

- The env file keeps the first definition of a repeated key, and settings load at import (see [Set up once](#set-up-once)).
- The sim runs one node at a time and never runs the End node, so `no_matching_handoff` on the last turn is a fired intent, not an error. It never runs `on_enter` or speaks `session.say()` lines, so greetings and announcements need a real call.
- An empty agent turn is read as a silent 429 and the scenario restarts (up to two retries). Look for repeated attempt headers before calling a run hung. A run can hang for good; kill it by PID.
- In the report, a turn whose only tools are `update_*` shows the previous question as the agent text, and an empty agent line often means the next question landed in the next record.
- Text cannot show the idle timer, stalls after an acknowledgement, speech-to-text and spelling errors, barge-in timing or latency. Hunter's caller cannot follow Hindi and mishears spelled letters, so judge language and read-backs from our own logs.
- Detect from instructions (`suites/rapido/detect_preview.py` calls it) drops Inputs at random. Run it three times after any change to the Task and check the count.

**Hunter**

- The persona stops talking at about 290 seconds into a call and replies after about 5 seconds (10.5 at p90). Keep a walk under five minutes. An agent turn that only acknowledges, without a question, stalls the call.
- To make the persona stonewall, give it one exact line to repeat and cap `maxTurns`.
- Write expected callback variables in their stored form (ISO dates, choice ids, yes or no), and only for questions the scenario reaches. The judge also grades every key the flow posts, so a discussed field must never be posted empty.
- A voicemail persona gets no goal block and `allowInterruptions: false`.
- The real clinic API holds real patient records and is never a test target. Use the mocks in `suites/fhcsd/mock*` and `suites/vapi-clinic/mock-clinic`: the caller's last name picks the branch (FHCSD: no match, two matches, no slots, 401, 409; vapi-clinic: not found, ambiguous, system down and the insurance cases), so the conversation is the only variable.

## Not in this repo

- **Customer flow exports** (`flow.json`, `agentConfig`, database dumps, node prompts). Export them again from the console or the database when you need them. The Hunter payloads here had `agentConfig`, auth headers and personal tunnel hosts removed, and `suites/v29-stress/pack/local_stress_cases.py` has a placeholder where the clinic node's Task was.
- **Real phone numbers and addresses.** Personal and unconfirmed numbers were swapped for placeholders in every form (digits, spaced, spelled out), including inside scenarios. Company caller ids and Hunter pool numbers were kept.
- **Run outputs** (`runs/`, `reports/`, `logs/`, boards, ledgers). They held transcripts built on customer flows and were several GB.
- **Real call data.** Anything copied from a production call was left out.
- **Secrets.** Env files, cookies, API keys and the clinic mock's passcode. The passcode is `change-me` in `suites/fhcsd/mock*/worker.js` and the lane reads it from there; set your own before deploying the mock.
- **agent-runner code.** The sim CLI (`src/simulation/cli`, documented in agent-runner's own docs/simulation-cli.md and its `simulation-cli` skill), its `eval_tests/` corpus of 50 production flows, and `tests/v29_model_eval` (Lane A) all live in the agent-runner repo. The System One lane also needs a small simulator patch on its tree (keypad turns and `action_envs`) that is not included here.
- **cx-skills.** `suites/subtle-confirmations` and `suites/cx-skills-gemma` run the plivo-labs/cx-skills task suites, which are in their own repo.
