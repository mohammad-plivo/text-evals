---
name: hunter
description: Use when working with Hunter (hunter.contactodev.com), the QA team's voice-agent test harness — author test scenarios for a CX flow, trigger a run, fetch results, pull call transcripts and judge verdicts, correlate calls to CX flow runs, retrigger a batch, poll a run to completion, or compare two runs. Triggers on Hunter dashboard URLs, "hunter run", "QA batch", "create tests/scenarios for this flow", "retrigger the batch", "get the transcripts from that run".
---

# Hunter — QA voice-agent test harness (API recipes)

Hunter dials the agent under test over PSTN (or has the agent dial it), transcribes
both sides, scores the call with an LLM judge against per-scenario rubrics, and
(optionally) applies a human review override. QA runs
screening/e2e batches on it. Full CRUD is available over the API — the dashboard
is just a client.

## Endpoints and auth

- Base: `https://hunter.contactodev.com` — the root URL serves the API itself
  (`{"status":"ok","service":"Test Voice Agent"}`); the dashboard lives under
  `/dashboard/...`. `GET /openapi.json` is public — consult it when an
  endpoint's shape is in doubt.
- Auth: the user's `hunter_session` JWT cookie (minted only by Google OAuth:
  `/api/auth/google/login` → callback sets it; expires ~24h). It is **HttpOnly**
  (verified) — `document.cookie` cannot read it, so there is no self-serve
  extraction; get it from the user (devtools → Application → Cookies, or
  copy-as-curl on any dashboard request). Direct API calls without it return
  401. Cache it in the scratchpad, never in a repo:

```bash
COOKIE="hunter_session=<jwt>"
curl -s -b "$COOKIE" https://hunter.contactodev.com/api/runs/<run_id>
```

Anything you trigger is attributed to the cookie owner's email. Verify the
cookie before a batch: `GET /api/auth/me` → `{"email": ...}` (401 = expired).

## Object model

`scenario` (saved test case: `{name, description, category, payload}` where
`payload` is a `MakeCallRequest`) → `run` (batch over scenario ids) → `call`
(one dial: transcript, judge verdict, STT eval, CX correlation). Categories are
free strings and act as folders in the UI.

## Endpoint map (all verified live)

