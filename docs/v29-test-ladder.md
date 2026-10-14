# V2.9 procedure — from a customer flow to a proven release

_Scope: any flow built on the V2.9 agent node (typed Input collection, actions with an execution policy,
screening, intents). Written 2026-09-21 from the FHCSD and Sigma programmes; every rule below was paid for
at least once, and each was re-derived at source before it was written down. Companion to `agents.md`
(how a session works), `setup.md` (the machine), `SKILL.md` (the tools) and `../HUNTER-PROTOCOL.md` (the
voice board) — this file is the order of operations, those hold the detail it points at. When this file
and a flow's `Decisions.md` disagree, the flow's ruling wins for that flow; record the divergence there._

---

## 0. The shape of V2.9, in one screen

| Layer | Owns | Where it lives |
|---|---|---|
| Console (`contacto-console`) | Authoring: node prompt, the Input list (name, type, options, `known_value`, retries), actions and their `execution_policy`, screening, intents, Settings → Timezone | node config JSON, saved through the config service |
| PHLO-core | Storing and serving the node config; the GET projection; event callbacks; screening `intents` | Postgres (phlo db) + two Redis caches (§1) |
| agent-runner (`src/`) | Executing: `src/units/collect_input.py` routes one collector per field (`src/units/tasks/collect_*.py`), `src/tools/action_policy.py` admits actions and their rejections, `src/cx_agent.py:llm_node` is the model seam, `src/livekit_overrides.py` the SDK patches | LiveKit worker, one per call |
| Model | Gemma (`google/gemma-4-31b-it`) via LiveKit Inference by default; Azure GPT only for the Hunter persona, the judges and screening | **the org row** (`org_ai_settings` × channel) + the `LIVEKIT_INFERENCE_*` pair in the worker env. A per-node `llm_model_config` in the DB never reaches the worker |
| Hunter | The voice board: scenarios (rubric = `evaluationPrompt` + expected callback variables), personas, runs | `https://hunter.contactodev.com` |

Vocabulary used below: **walk** = one full collector sequence through the node. **Receipt hold** = the
pause while an action's tool return is delivered before the next speech. **Parity shim** = sim-only code
standing in for a live path. **Miller** = `miller-cx[bot]`, the PR review bot (§5).

Three facts that govern everything:

1. **The model sees tool calls and tool returns, not your prose.** What a collector returned decides the
   next turn; the prompt only shapes it. Root-cause from the tool-call log, never from the prompt text.
   Anything a tool wants the model to read goes in its **return string** — appended system messages are
   dropped from the tool-response and handoff contexts (11/24 calls re-collected a known value that way).
2. **A config has four copies and only one is live.** Console download, DB row, and two Redis caches (§1).
   A DB edit that is not written into the cache never reaches a call.
3. **Text can prove logic; only voice can prove speech.** The text lane finds routing, re-ask, decline,
   variable and exit defects in minutes for cents. Timing, TTS pronunciation, idle timers and
   action-interleaved routing need a live call. But "text cannot show it" is a claim to check, not assume:
   the planning-block leak sat in 26 of 49 text agent lines while we called it live-only (§3.2).

---

## 1. What to fetch from where — the truth table

Fetch the live copy, note its identity (sha, run id, commit), write that identity into the working doc.
Anything fetched without an identity is not evidence.

