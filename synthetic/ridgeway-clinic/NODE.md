# sim-prepared: the campaign node

One `ai_agent_v29` node — **Clinic Reschedule Desk** — rewritten inside a copy of the shipped pack
(`examples/simulation/v29-agent-node/flow.json`). Every other node, id and edge handle is the pack's,
so the walk still routes: the five intent ids are kept, `Transfer To Coordinator` leaves through the
`Log Lead Transfer` http hop into the call forward, and `Reschedule Booked` leaves through the
`Update Lead Record` http hop into an end node. Task: a patient moving an appointment they already
have; warm, brief, one question at a time, and each Input's own collector asks its question.

Ten Inputs, each with a saved collection configuration (the configured path, which is what the
product ships), in walk order:

| # | Input | collect type | prepared display? |
|---|-------|--------------|-------------------|
| 1 | `patient_full_name` | name | **no — identity type** |
| 2 | `date_of_birth` | dob | yes |
| 3 | `new_appointment_date` | date | yes |
| 4 | `preferred_time_of_day` | choice (4 labels) | yes |
| 5 | `journey_time_minutes` | number | yes |
| 6 | `interpreter_needed` | boolean | no — acknowledgement shape, no value spoken |
| 7 | `access_notes` | text | yes |
| 8 | `outstanding_fee` | currency | yes |
| 9 | `mobile_number` | phone | **no — identity type** |
| 10 | `confirmation_email` | email | **no — identity type** |

Six of the ten can carry a prepared display; one (boolean) is the acknowledgement arm's shape; three
are the identity types the arm never speaks.

## Why, in the code's own words

A field gets a prepared display only if BOTH tables admit it. `src/units/collect_input.py:42-50`:

```python
# below). Absent on purpose: name, phone, email, dtmf -- the values a wrong hearing costs most.
# dob/date/text/address joined the stated shapes on MK's call (D-089); the API verifies a dob.
_STATE = "state"  # the agent states the value once, inside its next step, and asks nothing
_ACK = "acknowledge"  # the agent acknowledges the answer; the value itself is never repeated
_SHAPE = {
    "choice": _STATE, "currency": _STATE, "number": _STATE,
    "dob": _STATE, "date": _STATE, "text": _STATE, "address": _STATE,
    "boolean": _ACK,
}
```

and `src/utils/prepared_display.py:74-81`:

```python
_DISPLAY: dict[str, Callable[[Any], str]] = {
    "dob": _dob, "date": _date, "number": _number, "currency": _currency, "text": _text,
    "choice": _choice,
}

#: The shapes this arm can speak. Address is deferred (spoken part order); name, phone, email and
#: DTMF are excluded by §4/§4.1 and are not reopened here.
RENDERABLE_TYPES = frozenset(_DISPLAY)
```

`prepared_state.state_eligibility` (`src/utils/prepared_state.py:282-324`) is the gate that reads
both, and names the failure per field:

```python
    if _SHAPE.get(task_type) != _STATE:
        return "shape_not_state"
    if task_type not in RENDERABLE_TYPES:
        return "type_excluded"
```

So, per Input in this node:

- **choice, currency, number, dob, date, text** — `_STATE` in `_SHAPE` *and* in `RENDERABLE_TYPES`:
  a display exists, rendered by the collector's own read-back helper (`_dob_readback`,
  `_format_date_time`, `_number_readback`, `_currency_readback`, `CollectTextResult.value`,
  `CollectChoice._readback_value`), never by this seam inventing a string.
- **boolean** — `_SHAPE["boolean"] is _ACK`, so `shape_not_state`. It is not an identity type; it is
  the arm that "acknowledges the answer; the value itself is never repeated". It is what ARM A
  (`prepared_speech.ack_eligibility`) is for, not the state frame.
- **name, phone, email** — the identity types. They are absent from `_SHAPE` (the collector's own
  read-back stays on) and absent from `_DISPLAY`, "excluded by §4/§4.1 and are not reopened here".
  `collect_input.py:1195` is where they land: *"the identity types `_SHAPE` excludes reach only here,
  so this is where their readback is observed"*. `address` and `dtmf` are the other two exclusions
  and are not used in this node.

Two configuration rules the node obeys so the six stay eligible:

- no `require_confirmation` / `confirm_before_complete` on any of them — **true** gives
  `confirmation_required` and **false** gives `readback_declined`, and both kill the frame
  (`prepared_state.py:312-316`). Of the six, only `choice` and `number` still expose those keys at
  `_SCHEMA_REVISION 5`; dob/date/currency/text drop them as obsolete, so for those four the accepted
  record's disposition is the only confirmation truth.
- English only: `RENDERER_LANGUAGES = {"English": "en"}`, so any other call language falls back with
  `language_unsupported`.

## Three things this workspace cannot test, by construction

1. **The entry arm (P1) never fires through the sim CLI.** `prepared_entry._eligibility` refuses with
   `no_inputs_contract` unless `config.inputs_complete`, and `src/simulation/flow/agent_config.py`
   `_base_agent_config` builds the engine's config from a fixed key list that does not include
   `inputs_complete` — the node here authors `"inputs_complete": true` and the loader drops it
   (verified: `"inputs_complete" in bundle.agent_configs[node]` is `False`). The same gate narrows
   the tool list in `tools/tool_factory.py:36`, so that is off in sim too. The state-frame arm, which
   is what the display table above is about, needs only the resolved configuration and does run.
3. **The end nodes are the pack's, and they are a MOVERS script.** Only the one agent node is
   rewritten; `End conversation 9/10` still say "…if the caller isn't a fit or the move can't
   proceed…" and `Callback Follow Up` (the voicemail path only) still names a move to Denver and a
   phone number. Nothing in the agent node carries a placeholder, so the clinic persona contradicts
   nothing the desk itself sees, but a closing line that mentions "a move" is possible and no
   scenario checks it. Accepted.

2. **No `prepared_transitions` are declared**, so the per-outcome arms (E1a / ARM A) sit at
   `no_declared_transition` — `prepared_speech.transitions` reads them "from the node's own
   `prepared_transitions` (§6): never inferred from `Inputs` order". Add them to the node if the
   campaign is extended to those arms; the boolean and a two-option choice are the only shapes that
   qualify.

## Authoring rules this node keeps

- **No example values in any tool-backed field text.** Not in the Task, not in an Input's prose, not
  in a collection's `instructions` — a model speaks the example back as if it were the caller's own
  answer. `build_ws.py --self-test` asserts no digit and no `@` appears in any Input text.
- **No `{{…}}` placeholder anywhere in the node.** The CLI substitutes `{{Start.*.params.*}}` in the
  raw flow *text* before parsing, so a placeholder in the Task would be digested rendered and never
  match the version stamped at build time — every field would read stale on every call.
- Versions are stamped with the runtime's own digest via `scripts.stamp_collection_versions.stamp`,
  and the self-test asserts nothing resolves stale.

## Use

```
STRESS_REPO=<tree> <tree>/.venv/bin/python build_ws.py --self-test     # rebuild + check
./run_arm.sh prepared <tag> <env-file> 5                              # one arm, 5 repeats
./run_arm.sh off      <tag> <env-file> 5                              # its twin
```

`<tree>` is `stress-evals/trees/cd6ac6c5`; `run_arm.sh` refuses any other tree, a DIRTY tree, an
unbuilt workspace, a node not on `gpt-4.1`, a missing env file and one that is not mode 600, and
prints only the env file's key names. It writes the env file's sha256 into `RUN-INFO.txt` so the two
arms can be proven to have run the same one, and notes whether `AZURE_OPENAI_SIM_DEPLOYMENT` is
among its keys — when it is set, it, not the node's `"model"` line, is the deployment that answers
inside a simulation (`config/settings.py:235`).

Then judge the pair — **the `run` exit code is not the verdict.** The engine compares
`expect.variables` literally by key, so a phone stored with a country prefix and a currency stored
without an inferred code print engine failures that are right by value. Only `judge.py` decides:

```
<tree>/.venv/bin/python judge.py prepared-arms/<tag>-prepared prepared-arms/<tag>-off
```

A scenario's numbered "Judged by transcript" criteria are PROSE. `judge.py` reads `expect:` only and
never reads a description; where a criterion could be made mechanical it has been moved into
`expect:` or into the judge (see README).