| Endpoint | Notes |
|---|---|
| `GET /api/runs?limit=&offset=` | run list, newest first |
| `GET /api/runs/{id}` | run + `items[]` (`scenario_name`, `call_id`, `result`, `failure_tags`, `error_message`, `score`, `turn_count`) |
| `POST /api/runs` | `{"name", "scenarioIds": ["<id>", ...], "maxParallel": 5, "intervalSeconds": 0}` → `{runId, status}`. **Repeat a test by duplicating its id** in `scenarioIds` (that's what the UI's "Repeat Each Test" does) |
| `POST /api/runs/{id}/retrigger` · `/stop` · `PATCH` (rename) | retrigger → new run "Re: <name>" |
| `GET /api/scenarios` | list (id, name, description, tier, category only) |
| `GET /api/scenarios/{id}` | full object incl. `payload` |
| `POST /api/scenarios` / `PUT /api/scenarios/{id}` | create/update with the FULL `{name, description, category, payload}` object; create returns `{id}` |
| `POST /api/scenarios/duplicate-category` | `{sourceCategory, newCategory, nameSuffix}` |
| `GET /api/calls/{id}` | everything: `transcript`, `comments` (judge), `eval_breakdown.criteria[]` (`[MET]/[NOT MET]` + accuracy each), `cx_transcript_text`, `cx_stt_evaluation`, `cx_flow_run_uuid`, `latency_metrics`, `turns[]` |
| `GET /api/calls?limit=&search=&result=` | call history |
| `POST /api/calls/{id}/rerun` · `/disconnect` · `PATCH /override` · `PATCH /review` | override = human verdict `{result, addTags, comments}` |
| `GET /api/calls/{id}/recording` | wav |
| `POST /api/calls/trigger` | `{"payload": <MakeCallRequest>}` — one ad-hoc call without creating a run (the UI's single-scenario "Run" button). Prefer a 1-scenario run for smokes: same cost, result stays queryable as a run |
| `GET /api/phone-numbers` · `/availability` | 15-number pool, engaged/free counts |
| `GET /api/background-sounds` | ambience ids for `backgroundSound` |
| `POST /api/generate-test-cases` (+ `GET .../{job}/status`) | LLM-generates scenarios from an `agentConfig` |

Dashboard pages: `/dashboard/runs/<id>`, `/dashboard/calls/<id>`.
CX run link: `https://cx.dev.contactodev.com/agent-runs/<flowId>/<cx_flow_run_uuid>`.

## Authoring scenarios (payload anatomy)

Two test types, distinguished by `payload.testType`:

**inbound-agent** (Hunter dials the agent): `phoneNumber` (agent's number),
`waitForAgentFirst: true`, `openEndedConversation: true`.

**outbound-agent** (agent dials Hunter — for outbound flows): Hunter allocates a
pool number, substitutes it into the trigger body, POSTs the flow's trigger URL,
answers the dial-back, plays the persona.

```json
{
  "testType": "outbound-agent",
  "initiationRequest": {
    "method": "POST",
    "url": "https://dev-runner-service.contactodev.com/v1/account/<AUTH_ID>/flow/<FLOW_UUID>",
    "headers": {"Content-Type": "application/json"},
    "bodyTemplate": "{\"customer_name\": \"{{customer_name}}\", \"phone\": \"{{INBOUND_NUMBER}}\"}",
    "inboundNumberPlaceholder": "{{INBOUND_NUMBER}}"
  },
  "initiationVariables": {"customer_name": "Priya Sharma"},
  "botGreetsFirst": true,
  "allowInterruptions": true,
  "conversationPrompt": "<persona> TARGET is achieved when <end condition>.",
  "evaluationPrompt": "<judge preamble> Evaluate these criteria: 1) ... 2) ...",
  "evaluationThreshold": 0.8,
  "maxTurns": 26,
  "evaluationConfig": {"autoDisconnectEnabled": true, "maxNonActualIntentRetries": 3},
  "voiceId": "21m00Tcm4TlvDq8ikWAM",
  "webhookBaseUrl": "https://<hunter-webhook-host>",
  "event": "<slug>", "testId": "voice-<slug>", "testRegion": "us-east",
  "agentConfig": { "flowId": "<uuid>", "nodes": [...], "edges": [...] }
}
```

- `conversationPrompt`: persona text; the UI convention appends
  `"TARGET is achieved when …"`. For screening-node flows, prepend an opening
  boilerplate telling the persona to confirm identity + permission quickly.
- `evaluationPrompt`: numbered criteria; the judge returns one
  `[MET]/[NOT MET] accuracy=N` line per criterion in `eval_breakdown.criteria`.
  Scope it explicitly ("evaluate ONLY the booking segment, ignore the opening
  identity exchange") or it will judge the wrong node.
- `agentConfig` = the flow's builder-export JSON (Download config, or assemble
  from DB: `{flowId, name, nodes:[{id:uuid, type, data:{config: node.config.model}}], edges: phlo_connections.connections}`).
  Hunter stores it for the STT-eval and dashboards; it is not executed.
- `webhookBaseUrl`: copy the value from any existing QA scenario.
- `answerBehavior` (outbound only): `answer` | `reject_busy` | `reject_decline`
  | `no_answer` — simulates a telephony disposition instead of conversing, to
  exercise carrier branches; no conversation happens.
- `allowInterruptions: false` = bot never barge-ins (screener/hold cases).
  `botGreetsFirst: true` = bot speaks the instant the call connects (voicemail
  greetings, "Hello?" openers).
- Voice ids: Rachel `21m00Tcm4TlvDq8ikWAM` (default), Antoni (male)
  `ErXwobaYiN019PkySvjV`, Neha (Indian F) `QTKSa2Iyv0yoxvXY2V8a`. Full list in
  the dashboard bundle. Also on `MakeCallRequest`: `language` (non-English
  personas), `backgroundSound` + `backgroundVolume` (ambience ids from
  `GET /api/background-sounds`).
- Alternative to a freeform persona: `conversationFlow` with scripted
  `steps[]` (`stepNumber`, `utterance`, `expectedAnswers[]`, `isRequired`,
  `evaluationNotes`) + `closingMessage` + `minStepsPassed` — deterministic
  turn-by-turn scripts instead of `openEndedConversation`. **Untested by us**
  (schema-verified only); QA's batches all use the persona style.
- Working reference payloads: any scenario in the `fhcsd outbound v2` or
  `Screening Node 2` categories (outbound), `smoke-test-prod` (inbound).

## Prerequisites for outbound-agent tests (check BEFORE burning calls)

1. **The flow must dial `{{Start.http.params.<phone-field>}}`** — outbound flows
   commonly hardcode `to` on the dial node. If so, the flow will ring some real
   number, not Hunter, and every test "fails" with an empty transcript. Template
   the `to` field (builder edit + publish, or DB edit — but see the phlo
   node-config Redis cache trap in memory: a DB edit is invisible to the runner
   until the `PHLO:{flow}:NODE:*:CONFIG` keys are evicted; publish does NOT
   clear them).
2. **Start node `require_http_auth` must be false**, or put the account's Basic
   auth header in `initiationRequest.headers`. Otherwise every item errors with
   `502: ... HTTP 401` at trigger time (no call is placed, nothing is wasted).
3. **Omit `expectedCallerId`** — QA's working scenarios all leave it null.
4. Smoke ONE scenario first (`POST /api/runs` with a single id) before a suite.
5. **CX correlation is an inbound webhook, not a lookup.** Transcript/STT eval/`callback_variables`/
   variable validation appear only if the FLOW's Event Callbacks (`phlo.event_callbacks`, builder flow
   settings) POST `HANGUP` → `https://hunter.contactodev.com/webhook/cx/hangup` and `RECORDING`
   (transcription on) → `…/webhook/cx/recording` with Hunter's bearer token (copy from a wired flow).
   Missing ⇒ every call stays "CX Transcript Pending" and any variable test is
   `VARIABLE-EXTRACTION-FAILED` by construction. The runner reads it from the cached
   `PHLO:<uuid>:V:<active_version>` bundle (TTL ~29 h) — patch DB **and** bundle (`SET … KEEPTTL`).
   Check one call's `correlation_status` (`bound` vs `None`) before trusting a suite.

## Failure triage (decision tree)

- Item `status: "error"` + `error_message` `502/401/...` → trigger API failed;
  no call placed. Fix flow auth/URL.
- `result: fail` with `duration_ms/turn_count/score` all null + empty
  `transcript` → call never reached Hunter's bot (flow dialed the wrong number,
  or never dialed back within ~120s). Check the CX side: the flow run's
  `initiate_call` NODE_EXECUTED log shows the actual `to` dialed
  (S3 `logs_url` on `conversation_run_summary`).
