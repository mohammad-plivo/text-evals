# FHCSD per-scenario stability across 6 valid boards (2026-09-01)

Every FHCSD board with >=12 judged items, name-keyed. Board totals ranged **13/18 to 17/18** (72%-94%).

| pass rate | scenarios |
|---|---|
| **100% stable (5)** | Emergency Chest Pain · No Availability Callback · No Patient Match · Partial DOB Then Completed · Two Patients Match |
| 83% — fails 1 in 6 (8) | Booking Fails · Declines Backs Out · Declines Not Interested · Chooses Second Slot · Transfer To Staff · Out Of Scope Cost · Privacy Demands · Refuses DOB |
| 67% (3) | Books First Slot · Privacy Spouse · Upset Angry |
| 50% (1) | Human Requested — During Screening (17800) |
| **33% (1)** | Happy Path — Patient Gives A Date Range |

**The headline finding: there are ZERO always-red scenarios.** Even 17800, which we have been calling an honest
red pending Defect B, passes 3 of 6. Even Date Range, our worst, passes 2 of 6. Nothing in this suite is
deterministically broken.

**Consequence for the >=90% target.** A single board cannot establish the number. With 18 scenarios at these
rates the *expected* board lands around 15-16/18 (83-89%) with a spread of several items either way, which is
exactly the 13-17 range observed. TeleCRM saw the same thing from the other direction: 17/35 -> 24/35 with no
code or config change between the two boards. So:
- quoting any single board as "we are at N%" is not defensible, in either direction
- the honest metric is a **per-scenario pass rate over repeats**, which is what MK's own "fixed = x3 + judge
  PASS + transcript" rule already asks for
- a scenario moving pass->fail between boards is NOT evidence of a regression unless it moves consistently

**It also validates where the fixes are aimed.** The two worst scenarios are precisely the two with diagnosed
root causes: Date Range 33% (r17, the propose-back reorder) and 17800 50% (Defect B, the missing screening
status for a transfer request). Privacy Spouse at 67% matches Defect A firing only when the persona answers with
a role rather than a name, not on every call. The fixes are pointed at the right targets; what they will move is
the *rate*, not a binary red-to-green.

## Board cb62830d (09-01 14:46, clean pod, refreshed fixtures): 15/18, ZERO variable failures
16 VARIABLE-VALIDATION-PASSED, no VARIABLE-EXTRACTION-FAILED, no VARIABLE-VALIDATION-FAILED anywhere.
Three fails: Date Range (r17), 17800, Privacy-Demands (STT-ISSUE + TARGET-NOT-REACHED).

**Do not read this as "variable extraction is fixed."** VAPI's screening fix is NOT on dev (branch unpushed),
so the two variable reds going green is the good end of known variance, not a fix:
- Spouse recorded `screening_relationship: "wife"` this time instead of `""`. Same code as yesterday — the model
  simply filled the field on this roll. Defect A is intermittent, which is exactly why that scenario sits at 67%.
- Upset passed because its ECV was trimmed to two always-emitted keys; its `screening_status` still varies run to
  run (`do_not_call` yesterday, `refused` today). That fix IS real and durable — the trim removed our exposure to
  a value we cannot pin.

## NEW HARD BUG — the agent SPOKE A TOOL CALL to the caller (17800, board cb62830d)
Transcript, agent turn 2, verbatim:
> "Complete underscore permission. Underscore to underscore continue status equal sign permission underscore granted."
That is `complete_permission_to_continue(status=permission_granted)` rendered as SPEECH instead of emitted as a
tool call. Customer-facing gibberish. It occurred exactly once across all 18 calls, on the one path where the
caller asks for a human during screening — i.e. precisely where Defect B lives (there is no
`_PERMISSION_STATUSES` member for a transfer request). The model, having no valid way to express the caller's
request, verbalised the tool instead of calling it, then carried on asking for the DOB it had already said it
would bypass ("I'll connect you to a staff member. One moment, please.").
**This upgrades Defect B from "records a wrong value" to "emits a tool invocation as speech to the caller."**
Escalate to Kishan with the transcript.

## Date Range double-confirmation — ground truth from the runner tool-call log (call 4ee07f8f, run fe561b4b)
The complete tool sequence for the call, 8 calls, from VictoriaLogs `Tool call tool=… arguments=…`:
1. `update_identify_contact` (target_contact, Raymond Bennett, self) · 2. `complete_permission_to_continue`
(permission_granted) · 3. `update_dob` (1958-11-12) · 4. `confirm_dob` · 5. `update_boolean_answer {value:true}`
= wants_to_reschedule 09:20:35 · 6. `update_date {2026-09-06}` = preferred_start_date · 7. `update_choice
{choice:"1"}` = selected_slot 09:21:23 · 8. `update_boolean_answer {value:true}` = booking_confirmed 09:21:59.

**`booking_confirmed` was committed EXACTLY ONCE.** There is no duplicate commit, no `confirm_boolean_answer`,
and no re-confirmation path fired. So the double question is NOT `require_confirmation` (already `false`), NOT
`_answer_changed` and NOT `_reconfirm_after_away` — all three would have left a second tool call. The model
simply asked, got "Yes", did not commit, asked again, then committed on the second yes.

**Leading hypothesis (testable, not yet proven): stacked readback duties.** `update_choice`'s tool output is the
"This is what you say now…" readback instruction, so after recording the slot the model is told to read the
choice back — and `booking_confirmed`'s own instructions ALSO say "Read the chosen option back exactly as
written above … and ask for a clear yes." That is two consecutive read-it-back-and-confirm duties over the same
slot, which is exactly what the transcript shows: "Option one, Monday September seventh… Sure thing." →
"Would you like to confirm your booking for Monday September seventh…?" → "Can I confirm your booking for
Monday September seventh…?" — three restatements of one slot.
**Candidate fix (r19):** drop the readback duty from `booking_confirmed`'s instructions and leave it a plain
confirmation question, since `selected_slot` already reads the choice back. Instruction-text only, no code.
Falsifiable: if the stacking is the cause, the third restatement disappears and the criterion stops firing.

**Correction to the earlier attribution:** this scenario's failure today was NOT the r16/r17 same-breath defect.
The agent proposed the caller's window back correctly ("Sure thing next week. Sunday, September six") with no
re-ask at all. Date Range's 33% rate comes from DIFFERENT failure modes on different boards, so r17 alone will
not fix it.
