# Subtle-confirmation training datasets — v3 (2026-07-25)

Contrastive **multi-field** caller/agent conversations teaching the model what a
subtle confirmation sounds like versus a non-subtle (robotic) one. Classification follows
the tagged-transcripts page (`tests/_tagged_transcripts.py`): SUBTLE = choice, boolean,
number, currency, text, address, datetime, contact_screening.

## What changed from v1

v1 conversations were 4-9 turns and collected one field each. That was the wrong shape.
Real calls ask many things in the same conversation, and that is exactly where subtlety
lives: **we cannot ask the same type of question in the same tone to the same user.** One
confirmation can be faked. Fifteen in one call cannot — the agent runs out of templates and
either varies like a person or exposes itself.

v2 overshot at 26-40 turns and 8-11 fields. v3 is the tightened version: every conversation
is a real call segment of **14-22 turns** collecting **4-5 values, five being the ceiling**,
most of them in the file's focus task type. English only this round.

| | v1 | v2 | v3 (current) |
|---|---|---|---|
| turns per conversation | 4-9 | 26-40 | 15-22 (avg 19.5) |
| fields per conversation | 1 | 6-11 | 4-5 |
| total turns | ~1,100 | 5,888 | 3,502 |
| languages | en/hi/hinglish/es | en only | en only |

Four or five confirmations in a row is still enough to expose a template, and with fewer
fields each one has to earn a *different* move, so there is no filler.

## Files (20 conversations each: 10 per label, paired by `pair_id`)

| file | good label | bad label | what the contrast teaches |
|---|---|---|---|
| choice.json | subtle | non_subtle | picks ride into the next question; explicit checks reserved for corrections and unclear options |
| boolean.json | subtle | non_subtle | a run of yes/no is where robots are most audible; most booleans get reflected, not confirmed. Consent booleans stay explicit in both labels |
| number.json | subtle | non_subtle | human number-speak resolved without parsing; fifteen/fifty is the one place a number earns an explicit check |
| currency.json | subtle | non_subtle | amount and unit first, caller's idiom kept (lakh/quid/grand), currency named once, one reason then drop on a refusal |
| text.json | subtle | non_subtle | prose values echoed and passed; **codes/PNRs/policy numbers stay spelled char by char in both labels** |
| address.json | subtle | non_subtle | standalone city/country settle subtly; a full postal address gets ONE consolidated readback with the postcode char by char, not line-by-line confirmation |
| datetime.json | subtle | non_subtle | relative dates resolved aloud (that resolution *is* the confirmation), ambiguity settled in one beat, never double-gated |
| contact_screening.json | subtle | non_subtle | permission, DNC and identity stay explicit in both labels; only the wrapper differs, and dispositions close short |
| credit_card_expiry.json | subtle | strict_required | the conditional rule — see below |

### The credit-card expiry rule

`credit_card_expiry.json` is the one file where **both labels are correct behaviour**. The
contrast teaches *when each applies*, not good versus bad:

- Card number and CVV: always digit by digit, in every conversation of both labels.
- Expiry **unambiguous** ("December 2036", month said as a word) → `subtle`: it settles in
  one beat, folded into the next question.
- Expiry **ambiguous** ("02/01/26", "05/08", a third numeric component in play) →
  `strict_required`: the agent stops, names the problem, offers both readings, and only
  moves on after an unambiguous re-statement as month-word plus full year.

Each `pair_id` is the same payment scenario run twice, once down each branch, so the trigger
is isolated.

## Schema

```json
{
  "task": "...", "tier": "subtle", "description": "...",
  "style_rules": {"subtle": [...], "non_subtle_tells": [...]},
  "conversations": [{
    "id": "task_01_subtle", "pair_id": "task_01",
    "label": "subtle | non_subtle | strict_required",
    "language": "en",
    "scenario": "business context and the friction in this call",
    "fields": [{"name": "cabin_class", "value": "business", "tier": "subtle",
                "strategy": "one-beat correction, then echo into the seat question"}],
    "turns": [{"speaker": "agent", "text": "...", "tier": "strict"}],
    "notes": "why this reads human / which tells make it robotic"
  }]
}
```

- `fields` is required on correct-label conversations; `strategy` names the confirmation
  move used for that value, which is the training signal.
- `tier: "strict"` on a turn marks a verbatim-readback line and exempts it from the
  humanness checks. `tier` on a *field* records what the field itself demands.
- Caller turns are held essentially identical across a pair, so the only delta the model
  sees is the agent's wording.

## The confirmation moves a subtle call rotates through

Echo-and-advance (fold the value into the next question, no round trip — the default and
most common); bare value-as-question ("Business, yeah?" — for corrections and unclear
values); silent accept (just move on, for values stated emphatically or already repeated);
deferred confirmation inside a closing summary rather than on the spot; one-beat correction
(re-echo the new value and go). A good conversation uses four or five of these in one call.

Enforced mechanically: an agent turn's first word repeats at most twice per conversation and
never in consecutive agent turns; each check tag ("right?", "yeah?", "correct?") at most
twice per conversation; at least two agent turns carry no tag at all.

## Fidelity boundaries the datasets deliberately DO NOT soften

Codes, PNRs, policy and order numbers spelled character by character. Full postal addresses
read back complete, postcode char by char. Email spelled letter by letter, symbols named.
Phone digit by digit in groups. Card number and CVV digit by digit. Consent,
permission-to-continue and do-not-call explicit in both labels.

Sixteen conversations across the set are **wrong-direction bad examples**: the agent is warm
and casual but *drops* one of these floors (skips a code spell-out, omits the unit number,
assumes consent, lets "a few" stand unresolved). Their `notes` say "wrong-direction". They
exist so the model learns subtle ≠ sloppy.

## Validation

`python3 validate_datasets.py` checks schema, 10/10 label split, pair integrity, English
only, turn range (14-22), field count (4-5), caller-turn parity across pairs, opener repetition,
check-tag caps, untagged-turn floor, and bans em dashes, praise slop, status phrases
(noted / recorded / saved / captured / registered / on file / in the system), "I heard" and
chatbot closers from correct-label agent turns; robotic twins must show at least three tells
(wrong-direction examples are exempt, since their error is the opposite).

All 9 files pass. 180 conversations, 3,502 turns.