- `result: fail` with real turns → behavioral; read `eval_breakdown.criteria`
  + `transcript`, then verify the claim against the agent's own committed text
  in the CX run log before blaming the agent (judge rubrics and personas both
  err; see interpretation rules below).
- `cx_flow_run_uuid` often stays null/`cx_transcript_status: pending` for a
  while after completion — correlate via dev DB
  `conversation_run_summary` (`phlo_uuid` + `created_at` window) instead of
  waiting.

## Reading transcripts — speaker labels are inverted

In `transcript[]`/`turns[]`: **`assistant` = Hunter's persona bot (the fake
customer), `user` = the agent under test.** In `cx_transcript_text`:
`[Customer]` = Hunter's bot, `[Ai_agent]` = agent under test. Relabel before
showing a human (persona→CALLER, agent→AGENT) or every reading is backwards.

## How the tests work (interpretation rules)

- **Dial-back model**: Hunter fires the flow's API trigger, then waits ≤120s
  for the flow to CALL BACK its test number. A test with no
  `cx_flow_run_uuid` means the flow never dialed back (infra/trigger issue),
  not agent misbehavior — there is nothing behavioral to judge.
- **Read the transcript before trusting a verdict.** Judge rubrics can
  contradict the flow's actual wiring (e.g. demanding a silent hangup on a
  path the flow routes to a speaking node), the prompt spec, or the node
  type's actual contract (e.g. agent_node has NO closing-summary step —
  `confirm_announcement` is a top-of-walk confirm; a rubric demanding a final
  readback false-fails it). A fail is a claim, not a fact.
