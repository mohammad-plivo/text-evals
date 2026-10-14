# Family Health text-test handoff — 2026-09-10

## Frozen inputs

- Runtime: `d3f17abcc614418cf2632dc5ffb083509f067230`, clean, source identity `1a335ffba9555e74e8f1e6e2c030a05063c69158fcf3c375eb301583967e6dc5`.
- Mock flow candidate: `1649119cecd27fc7382553aed66c211cbbc5869f2ae470bf984f40eb064323aa`.
- The earlier 24/24 result covers only first-turn probes from a prior run. It is not new evidence for the current multi-turn work.

## Current offline evidence

The offline graph-path run completed 18 passed and 1 failed in 0.05 seconds. Log: `online-v29-multiturn-glV3d4/graph-paths-r1.log`.

The failure is a real graph-contract gap: with only option 1 present in the mocked API response, synthetic state containing `selected_slot=option 2` and `booking_confirmed=yes` still reaches Save Slot 2. This is injected-state coverage; it is not a model reproduction and does not prove an actual booking occurred.

The other 18 checks cover consent fail-closed behavior, single-save fan-out, rendered request templates, unsuccessful-save routing, and post-save follow-up routes. The 409 case is a seeded branch replay only. The HTTP simulator emits only status 200 or 500, so it does not reproduce a 409 response wire path.

## Scope and next checks

- Eleven multi-turn cases were prepared and both bounded pilots are recorded below.
- R2 is complete; its known failures do not need a repeat paid run without a source or flow change.
- Mocked node effects are not proof of the complete 41-node flow or production API behavior.
- The Get Slots `StartDate` ISO-format boundary remains an explicit product/API decision.
- No production runtime, flow, or PR was changed by this work.

## Multi-turn preflight update

The earlier R3 offline harness gate passed all 78 checks in 3.15 seconds: 30 new multi-turn controls plus 48 baseline controls. The immutable log is `online-v29-multiturn-glV3d4/multi-turn-offline-r3.log`.

Earlier logs retain their original meaning: R1 was 76 passed with two fixture errors; R2 was 73 passed with five genuine oracle gaps; R3 is the first all-green 78-check result after those fixture and oracle corrections. Do not relabel or replace the earlier evidence.

Later adapter-boundary preflights also remain distinct. R4 produced 85 passes and 4 failures; all four failures came from invalid direct-`AgentTask` fixtures that did not exercise the simulation boundary. R5 replaced those fixtures with actual `SimSession.turn` and seeded SDK `RunResult` boundary controls and passed 89 checks with 2 warnings in 3.28 seconds. These are boundary tests, not proof of the complete collector lifecycle.

- Runtime remains frozen at `d3f17abcc614418cf2632dc5ffb083509f067230`, source identity `1a335ffba9555e74e8f1e6e2c030a05063c69158fcf3c375eb301583967e6dc5`.
- Flow remains frozen at `1649119cecd27fc7382553aed66c211cbbc5869f2ae470bf984f40eb064323aa`.
- Earlier offline-preflight multi-turn adapter: `f7ac7bc02253a1efbb471d1b76e1760d8fcdc5f9f9cb20d76d591fbce912e26f`. This is historical, not the final adapter.
- Earlier offline-preflight oracle tests: `5f2cd2e55609c38b301c6a043e82efaa1211d69f1a9c1d0b0084c91f7620376d`. This is historical, not the final test hash.
- Final R2 adapter: `850d55238d7d04a26e1da630abb6c8b1569c37e319d16baa445d13286739fc07`.
- Final R2 oracle tests: `a636040c96d4d465cecc893ba21b7fa77e4251e45ef9148dd4653af19216ddff`.

## Multi-turn R1 pilot

R1 attempted the 11 planned one-repetition cases. Ten executed before the campaign stopped; `choose_invalid_option` did not run because an earlier expected `ChangeRequest` surfaced as a simulator error. The raw result was 2 passes and 8 flags across those 10 case executions. All 34 owned GPT-4.1 requests were verified and settled.

The R1 result is preserved, but two adapter-observability defects affected its raw classifications:

- `choose_fresh_yes` produced the complete booking readback, a fresh consent, canonical affirmative storage, and the `book` handoff. Streaming emitted the words as separate chunks with whitespace-only chunks between them. The oracle discarded those separators while reconstructing speech and raised a false missing-facts flag. The new adapter retains every nonempty owned chunk, including whitespace.
- Expected collector `ChangeRequest` and `HandBack` control transfers were rethrown by the SDK run result, but the simulation runner's internal control-signal tuple did not include those two types. The new adapter temporarily extends that tuple only around `run_session`. It does not suppress ordinary `ToolError`, change settling, or modify production runtime code.

Five follow-up cases stopped before their authored substantive caller responses were delivered. The parent node asked the `needs_more_help` question itself instead of routing to the required boolean collector. This is a confirmed orchestration-policy deviation: the Input requires `known_value=null` and `options.ask_before_update=true`, and V6 prohibits the parent from eliciting the field before routing. The new adapter may continue these cases diagnostically, but it records a sticky policy-deviation event and the final strict verdict remains failed even when a downstream handoff is observed.

