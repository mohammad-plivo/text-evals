# Running an agent_tasks node locally, text-only, against Azure OpenAI (branch kishan/ser-5959-agent-tasks @ 31dc694)

All paths relative to the worktree: `/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/plivo-cx-livekit-ser5959`

## 1. Exact commands

Setup once (Mac, CPU-only is fine — sim is text-only, no STT/TTS/telephony):

```bash
cd "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/repos/plivo-cx-livekit-ser5959"
uv sync            # uv.lock committed; python >=3.12,<3.14 (pyproject.toml:5)
```

Simulation CLI (entry: `src/simulation/cli/__main__.py:111-150`; docs: `docs/simulation-cli.md:19-32`, skill: `.claude/skills/simulation-cli/SKILL.md:23-28`):

```bash
# scaffold a workspace from a flow config
uv run python -m src.simulation.cli init my-tasks-flow --flow /path/to/flow.json     # __main__.py:121-123

# run (text-only conversation, live HTML report auto-opens; --no-open to suppress)
uv run python -m src.simulation.cli --env-file <dotenv> run my-tasks-flow \
    [--scenario NAME] [--mode scripted|simulated] [--repeat 5] [--node ID] [--no-open]   # __main__.py:131-137

# LLM-generate scenarios
uv run python -m src.simulation.cli --env-file <dotenv> generate my-tasks-flow --count 5  # __main__.py:125-129
```

Smoke check the plumbing works at all (non-agent_tasks example): `uv run python -m src.simulation.cli --env-file <env> run examples/simulation/movers-press1` (`docs/simulation-cli.md:34`).

**How the flow/agent config is supplied** — `flow.json` in the workspace, two accepted shapes (`src/simulation/cli/flow.py:70-114`):
- Console flow export `{"nodes": [...], "edges": [...]}`. An agent_tasks node is node `type: "agent_node"` (`flow.py:31`), with `data.config` carrying `instructions/intents/agent_tasks/actions/first_response/...` — mapped at `flow.py:175-187`; `agent_tasks` is what makes the runtime build an AgentTasksUnit (`flow.py:177-182`). Intent→node edges become fast-path plan entries (`flow.py:199-241`).
- A **bare AgentNodeConfig dict** (no `"nodes"` key; must have `"instructions"`, `flow.py:75-81`). For agent_tasks include `"agent_tasks"` and (for terminal routing) an inline `"output_state_config"` — SimSession reads it from the same dict (`src/simulation/runner.py:444`).

Flow-session mode (the FlowRootAgent loop, which is what agent_tasks needs) is switched on automatically when any node config carries `agent_tasks` or `screening_task` (`src/simulation/cli/engine.py:87-94`); the run header prints `[scripted, flow-session]` (`engine.py:295`).

**No SparkClean and no agent_tasks example/golden config exists on this branch:**
- `grep -ri sparkclean` over the whole tree: **0 hits**.
- `grep -l agent_tasks eval_tests/*/flow.json examples/simulation/*/flow.json`: **0 hits** — all 50 `eval_tests/` workspaces are `ai_agent_v2` flows (`eval_tests/README.md:1-27`), `examples/simulation/movers-press1` likewise.
- Golden harness: `tests/golden_harness/flowspec.py:56-61` passes an `agent_tasks` key through the compiler, but no committed golden flow uses it (`tests/golden_harness/flows/` has only `two_node_smoke.*`), and the comment at `flowspec.py:57-60` ("the sim runtime does not yet build an AgentTasksUnit") is **stale** — `src/simulation/runner.py:466-478` does build it on this commit.
- Config shape for authoring one: `AgentTasksConfig` at `src/models/ai_config.py:198-218` (`variables: [{name, type, instructions, params, optional, confirm_if_known, known_value}]` per `ai_config.py:168-187`, `extract_only: [{name, instructions}]` per `ai_config.py:190-195`, plus `confirm_announcement`, `max_restarts`). Intents live at NODE level, not inside agent_tasks (`ai_config.py:203-206`); a walk-end pick with 0 intents falls back to conversation_complete (`src/units/agent_tasks.py:888-891`).