| You need | Source of truth | How | Trap that bit us |
|---|---|---|---|
| The node config a call actually used | Redis **string** `PHLO:<flow>:NODE:<node>:CONFIG` (the node.config JSON; the sibling `PHLO:<flow>:NODE:<node>` is a hash), TTL ~30 h | `bash ~/.claude/skills/cx-db-tunnel/scripts/tunnel.sh redis` then `redis-cli --raw GET <key>`; or `v29-revamp/stress-evals/sim-fh/dump_dev_flow.sh <flow-uuid> <out-dir>`, which opens its own tunnels and writes one JSON per node | `HGETALL` on `:CONFIG` returns WRONGTYPE. **Resolve the live node uuid from `phlo_connections` at `phlo.active_version_id` first** — a console save can mint a new node uuid, and the old key then reads "unchanged" while the edits are live. After a DB edit: TTL > 0 → `SET … XX KEEPTTL`; TTL −2 → leave it, the next call reloads from the DB. Never `DEL` mid-life; never `SET` an absent key with `KEEPTTL` (no expiry is set, the key becomes permanent and the node never re-reads the DB). |
| Flow-level settings (Event Callbacks, idle timeout, the active node set) | Redis bundle `PHLO:<flow>:V:<active_version_id>`, TTL ~29 h | same tunnel; `GET` | The warm path builds the flow from this bundle, not from the DB. A DB-only UPDATE is invisible until it expires or the flow is re-published — no variable check fired for ten days on a flow wired in the DB. |
| What the model was told and what it did | VictoriaLogs, the call's own rows | `vlogs query '{aws.ecs.cluster="dev-contacto-agent-runner"} "<call_uuid>" AND "Tool call tool="' --since 6h` (`--env prod`, cluster `prod-contacto-agent-runner`) | Tool returns outrank prompt prose. Per-turn STT metrics hide ingress lag. Before concluding a path is silent, check a line you know fires — some loggers are filtered, and the sim CLI drops INFO unless `--verbose`. **Scrub tokens; caller values never reach a report or a commit.** |
| The code that ran | The image tag → the build → the commit | task-definition image tag → Jenkins build number → its `consoleText` line `Checking out Revision <sha>` → `git diff <sha> <tested-head>` must print nothing | "Same branch" is not "same tree". The image tag is `<branch>-<version>`, so the tag alone does not give you the commit. |
| A Hunter scenario, run, verdict, or the judge's reasoning | `hunter.contactodev.com` — `/api/scenarios/<id>`, `/api/runs/<id>`, `/api/calls/<id>` | `curl -H "Cookie: hunter_session=<jwt>"`; the JWT comes from the owner and expires within the day | Rubrics have two owners — a board script writes the generated ones, humans edit others in Hunter. **Pull live before any edit; classify every diff before a PUT**; both directions have reverted a fix. Score = min criterion accuracy: one NOT MET fails the call. In `transcript_json`, `user` is the agent and `assistant` is the persona. |
| Callback variables Hunter grades | The flow's Event Callbacks → Hunter `POST /webhook/cx/hangup` | check `correlation_status` on the run before reading any variable red | Without Event Callbacks on the flow, every variable criterion is red and reads as an agent failure. `event_callbacks` is a JSON `null`, not SQL NULL. |
| Deploy state | The runtime, not the CI page | image tag in the task definition; one unbroken log stream = nothing restarted; the boot line in `vlogs` | Only **Build with Parameters + `deployDev`** deploys — a green push-triggered build deploys nothing — and it builds whatever the tip is when it *starts*, so merge first and record dev's tip. Proof is three `consoleText` lines: `deployDev=true`, `Checking out Revision <sha>`, steady state. A phlo-core merge is inert until config-service and runner-service rebuild. A merged PR is not a deployed variable (ctmpl allow-list). Dev Consul has two DCs — write both. |
| Env deltas dev ↔ prod | Consul KV + the ctmpl, rendered | diff the rendered env, not the repo | Only the Deepgram URL and scribe tier differ by design; report **our** deltas and filter the rest. Behaviour lives in code or builder-visible config, never env flags. |
| Secrets, passcodes, keys | Never fetched into a file | reference by location (`…/plivo-cx-livekit/.env`), never by value | A mock's passcode stays in the mock's source. Never `--no-verify` — the git wrapper reports it to IT. |
| The flow's decisions and audits | `<Flow>/Decisions.md`, `<Flow>/evidence/*.md`, the audit file the auditor reads | read the auditor channel **before every change** | 14 rulings went unread once and rejected designs shipped. Audit requests go into the MD; never spawn your own auditor. |

**Writing to dev** (DB, Redis, Hunter) is refused by the auto-mode classifier. Put the write in one
reusable script at a stable absolute path and ask the owner for a `Bash(python3 <path>:*)` rule. Never
retry a refused command, and never ask a peer to run it.

---

## 2. Building the flow right — author-side checks before any call

Do these in the console, then **prove persistence at the store**: reopen the page *and* read the Redis
value. A field you cannot find there is not configured.

**Settings**
- **Timezone.** The runtime reads `ai_config.agent_config.timezone` (`src/cx_agent.py:249`), filled from
  the flow's `schedule.timezone`; an unset schedule defaults to the org's timezone (India on dev). Set
  the customer's timezone and Publish, or the agent's "tomorrow" lands a day off. **Never run two clocks**
  — any date the judge is told must come from the same source the agent speaks.
- **Event Callbacks** on the flow, or Hunter cannot grade variables — and the bundle cache above means a
  DB-only edit will not take.
