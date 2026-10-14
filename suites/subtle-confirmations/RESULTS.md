# Subtle Confirmations — results

**Question (Mohammad):** can our voice-agent confirmations sound human/subtle where safe, and
strict where mistakes are unrecoverable, **via instruction-prompt changes only**?
**Answer: YES** — proven across the 5 main Collect* tasks, instruction-only, the confirmation
gate KEPT, cross-language, with zero net regression (every residual is pre-existing).

## Scope & method
- **Isolated sandbox** `cx-skills-subtle/` (branch `subtle-confirmations`, git remote removed — cannot
  collide with the other chat). Forked pristine `plivo-labs/cx-skills` @ `ec8b057`. Only the 31B
  harness wiring was ported (Azure caller/judge + hosted agent); task instructions started pristine.
- **Agent under test:** Gemma-4-31B (LiveKit hosted, US) — the harder serving case. Caller
  gpt-4.1-mini / judge gpt-5.5, both Azure. (GPT-4.1 agent arm deferred — no OpenRouter key in env
  and the harness has no Azure *agent* path; that's plumbing, not an instruction change.)
- **Fix surface:** task instruction-template text ONLY (`tasks/*.py`). Scenarios/judges/deterministic
  contracts frozen (except the 3 exploratory Path-2 choice scenarios, below).
- **Per task:** pristine baseline → warm-wording tweak → full-suite tweaked sweep → any miss
  attributed by re-running that case on pristine (pre-existing vs regression).

## The pattern (Path 1 — "warm wording, gate kept")
Every affected confirmation surface now: **LEADS with a short, warm, value-naming acknowledgment**,
folds in a light confirm cue, and still fires the confirm tool (gate intact). Bans the formulaic
openers ("You meant", "So that's", "Just to confirm", "I heard", "Read back"). Rotates the ack + cue.
For codes/identifiers the **char-by-char / digit-by-digit readback is preserved** — warmth lives only
in the wrapper. The ack is composed **in the configured language/mode** and is **never a
'noted/recorded/saved' status phrase** (the text round proved both guards are load-bearing).

## Results (instruction-only, Gemma-31B, gate kept)

| task    | suite  | net regression | notes |
|---------|--------|----------------|-------|
| choice  | 69/69  | none           | warm wording; full-suite clean |
| boolean | 35/35  | none           | warm wording FIXED a baseline miss (pristine 34/35 → 35/35) |
| number  | 65/65  | none           | warm wording; clean |
| text    | 45/47  | none           | 2 residuals pre-existing (garble-rc-off; hinglish Devanagari script-band); needed 1 refinement round (language + no-'noted' guard) |
| address | 57/59  | none           | 2 residuals pre-existing (ambiguous-trip-asks; zip partial-correction); warm on single-field city/country, value-readback on full address |
| dtmf    | 11/11  | none           | warm wrapper on the digit-by-digit confirm readback; digits kept exact (identifier stays strict) |
| currency| 29/30  | none (fixed +1)| warm wording + locale/language auto-inference VERIFIED passing (UK→GBP, India→INR, French→EUR, lakh→INR, CA→CAD, ambiguous-dollars→CAD); inferred currency still named aloud; 1 residual pre-existing (negative-amount-corrected) |

Every non-passing case was verified to ALSO fail on pristine `ec8b057` — the warm tweak introduced
**no net regressions**. (Two transient regressions the first text tweak caused were root-caused and
fixed in one refinement round; see below.)

## Before → after (samples)
- **choice**  "You meant UK for the country, right?" → "UK — got it, shall I keep that for the country?"
  · Spanish "…¿correcto?" → "Perfecto, … ¿está bien así?" · Hinglish gained "बढ़िया,…"
- **boolean** "So that's a yes to X, is that correct?" → "Wonderful, that's a yes for the reminders, right?"
  · "Understood, no to the reminders—is that correct?" · Spanish "Perfecto, entonces sí … ¿está bien?"
- **number**  "Read back the value … is it correct?" → "Twelve and a half years—got it, is that right?"
  · Spanish "Cuatro personas, perfecto, ¿es correcto?"
- **text**    codes stay char-by-char, now warm: "Got it, your appointment number is AB1234: A B 1 2 3 4.
  Is that correct?" · Tamil "…PNR XY34Z9: X Y 3 4 Z 9…" · French "Je corrige, votre numéro … : A B tiret 1 2 3 4 6…"
- **address** "United States — got it, that's the country?" · "Noida, Uttar Pradesh, India — got it, is that the city?"
  (full address keeps "I have … as the address", postal digit-by-digit)

## Key findings / lessons
1. **The pattern generalizes** across task types with the gate kept — the confirmation still happens,
   it just sounds human, and the deterministic contracts (which require the confirm tool) stay green.
2. **Multilingual/code tasks need two guards up front** (learned on text, cost one refinement round):
   the warm ack must be composed IN THE CONFIGURED LANGUAGE/MODE (English exemplars are illustrative
   only) and must NEVER translate into a 'noted/recorded' status phrase (French "C'est noté" was the
   trap). Baked into number/text/address; fold into any future task.
3. **True "ack-and-move-on" (no yes-gate) is NOT instruction-reachable** — see `DEFERRED-code-change.md`.
   The confirmation-OFF path completes silently by design; a spoken standalone "United Kingdom, got it"
   needs a small code change (deferred by Mohammad — instruction-prompt scope only). The no-gate
   *structural* behavior does work (3 exploratory re-scoped choice scenarios pass, silent record).

## Remaining (one task; different shape)
- **contact_screening** — a DIFFERENT category: its "confirmations" are terminal disposition
  acknowledgments (reached / wrong-person / callback / unavailable), not value readbacks, and per
  CLAUDE.md they are already short, human, and in the caller's language. So the robotic-"You meant
  X" problem this project fixes does not really apply there. If we warm it: only the benign closes,
  with the language/no-'noted' guard — and permission / do-not-call MUST stay EXPLICIT (consent
  tier, never softened). Note also its known serving residual (the LiveKit-hosted-Gemma <turn|>
  control-token leak on one Devanagari callback case) is not instruction-reachable.

## Venky feedback addressed (2026-07-22)
- **CollectCurrency — auto-infer currency from conversation language/locale:** the feature already
  exists (places → GBP/INR/USD; dialect → CAD/EUR; idioms lakh→INR / quid→GBP; `currency_inferred=true`
  always named in the readback). Verified the inference test cases EXIST and PASS on Gemma-31B (7/7:
  UK→GBP, India→INR, French→EUR, lakh→INR, Canadian→CAD, ambiguous-dollars→CAD, inferred-corrected).
  Also brought currency into the warm-confirmation set: baseline 28/30 → tweaked **29/30** (net +1),
  the 1 residual pre-existing.
- **CollectAddress — standalone city/country vs part of a full address:** confirmed our build already
  does exactly this. The tweak touched ONLY the single-field branch (standalone → settle subtly);
  the full-address branch is untouched (reads back EVERY captured part + postal digit-by-digit). No
  change needed.
- **ConfirmKnownValues — leave as-is:** never touched (`git diff ec8b057 HEAD` shows no
  confirm_known_values.py change). No change.

## Humanization pass (2026-07-22) — removing the "AI feel" (em dashes + repetition)
Mohammad: em dashes read as AI and it still wasn't human enough. Research (7-agent workflow →
`HUMANIZATION-research.md`): NO humanizer tool fits a real-time voice agent (latency, breaks
streaming, mangles tool calls, wrong target); the lever is prompt design (LiveKit's own advice).
Root cause was self-inflicted: my 23 em-dash exemplars → the model copied them (em dashes in ~33%
of choice turns). Built an offline scorer `humanness_score.py` (em-dash %, canned-ack %, contractions
%, favorite-opener share, pass) over the transcripts.

Piloted on choice through v2..v5 (key lessons: declarative acks dropped the confirm gate → require a
closing question; opener variety is MODEL-CAPPED ~30-42% on Gemma regardless of the pool). Winning
pattern (v5): no em dash (commas), de-canned (no default Great/Got it), contraction-rich,
question-ended, scoped to spoken, strict read-backs preserved. **Rolled out to all 7 tasks:**

| task | em-dash | canned ack | contractions | pass |
|------|---------|-----------|--------------|------|
| choice | 0% | 0% | 57% | 71/72 |
| boolean | 0% | 2% | 42% | 34/35 |
| number | 0% | 3% | 76% | 64/65 |
| text | 2% | 2% | 2%* | 45/47 |
| address | 0% | 0% | 18%* | 57/59 |
| dtmf | 0% | 9% | 9%* | 11/11 |
| currency | 3% | 3% | 90% | 30/30 |

Before-baseline em-dash rates were choice 61% / currency ~21% / number ~15%. *Low contractions where
read-backs are dominated by spelled codes/digits (little surface). Pass rates at parity (residuals =
known pre-existing cases + ~1-2% flake band; currency improved to 30/30). Model-cap: Gemma keeps a
favorite opener (~30-76%, usually "alright") — a natural word, not a sycophantic tell, and largely a
single-call-eval artifact.
Report section "Follow-up 2" (glance mohammad-kadiri/subtle-confirmations) has the metric
explainers, a full before/after call, and a cross-task example table.

## Pointers
- Sandbox commit trail: `git -C cx-skills-subtle log --oneline ec8b057..HEAD`.
- Confirmation-fidelity classification (which tasks may be subtle vs strict): glance
  `mohammad-kadiri/confirmation-fidelity`.
- Deferred code change: `DEFERRED-code-change.md`. Hour-by-hour log: `2026-07-2*_*/UPDATE.md`.

## Crisp round (Venky: "still not human", 2026-07-22)
Venky rejected the humanized pass: it had collapsed onto ONE wordy template,
"Alright, so it's <value> for the <field>, right?", every value, every call. Root cause:
the pass MANDATED a sentence shape AND fed that exact shape as the example — a concrete
exemplar is a behavioral anchor (diversity collapse; persists at any temp, 0.3 vs 0.7 A/B
barely moved). Fix = **crisp de-scaffolding**: drop the padding ("so it's" / "for the field"),
cap length (~3-6 words), give an inspiration MENU tagged "vary, never reuse", mandate
"start with the value / never open two turns the same". Char-by-char code safety untouched.

Results (Gemma-31B @ temp 0.7, real transcripts):
- currency: "Two hundred fifty pounds, yeah?" / "So, eight hundred to a thousand pounds, right?"
  / "Twelve hundred dirhams, right?" / "Twenty lakh rupees, right?" (28/30; 2 pre-existing
  correction-flow flakes, flip across the day).
- number: value-first 79% ("Two hundred, right?"). boolean: value-led, varied.
- text: was 100%-locked on "Alright, your <field> is <value>…"; root cause was the code-readback
  FORMATTER mandating field-first + forbidding value-first (overrode the crisp rule above it).
  Removed that mandate → "AB1234, A B 1 2 3 4, that's right?" / "data scientist, yeah?" / Hindi
  "00123, 0 0 1 2 3, सही है ना?". **Alright-opener 85% → 0%, 46/47.** (commit 5af53f8)
- address: standalone crisper ("You're in the United States, right?"); full addresses still read
  back in full (Venky's rule). choice pilot: avg words 9.1→5.2, distinct openers ~18→34.

Report "Follow-up 3" section carries the before/after table + the text deep-dive.
