# Building confirmation behaviour you can be certain about

**A working method, written from what actually happened — including the parts that went wrong.**

Plivo CX · subtle confirmations (v2.5 collectors) · 2026-07 → 2026-08

---

This is not a design doc. It is a record of how we got from "the agent sounds robotic when it
confirms things" to changes we can defend, and what we would tell the next person doing similar
work. The failures are included on purpose: nearly every durable rule in here came from being
wrong first, and a method that only reports its successes teaches nothing.

---

## 1. How the data was prepared

Four sources, each answering a question the others could not. Mixing them up was the single most
common way to reach a confident wrong answer.

| source | what it is | what it can prove |
|---|---|---|
| **`cx-skills/tasks/`** | **16 skill files, ~612k chars of prompt. 11 live in production.** | How a collector actually behaves. This *is* the task prompt — not a sample of one. |
| **`eval_tests/`** | 50 real customer flows, byte-faithful to production apart from sanitization: 81 agent instructions (median 3,696 chars, max **54,564**), 12 system prompts, 37 personas | Whether a change survives real customer prompts |
| **AO / Akhada** | ~12,000 live production sessions in 7 days, with **full system prompts embedded as `system:` turns in the transcripts** | What real callers actually say and what agents actually run |
| **sim workspaces + Hunter** | scenarios we author; Hunter places real PSTN calls and judges them | Controlled comparison; end-to-end reality |

### The distinction that cost us the most time

For about a day we believed we had **no real task prompts**, because none of the 50 customer
flows contained per-field instructions. That was a category error. The **task prompt is the
skill** — the 16 files that tell the model how to collect an email, a date, a phone number.
Those were in the repo the whole time, they are what production ships, and every test we ran
was already exercising them.

What was genuinely missing was narrower and worth stating precisely: **no real customer flow is
configured with these collectors yet.** The prompts were real; the field configuration and the
production traffic were not.

> **Practice:** before claiming a corpus is missing, say out loud what layer you are looking
> for. "Real prompts" meant four different things in this project, and three of them existed.

### Sanitization is not optional, and it belongs at the source

Production prompts carry live customer PII in plain text. One recovered agent prompt embedded a
real phone number, real member names, a real account number, and a real institution — inside the
prompt itself, as pre-call context.

The rule we settled on: **scrub before the data crosses a boundary**, not after. That prompt was
sanitized inside the browser, so the real values never entered a transcript, a log, or a repo.
Then a leak check ran before every commit.

> **Do not** pull production prompts into a working file "temporarily" and clean them later.
> There is no later — they are in the transcript, the scrollback, and the tool history already.

---

## 2. How the data reached the work

Worth writing down, because the highest-value inputs did not arrive as datasets.

**Credentials arrived as screenshots.** Practical, and it works — but it means the values are
now in the conversation. Treat any screenshot of a secret as a secret that needs rotating on a
normal schedule, and never let those values land in a repo. One of ours was already committed to
a GitHub file, which is worth fixing independently.

**Corrections arrived as one-line challenges, and they were the most valuable input of all.**

> *"the task prompts that were in the git repo, I think they are the prompts for v2.5. Remember
> the 16 skills."*

That single sentence overturned a conclusion that had shaped a day of planning. The person who
built the system knows things the tooling cannot index.

**Human memory worked as a search key when search did not.** An agent was described from memory
as *"Sandy from \<company, half-remembered and misspelled\>"*. No such name existed anywhere:
the agent's registered name was an auto-generated `Simple Inbound Call_default_…`. Searching
agent names found nothing across two regions. Searching **inside the prompts** for who the agent
says it is found her on the first pass — the persona name and the company appear in the prompt
text, never in the metadata.

> **Practice:** index what the agent *says it is*, not what it is *called*. Display names are
> arbitrary; the persona in the prompt is the real identity.

---

## 3. How the confirmation rules were made

### The finding everything else rests on

**An instruction competing in the system prompt loses to one competing in the tool return.**

The collector prompt already said the right thing in several cases. The model ignored it. The
same rule, delivered as the *return value of the tool the model just called*, wins — because it
is the newest thing in context at the moment the model decides how to speak.

The clearest proof: `collect_phone.py` already contains

> *"'double six' → 66 … never write a literal 2 or 3 for the words double or triple"*

and gpt-4.1 got it wrong **0 out of 6 times** anyway. Adding more wording would have failed
again. A guard on the tool return fixed it.

> **Rule:** when prose has already failed, do not write better prose. Change where the
> instruction is delivered.

### The architecture that followed

- **L1 — language-neutral rules.** What must be true in every language.
- **L2 — per-language style packs.** How it sounds in that language, with copyable example
  strings, because the model imitates the first example far more reliably than it follows a
  description of the example.
- **L3 — the flow selects a pack by name.**

**Four confirmation shapes**, and the tier is **per field, not per task**: a phone number and a
service type in the same conversation deserve different treatment. Unrecoverable values (email,
phone, names, identifiers) are read back element by element and the agent waits. Ordinary values
are stated once and the call moves on. Booleans are never parroted back.

### Every rule had to survive its own measurement — and four did not

