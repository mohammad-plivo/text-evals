# Subtle Confirmations — experiment context

**Started:** 2026-07-21 (evening IST) · **Owner:** Mohammad · **Driver:** Claude
**Working dir:** `Agent Runner/subtle tasks/`

---

## The idea (verbatim intent, from Mohammad)

After almost every collection task the agent runs a **confirmation** step — that's how we
know the agent captured the right thing (and can improve if it didn't). We want these agents
to sound **as human as possible, within constraints**:

- **A few fields must be confirmed word-by-word / character-by-character** — credit-card number,
  name, phone number, email, and similar — because there can be **zero** mistakes in those.
- **Everything else should be subtle and human.** Today the confirmation is very un-subtle:
  robotic → *“I heard United Kingdom, is that right?”*. A human version →
  *“United Kingdom, okay got it!”*
- **And it must vary.** If the agent has to confirm something else soon after, it must NOT reuse
  the same phrase (“got it” twice in a row is just a different flavour of robotic).

Hard rule from Mohammad: **we do NOT replace our tasks/skills with LiveKit’s own tasks** —
LiveKit’s are too basic. All work is on **Plivo’s own `cx-skills` tasks**.

## Constraints / why this directory exists

- **Another chat is already running instruction tweaks** on the live cx-skills instructions.
  Editing the same files here would collide. So this experiment works on an **isolated copy**.
- **Fix surface = task instruction-template text** (the `INSTRUCTIONS_TEMPLATE` /
  `CONFIRMATION_INSTRUCTION` prose inside each `tasks/*.py`, and the per-value render logic).
  Same doctrine as the 31B campaign: prompt/text only.
- Keep this directory as a **self-contained experiment log** (mirrors `31B-Experiments/`):
  timestamped `YYYY-MM-DD_HHMM/UPDATE.md` folders, updated hourly while work is active.

## The isolated sandbox

- `cx-skills-subtle/` — full copy of pristine `repos/cx-skills` @ commit `ec8b057`
  (the clean upstream original — same base the 31B campaign forked from).
  Branch `subtle-confirmations`, **git remote removed** (cannot push, cannot collide).
  `git diff ec8b057` here = exactly our confirmation tweaks.
- The other chat's work lives elsewhere (`31B-Experiments/cx-skills-gemma31b/` and/or the live
  repo); nothing here touches it.

## The classification (what gets which confirmation style)

Full grounded + adversarially-verified table:
**https://glance.plivo.com/mohammad-kadiri/confirmation-fidelity**

Four styles. **Fidelity is a property of the field, not the task** — most tasks can hold a
trivial value OR a consequential/regulated one, so each has a default + an escalation trigger.

| Style | When | Example |
|---|---|---|
| **Strict verbatim** | one wrong token is invisible & unrecoverable | “w r e n, at, g-mail dot com — right?” |
| **Value readback** | wrong = costly but not a spelled identifier | “September 6th at 10:15 in the morning — sound right?” |
| **Subtle human ack** | low error-cost / easily corrected / self-evident | “United Kingdom — got it.” |
| **Explicit consent** | legal/compliance; cannot be softened | “Just so I have it — you’re okay to continue? … Great.” |

**Can be subtle:** Choice, Boolean (preference), Number (low-stakes), Text (notes),
Address (city/country), DTMF (menu), IdentifyContact (benign closes).
**Must stay strict:** Email, Phone, Card/CVV (always); DOB, DateTime, Currency, Expiration,
Name-spelling, spelled-code Text/DTMF (value-readback minimum, never a bare “got it”).
**Explicit consent:** GetPermissionToContinue + any consent/DNC boolean.

## Critical caveat (do not soften blindly)

- Every task **except email** can have confirmation turned **off** by config; card/CVV/DOB/
  consent booleans have **no code-level floor**. Every task **defaults to no confirmation on
  text/chat** unless `require_confirmation=True`.
- So humanness must live **only in the wrapper sentence** — never by dropping the value or the
  explicit “yes.” A global “sound less robotic” tweak would ship silent-commit bugs on payments
  and consent.
- Anti-repetition machinery already exists: `_readback_count` / `repeat_note` vary-blocks force
  each re-read to shorten + change opener; `LK_AGENT_TEMP=0.7` was set partly to fight gpt-4.1
  re-emitting identical sentences.

## Method

1. Start narrow: **CollectChoice** (the “United Kingdom” poster child) as proof-of-concept.
2. Tweak its confirmation prose toward a warm, varied, value-anchored acknowledgment.
3. Run its eval suite → check (a) does it stay green, (b) do transcripts read human/varied,
   (c) does any **frozen** scenario/judge actually *require* the old robotic phrasing (the real
   tension — the frozen contracts may encode the current behavior).
4. If the loop works, expand to the rest of the subtle tier. Never touch the strict tier’s
   verbatim readback except to vary its surrounding sentence.

## Open decisions (pending Mohammad)

- **Agent under test:** Gemma-31B (LiveKit hosted, matches active campaign) vs GPT-4.1 (Azure,
  production path). Caller/judge default to Azure gpt-4.1-mini / gpt-5.5-1 (creds on hand).
- **Success bar** when a subtle edit collides with a frozen deterministic pin: note-and-flag the
  frozen contract, or keep the field strict. (Handling empirically first — run Choice, report.)

## Pointers

- Fork base: `Agent Runner/repos/cx-skills` @ `ec8b057` (clean).
- Reusable harness/creds reference: `Agent Runner/31B-Experiments/` (`.env`, `run_env.sh`,
  `run_baseline.sh`, `aggregate.py`).
- Confirmation-fidelity dossier: glance `mohammad-kadiri/confirmation-fidelity`.