- A **dev copy of a customer flow** points at a mock or sandbox and has its webhooks neutralised — a copy
  once posted 11 events to the customer's prod endpoint. Confirm whether the "sandbox" is actually live
  (FHCSD's was) before any write path is exercised.

**Inputs (collectors)**
- The collector type must match the field's configuration. A yes/no configured as `choice` makes the model
  call `collect_boolean`, the runtime refuses (`collect: <field> (boolean) refused: configured as choice`)
  and the model re-plans ~10 s later — a tax per occurrence, not a lost field.
- **One value per Input**, and the Task text uses exactly the Inputs tab's names. A bundled question makes
  the next collector re-ask what was already answered; a text/tab name mismatch makes the model mint new
  names. Both read as router defects — a router-side gate for them was refuted.
- **Seeding a value from the trigger so it is never asked**: put the template reference in the Input's own
  `known_value` — `{{Start.http.params.<field>}}` — not in the Task text. `AgentTaskVariable`
  (`src/models/ai_config.py:229-248`) carries `known_value` as "the trigger HTTP param feeding this field,
  rendered upstream, so at runtime it holds the resolved value or `''`"; the router reads it at
  `collect_input.py:320`. `confirm_if_known: true` puts the field in the read-back instead of skipping the
  ask; `false` accepts it silently. An action's side effect is never allowed to become a prefill
  (`agent_tasks.py:757`), and a seed that fails the collector's own validation is dropped, not asked about
  (`agent_tasks.py:786-794`).
- `known_value` is **top-level** on the input, a sibling of `type`/`params`, never under `params` — the
  console nests it there, where the runtime never looks, and the seed dies silently. Check the saved JSON,
  not the UI: the console may expose no field for it at all, which is a UI gap, not a runtime one.
- `template_vars` is the reference map for a copied node; rewrite it or the copy resolves the source's
  variables.
- **No example values in tool-backed fields** — the model spoke one as fact.
- An Input named like a sentence fragment (`that_broke_rather`) came from the console's older regex
  "Detect from instructions" button. Delete it; V2.9 detection never invents Inputs.
- Retries default to 1: one declined field halts the walk. Decide, per required field, what a refusal
  means (end state, hand back, route) — that decision is configuration, not a prompt sentence.
- Changing a field's lifetime (when it is cleared, carried, rejected) requires **every reader enumerated**
  first; one retained stash silenced intent speech for a reader no test covered.

**Actions**
- `execution_policy.on_success` / `on_reject` is the action's **configuration**: an action may reject a
  collected candidate only through its own rule (`result_equals {path, value}` → `rejects {field:
  argument}`). Nothing else may pop a caller's answer. PHLO passes `execution_policy` through whole; the
  console is the only author. `on_reject` is on `main` (`src/tools/action_policy.py`) and **not on `dev`**
  as of 2026-09-21 — `git grep on_reject <tree> -- src/tools/action_policy.py` before testing it.
- Chained auth / `response.0.Field` needs `response_format` set on the HTTP node.
- `http_retry_limit` is **total attempts** (config default 0, clamped to 1 at call time);
  `http_timeout_ms` defaults to 1000. Set 3 / 8000 for a flaky API, and **never ship `retry_limit: 0`** —
  the dev runner issues zero requests and the call dies silently at that hop (a local runner tolerated it,
  so a local pass proves nothing).
- After any paste, `json.loads` every JSON-string field: a `str` result is double-encoding, which 502s at
  the first action.
- A new backend-only node key must survive a console GET→PUT round trip against the real projection
  (config-service, phlo-core, console Zod) or the next save erases it.

**Prompt and intents**
- Once-only rules ("ask X only once") go in the **node prompt**; a tool-description exemption suppresses
  routing outright.
- The agent speaks acknowledgements inside the request it already makes — never `say()` literals, phrase
  packs or Python literals.
- A configured `intent_speech` is spoken by the runtime before the exit. Never also write the connect line
  in the prompt, or the caller hears it twice; on a failed-transfer scenario read the
  `intent speech intent=… scheduled=…` log line first.
- Screening exception exits need PHLO-core to emit the screening `intents`; the runtime keys are
  `disposition_intents` / `exception_intents` (`src/models/ai_config.py:224`). Until PHLO-core emits them,
  that path is inert — say so in `Decisions.md` rather than debugging it.
- Prompt length is latency: a 16k-char node costs ~20k tokens per turn with history. Trim before tuning.

**Copy the flow into the text lane the same day** (§3.2) so the lane's flow sha equals the live value. A
lane on a stale flow proves nothing and its passes are false.

---

## 3. The test ladder — cheapest proof first, and what each rung cannot prove

Each rung produces one artefact with an identity; the next rung starts only when the previous one is green
**on the same tree**.

### 3.1 Unit tests (seconds, free)
- Targeted tests per fix; **one** full `uv run pytest tests/ -q` at the end of the batch. A fix in shared
  machinery (the walk loop, session handling, config models, the receipt path) earns its own full suite.
- Each fix pins its failure first (red → green). A green suite minus its own test is not a proof.
- **Refute-tracers before a dev merge**: remove the load-bearing line → the test must fail → restore. Two
  bad commits once passed green suites.
- A test over a mocked SDK session says nothing about the SDK: `generate_reply(tools=)` takes ids, not
  objects, and the MagicMock never complained. A LiveKit bump needs a live call — 1.8.0 passed 3,225 tests
  and killed calls.
- A **tool-schema** change is proven by one `max_tokens=1` request to the real provider plus one sim walk:
  3,429 green tests pinned our serializer, and every sim then died at the first LLM call on a 400.
- A new worktree needs its own venv (`uv sync`, 3 s) — the editable finder maps `src` to one tree.

### 3.2 The text lane (minutes, cents)
`v29-revamp/stress-evals/sim-fh/` (FHCSD) and `Sigma/hunter-sim/` (Sigma) are the two **worked examples**,
not a generic tool: their canary action, real-action list, exit map, passcode env and livekit `.env` path
are hard-wired. A new flow copies one folder and rewrites those constants first.

The lane replays Hunter scenarios through the simulation CLI, entering at the V2.9 node, with Gemma as the
agent and Azure GPT as persona and judge. Order of operations, none skippable:

1. **Pull the scenarios** into a payload directory (`curl -b "hunter_session=$JWT"
   …/api/scenarios/<id> -o payloads/<id>.json`) — both build scripts take `--payloads DIR`.
2. **Build the twins from the live truth**: the Redis dump, the action environments, the passcode read at
   run time from the mock's source (`build_live_twins.py`, `convert.py`).
3. **Pre-flight and freeze** (`preflight.py`): a manifest with the flow/instructions/actions/variables
   shas, the tree commit **and tree object**, `uv.lock`, the harness files, personas, rubrics, today's date
   and timezone; an end-to-end canary against the actions; and a `dates_agree` check between rubrics and
   API. The manifest is what a pass is *of*.
4. **Negative controls** (`test_gate_negative.py`): the judge must FAIL, offline, every known false-pass
   shape — wrong exit, skipped coverage counted as satisfied, a judge reply that repeats criterion 1 and
   omits 2, simulator failures, an elicited turn, a missing variable, and **agent speech carrying a tag or
   a `snake_case` token**. A control that passes when it should fail voids the board.
5. **Run with exact repeats** (`run_live.py --payloads … --env-file … --repeat N --max-parallel 3
   --gemma`); the env file carries `AZURE_OPENAI_*` for the judge and the LiveKit inference pair. Stale
   judge files are deleted first; a non-zero exit on any failure.
6. **Judge with the evidence gate** (`judge.py`): the rubric score is a lower bound. FAIL if numbering is
   wrong, the simulator reported a failure, a turn was elicited, the exit intent differs from
   `--expect-intent`, a variable is unmet, or the agent spoke non-speech; PARTIAL when a screening key was
   never reached.
7. **A/B by code only**: 5–10 repeats per arm, arms differing by one commit, flipped with a flag. Never 3
   (noise). Gemma on both arms — a Gemma failure is fixed on Gemma, never attributed to the model by
   comparing against GPT.

**Read the agent lines yourself, for what is not speech.** The judge grades meaning; a tag or an
underscore reads fine to it. 26 of 49 agent lines in one board carried a planning block and every one
passed, while the same defect failed five Hunter calls. The lane is blind to how TTS *pronounces* a tag,
not to the tag.

Genuinely live-only, and to be written in the RCA before blaming code: timing seams; the idle timer and
its reminders; the receipt hold and its repair generation; **collector routing on an action-interleaved
Task** (live skipped `collect_dob` in 6 of 25 runs while 12 of 12 text sessions collected it); tool-
description wording effects (3/4 → 0/3 live, invisible in sim); any parity shim that only fires in walks.
The sim also runs one node and never the end node — `no_matching_handoff` on the last turn is a fired
intent, not an error — and a golden recording belongs to the tree that produced it.

**Gemma specifics.** Check the metrics label (`livekit.agents.inference.llm.LLM`) before trusting a Gemma
sim; the env file's first definition wins and settings preload. An intermittent Gemma defect may be one
replica: the same model id is served by several deployments (`extra_content` names it, a same-call retry
returns to the same one), so cross-tab outcomes by deployment before touching prompts. A Gemma weakness
(date arithmetic, calling hours) is fixed by moving that reasoning into the runtime, not by prose.

**Launch mechanics.** A long campaign is launched detached (`Popen(start_new_session=True)`, unique tag,
absolute worktree path) — a harness background command dies at its timeout and takes the sessions with it.
Stop it **by PID**; `pkill -f` once killed a launcher and duplicated a Hunter run.

**Budget.** Measured 2026-09-21 from the lane's own `LLM metrics collected` lines: at `--max-parallel 3`
with several arms side by side the lane peaked at **2.3M tokens/min** against the LiveKit project's
6M/min cap, with the voice boards sharing the same key. Keep it to one arm while a board runs, and record
the lane's UTC window in the run log so a quota question is answered from a file.

### 3.3 The local docker stack (only for what text cannot judge)
- Bind-mounted checkouts run the host tree: switch the branch on the host, `ast.parse` every touched file,
  clear `__pycache__`, restart the container. "Healthy" is the container, not the app.
- The livekit `.env` is a single-file bind mount that keeps its inode across recreates — rewrite in place,
  then recreate.
- Plivo's IP whitelist and a 402 both void a board and read as agent failures: grep the runner log first.
- Four calls machine-wide; any `pytest` during a batch voids it. A second flow runs on its own stack
  (`cx2`); never share a livekit worker between flows.
- Local numbers are for you. The owner reads dev numbers.

### 3.4 The dev Hunter board (the number)
Read `../HUNTER-PROTOCOL.md` first; these are the V2.9 specifics.

- **Pre-flight the shared pod in the same command that launches**: cookie valid (`GET /api/auth/me`), no
  foreign run (`GET /api/runs?limit=12`), numbers free (`GET /api/phone-numbers/availability`), and the
  action endpoint answering 200 from the runner's side. A dead mock share fails every action mid-call and
  reads as agent failure. After any Redis/DB/container/worker change, one smoke call before the batch.
  `Sigma/hunter/run_board.py` does this — copy it.
- `maxParallel 4`, `intervalSeconds 5`. 15 starves STT (10/20 vs 17/20 on the same build), and **boards run
  at different parallelism are never comparable** — identical totals once hid two collapsed calls. A
  re-asked answered field is suspected lag until `agent commit time − Hunter caller timestamp` and the
  "slower than realtime" count say otherwise.
- **A script owns the board's rubrics** — FHCSD: `FHCSD/hunter/align_dev_board.py`; Sigma:
  `Sigma/hunter/build.py` + `create.py`. Never hand-edit a generated scenario; regenerate and diff.
  (`Sigma/hunter-sim/board.py` grades a text-lane launch; it writes no scenarios.)
- **Refresh the dates the morning of a board** with whichever script owns them. A board whose fails are
  all the one date criterion, everything else MET, after a day roll is **void, not red** — stop,
  regenerate, re-run; never diff it against a previous board.
- **Do not assert what the agent cannot know**: a rubric naming the slot the API will return fails a
  correct agent. Judge relations — on/after the preferred date, at most three offered, the booked slot
  equals the chosen one, nothing invented — against the call's own tool results.
- **Expected variables** are authored in the **stored** form read from one real run's callback (ISO dates,
  choice ids, yes/no) — never prose or names — and the flow must not post a discussed variable as `""`:
  the judge grades every posted key, so omit it or give it a sentinel.