Four changes that were well-reasoned, sounded obviously right, and were **reverted because the
measurement said no**:

1. lowering the date gate
2. rendering the weekday in the readback
3. naming the resolved date in a refusal
4. escalating lakh amounts to a full readback

The last one is the most instructive. The reasoning was: *what code cannot decide, the caller
can — if they hear it.* It rested on an untested assumption, that a caller who hears "eight
lakh" after saying "eighty lakh" will object. Measured over 8 runs each:

| | correct | 10× low | **missing entirely** | avg turns |
|---|---|---|---|---|
| before | 5 | 3 | **0** | 8.4 |
| after | 2 | 3 | **3** | 10.2 |

The error rate was **unchanged** (Fisher exact p = 1.000). What the change did do was push three
runs past their turn budget, so a field that used to arrive wrong sometimes stopped arriving at
all.

> **Practice:** state the mechanism your change depends on as a claim that could be false, then
> test that claim. "The caller will notice" is a hypothesis, not a design.

---

## 4. Good practices worth keeping

**Prefer a guard to a sentence.** A guard is deterministic, testable, and cannot be
out-competed by the rest of the prompt. Keep its scope narrow enough that it cannot fire on
values the caller really said — ours refuse only when the shortfall is explainable by the exact
thing being guarded.

**Probe a credential against its own service.** A day was spent inferring whether a model was
serving from latency, cost, and dashboards. A 5-second script that minted a token and called the
gateway answered it outright. If a credential is in question, use it.

**Read the transcript before believing any verdict.** LLM judges were wrong repeatedly in both
directions — failing an agent that behaved correctly, and passing calls that ended before the
agent could reply. A failure is a claim, not a fact.

**Test the call the runtime actually makes.** One guard shipped completely dead because it read
keyword arguments while the framework passes positionally. It passed its unit test and its
end-to-end test, and did nothing in production. There is now a test that invokes tools exactly
as the runtime does.

**Pin the invariant, not just the behaviour.** The screener and the confirmation rules are kept
apart by three independent things: dispatch order, class hierarchy, and a validator. Two were
pinned by tests; the third was load-bearing and unpinned. A future refactor could have silently
routed identity verification through confirmation rules with nothing failing.

**Write down what a measurement cannot tell you.** "50 real flows passed" meant *the call
survived the opening exchange on 50 real flows* — each ships only a two-turn smoke. True, and
much weaker than it sounds.

---

## 5. What not to do

**Do not ship a guard that only works in English.** Two of ours did. Production traffic is
code-switched — Devanagari appeared in 7 of 149 sampled caller utterances, and two of the busiest
agents run Hinglish and Tamil. An English-only guard is not a weaker guard for those callers; it
is an **absent** one that measures as passing, because every test arm is in English.

**Do not trust a fix that looks like it works.** Widening a tokenizer to `\w+` to support
Devanagari looked correct and was not: Devanagari vowel marks are combining characters, which
`\w` excludes. `नौ` became `न`. Every numeral *with* a vowel mark failed while the few *without*
one matched — so the probe reported "the multiplier works, the digits don't", which reads like a
missing table entry rather than a broken tokenizer. **A table tested only with its easy cases
passes while being half dead.**

**Do not let a guard read only the most recent turn.** The lakh guard checked the newest caller
utterance. But the collector *mandates* a clarifying question — "per month, or for the whole
job?" — so by the time the value is recorded, the word "lakh" is two turns back. The guard went
silent on the exact path the product requires, while still reporting success.

**Do not read direction into a measurement taken somewhere else.** We claimed a model swap would
make calls ~200–350 ms slower, based on numbers measured from India. From the server's own region
the same path is faster. "It did not move" was the only claim the data supported.

**Do not assume silence means nothing happened.** Deploys defaulted to *not deploying* unless a
box was ticked; builds ran green having shipped nothing. Branch pushes produced no status checks
at all, so "no build appeared" was not evidence. Verify the deployed revision, never the colour
of a status.

**Do not write a rubric that punishes correct behaviour.** One test marked the agent down for
not offering a *morning* appointment window on a **2 p.m.** booking. Another was unwinnable for a
subtler reason: when a caller interrupts, the agent's half-finished sentence is recorded
**truncated and unmarked**, so a judge grading "did it read the value back in full" fails an agent
that did exactly that. Never pair a full-readback criterion with interruptions enabled.

**Do not take an agent's report at face value — including your own tooling's.** An adversarial
review layer rejected **8 of 8** proposed test scenarios as unfair. That was the layer working:
it cost tokens instead of eight real phone calls producing verdicts we could not have trusted.
Two of its findings were verified independently and turned out to be real product defects.

---

## 6. The shortest version

1. Know which layer of "the data" you are looking at. Most confusion was a category error.
2. Sanitize at the source. There is no later.
3. If prose has already failed, move the instruction — do not rewrite it.
4. Every rule earns its place by measurement, and some good ideas will lose. Keep the arm.
5. Assume your guard is English-only and dead until a test proves otherwise.
6. Read the transcript. Probe the credential. Verify the revision.
7. The person who built the system knows things your tools cannot index. Ask them, and take the
   correction.