Minimal working bare `flow.json` you have to author yourself (validated by `AgentNodeConfig.model_validate` at `runner.py:438`; mirrors the dispatch test fixture at `tests/test_simulation_runner.py:925-943`):

```json
{
  "instructions": "Collect the caller's booking details.",
  "agent_name": "Aria",
  "intents": [
    {"intent_name": "Details Collected", "intent_instructions": "All details were collected."},
    {"intent_name": "Caller Declined", "intent_instructions": "The caller refused."}
  ],
  "agent_tasks": {
    "variables": [
      {"name": "appointment_date", "type": "date", "instructions": "Preferred appointment date"},
      {"name": "email", "type": "email", "instructions": "Work email"}
    ],
    "extract_only": []
  },
  "output_state_config": {
    "Details Collected": {"type": "end_conversation", "end_message": "Thanks, goodbye!"},
    "Caller Declined": {"type": "end_conversation", "end_message": "No problem, goodbye!"}
  }
}
```

Then a scenario in `my-tasks-flow/scenarios/*.yaml` (scripted `turns:` or `simulated_user:`; schema at `docs/simulation-cli.md:66-133`).

## 2. Required env vars and where they're read

- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` — pydantic `AppSettings` fields (no env_prefix, so field name = env var) at `src/config/settings.py:71-72`; enforced in `_build_llm` (`src/agent_factory.py:96-99`). Also read directly by the CLI's user-simulator/scenario-generator client (`src/simulation/cli/azure_chat.py:22-25`).
- `AZURE_OPENAI_SCRIBE_DEPLOYMENT` — `settings.py:80`, used by `build_scribe_llm` (`src/scribe.py:81-98`); built unconditionally at sim start (`runner.py:476/488/498`). For agent_tasks the Scribe lane only fires when `extract_only` vars exist (`src/units/agent_tasks.py:743`), but docs list it as required (`docs/simulation-cli.md:15`).
- `AZURE_OPENAI_API_VERSION` — optional, defaults `"2024-12-01-preview"` (`settings.py:73`, `azure_chat.py:29`).
- Optional failover pair: `AZURE_OPENAI_ENDPOINT_FAILOVER` / `AZURE_OPENAI_API_KEY_FAILOVER` (`settings.py:76-77`).
- **Deployment names required on the Azure resource**: `gpt-4.1` — `_build_llm` hardcodes `cfg.model = "gpt-4.1"` whenever provider is `"openai"` (`src/agent_factory.py:92-94`), and `ModelConfig` defaults to `model="gpt-4.1", provider="openai"` (`src/models/ai_config.py:60-62`). The AgentTasksUnit walk-end forced-enum intent pick uses that same `self.llm` (`src/units/agent_tasks.py:877-881`). The CLI's caller-LLM/generator default is also `gpt-4.1` (`azure_chat.py:14`), overridable via `simulated_user.model` (`docs/simulation-cli.md:107`) or `generate --model`. Plus whatever `AZURE_OPENAI_SCRIBE_DEPLOYMENT` names.
- `--env-file <dotenv>` loads with `os.environ.setdefault` (real env wins) at `__main__.py:26-37`, applied in `main()` **before** any `src.*` import (`__main__.py:140-141`; engine imports are deferred inside `_run` at `__main__.py:68-73`) — this matters because `app_settings = AppSettings()` is instantiated at import time (`settings.py:203`). Local convention: `cx-dev-dockerized/services/livekit/config/.env` (`docs/simulation-cli.md:17`, `SKILL.md:20-21`).
- Nothing else needed: Redis/QES/Postgres/console are short-circuited by the simulation context (`docs/simulation-cli.md:9-11`); a `Background continue_ai failed ... redis:6379` ERROR after handoffs is documented harmless noise (`docs/simulation-cli.md:181-184`).

## 3. Dependencies / setup

- `pyproject.toml:5` — `requires-python = ">=3.12,<3.14"`. `uv.lock` committed; use `uv sync` / `uv run`.
- Key pins: `livekit-agents[silero,turn-detector]==1.6.5` (exact pin, rationale comment `pyproject.toml:9-13`), `livekit-plugins-openai==1.6.5`, `livekit-plugins-deepgram/elevenlabs==1.6.5`, `agent-transport[livekit]`, `openai` (transitively via plugin; `azure_chat.py` imports `openai.AsyncAzureOpenAI`), `jinja2`, `pydantic-settings`, `pyyaml`, `dateparser`. Dev group: `pytest`, `pytest-asyncio`, `debugpy` (`pyproject.toml:45-51`).
- No GPU, no telephony, no docker required for the sim path; STT/TTS plugins are never constructed in sim (see §4).
- Offline test commands: `uv run pytest tests/units/test_agent_tasks.py tests/test_simulation_runner.py` (fake LLMs, no network — `tests/units/test_agent_tasks.py:1-8`).

## 4. Does the sim exercise the SAME AgentTasksUnit as production?

Yes — same class, same LLM builders, same downstream flow loop; not a shortcut:

- `SimSession.start()` at `src/simulation/runner.py:466-478`: when `flow_session` and `agent_config.agent_tasks is not None`, it constructs `src.units.agent_tasks.AgentTasksUnit` with `_build_llm(...)` + `build_scribe_llm()` — the identical builders prod's `build_first_unit` uses (`src/units/factory.py:31-56`). The comment at `runner.py:467` explicitly states "Same decision point as prod's build_first_unit". Dispatch parity is unit-tested at `tests/test_simulation_runner.py:899-943`.
- The unit is wrapped in the same `FlowRootAgent(first_unit=...)` as production (`runner.py:511-514` vs prod `src/agent.py:228-232`), and mid-flow node transitions go through the same `build_next_unit` factory (`src/units/root.py:23,63,122` → `src/units/factory.py:58-77`). Cross-node per-turn overrides are rejected in flow-session mode because "the flow loop owns transitions" (`runner.py:613-618`).
- Deliberate differences from a real call: no `stt=`/`tts=` plugins passed (text-only — prod passes `_build_stt`/`_build_tts`, `factory.py:52-54`); `preemptive_generation=False` and no idle timeout (`runner.py:515-519`); `on_enter` greeting suppressed with an empty elicitation turn folded in by the CLI (`engine.py:162-176`); Redis/QES/DB replaced by the sim context (`runner.py:427-435`). Main-model gpt-4.1 hardcoding is shared with prod (`agent_factory.py:92-94`), so it is not a sim divergence.

## 5. Latency / A/B scripts on this branch

- **No TTFT/latency measurement or AB-latency scripts exist.** grep for `ttft|p50|p90|percentile|benchmark` hits only runtime metrics/log modules (`src/metrics/prometheus.py`, `src/handlers/event_handlers.py`), no harness/scripts. `eval.md` does not exist anywhere on the branch (`find -iname 'eval*.md'` → nothing). The p50/p90 numbers quoted in the task were not produced by anything in this repo.
- **Golden-transcript A/B parity harness** (behavior, not latency): `tests/golden_harness/` — `record` / `sanity` / `replay --out` / `diff` commands at `tests/golden_harness/README.md:24-38`, run as `uv run python -m tests.golden_harness ...`; pinned-LLM replay is offline/CI-safe. It carries the `agent_tasks` key through its compiler (`flowspec.py:56-61`) but has **no committed agent_tasks case**, and its stale note claims the sim can't build an AgentTasksUnit (contradicted by `runner.py:466`).
- **DEBUG_MODE latency tracing** exists but only for the production audio entrypoint: `src/livekit_overrides.py:1-45` (monkey-patches LiveKit SDK stages, gated on `app_settings.debug_mode` / `DEBUG_MODE` env, `settings.py:141`), imported solely by `src/agent.py:18` — it is NOT active under the simulation CLI.
- Sim runs do emit per-run artifacts usable for coarse timing/AB by hand: `reports/<stamp>.json` + `<stamp>.jsonl` + live `<stamp>.html` per workspace (`docs/simulation-cli.md:151-158`, `src/simulation/cli/report.py`), and `--repeat N` for rate-based comparison (`docs/simulation-cli.md:146-148`).