- **Grade the stored variables beside the judge**, every board. The judge grades speech, not storage; a
  board classified on speech alone hid a parent that ran the whole interview and stored nothing.
- **Every pass needs a tool-call audit**: a call judged 1.0 with zero `TOOL_CALL_EVENT`s is a false pass.
- **Reading a fail** — three sources, in order: `HangupSource`/`HangupCause` (the persona quits around the
  5-minute mark, a Hunter-side idle default: 18 of 25 board-5 fails were that, and `USER_BUSY` at 0 s on
  two pools is a Hunter outage, not our timeout); the judge's own words (`GET /api/calls/<id>` →
  `eval_breakdown` criteria) for the failing criterion; then the runtime log line beside it. Pair calls by
  first utterance and filter by call id — persona names have falsely accused scenarios.
  A "repeat" preceded by `User idle, sending reminder` is the persona not answering, not a code class;
  an idle hang-up right after an acknowledge-only agent turn is the persona waiting for a question (p90
  reply 10.5 s), which is a test-rig fit, not a production timeout to change.
  A walk that cannot finish inside the persona's window fails regardless of the runtime — cut per-turn
  cost or shorten the scenario.
- **Board numbers come from ONE full uncontaminated run** — no composites, no mid-run rubric edits.
- **Do not poll logs while the owner is on a call**; ask what he heard.
- A dev board is a fix-test only after the deployed tree equals the tested head (§1, deploy row).

