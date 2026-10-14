# Hunter fix-loop protocol — all three sessions (VAPI · TeleCRM · FHCSD)

Written 2026-08-30 20:35 after MK's 20:24: "I asked you to be absolutely sure the thing is fixed, and only then go to Hunter… there is some approach problem with all three of you." Each rule below cost at least one real run today. Amend only with a dated line; never soften a rule without the failure that justifies it.

## A. Before any call is placed
1. **The launcher runs the checklist and fails closed** — containers healthy, both tunnels answer, every node key present (hash + `:CONFIG`), mock 200 via the tunnel in < 2 s, tree parses (`ast.parse`) with no conflict markers, AC power + `caffeinate`, load below the gate (6 alone, 8 when sharing 2+2), no pytest, cookie valid, no untracked run of your own on `/api/runs`. Scripts today: `Vapi Flow` scratchpad `precheck.sh`, FHCSD scratchpad `preflight_cx2.sh`; merge into one sourced file. *(all three)*
2. **No infra mutation without a one-call smoke** — Redis, DB, container, tree swap: mutate → verify the exact key/state the runner reads → one scenario → then the batch. *(vapi: Redis glob + deleted `:CONFIG`; telecrm: the `:CONFIG DEL` ritual; fhcsd: restart on conflict markers)*
3. **Reviewer pass before anything touches a live tree**; choose the seam from the raw log/SDK, never from a filtered timeline. *(fhcsd ×2, vapi's say-raise hole)*
4. **Kill by PID, then re-poll `/api/runs` for two minutes** — never `pkill -f` with a launcher alive. *(vapi duplicate run)*

## B. What "fixed" means
5. **×3 on the corrected config, judge PASS each, transcript read by you** — never a log signal, never n=1, regardless of lane pressure. *(vapi D-031; fhcsd r12; telecrm Wrong Number)*
6. **Full-rubric rule** — quote the target criterion verbatim in the fix note before the first fix round; fixing from the one-line excerpt burns rounds. *(telecrm ×3)*
7. **Prompt text is not a fix for a mechanism** — when the log shows a mechanism (tool dropped, silent path, wrong seam), go structural or stop. *(fhcsd hold false-positive; vapi D-020)*
8. **A "never passed" list in every report** — each entry root-caused and fixed, or put in front of MK as an explicit decision within the hour, never left as "rubric/persona/not ours" without recording evidence. *(vapi silent transfer 8 h; fhcsd "structural/not ours" 8 h)*

## C. Reporting and shared learning
9. **Single-artifact finality** — any suite-state claim to MK cites ONE run id; composites are working notes. *(telecrm "28/30")*
10. **Lesson sweep within the hour** — when one session measures a surface rule (field_label spoken, stored-is-spoken, negation priming, name-beats-prose, `:CONFIG` never repopulates), the other two grep their own flow for it before their next batch. *(all three paid twice for mapped lessons)*
11. **Mechanism-or-no-ritual** — nothing enters setup.md as a procedure without a one-line "why this works". *(telecrm §12.1)*
12. **Watchers emit a heartbeat; silence = unknown** — a monitor that prints nothing is dead, not fine; one session posts load/ttft per minute while calls are up. *(nobody saw the 16:36 sleep for 2.5 h)*
12a. *(21:06 amendment, vapi)* **A process detector prints the pid + cmdline it matched** — `pgrep -f pytest` matched my own shell text and raised a ghost alarm during a live run; match real runners only (`[b]in/pytest|[p]ython -m pytest`).
12b. *(21:25 amendment, vapi)* **A gate that fails silently is a dead gate** — under `set -euo pipefail`, a `pgrep` with no match aborted the launcher before it printed a reason; the retry loop showed "precheck red:" with nothing after it for three minutes. Every refusal prints WHY; every `$(cmd)` that may legitimately return non-zero ends in `|| true`.
13. **One tripwire, shared** — stop your own run on ttft max > 4 s for two minutes or > 10 slow-inference/min; load is warn-only (it sits 8–15 at 2+2 with ttft fine). *(fhcsd's healthy run stopped at load 23 / ttft 1.05 s)*
13a. *(2026-08-30 21:02, telecrm+fhcsd)* **Completion = the RUN's status field, never an item's** — two waiters this evening declared DOWN on an item status matching; both retracted.

14. **Integration gate before any push (added 20:36 after MK 20:34)** — one branch `integration/<date>` = `main` + every PR commit from all three sessions in dev-landing order (telecrm builds; SHAs posted in ACTIVE-WORK); one full pytest on it; integrated Hunter from that same branch on BOTH stacks (shared-path scenarios the same night, full finals before the push if MK asks); anything found is fixed on the integration branch first and back-ported to the owning PR. Nothing lands on dev that was not run stacked. *(today: stack 1 stacked vapi+telecrm+#365 all day; fhcsd's #367–#371 never ran with them — #371 vs 71a6d292 share the idle subsystem, #369 meets the V2 handoffs)*


## Rule 12 restated by MK (2026-08-31 12:27)
"When you say telecrm is 30 out of 35 in dev, that should only be visible in the final Flow test. You should not fix
individual tests and add it to the 35 list." → A board is ONE fresh full-suite run id and its count. Re-dials, ×3 proofs,
re-judges and A/Bs are diagnostics, reported separately, never folded into N/N.
## Rule 15 — dev differs by design; report OUR deltas (MK 12:27)
Dev is shared and "will get corrupted". Gap tables lead with the differences relevant to our flows/flags/code paths; the rest
is an appendix. Parity target = a main-like environment; dev-like is the test bed.

## Rule 16 — dev suites run at maxParallel 4 (MK, 2026-08-31 16:51: "15 concurrent calls is a problem so lets do 4")
One board = one fresh full run at 4; @15 boards from 31 Aug are load-tainted diagnostics. Sequence suites on the pool; never overlap.
