# Readback modes in V2.9 — brainstorm note (2026-09-06 03:35, for MK)

**The question.** V2.5's console has per-field checkboxes for how a collector reads a value back (spell a name letter by letter, digit groups for a phone, and so on). V2.9 has no panel. How does a flow say "spell this one back"?

**What the collectors already do, by type (verified on tonight's calls).**
- `email`: always letter by letter, with in-collector corrections ("m a r i a, dot, l o p e z…"). Nothing to add.
- `phone`: digit groups ("4 1 5, 5 5 5, 0 1 1 4"), correction by replacing digits. Nothing to add.
- `dtmf`: keypad digits read back as digits. Nothing to add.
- `name`: read back as words ("Just to confirm, is your name Maria Lopez?"). Letter-by-letter exists behind the constructor flag `verify_spelling`, which only the V2.5 checkbox sets. This is the one gap.
- `address`, `text`, `date`, `dob`, `currency`, `number`, `choice`, `boolean`: read back in words; spelling makes no sense for them.

**So "how will we know?"** — by type for eleven of twelve; the flow author decides only for `name`, exactly as the V2.5 checkbox does today.

**Three ways to give `name` the lever, smallest first.**
1. **One boolean tool argument `spell_back`** (default false). The model sets it when the node prompt says "spell the name back" / "confirm the spelling"; the router maps it to `verify_spelling=True` for `name` and ignores it for every other type. Authoring stays in the prompt, the argument is yes/no, the collector is untouched, and it mirrors the checkbox one to one. ~6 lines in the router + description sentence + 2 tests.
2. **Always spell names** (`_DEFAULTS["name"] = {"verify_spelling": True}`, like D-032). Zero authoring, but every name costs one more turn on every call; V2.5 leaves it off by default, so this changes the default experience.
3. **Prompt only** (write "spell it back" in the instructions the router relays). The name collector's spelling gate is enforced in code, not in its prompt, so the instruction alone is unreliable — rejected.

**Recommendation:** option 1, after the current board is clean. It is the same shape as `choices`/`num_digits` (D-018: arguments the collector needs and the prompt cannot carry).
