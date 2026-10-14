# Writing v2.10 AI node instructions

A guide for the Vibe agent, and for anyone who writes the Instructions of an `ai_agent_v2` node on a flow that runs on v2.10. It says how to write the Instructions so that Jev and gpt-5.6-luna make the right variables on the first fill, and keep them right after an edit.

Every rule here was measured against the real services: Jev (`jev-1.13.0`) and gpt-5.6-luna on the dev runner. Section 8 says how, and the appendix holds the 23 example flows with their results.

Status on 14 Oct 2026:

- The runner side (fill, descriptions, and the edit questions) is on main and on dev (agent-runner #651).
- The builder sends an edit as an edit, the old text with the new one, only with cx-console #4144. It is open on main and merged to dev as #4146. Without it the builder reads the whole text again on every change.
- Open decisions are on [their own page](https://glance.plivo.com/mohammad-kadiri/v210-vibe-guide-questions).

## Contents

1. [What changes on v2.10](#1-what-changes-on-v210)
2. [How the Variables tab is made](#2-how-the-variables-tab-is-made)
3. [Rules for the first fill](#3-rules-for-the-first-fill)
4. [Rules for an edit](#4-rules-for-an-edit)
5. [What the Vibe agent must do differently](#5-what-the-vibe-agent-must-do-differently)
6. [What wording does not fix](#6-what-wording-does-not-fix)
7. [Reference: types, settings, saved shape](#7-reference-types-settings-saved-shape)
8. [How this was checked](#8-how-this-was-checked)
9. [Appendix: 23 example flows](#appendix-23-example-flows)

## 1. What changes on v2.10

A flow runs on v2.10 when its row carries `phlo.attributes.agent_engine_version: "v2.10"`. Since 13 Oct 2026 a new flow gets this stamp when it is created (cx-console #4145, cx-phlo-config-service #417). Older flows keep what they have until someone changes it in the database. The stamp changes only `ai_agent_v2` nodes, and only on voice calls. Chat and SMS still run them as V2.

| | V2 (no stamp) | v2.10 (stamped, voice) |
|---|---|---|
| What a variable is | A value the Scribe pulls out of the transcript after the node ends. | A question to the caller. One typed collector per variable asks, checks, confirms and stores the value during the call. |
| Who writes the variables | The author, by hand: a name and a line of instructions. | Jev reads the Instructions and makes one row per value, with its type and settings. gpt-5.6-luna writes each row's description and a real name. The author can change any field; with #4144 a changed field is never overwritten. |
| Saved per variable | `variable_name`, `variable_instructions`, and format keys nothing reads. | The same, plus `collection` (section 7). |
| What the node's model sees | Nothing about variables. | Every variable with its description and settings. Jev picks each step: one `collect <name>` per variable, each action, each handoff, or only speaking. |
| What a collector reads | (no collectors) | Only its own variable's description and settings. It never sees the node Instructions. |
| Required values | Whatever the Instructions say. | `required` is on unless the text makes the value optional. A refusal is asked about once more, then left. The node's first exit is refused once while a required value is missing. |
| When a value is stored | At the handoff or hang-up. | The moment its collector finishes, as `{{Node.<variable_name>}}`. A value the caller only mentions in passing is never stored. |
| Value format | Whatever the Scribe wrote. | Fixed per type: a name as "First Middle Last", a date as `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`, a yes/no as `yes` or `no`, a digit code as digits, money as `INR 500 per month`, a choice as its option text. |

## 2. How the Variables tab is made

The Instructions are the only input. Nothing else about the node reaches Jev or Luna.

**First fill.** The builder runs it when the Instructions box loses focus, or when the Variables tab opens, and the text has changed.

1. Jev reads the whole Instructions. For each of the 12 types it answers three things: is a value of this type asked for, how many (one, two, three), and each setting of that type. It never sees variable names.
2. The runner makes one row per value. Its first name is the type (`phone`, `date_1`, `date_2`), and its type and settings come from Jev's answers.
3. gpt-5.6-luna then writes each row's description and a real name (`patient_date_of_birth`). It gets the Instructions and one row at a time, with the other rows' names.

**Edit** (a node that was filled before; needs #4144):

1. Jev gets the old text, the new text, and the node's variables with their descriptions. It answers whether the edit changes what is asked, then for each variable: the same, changed, or no longer asked.
2. Jev also reads the old and the new text as in a first fill. A type the new text asks for more often than the node holds becomes a new variable.
3. A changed variable gets Jev's new settings. A variable no longer asked is removed. A new one gets its name and description from Luna. Jev only acts on answers it is sure of.
4. A field the author changed by hand is kept.

**Who reads what:**

| Reader | Reads | Does not read |
|---|---|---|
| Jev, fill | the Instructions | names, descriptions |
| Jev, edit | old and new Instructions; each variable's name, type and description, and which fields the author set | the variables' settings |
| gpt-5.6-luna | the Instructions, one row's type and settings, the other rows' names, and their descriptions once they have them | anything outside this node |
| The collector, on the call | its own variable's description and settings | the node Instructions |

So a rule that lives only in the Instructions reaches the call only if Jev turns it into a setting or Luna puts it into the description. The rules below are about writing the Instructions so that both of them read each value right.

## 3. Rules for the first fill

The numbers come from Jev reads of the same text, five reads per wording unless said otherwise. "Exact" means Jev found exactly the values the text asks for, no more and no fewer.

### R1. One value per STEP, with a title that names it

Keep the Vibe template: `STEP n: TITLE`, then the line that asks, then its `If ... ->` lines. The titles help Jev count.

- With titles, the 24 first-draft flows read exact in 38 of 72 reads. With the titles blanked, 28 of 72. With the STEP lines removed, 23 of 72.

### R2. Say the kind of value in its plain word

Use the word the type is about: phone number, email address, date of birth, date, time of day, how many, how much (for money), which of these (for a list).

```md
WRONG  - Ask for a mobile number for the reminder text.
RIGHT  - Ask for the caller's phone number for the reminder text.
```

The first found no phone value in 5 of 5 reads. The second found it in 5 of 5.

### R3. A fixed list: "which of these", the options, then whether to read them aloud

```md
WRONG  - Ask what the caller noticed: lights out, flickering lights, a loud bang, or sparks.
RIGHT  - Ask which of these the caller noticed: lights out, flickering lights, a loud bang, or sparks.
```

The first was also read as a free-text value in 5 of 5 reads. The second in 0 of 5.

```md
WRONG  - Ask for the caller's employment status: full-time, part-time, self-employed, retired, or not employed. Do not read the list aloud; match what the caller says.
RIGHT  - Ask which of these describes the caller's employment: full-time, part-time, self-employed, retired, or not employed. Do not read the options aloud.
```

"Match what the caller says" added a free-text value in 5 of 5 reads. "Match their answer to ..." in a survey made Jev miss the list altogether (4 of 4).

Write every option in the Instructions. The fill never saves the options; the node passes the list it finds in the text at call time.

### R4. An optional value: "This is optional; if they do not want to give one, skip it."

```md
WRONG  - Ask for an email address to send the arrangement terms to. This is optional; if the caller declines, say the terms will be mailed.
RIGHT  - Ask for an email address to send the arrangement terms to. This is optional; if they do not want to give one, skip it.
```

A decline that leads to something else reads as one more yes/no question: two yes/no values in 5 of 5 reads, against one in 5 of 5. The email stayed optional in 3 of 3 dev runs. Asking for a value only on some paths ("Only if they chose home delivery, ask for the delivery address") also makes it optional.

### R5. Ask for a time of day in the same step as its date

A date value covers "a calendar date or time", so a time asked in its own step reads as a second date.

```md
WRONG  STEP 4: NEW DATE
       - Ask for the new departure date. It must be a future date, and today is not allowed.
       STEP 5: TIME OF DAY
       - Ask which part of the day they prefer: morning, afternoon, or evening.

RIGHT  STEP 4: NEW DATE
       - Ask for the new departure date. It must be a future date, and today is not allowed. Then ask whether they prefer a morning, afternoon, or evening flight.
```

Two dates in 5 of 5 reads, against one date in 5 of 5.

### R6. A side condition describes a situation, not something the caller says

`If ... ->` lines and HANDLING blocks are read too. "If the caller says [a fact]" reads as a value the caller gives.

```md
WRONG  - If the caller says the medicine is a controlled substance -> explain that the patient must bring a new paper prescription to the store.
RIGHT  - If the medicine is a controlled substance -> explain that the patient must bring a new paper prescription to the store.
```

Exact in 0 of 5 reads (an extra free-text value every time), against 5 of 5. A caller's question is fine as it is: "If the caller asks about interest rates -> ..." caused no extra value in any flow.

### R7. A safety check that applies at any point goes in General Instructions

Emergencies and other checks that can come up anywhere in the call belong in the `## General Instructions` section above `## Instructions`, written as "If [X] comes up at any point, [do Y]." In a HANDLING block at the bottom, Jev reads them as a yes/no question ("does the caller have chest pain?") or as free text.

```md
WRONG  HANDLING URGENT SYMPTOMS:
       - If the caller describes chest pain, trouble breathing or heavy bleeding -> tell them to hang up and call emergency services now.

RIGHT  ## General Instructions
       - If chest pain, trouble breathing or heavy bleeding comes up at any point, tell the caller to hang up and call emergency services now.
```

Six reads each, exact: the clinic flow 5 of 6 with the HANDLING block and 6 of 6 at the top; the dental flow 4 of 6 and 6 of 6. As a Boundaries line ("Never continue when ...") it was 3 of 6. Other phrasings inside a HANDLING block ("If the patient has ...", "If the caller brings up ...") all let an extra value through in some reads. On dev, before the move the clinic flow got an extra "urgent symptom present" yes/no in 2 of 3 runs and the dental flow a second free-text value in 3 of 3; after it, 0 of 3 and 1 of 3.

### R8. A digit code: the exact number of digits, keyed on the keypad

```md
WRONG  - Ask the caller to say or key in their order code. It is exactly 8 digits.
RIGHT  - Ask the caller to enter their 8-digit order code on the keypad.
```

Exact in 1 of 5 reads (a second free-text value in 4 of 5), against 5 of 5. Without a digit count, or with one outside 3 to 12, the value becomes free text.

### R9. At most one free-text value per node

Jev counts free text once. A node that asked for a policy number with letters and for a description of what happened got one free-text value in 10 of 10 reads (two wordings). A node that asked for a company name and for dietary needs got one in 20 of 20 (four wordings).

- If you need a reference code, make it digits and keyed (R8), or move the second free-text value to another node.
- A keyed patient ID in the same node as a free-text reason was counted as a second free-text value (5 of 5). Asking for the patient's date of birth instead read exact in 5 of 5.

### R10. Avoid two values of the same type in one node

Jev reads each setting once per type, so both values share every setting. gpt-5.6-luna then often describes both as the same value. From the dev runs:

- A missed visit's date (may be in the past) and a new date (must be in the future): both got "must be a future date", Luna described both as the new date, and the second kept the name `date_2` (3 of 3 runs).
- The patient's name and the referring doctor's name: the second was described as the patient (3 of 3).
- A loan amount and an income "per month or per year": the loan amount also had to be given per month or per year (3 of 3).

Two values of one type worked when they share every rule: hotel check-in and check-out dates were right in 3 of 3 runs, and a survey's two plain yes/no questions in 2 of 3.

### R11. Say a confirmation once, on the value it belongs to

```md
WRONG  - Spell the last name back letter by letter and ask them to confirm it.
RIGHT  - Spell the last name back letter by letter.
```

"And ask them to confirm it" read as one more yes/no value in 5 of 5 reads, and in 0 of 5 without it. The collector confirms a spelled name by itself.

### R12. Use the setting words Jev knows, and only when they are true

The table in section 7 lists them. Two that surprised:

- "They must say which currency it is in." on a required value turned the setting on in 5 of 5 reads. "The currency must be stated. This is optional ..." left it off in 5 of 5.
- "Ask for their average monthly electricity bill in dollars." turned "must say the currency" on (5 of 5), so the caller would be asked which currency. Name the currency only when the caller must say it.

A date accepts past dates unless the text says it must be in the future.

### R13. List only values the caller gives

Every variable is a question on the call.

- No values worked out from other values (a country from the phone number, a lead score).
- No values the agent says. "Tell the caller the overdue balance" is fine as an instruction, but gpt-5.6-luna may describe the money variable as that balance (section 6, G1).

## 4. Rules for an edit

Results on dev, 86 edits run 3 times each against the filled node: a rewording was right in 64 of 69, a changed rule in 55 of 63, an added value in 49 of 63, a removed value in 40 of 63.

### E1. Get the first fill right first

Its mistakes carry into every edit. When the first fill and the descriptions were right, edits were right in 161 of 181. When they were not, in 47 of 77. On the first drafts the split was 111 of 135 against 78 of 135.

### E2. Change a rule by rewriting its line in place

Keep the step and its title.

```md
BEFORE - Ask for an email address for the appointment reminder. This is optional; if they decline, skip it.
AFTER  - Ask for an email address for the appointment reminder. It is required for every new patient.
```

Jev marked the email as changed, and nothing else, in 3 of 3 runs.

### E3. To stop asking for a value, delete its whole step

Delete the title, the line that asks, and its `If ... ->` lines. Then remove other mentions of the value. Removals are the weakest kind of edit (40 of 63), for two reasons:

- Jev's "no longer asked" answer is often just under the line where it counts as sure. Removing the callback-number question from the insurance flow was caught in 1 of 3 runs. Removing a blood-thinner question was caught in 1 of 3 runs in one full run and 3 of 3 in the next.
- If the new text still reads as a value of that type somewhere else, nothing tells the runner the value went. Removing the vehicle question from the car-service flow was caught in 0 of 3 runs in both full runs: another line still read as free text.

### E4. To add a value, add a new step that follows section 3

New values of a type the node does not have yet were found reliably (email, phone, choice, yes/no, number). Two cases were not:

- Adding a mobile number to a node that asks for a 10-digit account number gave two phone values (3 of 3 runs).
- Adding a keyed member ID to a node with a letters-and-digits referral code gave two digit codes (3 of 3).

### E5. Do not change a value's type by rewording it

Delete its step and add a new one. When Jev cannot tell which new value an old one became, the runner removes the old variable and adds a new one, and the old name is gone.

### E6. Rewording and reordering are safe

64 of 69 rewordings left every variable alone. The two that also moved steps were right in 4 of 6 runs.

## 5. What the Vibe agent must do differently

These facts come from aiassist main `7f300460` (`usecases/vibe_agent`) and agent-runner main. They were read from the code, not watched on a live flow.

**It cannot see the stamp.** No Vibe code reads or writes flow `attributes`, and a new flow is stamped when it is created. Treat every AI node you write as v2.10 on voice.

**A variable is a question.** `extract_variables` rows become collect steps. The schema text "Variables to extract from conversation" and the rule that derived variables are valid no longer hold on v2.10 (R13).

**Per-value rules belong in the step that asks for the value.** The collector reads only its own variable: its settings, which Jev reads from the text, and its description, which Luna writes from the text. Put a format, a limit or a confirmation in the step that asks for the value, so both of them tie it to that value.

**Today it cannot keep typed variables.**

- Its rows carry only `variable_name` and `variable_instructions`. The normalizer rebuilds the whole node from a fixed list on every AI-node edit, so `collection` (the type and settings the builder filled) is dropped the first time the Vibe agent touches the node. So are `model_config`, `knowledge_base_ids` and `leader_profile`.
- The builder treats a node whose rows have no type as never filled. On the next Instructions blur it runs a first fill and adds typed rows next to the old rows, so every value appears twice. With #4144 there is no delete button on v2.10.

**Until that changes:**

1. For a new AI node, write the Instructions by this guide and leave `extract_variables` empty. Tell the user to open the node once in the builder (click in the Instructions box and out again, or open the Variables tab), check what Jev and Luna filled, and save.
2. Make Instruction edits to an existing v2.10 AI node in the builder, not through the Vibe agent, so Jev reads the change as an edit.
3. If a node already has duplicates: with #4144, clearing the Instructions box removes every variable, and pasting the text back fills them again from scratch. Names can change, so check the references in later nodes.

**What it would take to do this from the Vibe agent** (code, not wording):

- A tool that calls the runner's `POST /v1/collection-configuration/suggest` the way the builder does: a first fill (`propose_inputs: true`, `engine: "jev"`), then `describe: true` for the new rows; for an edit, `previous_instructions` with the current rows and their `collection`. The `auth_id` goes in the body. Strip `source`, `passes` and `dropped_settings` before saving.
- A normalizer and schema that keep `collection` on rows the Vibe agent did not change.
- A v2.10 block in `review_guidelines.md`, which today still asks for "## Persona" and "## Languages" sections the builder prompt forbids.

## 6. What wording does not fix

These come from the runner or the builder. The guide's rules work around some of them. Each ends with a possible fix. None of the fixes is built; only the two-pass describe in G1 was tried, by calling the dev runner twice per node.

**G1. Luna describes each row on its own, and open types get mixed up.** Each row is described in a separate call that sees the other rows only by name. A row whose type fits many parts of the text (free text, a choice, money, a number) is often matched to the wrong one. In the final dev run, 7 of the 23 flows had such a row:

| Flow | Value | Described as | Runs |
|---|---|---|---|
| Pharmacy refill | tablets left (number) | the prescription number | 3 of 3 |
| Debt promise to pay | promised amount (money) | the overdue balance the agent states | 3 of 3 |
| Payment arrangement | down payment (money) | the past-due balance the agent states | 3 of 3 |
| Flight change | morning, afternoon or evening (choice) | the change-fee question | 3 of 3 |
| Conference registration | company (free text) | the attendee's name | 3 of 3 |
| Car service | make and model (free text) | a summary of every value, or "what they want to book" | 3 of 3 |
| Lab booking | referral code (free text) | a summary of every value, or the patient's name | 2 of 3 |

The edits of those values then fail too (E1). A second pass fixes part of it: describing the specific types first (name, phone, email, date of birth, date, address, digit code), then the open types with those descriptions in view, fixed the pharmacy and conference rows (3 of 3 each, read by hand). The other five stayed wrong. Wording did not get round it: "Then ask which of these flight times they prefer: morning, afternoon, or evening." fixed Luna's description of the flight-change choice (3 of 3) but made Jev read two dates again, and no wording kept Luna off a balance the agent states.

Possible fix: describe in two passes as above (fixed 2 of the 7), or in one call per node that sees every variable at once. The one call is not tried; it could also write a choice's options, which nothing writes today. Also not tried: tell Luna what each type means (the collect tools' own one-line definitions), and that a value the agent says to the caller is never the value to collect.

**G2. Settings are read once per type.** Two values of one type always share every setting (R10). Possible fix: when a type has two values, ask the setting questions per value, naming each value's line.

**G3. Jev sometimes counts one value twice.** Wording did not fix these:

- Solar qualification: the monthly electricity bill read as money and as a number. In each of 15 wordings that ask for the bill as an amount, most reads found a number value as well. This flow is out of the example set for that reason.
- A phone question next to a 10-digit account number: two phone values (3 of 3 runs in both full runs; 14 of 15 reads across three wordings, including an 8-digit code).
- A keyed digit code next to a letters-and-digits code: two digit codes (3 of 3 runs in both full runs; one wording tried).

In the first-draft dental flow Jev counted two numbers in 5 of 5 reads, yet asked which line held the second request it answered "none" (0.64). Possible fix: confirm a second value of a type with that question before adding a row for it.

**G4. A read-back rule spreads to other types.** "Read the prescription number back digit by digit and ask them to confirm it" also turned on read-back for the tablet count (5 of 5 reads), which then helped Luna mistake the count for the prescription number (G1). A consent question's "Repeat their answer back and confirm it" turned it on for the employment choice too (5 of 5). The per-type setting questions do not say which value a rule belongs to. Possible fix: the same as G2.

**G5. Luna keeps some placeholder names.** In the final run `name` stayed in 8 of 69 runs (3 of 3 in the clinic flow), `text` in 4, `dtmf` in 3 (Luna had given `prescription_number` to the wrong row first), and `text_2` in 3 (a value counted twice). The prompt says to replace a name that only repeats the type; for a person's name, `name` does not look like a placeholder to it. Possible fix: name these cases in the prompt, or treat a returned name equal to a type as no answer.

**G6. Removals are often unsure.** See E3. Possible fix: when the old text reads a type and the new text reads none of it, drop the only variable of that type even when Jev's per-value answer is unsure.

**G7. The builder drops `readback` from free text on save.** Jev sets "read it back character by character" from the text, and the runner keeps it, but the builder's save leaves the key out. A booking reference or a policy code then loses its read-back after the first save. Possible fix: keep `readback` in the builder's save.

## 7. Reference: types, settings, saved shape

### The 12 types

| Type | Collects | Not this |
|---|---|---|
| `name` | A person's name, whole or in parts. | A company or a place (text or address); a nickname (text). |
| `phone` | Any telephone number. | |
| `email` | An email address. | |
| `address` | A postal address, or the parts asked for. City only is still an address. | |
| `date` | A calendar date, with or without a time of day. | A birth date (`dob`). |
| `dob` | A date of birth. | Any other date. |
| `currency` | An amount of money. | A plain count (`number`). |
| `number` | A count or a measure. | Money (`currency`); a code with leading zeros (`dtmf`). |
| `dtmf` | A digit code the caller keys or says: a PIN, last digits, an order or patient ID made of digits. Needs its exact length. | A count (`number`); a reference with letters (`text`). |
| `text` | Free words: a reason, a description, what happened, a note, a reference with letters, a nickname. | Anything that has its own type. |
| `choice` | One option, or several, from a fixed list. | A yes/no question (`boolean`). |
| `boolean` | A yes or no answer to one question. | |

### Settings Jev can set, and the words that set them

Jev sets a setting only when the Instructions state it plainly. Otherwise the default applies. Settings are read once per type (G2).

| Type | Setting | Default when not stated | Say this to set it |
|---|---|---|---|
| every type | `required` | on | "This is optional; if they do not want to give one, skip it." Asking only on some paths also makes it optional. |
| `name` | `first_name`, `last_name`, `middle_name` | first and last on, middle off | "Ask for their first name only." "Ask for their first, middle and last name." |
| `name` | `spell_back` | off | "Spell the last name back letter by letter." |
| `phone` | `vanity` | on | "Digits only, no letters." |
| `date` | `accept_past` | past dates accepted | "It must be a future date." For a past date: "the date it happened". |
| `date` | `accept_today` | today accepted | "Today is not allowed." |
| `date` | `require_time` | off | "and they must give a time of day" |
| `dob` | `require_time` | off | "Also ask for the time of birth; it is required." |
| `currency` | `required_currency` | off | "They must say which currency it is in." (on a required value, R12) |
| `currency` | `required_period` | off | "They must say the period it covers, such as per week or per month." |
| `number` | `allow_decimal`, `allow_negative` | decimals left to the collector, negatives refused | "It must be a whole number." "Decimals are allowed." |
| `number`, `choice`, `boolean` | `require_confirmation` | off | "Read it back and ask them to confirm it." (spreads to other types, G4) |
| `dtmf` | `num_digits` | none: without it the value becomes free text | "Ask the caller to enter their 6-digit patient ID on the keypad." |
| `dtmf` | `ask_for_confirmation` | off | "Read the digits back to confirm." |
| `text` | `uppercase` | off | "Record it in capital letters." |
| `text` | `readback` | none | "Read it back character by character." (lost on a builder save, G7) |
| `choice` | `multiple` | one pick | "They may pick more than one." |
| `choice` | `present_options` | options read aloud | "Read the options aloud." / "Do not read the options aloud." |

The fill never reads address parts from the text: a filled address asks for street, city and country unless the author changes "Fields to collect".

### What a filled variable looks like when saved

```json
{
  "variable_name": "new_departure_date",
  "variable_instructions": "Ask for the new departure date. It must be a future date; today is not allowed.",
  "collection": {
    "type": "date",
    "options": {"accept_past": false, "accept_today": false, "require_time": false},
    "choices": null,
    "choices_from_call": false,
    "num_digits": null,
    "spell_back": null,
    "readback": null,
    "fresh_question": false,
    "required": true,
    "instructions": null,
    "version": null
  }
}
```

- `choices_from_call` is true for every filled choice: the node reads the options from the Instructions at call time.
- `num_digits` is set only for `dtmf`, `spell_back` only for `name`, `readback` only for `text`.
- Names are lowercase snake_case. The value is stored as `{{<node name>.<variable_name>}}`.
- An empty or partial `collection` fails that variable for the whole call. Leave `collection` out rather than write part of one.

## 8. How this was checked

**Jev reads.** The fill questions only, sent from the local engine, whose code for this path is the same as main and dev, to the same Jev model (`jev-1.13.0`). Each wording was read 3 to 6 times, about 2,000 reads in all. This is where the WRONG/RIGHT numbers come from.

**The whole path on dev.** The dev runner's `POST /v1/collection-configuration/suggest`, with real Jev and gpt-5.6-luna, sending what the builder sends: a first fill, the descriptions and names, then each edit on its own against that filled node. Three runs per flow.

| | First drafts (24 flows) | After the rules (23 flows, final run) |
|---|---|---|
| First fill right (types and settings) | 36 of 72 runs | 61 of 69 runs |
| Names with no placeholder, all different | 66 of 72 runs | 53 of 69 runs |
| Each value described as itself | not checked | 370 of 393 values |
| Edits right | 189 of 270 | 208 of 258 |

"Described as itself" was checked by Luna's name, or for a placeholder name by its description, and confirmed by reading every description of the final run. Most of the 23 misses are the seven rows in G1.

Two caveats on these numbers:

- Run-to-run noise is a few points. A full run earlier the same afternoon, with the same texts except the safety lines still in HANDLING blocks, gave 61 of 69, 60 of 69, 372 of 393 and 219 of 258.
- Jev's reads drift between batches, and the runs of one flow move together. The delivery flow, unchanged between those two runs, read one free-text value in 3 of 3 runs the first time and two in 3 of 3 the second. Trust the totals more than any one flow's line.

Not tested: real calls, chat and SMS, the builder screen itself, edits of fields the author changed by hand, languages other than English, nodes with more than 7 values.

**Files, next to this guide:**

- `bench.py`: runs the flows on dev (`run`), scores them (`score`), and prints this appendix (`examples`). Needs the Primary VPN.
- `flows.json`, `results.json`: the 23 flows and their dev results.
- `flows_draft.json`, `results_r1.json`: the first drafts and their dev results.
- `probe.py`: Jev's fill reads for any set of texts, run inside the local engine. The WRONG/RIGHT numbers come from it.

```sh
python3 bench.py run flows.json results.json --runs 3
python3 bench.py score flows.json results.json
python3 bench.py examples flows.json results.json
```

## Appendix: 23 example flows

Each flow follows the rules above. The numbers are from the final dev run, three runs per flow. "Described right" counts runs where Luna's name (or, for a placeholder name, its description) named that value. Each edit was applied on its own to the node filled in that run.

### A1. clinic-new-patient

```md
## General Instructions
- If chest pain, trouble breathing or heavy bleeding comes up at any point, tell the caller to hang up and call emergency services now.

## Instructions
Book a first visit for new patients calling the clinic.

STEP 1: PATIENT NAME
- Ask for the patient's first and last name. Do not ask for a middle name.
- Spell the last name back letter by letter and let the caller correct it.

STEP 2: DATE OF BIRTH
- Ask for the patient's date of birth.

STEP 3: PHONE
- Ask for the best phone number to reach the patient.

STEP 4: REASON FOR VISIT
- Ask for the main reason for the visit, in the caller's own words.

STEP 5: CLINIC LOCATION
- Ask which location they prefer: Downtown, Riverside or Hillcrest. Read all three options aloud.

STEP 6: PREFERRED DATE
- Ask for the preferred appointment date and time of day. It must be a future date, and they must give a time.
- If they only give a date -> ask for a time on that date.

STEP 7: EMAIL
- Ask for an email address for the appointment reminder. This is optional; if they decline, skip it.

## Boundaries
- Never give a diagnosis or medical advice.
- Never ask for insurance or payment details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on, middle_name off, spell_back on | `name` | 3 of 3 |
| 1 | dob | defaults | `date_of_birth`, `patient_date_of_birth` | 3 of 3 |
| 2 | phone | defaults | `patient_contact_phone`, `best_reach_phone` | 3 of 3 |
| 3 | text | defaults | `visit_reason` | 3 of 3 |
| 4 | choice | present_options on | `preferred_clinic_location`, `clinic_location_preference` | 3 of 3 |
| 5 | date | accept_past off, require_time on | `preferred_appointment_datetime`, `preferred_appointment_date_and_time`, `preferred_appointment_date` | 3 of 3 |
| 6 | email | required off | `appointment_reminder_email` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| email becomes required | changes #6 | 3 of 3 |
| drop date of birth | drops #1 | 1 of 3 |
| add referral question | adds boolean | 3 of 3 |

### A2. clinic-followup-reschedule

```md
## General Instructions
- If worse symptoms come up at any point, advise the caller to contact their doctor or urgent care today.

## Instructions
Reschedule follow-up appointments for existing clinic patients who cannot make their booked visit.

STEP 1: PATIENT NAME
- Ask for the patient's full name.

STEP 2: DATE OF BIRTH
- Ask for the patient's date of birth to find their record.

STEP 3: NEW DATE
- Ask for the new date they would like. It must be a future date and cannot be today.
- If they ask for a weekend -> explain the clinic is closed on weekends and ask for a weekday.

STEP 4: REASON
- Ask why they need to reschedule. This is optional; if they would rather not say, move on.

HANDLING A CANCELLATION:
- If the visit should be cancelled rather than moved -> tell the caller to call the front desk to cancel it.

## Boundaries
- Never change the doctor or the visit type.
- Never give medical advice.
- Never ask for payment details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `patient_full_name`, `name` | 3 of 3 |
| 1 | dob | defaults | `patient_date_of_birth` | 3 of 3 |
| 2 | date | accept_past off, accept_today off | `new_reschedule_date`, `new_follow_up_date` | 3 of 3 |
| 3 | text | required off | `reschedule_reason` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| new date may be today | changes #2 | 3 of 3 |
| add contact phone number | adds phone | 3 of 3 |
| drop reason for rescheduling | drops #3 | 3 of 3 |

### A3. pharmacy-prescription-refill

```md
## Instructions
Take prescription refill requests for pharmacy customers over the phone.

STEP 1: PATIENT NAME
- Ask for the patient's first and last name.

STEP 2: DATE OF BIRTH
- Ask for the patient's date of birth to find their record.

STEP 3: PRESCRIPTION NUMBER
- Ask the caller to key in the 7-digit prescription number printed on the bottle label.
- Read the prescription number back digit by digit and ask them to confirm it.

STEP 4: SUPPLY LEFT
- Ask how many tablets they have left. It must be a whole number.
- If they have none left -> tell them the pharmacist will treat the refill as urgent.

STEP 5: PICKUP OR DELIVERY
- Ask how they want to receive the refill: store pickup or home delivery.

STEP 6: DELIVERY ADDRESS
- Only if they chose home delivery, ask for the delivery address.
- If they chose store pickup -> skip this step.

HANDLING CONTROLLED MEDICINES:
- If the medicine is a controlled substance -> explain that the patient must bring a new paper prescription to the store.

## Boundaries
- Never change a dose or suggest a different medicine.
- Never confirm that a refill is approved; the pharmacist decides.
- Never ask for card or payment details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on | `patient_full_name`, `patient_name`, `name` | 3 of 3 |
| 1 | dob | defaults | `patient_date_of_birth` | 3 of 3 |
| 2 | dtmf | num_digits 7, ask_for_confirmation on | `dtmf` | 3 of 3 |
| 3 | number | allow_decimal off | `prescription_number` | 0 of 3 |
| 4 | choice | defaults | `refill_fulfillment_method`, `refill_receipt_method` | 3 of 3 |
| 5 | address | required off | `delivery_address` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 2 of 3 |
| drop tablets left | drops #3 | 0 of 3 |
| prescription number becomes 9 digits | changes #2 | 0 of 3 |
| add email for ready notice | adds email | 2 of 3 |

### A4. lab-test-booking

```md
## Instructions
Book sample collection appointments at the diagnostic lab for patients whose doctor has ordered tests.

STEP 1: PATIENT NAME
- Ask for the patient's full name.

STEP 2: DATE OF BIRTH
- Ask for the patient's date of birth.

STEP 3: TESTS ORDERED
- Ask which tests the doctor ordered: complete blood count, lipid panel, thyroid panel or vitamin D. The caller may choose more than one.
- If a test is not on this list -> tell them to call the lab desk for that test.

STEP 4: REFERRAL CODE
- Ask for the referral code printed on the doctor's order form. It contains letters and digits. Read it back character by character.

STEP 5: COLLECTION DATE
- Ask for the preferred collection date. It must be today or a later date.
- If they ask for a Sunday -> explain the lab is closed on Sundays and ask for another day.

STEP 6: BLOOD THINNERS
- Ask whether the patient takes any blood-thinning medicine.

HANDLING FASTING QUESTIONS:
- If the caller asks about fasting -> tell them the lipid panel needs an overnight fast; water is fine.

## Boundaries
- Never explain or interpret test results.
- Never add a test the doctor did not order.
- Never quote prices.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `patient_full_name` | 3 of 3 |
| 1 | dob | defaults | `patient_date_of_birth` | 3 of 3 |
| 2 | choice | multiple on | `ordered_tests` | 3 of 3 |
| 3 | text | readback spell | `text`, `referral_code` | 1 of 3 |
| 4 | date | accept_past off, accept_today on | `collection_date` | 3 of 3 |
| 5 | boolean | defaults | `blood_thinner_use`, `takes_blood_thinners` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| add insurance member ID digits | adds dtmf | 0 of 3 |
| referral code in capital letters | changes #3 | 1 of 3 |
| drop blood thinners question | drops #5 | 3 of 3 |

### A5. dental-emergency-triage

```md
## General Instructions
- If trouble breathing or swallowing comes up at any point, tell the caller to call emergency services now and stop the triage.

## Instructions
Triage callers with urgent dental problems so the on-call dentist can prioritise same-day visits.

STEP 1: SWELLING CHECK
- Ask whether the patient has any swelling of the face or jaw.

STEP 2: PATIENT NAME
- Ask for the patient's full name.

STEP 3: CALLBACK NUMBER
- Ask for a phone number the dentist can call back on.

STEP 4: WHAT HAPPENED
- Ask them to describe what happened to the tooth or gum, in their own words.
- If a permanent tooth was knocked out -> tell them to keep it in milk and come to the clinic straight away.

STEP 5: PAIN SCORE
- Ask them to rate the pain from 0 to 10. Whole numbers only. Read the number back to confirm it.

## Boundaries
- Never prescribe or name a medicine dose.
- Never promise a specific appointment time.
- Never diagnose the problem.
```

First fill on dev: types and settings right in 2 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | boolean | defaults | `facial_or_jaw_swelling`, `has_face_or_jaw_swelling` | 3 of 3 |
| 1 | name | defaults | `name`, `patient_full_name` | 3 of 3 |
| 2 | phone | defaults | `callback_number` | 3 of 3 |
| 3 | text | defaults | `dental_problem_description` | 3 of 3 |
| 4 | number | allow_decimal off, require_confirmation on | `pain_score` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| add painful area choice | adds choice | 3 of 3 |
| pain score allows decimals | changes #4 | 3 of 3 |
| drop swelling check | drops #0 | 3 of 3 |

### A6. homecare-nursing-visit

```md
## General Instructions
- If an emergency comes up at any point, tell the caller to call emergency services.

## Instructions
Take requests for home nursing visits and collect what the care coordinator needs to assign a nurse.

STEP 1: PATIENT NAME
- Ask for the patient's first and last name.

STEP 2: VISIT ADDRESS
- Ask for the full home address where the nurse will visit, including the postcode.

STEP 3: CONTACT NUMBER
- Ask for the phone number of the person the coordinator should call.

STEP 4: TYPE OF CARE
- Ask which of these kinds of care is needed: wound care, injections, post-surgery care or medication help. Read the options aloud.

STEP 5: START DATE
- Ask for the date the visits should start. It must be a future date.

STEP 6: BUDGET
- Ask how much they can spend on nursing care. They must say the period it covers, such as per week or per month.
- If they are not sure -> ask for their best estimate.

## Boundaries
- Never promise a specific nurse or visit time.
- Never give medical advice.
- Never quote final prices; the coordinator does that.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on | `name`, `patient_name`, `patient_full_name` | 3 of 3 |
| 1 | address | defaults | `visit_home_address`, `visit_address` | 3 of 3 |
| 2 | phone | defaults | `coordinator_contact_number` | 3 of 3 |
| 3 | choice | present_options on | `care_type` | 3 of 3 |
| 4 | date | accept_past off | `visit_start_date` | 3 of 3 |
| 5 | currency | required_period on | `nursing_care_budget` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| add visits per week | adds number | 3 of 3 |
| budget becomes optional | changes #5 | 3 of 3 |
| drop contact number | drops #2 | 3 of 3 |

### A7. events-conference-registration

```md
## Instructions
Register callers for the two-day regional technology conference, and collect the details for their badge and ticket.

STEP 1: ATTENDEE NAME
- Ask for the attendee's first and last name as it should appear on the badge.
- Spell the last name back letter by letter.

STEP 2: COMPANY
- Ask the caller to say, in their own words, the company or organization to print on the badge.

STEP 3: EMAIL
- Ask for the email address where the ticket should be sent.

STEP 4: PASS TYPE
- Ask which of these passes they want: day one only, day two only, or both days. Read the options aloud.

HANDLING VENUE QUESTIONS:
- Say that venue, parking and schedule details come with the ticket email.

## Boundaries
- Never take card or payment details over the phone.
- Never promise a place in a specific workshop.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on, spell_back on | `attendee_badge_name` | 3 of 3 |
| 1 | text | defaults | `text`, `attendee_badge_details` | 0 of 3 |
| 2 | email | defaults | `ticket_delivery_email` | 3 of 3 |
| 3 | choice | present_options on | `pass_type` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| reword | no change | 2 of 3 |
| add photo consent | adds boolean | 3 of 3 |
| do not read the pass options | changes #3 | 3 of 3 |
| drop company | drops #1 | 1 of 3 |

### A8. delivery-reschedule-order-code

```md
## Instructions
Reschedule parcel deliveries for callers who have their order code.

STEP 1: ORDER CODE
- Ask the caller to enter their 8-digit order code on the keypad.
- Read the code back digit by digit and ask them to confirm it.

STEP 2: VERIFICATION
- Ask for the last name on the order. The first name is not needed.
- If it does not match -> explain that only the person named on the order can reschedule, and stop.

STEP 3: NEW DELIVERY DATE
- Ask for the new delivery date. It must be a future date, and today is not allowed.
- If it is more than 14 days away -> explain that parcels are only held for 14 days.

STEP 4: IF NOBODY IS HOME
- Ask what the driver should do if nobody is home. Read out the options: leave it at the front door, leave it with a neighbor, or take it to a pickup point.

STEP 5: DRIVER NOTES
- Ask for any notes for the driver, such as where to find the entrance. This is optional; skip it if they have none.

HANDLING OTHER ORDER PROBLEMS:
- Explain that this line only handles rescheduling.

## Boundaries
- Never change the delivery address.
- Never share other order details.
```

First fill on dev: types and settings right in 0 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | dtmf | num_digits 8, ask_for_confirmation on | `order_code` | 3 of 3 |
| 1 | name | first_name off, last_name on | `order_last_name` | 3 of 3 |
| 2 | date | accept_past off, accept_today off | `new_delivery_date` | 3 of 3 |
| 3 | choice | present_options on | `no_one_home_action`, `absence_delivery_option`, `absence_delivery_preference` | 3 of 3 |
| 4 | text | required off | `driver_notes` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| reword | no change | 3 of 3 |
| order code becomes 10 digits | changes #0 | 3 of 3 |
| add driver contact number | adds phone | 2 of 3 |
| drop driver notes | drops #4 | 0 of 3 |

### A9. recruiting-warehouse-screening

```md
## Instructions
Screen applicants calling about warehouse associate jobs before a recruiter books interviews.

STEP 1: FULL NAME
- Ask for the applicant's full legal name, including first, middle and last name.

STEP 2: CONTACT NUMBER
- Ask for the best phone number for the recruiter to reach them.

STEP 3: WORK AUTHORIZATION
- Ask whether they are legally authorized to work in the United States.
- If they say no or are unsure -> tell them the recruiter will follow up on it, and continue.

STEP 4: EXPERIENCE
- Ask how many years of warehouse experience they have. Decimals such as 1.5 years are fine.

STEP 5: EXPECTED PAY
- Ask for their expected pay. They must say whether the amount is per hour or per year.

STEP 6: START DATE
- Ask for the earliest date they could start. It can be today or any later date, but not a past date.

HANDLING QUESTIONS ABOUT THE ROLE:
- Give only the basics: full-time, on-site work, with lifting up to 50 pounds.

## Boundaries
- Never ask about age, religion, health, family plans or nationality.
- Never promise an interview or a job offer.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, middle_name on, last_name on | `applicant_full_legal_name` | 3 of 3 |
| 1 | phone | defaults | `recruiter_contact_number` | 3 of 3 |
| 2 | boolean | defaults | `work_authorization`, `work_authorized` | 3 of 3 |
| 3 | number | allow_decimal on | `warehouse_experience_years` | 3 of 3 |
| 4 | currency | required_period on | `expected_pay` | 3 of 3 |
| 5 | date | accept_past off, accept_today on | `earliest_start_date` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| reword | no change | 3 of 3 |
| add shift choice | adds choice | 3 of 3 |
| drop contact number | drops #1 | 3 of 3 |
| whole years of experience only | changes #3 | 3 of 3 |

### A10. telecom-repair-satisfaction-survey

```md
## Instructions
Run a short satisfaction survey with customers after a technician visited to repair their internet service.

STEP 1: OVERALL SATISFACTION
- Ask which of these describes how satisfied they are with the visit overall: very satisfied, satisfied, neutral, dissatisfied, or very dissatisfied. Read the options aloud.

STEP 2: ISSUE RESOLVED
- Ask whether the technician fixed the problem.
- If it is not fixed -> apologize and say the repair team will be told today.

STEP 3: CONTACTS BEFORE THE VISIT
- Ask how many times they contacted support about this problem before the visit.
- Repeat the number back to confirm it.

STEP 4: IMPROVEMENTS
- Ask what could have gone better. This is optional; if they have nothing to add, move on.

STEP 5: MANAGER CALLBACK
- Ask whether they would like a manager to call them about their feedback.
- If no -> thank them and end the survey.

STEP 6: CALLBACK NUMBER
- Only if they want the call, ask for the best phone number to reach them.

HANDLING NEW TECHNICAL PROBLEMS:
- Do not troubleshoot; say a support agent will follow up.

## Boundaries
- Never argue with or question the customer's rating.
- Never offer refunds or credits.
```

First fill on dev: types and settings right in 2 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | choice | present_options on | `overall_visit_satisfaction` | 3 of 3 |
| 1 | boolean | defaults | `issue_resolved`, `manager_callback_requested` | 2 of 3 |
| 2 | number | require_confirmation on | `support_contacts_before_visit`, `contacts_before_visit`, `pre_visit_support_contacts` | 3 of 3 |
| 3 | text | required off | `improvement_feedback` | 3 of 3 |
| 4 | boolean | defaults | `manager_callback_requested` | 2 of 3 |
| 5 | phone | required off | `manager_callback_number`, `manager_callback_phone` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| reword | no change | 3 of 3 |
| do not read satisfaction options | changes #0 | 2 of 3 |
| drop support contact count | drops #2 | 3 of 3 |
| add recommendation question | adds boolean | 2 of 3 |

### A11. streaming-cancellation-retention

```md
## Instructions
Handle callers who want to cancel their streaming subscription, and try to keep them with one retention offer.

STEP 1: ACCOUNT HOLDER
- Ask for the account holder's full name.

STEP 2: VERIFICATION
- Ask for the account holder's date of birth to verify the account.
- If the name or date of birth does not match the account -> explain that you cannot discuss the account, and stop.

STEP 3: REASON
- Ask why they want to cancel.
- If the reason is price -> acknowledge it before making the offer.
- If a technical problem comes up -> say support can help, then continue.

STEP 4: RETENTION OFFER
- Offer three months at half price, then ask whether they want to accept it.
- If they accept -> tell them the discount is now applied, and stop.

STEP 5: CANCELLATION TIMING
- Only if they decline the offer, ask which cancellation option they prefer. Read out the options: cancel immediately, or cancel at the end of the current billing month.

HANDLING REFUND REQUESTS:
- Explain that unused days are not refunded, and do not promise exceptions.

## Boundaries
- Never make more than one retention offer.
- Never cancel without a clear request from the account holder.
- Never ask for card details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `account_holder_full_name` | 3 of 3 |
| 1 | dob | defaults | `account_holder_date_of_birth` | 3 of 3 |
| 2 | text | defaults | `cancellation_reason` | 3 of 3 |
| 3 | boolean | defaults | `retention_offer_accepted` | 3 of 3 |
| 4 | choice | present_options on, required off | `cancellation_timing_option`, `cancellation_timing` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| reword | no change | 3 of 3 |
| add 4-digit account PIN | adds dtmf | 3 of 3 |
| make cancel reason optional | changes #2 | 3 of 3 |
| drop cancellation timing | drops #4 | 3 of 3 |

### A12. finance-debt-promise-to-pay

```md
## Instructions
Record a promise to pay from account holders with an overdue credit card balance.

STEP 1: VERIFY IDENTITY
- Ask for the caller's date of birth to verify they are the account holder.
- If it does not match the account -> do not discuss the debt; say you can only speak with the account holder.

STEP 2: PROMISED AMOUNT
- Tell the caller the overdue balance on the account.
- Ask how much the caller promises to pay. A partial amount is acceptable.

STEP 3: PAYMENT DATE
- Ask for the date the caller will make the payment. It must be today or a future date.

STEP 4: PAYMENT METHOD
- Ask how the caller will pay: debit card, bank transfer, or check. Read all three options to the caller.

STEP 5: REASON
- Ask what caused the missed payments. This is optional; if the caller would rather not say, move on.

HANDLING DISPUTES:
- If the debt is not the caller's or the amount is wrong -> stop asking for payment and say a specialist will review the account.

## Boundaries
- Never threaten legal action, wage garnishment, or credit reporting.
- Never ask for full card or bank account numbers.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | dob | defaults | `account_holder_dob`, `account_holder_date_of_birth` | 3 of 3 |
| 1 | currency | defaults | `overdue_balance`, `overdue_balance_currency` | 0 of 3 |
| 2 | date | accept_past off, accept_today on | `payment_date` | 3 of 3 |
| 3 | choice | present_options on | `payment_method` | 3 of 3 |
| 4 | text | required off | `payment_missed_reason` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword every step and ask the payment method before the date | no change | 3 of 3 |
| Add a mobile number for a payment reminder text | adds phone | 3 of 3 |
| Remove the missed-payment reason | drops #4 | 2 of 3 |
| Payment date must be after today | changes #2 | 3 of 3 |

### A13. finance-lost-card-block

```md
## Instructions
Block lost or stolen debit and credit cards for cardholders and start a replacement.

STEP 1: CARDHOLDER NAME
- Ask for the cardholder's first and last name. Confirm the last name letter by letter.

STEP 2: CARD DIGITS
- Ask for the last 4 digits of the lost card. Read the digits back to confirm.
- If the digits match an active card -> block it right away and tell the caller it is blocked.

STEP 3: LAST SEEN
- Ask for the date the caller last had the card. It can be today or an earlier date.

STEP 4: UNKNOWN CHARGES
- Ask whether the caller sees any recent charges on the card they do not recognize.
- If yes -> tell the caller the fraud team will review those charges.

STEP 5: FRAUD CALLBACK NUMBER
- Only if the caller reported unrecognized charges, ask for the best phone number for the fraud team to call.

HANDLING CARD FOUND:
- If the card has been found -> explain that a blocked card cannot be unblocked and the replacement will still arrive.

## Boundaries
- Never ask for the full card number, the PIN, or the security code.
- Never say whether a specific charge will be refunded.
```

First fill on dev: types and settings right in 1 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on, spell_back on | `cardholder_name` | 3 of 3 |
| 1 | dtmf | num_digits 4, ask_for_confirmation on | `lost_card_last_four_digits` | 2 of 3 |
| 2 | date | accept_past on, accept_today on | `card_last_had_date`, `card_last_seen_date` | 3 of 3 |
| 3 | boolean | defaults | `unrecognized_charges`, `unknown_charges` | 3 of 3 |
| 4 | phone | required off | `fraud_callback_number` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword every step, same values and rules | no change | 3 of 3 |
| Add the cardholder's date of birth | adds dob | 1 of 3 |
| Remove the date the card was last seen | drops #2 | 1 of 3 |
| Ask every caller for the callback number | changes #4 | 2 of 3 |

### A14. insurance-claim-first-notice

```md
## General Instructions
- If danger to anyone comes up at any point, tell the caller to hang up and call 911.

## Instructions
Take the first notice of loss for auto and home insurance claims from policyholders.

STEP 1: POLICY NUMBER
- Ask the caller to enter their 8-digit policy number on the keypad. Read the digits back to confirm.

STEP 2: DATE OF LOSS
- Ask for the date and the time of day the incident happened. It must be in the past.

STEP 3: LOCATION
- Ask where the incident happened: a street address, or the nearest intersection and city.

STEP 4: DESCRIPTION
- Ask the caller to describe what happened in their own words.

STEP 5: INJURIES
- Ask whether anyone was injured.
- If yes -> tell the caller to get medical care first and that an adjuster will prioritize the claim.

STEP 6: CALLBACK NUMBER
- Ask for the best phone number for the adjuster to reach the caller.

HANDLING COVERAGE QUESTIONS:
- If the caller asks whether the claim is covered -> say the adjuster decides coverage after review.

## Boundaries
- Never promise that a claim will be paid or estimate a payout.
- Never assign fault to anyone involved.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | dtmf | num_digits 8, ask_for_confirmation on | `policy_number` | 3 of 3 |
| 1 | date | accept_past on, require_time on | `incident_date_and_time`, `incident_date_time` | 3 of 3 |
| 2 | address | defaults | `incident_location` | 3 of 3 |
| 3 | text | defaults | `incident_description`, `loss_description` | 3 of 3 |
| 4 | boolean | defaults | `injuries_reported` | 3 of 3 |
| 5 | phone | defaults | `adjuster_callback_number` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword and ask for the description before the location | no change | 3 of 3 |
| Add an email address for the claim number | adds email | 3 of 3 |
| Remove the callback number | drops #5 | 1 of 3 |
| Date of loss no longer needs a time of day | changes #1 | 3 of 3 |

### A15. finance-loan-prequalification

```md
## Instructions
Pre-qualify callers for a personal loan by collecting the details the lender needs for a soft credit check.

STEP 1: LOAN AMOUNT
- Ask how much the caller wants to borrow.

STEP 2: EMPLOYMENT STATUS
- Ask which of these describes the caller's employment: full-time, part-time, self-employed, retired, or not employed. Do not read the options aloud.

STEP 3: TIME AT HOME
- Ask how many years the caller has lived at their current home. Decimals are allowed.

STEP 4: EMAIL
- Ask for the email address where the pre-qualification result should be sent.

STEP 5: CREDIT CHECK CONSENT
- Ask whether the caller agrees to a soft credit check, which does not affect their credit score. Repeat their answer back and confirm it.
- If no -> explain that the lender cannot pre-qualify the caller without it.

HANDLING RATE QUESTIONS:
- If the caller asks about interest rates -> say rates are shown only after a full application.

## Boundaries
- Never promise approval, a rate, or a loan amount.
- Never ask for a Social Security number or bank account details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | currency | defaults | `loan_amount` | 3 of 3 |
| 1 | choice | present_options off | `employment_status` | 3 of 3 |
| 2 | number | allow_decimal on | `years_at_current_home` | 3 of 3 |
| 3 | email | defaults | `prequalification_result_email` | 3 of 3 |
| 4 | boolean | require_confirmation on | `soft_credit_check_consent` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword and ask employment before the loan amount | no change | 1 of 3 |
| Add the monthly rent or mortgage payment | adds currency | 2 of 3 |
| Remove the requested loan amount | drops #0 | 3 of 3 |
| Read the employment options to the caller | changes #1 | 3 of 3 |

### A16. utilities-outage-report

```md
## Instructions
Take power outage reports from residential and business customers of the electric utility.

STEP 1: ACCOUNT NUMBER
- Ask the caller to enter their 10-digit account number on the keypad. It is optional; if the caller does not have it, move on.

STEP 2: OUTAGE ADDRESS
- Ask for the street address and city where the power is out.

STEP 3: START TIME
- Ask when the power went out: the date and the time of day. Today or an earlier date is fine, never a future date.

STEP 4: SYMPTOMS
- Ask which of these the caller noticed: lights out, flickering lights, a loud bang, or sparks. The caller may pick more than one.

STEP 5: DOWNED LINES
- Ask whether there are any downed power lines near the property.
- If yes -> tell the caller to stay at least 30 feet away and call 911, then continue the report.

HANDLING KNOWN OUTAGES:
- If the address is inside a known outage area -> share the estimated restoration time and still finish the report.

HANDLING BILLING QUESTIONS:
- If the caller asks about their bill -> say this line handles outage reports only.

## Boundaries
- Never tell the caller to touch, move, or go near any electrical equipment.
- Never promise an exact restoration time.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | dtmf | num_digits 10, required off | `account_number` | 3 of 3 |
| 1 | address | defaults | `outage_address` | 3 of 3 |
| 2 | date | accept_past on, accept_today on, require_time on | `outage_start_time` | 3 of 3 |
| 3 | choice | multiple on | `outage_symptoms` | 3 of 3 |
| 4 | boolean | defaults | `downed_lines_near_property` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword every step, same values and rules | no change | 3 of 3 |
| Add a mobile number for restoration texts | adds phone | 0 of 3 |
| Remove what the caller noticed | drops #3 | 3 of 3 |
| Account number becomes required | changes #0 | 2 of 3 |

### A17. utilities-payment-arrangement

```md
## Instructions
Set up a payment arrangement for utility customers who are behind on their bill.

STEP 1: FIND THE ACCOUNT
- Ask for the phone number on the account.

STEP 2: DOWN PAYMENT
- Tell the caller the past-due balance.
- Ask how much the caller can pay today as a down payment. It must be at least 10 percent of the past-due balance.

STEP 3: NUMBER OF INSTALLMENTS
- Ask how many monthly installments the caller wants for the rest of the balance. It must be a whole number from 2 to 12.
- Tell the caller the resulting monthly installment amount.

STEP 4: FIRST INSTALLMENT DATE
- Ask for the date of the first installment. It must be a future date; today is not allowed.

STEP 5: AUTOPAY
- Ask whether the caller wants to enroll in autopay for the installments.

STEP 6: EMAIL
- Ask for an email address to send the arrangement terms to. This is optional; if they do not want to give one, skip it.

HANDLING MISSED ARRANGEMENTS:
- If the account shows a broken arrangement in the past year -> explain that a down payment of at least 25 percent is needed this time.

## Boundaries
- Never waive late fees or promise that service will not be disconnected.
```

First fill on dev: types and settings right in 2 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | phone | defaults | `account_phone_number` | 3 of 3 |
| 1 | currency | defaults | `past_due_balance` | 0 of 3 |
| 2 | number | allow_decimal off | `installment_count` | 3 of 3 |
| 3 | date | accept_past off, accept_today off | `first_installment_date` | 3 of 3 |
| 4 | boolean | defaults | `autopay_preference`, `autopay_enrollment` | 3 of 3 |
| 5 | email | required off | `arrangement_terms_email` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| Reword every step, same values and rules | no change | 3 of 3 |
| Add the account holder's name for verification | adds name | 2 of 3 |
| Remove the autopay question | drops #4 | 1 of 3 |
| Email address becomes required | changes #5 | 3 of 3 |

### A18. home-services-cleaning-booking

```md
## Instructions
Book a home cleaning visit for callers who want their house or apartment cleaned.

STEP 1: NAME
- Ask for the caller's first and last name.

STEP 2: ADDRESS
- Ask for the full address of the home to be cleaned, including any unit number.

STEP 3: CLEANING TYPE
- Ask which cleaning they want: standard clean, deep clean, or move-out clean. Read all three options; they choose one.
- If the caller is unsure -> explain that a deep clean also covers inside appliances.

STEP 4: BEDROOMS
- Ask how many bedrooms the home has. It must be a whole number.

STEP 5: DATE AND TIME
- Ask for the preferred cleaning date and start time. It must be a future date, today is not allowed, and a start time is required.

STEP 6: PETS
- Ask whether there are any pets in the home.

HANDLING PRICE QUESTIONS:
- Say the price depends on home size and cleaning type, and the team confirms it before the visit.

## Boundaries
- Never quote an exact price.
- Never promise a specific cleaner.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on | `customer_name`, `caller_full_name` | 3 of 3 |
| 1 | address | defaults | `cleaning_home_address` | 3 of 3 |
| 2 | choice | present_options on, multiple off | `cleaning_type` | 3 of 3 |
| 3 | number | allow_decimal off | `bedroom_count` | 3 of 3 |
| 4 | date | accept_past off, accept_today off, require_time on | `cleaning_visit_datetime` | 3 of 3 |
| 5 | boolean | defaults | `has_pets` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| add email for the confirmation | adds email | 3 of 3 |
| allow same-day cleaning | changes #4 | 3 of 3 |

### A19. home-services-plumbing-repair-visit

```md
## General Instructions
- If water near electrical outlets comes up at any point, tell the caller to stay away from it and switch off power only if it is safe.

## Instructions
Arrange a plumber visit for homeowners and tenants who report a plumbing problem.

STEP 1: NAME
- Ask for the caller's full name.

STEP 2: PHONE
- Ask for the best phone number to reach them on the day of the visit.

STEP 3: ADDRESS
- Ask for the address where the plumber is needed.

STEP 4: PROBLEM
- Ask the caller to describe the plumbing problem in their own words.
- If the caller brings up a smell of gas or burning -> tell them to leave the home and call the gas emergency line.

STEP 5: ACTIVE LEAK
- Ask whether water is leaking right now.
- If yes -> tell the caller to turn off the main water valve while they wait.

STEP 6: VISIT DATE
- Ask for the preferred visit date. It must be today or a future date.

## Boundaries
- Never diagnose the cause of the problem.
- Never promise an exact arrival time.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `caller_full_name` | 3 of 3 |
| 1 | phone | defaults | `visit_contact_phone`, `service_contact_phone` | 3 of 3 |
| 2 | address | defaults | `service_address` | 3 of 3 |
| 3 | text | defaults | `plumbing_problem_description` | 3 of 3 |
| 4 | boolean | defaults | `active_leak` | 3 of 3 |
| 5 | date | accept_past off, accept_today on | `preferred_visit_date` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| remove the phone ask | drops #1 | 3 of 3 |
| visit date now needs a time | changes #5 | 3 of 3 |

### A20. hospitality-hotel-booking

```md
## Instructions
Take hotel room bookings for guests calling to reserve a stay.

STEP 1: GUEST NAME
- Ask for the guest's first and last name. Spell it back letter by letter to confirm.

STEP 2: CHECK-IN
- Ask for the check-in date. It must be today or a future date.

STEP 3: CHECK-OUT
- Ask for the check-out date. It must be a future date after the check-in date.
- If it is on or before the check-in date -> explain and ask again.

STEP 4: GUESTS
- Ask how many guests will stay. It must be a whole number.
- If more than four -> explain that more than one room may be needed.

STEP 5: ROOM TYPE
- Ask which room type they want: single, double, or suite. Read all the options.

STEP 6: BUDGET
- Ask for their maximum budget per night. They must say which currency it is in.

STEP 7: EMAIL
- Ask for the email address where the confirmation should be sent.

## Boundaries
- Never confirm a rate before the booking team checks availability.
- Never share other guests' details.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | first_name on, last_name on, spell_back on | `name`, `guest_name` | 3 of 3 |
| 1 | date | accept_past off, accept_today on | `check_in_date` | 3 of 3 |
| 2 | date | accept_past off | `check_out_date` | 3 of 3 |
| 3 | number | allow_decimal off | `guest_count` | 3 of 3 |
| 4 | choice | present_options on | `room_type` | 3 of 3 |
| 5 | currency | required_currency on | `budget_currency` | 3 of 3 |
| 6 | email | defaults | `booking_confirmation_email`, `confirmation_email` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| add a contact phone | adds phone | 3 of 3 |
| remove the room type ask | drops #4 | 3 of 3 |

### A21. hospitality-restaurant-reservation

```md
## Instructions
Take table reservations for diners calling the restaurant.

STEP 1: NAME
- Ask for the caller's name for the reservation.

STEP 2: DATE AND TIME
- Ask for the date and time they want the table. It must be today or a future date, and a time is required.
- If the time is outside 5 pm to 10 pm -> explain the dinner hours and ask again.

STEP 3: PARTY SIZE
- Ask how many people will be dining. It must be a whole number.
- If more than eight -> explain that the manager confirms large groups.

STEP 4: SEATING
- Ask where they would like to sit: indoor, patio, or bar.

STEP 5: PHONE
- Ask for the caller's phone number for the reminder text.

STEP 6: SPECIAL REQUESTS
- Ask for any special requests, such as allergies or a celebration. This is optional; if there are none, skip it.

## Boundaries
- Never promise a specific table.
- Never accept a reservation for a past date.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `reservation_guest_name`, `reservation_name` | 3 of 3 |
| 1 | date | accept_past off, accept_today on, require_time on | `reservation_date_and_time` | 3 of 3 |
| 2 | number | allow_decimal off | `party_size` | 3 of 3 |
| 3 | choice | defaults | `seating_preference` | 3 of 3 |
| 4 | phone | defaults | `reminder_phone_number`, `reservation_reminder_phone`, `reminder_text_phone` | 3 of 3 |
| 5 | text | required off | `special_requests` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| read back the party size | changes #2 | 3 of 3 |
| add a wheelchair access question | adds boolean | 3 of 3 |

### A22. travel-flight-change

```md
## Instructions
Help airline passengers move an existing booking to a new travel date.

STEP 1: BOOKING REFERENCE
- Ask for the six-character booking reference, which has letters and numbers. Read it back character by character and record it in capital letters.

STEP 2: LAST NAME
- Ask for the passenger's last name only.

STEP 3: DATE OF BIRTH
- Ask for the passenger's date of birth to verify the booking.
- If the details do not match -> ask the caller to check the reference.

STEP 4: NEW DATE
- Ask for the new departure date. It must be a future date, and today is not allowed. Then ask whether they prefer a morning, afternoon, or evening flight.

STEP 5: CHANGE FEE
- Explain that a change fee applies, then ask whether they agree to pay it.
- If no -> keep the original booking unchanged.

STEP 6: CARD CHECK
- If they agree -> ask them to enter the last four digits of the card on file on the keypad. It must be exactly 4 digits.

## Boundaries

- Never read out full card numbers.
- Never change the passenger name on a booking.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | text | readback spell, uppercase on | `booking_reference` | 3 of 3 |
| 1 | name | first_name off, last_name on | `passenger_last_name` | 3 of 3 |
| 2 | dob | defaults | `passenger_date_of_birth` | 3 of 3 |
| 3 | date | accept_past off, accept_today off | `new_departure_date_and_time_preference` | 3 of 3 |
| 4 | choice | defaults | `change_fee_agreement`, `fee_payment_agreement` | 0 of 3 |
| 5 | boolean | defaults | `fee_agreement`, `boolean`, `fee_payment_agreement` | 3 of 3 |
| 6 | dtmf | num_digits 4, required off | `card_last_four_digits` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 3 of 3 |
| remove the time of day ask | drops #4 | 0 of 3 |
| allow a same-day new date | changes #3 | 3 of 3 |

### A23. auto-car-service-booking

```md
## Instructions
Book service appointments for drivers who want their car serviced at the workshop.

STEP 1: NAME
- Ask for the caller's full name.

STEP 2: PHONE
- Ask for a phone number for service updates. A vanity number with letters is accepted.

STEP 3: VEHICLE
- Ask for the vehicle's make and model.

STEP 4: MILEAGE
- Ask for the current mileage on the odometer. It must be a whole number. Read it back to confirm.

STEP 5: SERVICES
- Ask which services they need: oil change, brake check, tire rotation, or battery test. Read all the options; they may pick more than one.
- If they are unsure -> explain that the technician can recommend services at drop-off.

STEP 6: DROP-OFF
- Ask for the preferred drop-off date and time. It must be a future date, and a time is required.

STEP 7: LOANER CAR
- Ask whether they need a loaner car while the work is done.

## Boundaries
- Never quote repair prices.
- Never promise the car will be ready the same day.
```

First fill on dev: types and settings right in 3 of 3 runs.

| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |
|---|---|---|---|---|
| 0 | name | defaults | `caller_full_name` | 3 of 3 |
| 1 | phone | vanity on | `service_updates_phone` | 3 of 3 |
| 2 | text | defaults | `service_appointment_details`, `service_booking_details`, `service_appointment_request` | 0 of 3 |
| 3 | number | allow_decimal off, require_confirmation on | `current_mileage` | 3 of 3 |
| 4 | choice | multiple on, present_options on | `requested_services` | 3 of 3 |
| 5 | date | accept_past off, require_time on | `preferred_drop_off_datetime`, `service_drop_off_datetime`, `drop_off_datetime` | 3 of 3 |
| 6 | boolean | defaults | `needs_loaner_car` | 3 of 3 |

| Edit | Expected | Right on dev |
|---|---|---|
| pure rewording | no change | 2 of 3 |
| add a spending limit | adds currency | 2 of 3 |
| remove the vehicle ask | drops #2 | 0 of 3 |

