# Northwind flow in the local console: what it would take

These are notes only. I did not touch the console, the stack, Redis or any database. Everything below comes from reading source (the local console pin `deploy-console-dbb4f5b5` @ `dbb4f5b5d7`, which the Jev compose override mounts at `docker-compose.override.yml:228`; the runtime at `rw-text-lane` @ `a1bd6878a`) plus one offline probe.

## Short version

- `ws/flow.json` is the sim loader's shape, `{nodes:[{id,type,data:{config}}], edges}`. That is close to the builder format, but it is not the same thing. The console's Import and Cmd+V path runs no conversion (`hooks/use-copy-paste.ts`, `applyPastedContent`), so whatever gets pasted has to be builder format already.
- I would not use the canvas paste for this flow. Use the route FHCSD local flow `472875c4` took: a translated payload saved through the signed-in Console service, with a rollback payload kept, and the saved result read back afterwards (`LOCAL-FLOW-472875-TRANSLATION-CONTRACT-2026-09-27.md`). That route is known to keep the leader keys the console schema does not declare. The FHCSD node `518895a9` in `text-lane/flow-db` holds both a node-level `leader_contract` with `speech_steps` and 5 Input-level contracts in its `:CONFIG`.
- On a live call, `action_mocks` does nothing, and all 3 tools really send. `example.invalid` fails DNS, so every live call would end at `booking_failed`. The URLs have to point at a local mock first.

## Changes the builder payload needs

| # | Change | Why |
|---|---|---|
| 1 | Put an **Initiate Call** node between Start and the agent: `from {{Start.http.params.caller_id}}`, `to {{Start.http.params.phone_number}}`. Wire `answered` to the agent and `no_answer`, `busy_rejected` and `failed` to a new End. Add `caller_id` and `phone_number` to Start `payload_format`. | The sim starts the agent with no call. Console "Test agent" runs Start, then Initiate Call, then the AI node. I probed this offline: `check-out/flow-with-call.json` has that node, and `check_flow.py` on `rw-text-lane` gives exit 0, `preflight_reasons: []`, entry still the V2.9 node. |
| 2 | Set `require_http_auth: false` on Start. | The console defaults it to true and exports strip the key, so an unauthenticated trigger gets a 401. |
| 3 | Add an `id` to each of the 3 actions. | The console action schema requires `id: z.string()` (`config/validation.config.ts:243`). Ours have only `http_tool_name`. |
| 4 | Decide on the intent ids. They are currently equal to the names (`visit_booked` and so on), and every edge `sourceHandle` uses them. | The builder keys an AI node's output handle by `intent.id`, and ids are usually uuids. Because the ids here equal the handles, the edges should join. If the console rejects non-uuid ids, mint uuids and rewrite each `sourceHandle` in the same pass. Untested. |
| 5 | Human transfer: keep the End node, or add a **Call Forward**. | The sim uses an End as a stand-in. With a real Call Forward, preflight wants handoff metadata and every Call Forward outcome routed to an End (`src/jev_leader/harness.py`, the `call_forward` branch). Not built. |
| 6 | Point the 3 tool URLs at a local mock that returns the spec's bodies. | The live `http` transport (`src/jev_leader/tools/transports.py:40-63`) wraps the reply body just as the sim wraps a mock: `ok` is false only when the body has `success: false`, `ok: false` or an `error`. So the same bodies give the same outcomes. For example, the lookup `{"account_id":"NW-20417",...}` returns SUCCEEDED, and `{"success": false, ...}` returns REJECTED. A 5xx, a 408 or a timeout is sealed UNKNOWN. With no body template, the arguments are sent as the JSON body, so `lookup_account` sends a GET with a JSON body. A real endpoint may want `?phone={{phone}}` in the URL instead. The default timeout is 1 s (`http_timeout_ms`). |
| 7 | Keep synthetic data only, and no customer webhooks. | The Start payload for a live test is `lead_id`, `caller_id` and `phone_number`. The only callee should be a test phone. |

## Keys the console does not declare

The local console pin knows `leader_profile` on the V2.9 node, `leader_contract` on actions and intents (`validation.config.ts:240`, `:400`), and `collection` on an Input verbatim (`:685`). It has no field for two keys this flow depends on:

- **Node `leader_contract.speech_steps`**: `booking_summary` and `booking_success`. If this is lost, `visit_booked` can never fire, because its route contract needs the `booking_success` followup. The receipt and the arrival window also lose their binding.
- **The Input `leader_contract` on `confirm_booking`**: its prerequisite is the speech `booking_summary`. If this is lost, the go-ahead question can come before the summary.

A paste keeps node data as-is (`schemas/react-flow-schemas.ts`: `data: z.any()`). I have **not verified** whether a sidebar Save or the config service's flow GET keeps undeclared keys. The GET did erase backend-only V2.9 keys on 17 Sep (phlo-core `ModelMapper` projection). So after any save, read `PHLO:<flow>:NODE:<agent uuid>:CONFIG` and diff it against `ws/flow.json`. At minimum compare `leader_profile`, `leader_contract`, each Input's `collection` and `leader_contract`, and each action's and intent's `leader_contract`.

Two console behaviours can move things on Save, so diff after each one:
- The known "save each V2.9 node before Publish" workaround is about `{{Node.x}}` refs failing as "invalid variable". This flow has no `{{...}}` template refs at all (`lead_id` is a contract `node_var`), so that trap may not apply. If Publish does complain, save the node and diff again.
- A node Save can run Input detection and rewrite `collection`, and it can rename the node or add `model_config`. The Inputs carry none of the console's bookkeeping keys (`fingerprint`, `stale`, `overrides`). The runtime drops those three by name, so adding them is harmless to the resolver.

## Check before handing it over

1. Validate the payload with the console's own schema. `bun run` a few lines that import `reactFlowContentSchema` from `apps/web/src/v2/pages/flow/schemas/react-flow-schemas`, then check every edge `sourceHandle` against the source node's intent ids or its fixed ports.
2. Convert the builder payload back and run `check_flow.py` on it on the tree the stack runs. It should give `preflight_reasons: []`, 13 Inputs, 6 routes and 3 contracts, as in `FLOW-CHECK.md`.
3. After the save, run the `:CONFIG` diff above.
4. Only then place one call, reading the PIN with the phone keypad. On a real call, digits arrive through the room, so the keypad seam that blocks the text sim is not needed there.

## Open questions

- Should human transfer stay an End for the example, or become a real Call Forward to a test number?
- The console field for node speech steps and Input contracts: should it land in the console (the three-repo passthrough pattern), or does this flow stay service-saved like FHCSD?
