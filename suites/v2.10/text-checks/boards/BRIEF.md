# Briefing for every agent on the v2.10 voice failures of 11 October 2026

Read this whole file before anything else. It is the shared context; your own task comes in your prompt.

## Hard rules (a live voice test is running on this laptop)

- READ ONLY. Do not edit, create or delete anything except files inside your own scratch folder (your prompt names it).
- Do NOT run pytest or any test, do NOT run docker, do NOT call any network service (no Jev, no model, no Hunter), do NOT start
  long or CPU-heavy commands. `grep`, `sed -n`, `cat`, `wc`, `python3` one-liners over the evidence files, and read-only git
  (`git -C <repo> show|log|diff|blame`) are fine.
- Do not change git state. Do not switch, reset, stash or commit anywhere.
- Never print or look for keys, tokens, cookies or credentials. Do not open `.env` files or anything named `.hunter-cookie`.
- Your final answer is the structured result. Be exact: quote log lines with their clock time, cite code as `path:line`.
- Do not blame the model or the classifier for a failure ("the model is weak" is never a root cause). Find what in OUR code, OUR
  wording or OUR test suite makes the right behaviour unlikely.

## Where things are

- Engine source (clean, commit `917ceca79`, branch `mk/v210-lang`), read only:
  `/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.10/agent-runner-lang`
  The commit before tonight's eight fixes is `24755e55a`. `git -C <that path> log --oneline 24755e55a..917ceca79` lists them.
- The test flow ("the Stress Test flow"): `/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.10/logic-flow/`
  `spec.py` (steps, fields, exits, instructions), `callers.py` (30 callers: what each says and what the judge checks), `README.md`.
- Evidence of tonight's board (30 voice calls on `917ceca79`), one folder per call:
  `/private/tmp/claude-503/-Users-mohammad-kadiri-Documents-Plivo---Projects-Agent-Runner/81912535-e119-4fb8-bba6-1839fa73c266/scratchpad/rca/stress/logic-flow-NN/`
  - `timeline.txt`: OUR log and HUNTER's transcript merged on one UTC clock.
  - `judge.txt`: the judge's verdict per criterion, the caller's persona prompt, the judge's prompt.
- `.../scratchpad/rca/asks-stress.txt`: every question of the board that took three or more agent questions, with the lines.
- Result of the board: 26 of 30 pass. Failed: 02 and 26 (judge only), 28 and 30 (judge and our log check).

## How to read a timeline

```
HH:MM:SS.ss AGENT    what our agent said (our own text)
HH:MM:SS.ss CALLER (as our speech-to-text heard it)   what we heard the caller say
HH:MM:SS.ss HUNTER: its caller said        what the test caller really said (Hunter's text)
HH:MM:SS.ss HUNTER: it heard our agent say what Hunter's speech-to-text made of our agent's voice
HH:MM:SS.ss NODE     A -> B (way out: X)   the flow moved to another step
HH:MM:SS.ss saved    {...}                 a value was saved
HH:MM:SS.ss     engine: ...                a line of the engine's log
```

All three sources are on one UTC clock (IST is 5 h 30 min later). Hunter's line for a sentence carries the time it STARTED and ours the time it
was finished, so a Hunter line usually sits a few seconds before our line for the same words.
The caller is an LLM that only knows what Hunter's speech-to-text heard. When Hunter mishears our agent, the caller answers the misheard text.

Engine lines that matter:

- `system_one: step=<A or B ...> kind=<kind> allowed=<families or None> jev={...}`: one request led by Jev.
  `step=` is what stays open for the model. `kind` is the kind of question on the floor (`collect:text`, `readback`, `open`,
  `screen_identity`, ...). `jev={...}` holds Jev's answers: `step_intent` (the reading), `step` (the step answer),
  `repair_target`, `sensitive_question`, `language`.
- `system_one: dropped [(tool, args)], outside {...}`: the model called a tool that was not open and the engine threw the call away.
- `Tool call tool=<name> arguments=... output=... is_error=...`: a tool ran (logged when it finished). For `collect_*` tools the
  line appears when that question FINISHED, with its result text.
- `collect: <field> (<type>) ...`: the question router's own lines, e.g. `declined by the caller`, `required: the first refusal is not accepted`,
  `required: refused twice, the step ends here`, `drops the carried answer`, `takes the caller's later answer`.
- `exit_gate: ...`: main's rule that refuses a way out once while a required value has no record.
- `ToolError while executing tool: ...`: a tool refused and told the model why.

## The system in one page

This is a phone agent engine (LiveKit agents, Python). "main" is the production engine. "v2.10" is a local prototype: a flow
stamped `agent_engine_version = "v2.10"` runs its AI step with main's question collectors (`src/units/collect_input.py`,
`src/units/tasks/collect_*.py`) plus **System One**: a classifier service called **Jev** leads each request of the step's model.