### 3.5 Prod verification (after the owner's click)
- Image tag → build → commit → `git diff` against the merged tip: nothing.
- First two hours: bucket every error signature by "before/after the rollout minute" over a 30 h window.
  A signature that also appears before the rollout is not a regression; name the new ones with counts.
- Discovery/config routes (hodor, console) need a real save from the owner to be observed in the prod
  logs; ask for one.
- Items filed "for after prod" get an owner and a section in the flow's evidence MD; when a root fix lands,
  mark them superseded there — never silently.

---

## 4. The fix loop — one issue at a time, at the root

```
reproduce → tool-call log → root cause → "why did no test catch it?" → general or flow-specific?
   → fix at the root (the shared function, not the caller the ticket names)
   → pin with a test that fails before and passes after
   → text repro ×N → A/B (5–10 per arm) → batch with the other fixes → ONE dev deploy → board
```

- **Reproduce before theorising.** The text lane reproduces routing/decline/re-ask/variable/exit defects;
  a live-only defect gets one instrumented call and its call id in the RCA.
- **Before naming the layer, read which agent held the floor** at the failure. A nudge on the parent's
  generation path cannot fire while a collector holds the floor.
- **Prove the call id belongs to the scenario** before briefing anything — a Hunter transcript gap once
  became a "dead air" defect that never existed.