R1 spend was `$2.091130` conservative and `$0.418226` at the standard estimate. After R1, the shared campaign ledger recorded 2,157 requests, `$132.945210` conservative, and `$26.589042` standard, with seven pre-existing unresolved reservations. R1 introduced no new unsettled requests.

## Multi-turn R2 result

R2 completed all 11 planned one-repetition cases across the consent, revision, and follow-up groups. The immutable raw JSONL files are `online-v29-multiturn-glV3d4/gpt41-fhcsd-mt-r2-consent.jsonl`, `online-v29-multiturn-glV3d4/gpt41-fhcsd-mt-r2-revision.jsonl`, and `online-v29-multiturn-glV3d4/gpt41-fhcsd-mt-r2-followup.jsonl`. The raw verdict was 5 passes and 6 flags. All 51 owned requests were model-verified and settled.

| Case | Raw verdict | Observed outcome |
|---|---:|---|
| `choose_fresh_yes` | Pass | Option 1, fresh full-fact consent, canonical `yes`, then one `book` handoff. |
| `choose_decline` | Pass | Canonical `no`, then `Patient Declines`; no `book`. |
| `choose_tentative_consent` | Pass | Tentative answer did not book; final no routed to `Patient Declines`. |
| `choose_conditional_consent` | Pass | The agent accurately said charge information was unavailable, did not promise a fee outcome, and routed the final no to `Patient Declines`. |
| `choose_change_before_consent` | Flag | Option 2 was authoritatively stored, but the resumed confirmation used stale option 1 facts. No final booking yes or `book` was delivered. |
| `choose_invalid_option` | Flag | The parent accurately listed the three valid slots and invented/stored nothing, but did not enter the choice collector before the corrective option 2 response, so that response was never delivered and downstream behavior is unproven. |
| `followup_no_more_help` | Flag | Parent-owned help question violated the collector policy; diagnostic continuation still reached exactly one `Done` handoff. |
| `followup_factual_help` | Flag | Parent-owned help question violated policy. A later collector used `known_value='yes'` instead of the required null, the agent correctly answered Doctor Casey and Harbor Clinic, then canonical no reached `Done`. |
| `followup_new_booking` | Flag | Parent-owned help question violated policy; diagnostic continuation reached `Changes or New Booking`. |
| `followup_person` | Pass | Reached `Human Requested`, but the parent asked the help question and the child repeated it, so this is not a clean conversational result. |
| `followup_emergency` | Flag | Parent-owned help question violated policy; diagnostic continuation reached `Emergency Mentioned`. |

The exact stale confirmation in `choose_change_before_consent` was: “Your selected slot is option 2. Would you like to confirm your booking for September 15th, 2026 at 9:00 AM with Dr Casey at Harbor Clinic?” Option 2 should instead have been read back as September 16, 2026 at 2:30 PM with Dr Morgan at Cedar Clinic. The selected-slot correction was real, but the prior booking boolean resumed with its earlier option 1 instructions. This is the confirmed source-level seam; the oracle did not infer it from the final value alone. See the [correction/resume logic](v29-fixes-runtime/src/units/collect_input.py#L476).

All five follow-up cases reached their exact expected terminal handoff, and none emitted a second `book` handoff. Four remain strict failures because the parent bypassed the required `needs_more_help` collector. The raw passing `followup_person` row also retains the duplicated-question speech concern. Spoken month/day, digit style, and phrasing are manual text observations only; no physical voice path was exercised.

R2 used 51 requests, `$2.918310` conservative and `$0.583662` at the standard estimate. This turn's R1 plus R2 total was 85 requests, `$5.009440` conservative and `$1.001888` standard. The shared ledger now records 2,208 requests, `$135.863520` conservative, `$27.172704` standard, 2,201 settled requests, and seven pre-existing unresolved reservations. R2 added no unsettled requests.

### Bounded recommendations

1. When a selected-slot correction raises `ChangeRequest`, invalidate or rebuild the dependent booking-confirmation collector before resuming, so its readback is based on the newly stored slot rather than the prior boolean instructions.
2. Route invalid-option clarification through the authored `selected_slot` choice collector instead of asking from the parent node. Re-run the corrective option 2 and consent path after that boundary is enforced.
3. Route the post-save help question through the authored `needs_more_help` boolean collector with `known_value=null` and `options.ask_before_update=true`. Preserve sticky failure reporting while checking the downstream terminal routes.
4. Add the still-unimplemented `Which Slot` graph guard: the selected option must correspond to a populated Get Slots row before any Save Slot branch is reachable.
5. Resolve the `StartDate` boundary with a supported deterministic ISO-to-`MM-DD-YYYY` conversion at the API boundary, or confirm that the endpoint accepts ISO. Do not change canonical collector storage to address an API-format contract.

No repeat paid run is recommended for these unchanged known failures. R2 remains an isolated SDK text-node evaluation with synthetic caller data and no configured actions. It does not prove the complete 41-node flow, real HTTP booking, physical audio, or production behavior. Runtime, flow, and PR sources were unchanged.