Players:
- **The model** (google/gemma-4-31b-it for the step and the collectors, on voice and in the text runs; gpt-4.1 for the screening step): writes the words and calls tools.
- **A collector**: main's code for one question (a name, an email, a date, a choice, ...). The step's model opens it with
  `collect_<type>(name=..., instructions=..., known_value=...)`. Inside, a second model conversation runs with that collector's own
  tools: `update_<type>` (save the value), `confirm_<type>` (the caller confirmed a read-back), `decline_<type>_capture(reason)`,
  plus three shared ones built in `collect_input.py`: `hand_back(reason, value?)` (the caller raised something for the step itself),
  `answer_side_question(question, value?)` (a question or request this question cannot handle), `change_earlier_value(name, new_value?)`.
- **The router** (`collect_input.py`): runs the collectors, counts refusals of required questions (`_REQUIRED_DECLINE_LIMIT = 2`),
  keeps "carried" answers (`_Carry`, `_carried_answers`), and guards ways out (`exit_blocked_on_required`).
- **System One** (`src/system_one.py`, `src/system_one_intents.py`): wraps the model. On each fresh caller turn it asks Jev several
  multiple-choice questions and gets one probability per option:
  - `step_intent`, "the reading": what kind of reply was that? Question and options come from an APPROVED library,
    `src/prompts/jev/steps.json`, one entry per kind of open question, composed by `step_question()`; the kind and template values
    come from `current_step()`. It is flow-blind: it sees the agent's last line and the caller's words. Sure at 0.45 with a 0.1 lead.
  - `step`, "the step answer": what happens next? Options are the tools offered right now, each described by its own tool
    description, plus "only speak". Instructions: `src/prompts/system_one.json` key `step`. It is flow-aware (it reads the flow policy).
  - `repair_target`: does this turn correct an earlier value, and which (`src/prompts/jev/core-decide.json`). Sure at 0.35 with 0.05 lead;
    a sure "none" hides `change_earlier_value`.
  - `sensitive_question`, `language`, `screen_review`: other approved questions.
- Decision path in `SystemOneLLM._led_by_jev`:
  1. `allowed(...)` turns the reading into permitted families (`VALUE`, `NEXT`, `explain`, `ANSWER`, `EXIT`, `decline:refused`,
     `decline:inability`, `clarify`, `repeat`, `WAIT`, ...) using each intent's `permits` in the library.
  2. `_permitted(...)` removes every tool the reading does not allow (`_may`, `NEEDS`, `tool_ops`).
  3. `_due(shares["step"], steps)`: one sure step (>= 0.5 with a 0.15 lead), else the likely ones (>= 0.15), else every step but an action.
  4. `_relay` drops any tool call outside what stayed open (`system_one: dropped ...`); `insist` re-asks the model with tool_choice
     "required" only after a dropped call.
  5. A turn Jev's reading is unsure of, or a step held back two caller turns in a row (`STALL_LIMIT = 2`), is "recovering": the reading
     no longer gates and the step answer alone leads.
- Constants: `STEP_FLOOR, SURE_FLOOR, MARGIN = 0.5, 0.6, 0.15`; read-back confirm/correct needs 0.6 with a 0.15 lead.

Tonight's eight commits on top of `24755e55a` (each has a letter):
B `ae7adbc99` language mark stripped in any case; D `a12784612` screening reply ends on the question when the reading is unsure;
E `34b19dfe6` a screening exception needs 0.15 on an unsure turn; A `afc1c3973` a value step the step answer is sure of stays open
(not forced) on a decline or yes reading; F `a3d689051` a change the step answer finds likely (>= 0.15) is not hidden and passes beside
Jev's pick; C `63f3e2dcf` one sentence in the library for "the right person"; H `5ec078b0f` bare option names spoken with spaces;
M `917ceca79` a list produced during the call is produced again after a correction.

## What the owner wants from a fix (binding)

- Smallest change at the root cause. No new helpers, no new abstractions, no config flags, no bloat. A comment is one line and only for a why.
- "Reuse or rewire, never rebuild": main's collectors and router already have rules (retry budgets, the exit gate). Prefer letting
  main's own rule work under System One over adding a second rule beside it.
- Where JEV'S UNDERSTANDING is the cause, the owner prefers fixing the WORDING Jev reads, with contrastive examples inside the option
  text (one example that is this, one near miss that is not), over an engine rule. Approved library wording changes need the owner's yes,
  so propose the exact old and new text and keep it tiny. Wording is read on every flow and in Hindi and mixed calls: no flow words.
- Where OUR PLUMBING is the cause (a call thrown away, a counter never reached), fix the code.
- "Structural rules over inferred signals": a rule may key on what happened (a tool result, a count, a state the router holds),
  never on guessed meaning of words.
- "General layer over flow fixes": ask whether another flow would hit this. Never fix it for one flow or one caller.
- The owner's rule on asking: a REQUIRED question may be asked twice at most; an OPTIONAL one is skipped when the caller does not want
  to give it. He has also ruled: after a real read-back ("is that right?"), the caller saying the same value again IS a yes.
- A flow with the switch off must behave exactly as main. Changes to main's shared code need a strong reason and are called out.
- Text in reports for the owner: very simple English, a short call example first, no jargon.