- **Verify the premise of any report** — a reviewer, a bot, a peer, the judge — before fixing it: one PR
  fixed a case that cannot occur; an audit corrected a tree-identity claim; a bot caught a regression that
  a "silenced" test had hidden.
- **General over flow-specific**: ask "would another flow hit this?" If yes the fix is in `src/`, not in
  the prompt. A rule that activates on field wording is still a switch — make it an explicit property. A
  fit for the test rig (an idle timeout for Hunter's persona) belongs in neither code nor flow, and is
  labelled as such.
- **Two lanes share one fix set on dev.** Check dev and the other flow's audit file before branching;
  parallel branches conflicted in five files once.
- **Sim and live disagree → suspect a parity shim** before suspecting the model.
- **Never the patch-and-re-review loop.** When a reviewer rejects the third variant of the same guard,
  stop and redesign at the configuration level: name the owner of the state, its single writer, and the
  rule that decides — then implement that. The substring/exact-value action-attribution guard was rejected
  three times before the `on_reject` rule replaced it in one pass.
- **"Fixed" means ×3 + judge PASS + transcript read**, plus the pinned test. A fixed scenario failing again
  is not a flake until the flake is proven from the log.
- **Every error handed to the model terminates**: bounded repair, retry cap, safe end state. Session
  options are raised once per call and never lowered in `on_exit` (a lowered cap truncated 10 of 26 tool
  steps at one handoff).
- **Sweep the lesson sideways**: when one flow finds a new prompt or tool surface (an example value spoken,
  an exemption suppressing routing), every other V2.9 flow greps its own node config for the same shape
  the same day.
- Write the RCA into `<Flow>/evidence/` with the call ids, the tool-call excerpt (values redacted), the
  root cause, the test, and the falsification query you ran against your own claim.

---

## 5. The ship path — branches, PRs, reviews, deploys

- **Cut from `main`, never `dev`** — dev is integration only; a dev-cut branch entangles others' commits
  and a merged old branch once reverted main. But first, `git diff origin/main origin/dev -- <file>` for
  every file you will touch: a main-cut edit to a file dev has diverged **reverts dev's fix at merge**. If
  it has diverged, carry dev's hunk, or cut from dev deliberately and say so in the PR body.
- **Dev proof before any main PR**: the dev copy merged, deployed, called; the run ids in the PR body.
- **One PR per change**; hand over the link. The owner is the sole reviewer and the only one who clicks
  merge and deploy. "We'll do these" is a plan, not a go-ahead. **Never trigger a build or a deploy.**
- **Pre-push gate**: lint, whole-branch sweep, scoped review — no push until all three pass. Never
  `--no-verify`. No real-call data in **any** commit: check `git log --stat origin/main..HEAD` per commit,
  because a tip-only deletion leaves it in the ancestry.
- **PR body**: the LOC split table from `git diff --numstat` (runtime / tests / docs / CI), the dev run
  ids, the pinned tests, the design reasoning (code comments stay one-liners).
- **Miller CX** (`miller-cx[bot]`): comment `@miller-cx review` **≥75 s after the last push** — a push
  after the request aborts the review ("Automatic retries are stopped") — and the verdict is the
  `code-review/codex` status. Every finding is a lead: reproduce it, then attack its proposed remedy
  before folding it. A red CI stage is not yours until you have compared it with other PRs in the repo.
- **Composing a prod branch when dev carries other people's work**: decide per file by authorship
  (`git log --format=%an origin/main..<dev-tip> -- <file>`) — ours-only → dev's version; shared → main's
  version plus our hunks. Missing dependencies surface as test failures, not conflicts. **Never pipe a
  mutating command through `head`**: SIGPIPE rolled an apply back while the flushed lines printed "Applied
  cleanly".
- **After any merge or apply**: grep the tree for duplicated `def`s of every touched function (a
  conflict-free auto-merge once duplicated one and the second silently won), run the tests **on the merged
  tree**, and run main's own unmodified test files against a release branch. Never answer "is dev at parity
  with main" from `git cherry` — 51 files were resolved to dev's side while ancestry said nothing was
  missing.
- **After merge**: `git diff <merged-tip> <tested-head>` prints nothing; give the deploy links; verify from
  the runtime (§3.5). Hodor and console changes deploy on their own pipelines — list them.
- **Infra, not code**: a red build with `stages: []` never ran — retry it. A "Read timeout" in the dev
  scale-up Lambda is a zombie ASG instance — terminate it, never raise the timeout (five builds once went
  1 → 20 instances).
- **State you report is state you just queried**: PR bases, branch heads, deploy status, run ids.

---

## 6. Evidence discipline — what counts as proof

- **"Textually true, semantically nothing"** is the failure mode to fear: a substring match, a copied
  timestamp, `| head` on a `git apply`, a green suite minus its tests, "same branch" for "same tree".
  Every actionable claim gets one query designed to kill it before it ships.
- **The Bash tool is zsh**: an unquoted `$LIST` is one word, so `for id in $IDS`, `ruff check $FILES` and
  `git diff -- $FILES` silently match nothing and read as green. Write loops in Python; before trusting
  "identical" or "all checks passed", prove the check printed a non-empty file list.
- **Numbers**: one full run, one tree, one config; the manifest names all three.
- **Anchor every report with one worked call end to end**: call id, the tool calls in order, what the
  caller said (paraphrased, never with personal data), what the model returned, where it went wrong.
- **Report our deltas**: a main-like environment is the target; differences by design are named once and
  filtered.
- **Ask the owner in plain English**, numbered, one decision per number; never issue codes. After a major
  change, quiz him — a skimmed summary does not update him.
- **Working docs live beside the flow** and a new flow creates them on day 1: `Decisions.md` (dated
  rulings), `evidence/<topic>-<date>.md` (RCAs, audits, board reads), the audit file the auditor reads,
  and a release log (FHCSD calls it `DEV-RELEASE.md`, TeleCRM `RELEASE-TO-MAIN.md`). Append-only files get
  a dated correction, never a rewrite.
- **Hand-over is a standalone file**: rules, state with shas and PR numbers, the pending list in order,
  traps, recipes, and why each rejected approach was rejected — plus a pointer to the transcript.

---

## 7. Checklists

**New flow onboarding (day 1)**
- [ ] Flow uuid, live node uuid (from `phlo_connections` at the active version), version; `:CONFIG` read and saved with its sha
- [ ] Timezone = the customer's; one clock only
- [ ] Event Callbacks on (and the flow bundle refreshed or re-published); webhooks neutralised on the dev copy; sandbox vs live API confirmed
- [ ] Every Input: type matches configuration, one value per question, Task text names = Inputs tab names, `known_value` top-level, `template_vars` rewritten, retries decided, no example values
- [ ] Every action: `execution_policy` authored, `response_format` where chained, retry 3 / timeout 8000 where flaky, never `retry_limit: 0`, no double-encoded JSON fields
- [ ] Hunter suite created; rubrics generated by a script; `correlation_status` green on a smoke call
- [ ] A text lane copied from FHCSD or Sigma with its constants rewritten; twins built from the same sha; `preflight.py` manifest saved; negative controls pass
- [ ] `<Flow>/Decisions.md` opened with all of the above identities

**Before a dev board**
- [ ] Deployed tree = tested tree (image tag → build → `Checking out Revision` → `git diff` empty)
- [ ] Rubric dates refreshed by the owning script; `dates_agree` true; rubrics pulled live and diffed
- [ ] Pod pre-flight inside the launch command: cookie, no foreign run, numbers free, action endpoint 200; `maxParallel 4`
- [ ] Text lane green on the same tree; agent lines read for tags and `snake_case`
- [ ] Nobody placing manual calls; no `pytest` running on the machine

**Before a main PR**
- [ ] Branch cut from main, with `git diff main dev` checked for every file touched; one change
- [ ] Dev proof run ids in the body; lint, sweep, scoped review passed; LOC table from `--numstat`
- [ ] Every fix pinned by a test; refute-tracer done on the load-bearing line; merged-tree tests run
- [ ] No real-call data in any commit (`git log --stat`), no secrets, no `--no-verify`
- [ ] `@miller-cx review` ≥75 s after the last push; findings reproduced, remedies falsified

**After a prod deploy**
- [ ] Image tag → commit → `git diff` empty
- [ ] Error signatures bucketed before/after the rollout; new ones named with counts
- [ ] Hodor/console counterparts deployed and observed
- [ ] "After prod" items filed with owners; superseded items marked in place

---

## 8. Where things live

| | |
|---|---|
| This folder | `agents.md` (session rules), `setup.md` (machine, repos, local stack), `SKILL.md` (tools), `flow-paste-builder.md` (whole-flow paste), `audit_flow_row.py`, `check_codebase_map.py` |
| Voice board rules | `../HUNTER-PROTOCOL.md` |
| Pipeline and systems map | `../Orchestration/DEV-TO-PROD-PIPELINE.md`, `../Orchestration/LOCAL-STACK-AND-TEAM-TOOLING.md` |
| Text lane (FHCSD) | `../v29-revamp/stress-evals/sim-fh/` — `dump_dev_flow.sh`, `build_live_twins.py`, `preflight.py`, `run_live.py`, `judge.py`, `test_gate_negative.py`, `ab_compare.py`, `board_compare.py`, `run_pack.py`, `tally_spend.py` |
| Text lane (Sigma) | `../Sigma/hunter-sim/` — `convert.py`, `run_all.py`, `judge.py`, `board.py`, `test_gate_negative.py` |
| Board scripts | `../FHCSD/hunter/` (`align_dev_board.py`, `refresh_dates.py`, `add_provenance.py`, `build_suite.py`); `../Sigma/hunter/` (`build.py`, `create.py`, `run_board.py`, `preflight.py`, `grade_variables.py`) |
| Worked evidence | `../FHCSD/evidence/TEXT-LANE-PIPELINE-2026-09-20.md` (the lane, its audit, the fixes, the after-prod list), `../FHCSD/evidence/PR-*-AUDIT-*.md`, `../FHCSD/evidence/hunter-*-rootcauses.md`, `../Sigma/` audits |
| Repo | `contacto-io/agent-runner`; canonical clone `../repos/agent-runner`; one worktree per branch |
| Logs | `vlogs` (preprod default, `--env prod`); clusters `dev-contacto-agent-runner`, `prod-contacto-agent-runner`, `dev-contacto-phlo`, `prod-contacto-global-hodor` |
| Datastores | `bash ~/.claude/skills/cx-db-tunnel/scripts/tunnel.sh <core\|phlo\|crm\|redis>`; dev migrations hand-applied on `contacto_dev` (cluster core-16x; the skill's Postgres hosts are stale) |
| Session memory | `~/.claude/projects/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/memory/` — one fact per file, index in `MEMORY.md`; the incident behind most lines above is there |