- **Personas are LLMs and go off-script.** A scripted caller may skip its key
  line — the agent then fails the rubric while behaving correctly. Check the
  caller's actual lines against the scenario intent before blaming the agent.
  When the persona must stonewall (test a no-answer path), give it ONE exact
  line to repeat and cap `maxTurns`, or the call runs to the duration limit.
- **STT garbles letter-by-letter spellouts** (emails, names spelled aloud) —
  `STT-ISSUE` tag + `cx_stt_evaluation` tell you whether the mishearing is
  Hunter-side; the agent's own committed text in the CX run log is the ground
  truth for what was actually said.
- **Human overrides**: `comments` may contain
  `[Human override by <email>: FAIL]` or reviewer notes that disagree with
  the rubric verdict ("false pass") — surface both, don't collapse them.
- Timing: log timestamps are UTC; ~19 calls at `maxParallel: 5` ≈ 6 min; a
  13-call suite at `maxParallel: 6, intervalSeconds: 5` ≈ 10 min. Always
  verify a "fix" run started AFTER the fix's ECS rollout completed before
  comparing.

## Recipes

Fetch a batch + per-call summary (flow-run correlation included):

```bash
curl -s -b "$COOKIE" "https://hunter.contactodev.com/api/runs/$RUN" -o run.json
# then per item: curl -s -b "$COOKIE" ".../api/calls/$CALL_ID" and read
# .eval_breakdown.criteria, .transcript, .comments, .cx_flow_run_uuid
```

Create scenarios in bulk: build the payloads in a python script (start from a
`GET /api/scenarios/{id}` of a working scenario in the same test type), POST
each, collect ids, then `POST /api/runs` with those ids. Clone a suite onto a
second flow by rewriting only `initiationRequest.url`, `agentConfig`, `event`,
`testId`, and any flow-shape-specific opening boilerplate in
`conversationPrompt`.

Retrigger + poll to completion (poll survives transient failures):

```bash
curl -s -b "$COOKIE" -X POST ".../api/runs/$RUN/retrigger"   # → new runId
while :; do sleep 60
  body=$(curl -s --max-time 15 -b "$COOKIE" ".../api/runs/$NEW" || true)
  st=$(printf '%s' "$body" | jq -r '.status' 2>/dev/null || echo poll-error)
  [ "$st" = completed ] && break
done
```

Compare two runs: match `items[]` by `scenario_name` (indexes are stable in
practice but names are safer), diff `result` per scenario, and label flips
IMPROVED/REGRESSED. For every regression, pull the call's transcript + judge
comments before calling it real — persona flakes and rubric mismatches are
common.

## Reporting conventions (what the user expects)

- Per-scenario table: index, scenario, old→new result, one-line reason.
- For failures: quote the transcript tail and the judge's reason, then give
  YOUR verdict (code bug / prompt issue / rubric-vs-flow mismatch / persona
  flake / infra) — grounded in the CX-side logs when it matters.
- Separate "judge failed it" from "actually broken": verify each failed
  criterion against the node type's real contract in code before reporting.
- Provide CX run links (format above) so failures can be eyeballed in the
  builder's run view.
