"""Judge a sim-prepared campaign run, value-first: the model names the field freely, so match the
stored VALUE, and read the prepared-speech rules off the transcript.

    judge.py [arm=]PATH[,PATH...] [arm=PATH...] [--scenarios DIR] [--retries N] [--selftest]

PATH is a run directory, a report `.jsonl`, or an arm log `.err`. A run directory written by
run_arm.sh carries a RUN-INFO.txt and its own copy of every report it produced: all of those are
judged. Anywhere else (the shared workspace `reports/`), the newest wins. The arm name comes from
the `arm=` prefix, else from a path component ending in `-prepared`/`-off`; two specs that resolve
to one file are refused, and the columns are printed prepared-then-off so the delta has a sign.

Per walk, in order — a walk passes only when every rule is clean:

  completed   ended as the scenario declared, its declared `intent` reached, its `stop_reason`
              matched and its `not_intent` never fired. `ended: true` is assumed ONLY for a scenario
              that declares nothing at all. Plus the engine's own verdict, minus the by-key variable
              lines this judge redid by value AND passed.
  floor       the agent spoke at all, and a walk that left by Reschedule Booked (or ended with no
              other intent) stored every REQUIRED Input the scenario did not declare absent.
  variables   every `expect.variables` value: under the field's OWN key when the node declares that
              Input (`record_<field>` is the runtime's key, not the model's choice), else under any
              key. And every `variables_absent` field held by no key, with its campaign value (the
              union of every scenario's `expect.variables`) stored nowhere.
  speech 1    no acknowledgement line spoken twice for one answer — the same value stated in two
              sentences of one turn, or in two consecutive spoken turns with no new answer between.
              A closing recap (RECAP_VALUES values, or the last line carrying two) is exempt.
  speech 2    no read-back left stale: a value read back and then corrected must have the CORRECTED
              value read back afterwards.
  speech 3    no prepared line spoken before the answer it acknowledges — a value stated before the
              caller gave it and before any tool call carried it.
  speech 4    no spoken Python literal, bracketed placeholder or variable name.
  speech 3b   no campaign value SPOKEN for a field the scenario declares absent, when the caller
              never said it either — rule 3 only sees values that reached a tool.
  speech 5    at most one collector reopen per field beyond the configured retry (`--retries`).
  seeded      for the two scenarios whose trick is a value given before its collector opened
              (SEEDED_FIELDS), that collector's first call carries a non-empty `known_value`.

A value is judged with its YEAR: two dates that share a month and a day are two values, so a
year-only correction is visible. A line that names no year at all is judged on month and day.

Turn counts come from the report. Physical LLM request counts come from the arm's `*.err` log only,
and per WALK: see `turn_llm_counts` for why per-turn is not derivable. A walk the engine retried
(throttling) is named in a warning: its discarded attempt's requests land under the same call_uuid.

The `run` exit code is NOT the verdict — the engine compares `expect.variables` literally by key, so
a phone stored with a country prefix or an uninferred currency prints an engine failure that is
right by value. Only this judge's verdict counts.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

MAX_OPENS_OVER_RETRY = 1  # "at most one re-ask per field beyond the configured retry"
_REQUIRED: set[str] | None = None  # the node's required Inputs, read once off ws/flow.json
RECAP_VALUES = 3  # a turn stating this many of the walk's values is a closing recap, not an ack
NO_YAML = {"ended": None}  # a walk whose scenario has no YAML: speech rules only, no end demanded
RETRIES_DEFAULT = 1  # collect_*.max_collection_retries default; nothing in this pack's config sets it
BOOLISH = {"yes", "no", "true", "false", "none", ""}
SKIP_ARG_KEYS = {"instructions", "reason", "task_type", "options", "name", "min_value", "max_value",
                 "min_amount", "max_amount", "choices", "known_value"}
# the persona values the pack never pins in an `expect.variables` block, so an absence check has
# something to look for (check_report.py's MOBILE_DIGITS, same job)
VALUE_HINTS = {"mobile_number": ["07700900123"], "access_notes": ["wheelchair", "side entrance"]}
# the two scenarios whose whole trick is a value the caller gave before the collector opened:
# the first collect_* for the field must carry it as known_value (scenario -> field)
SEEDED_FIELDS = {"two-fields-one-breath-opening": "date_of_birth",
                 "two-fields-one-breath-mid-walk": "preferred_time_of_day"}

MONTHS = ("january february march april may june july august september october november december").split()
ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen").split()
TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
        80: "eighty", 90: "ninety"}
ORDINALS = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth",
            20: "twentieth", 30: "thirtieth"}
DIGIT_WORD = {w: str(i) for i, w in enumerate(ONES)} | {v: str(k) for k, v in TENS.items()}
_NUM_WORDS = "|".join(ONES + list(TENS.values()))
# a spoken YEAR, not a spoken quantity: "twenty five minutes" is not a year
YEAR_SPOKEN_RX = re.compile(rf"\bnineteen\s+(?:hundred|oh|{_NUM_WORDS})\b"
                            rf"|\btwenty\s+(?:hundred|oh|twenty|nineteen)\b")
EMAIL_RX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ISO_DATE_RX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
ATTEMPT_MARKER = "call.lifecycle phase=simulation_agent_entered"  # exactly one per sim attempt
PREPARED_MARKERS = ("prepared.ready", "prepared.fallback", "prepared.skip", "prepared.cancel")
NUMERIC_RX = re.compile(r"-?\d+(?:\.\d+)?")
# "GBP 40.0", "40", "£40", "45" - a value that IS a number, not free text carrying one (L2)
NUMBER_SHAPED_RX = re.compile(r"[A-Za-z$£€]{0,3}\s*-?\d+(?:\.\d+)?\s*[A-Za-z]{0,3}")
YEAR_RX = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# spoken-shape defects, scanned on the RAW agent text
BAD_SPEECH = (
    # True/False dropped: "True, that is the case." is English, not a literal (L3)
    ("python literal", re.compile(r"[\[{]\s*['\"]|\bNone\b(?! of\b)|datetime\.|"
                                  r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}:\d{2}:\d{2}\b")),
    ("bracketed placeholder", re.compile(r"[\[{<]{1,2}\s*[A-Za-z_][A-Za-z0-9_ .]*\s*[\]}>]{1,2}")),
    ("variable name", re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")),
)


def slug(s: str) -> str:
    """The record tool carries the SANITISED field name, as the router stored it."""
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def norm(s: str) -> str:
    """One transform for haystack and needle alike, so an email's dots, a hyphenated number word and
    the connectors a voice puts between a day and a month ('the ninth of June') all normalise the
    same on both sides."""
    words = re.sub(r"[^a-z0-9@]+", " ", str(s).casefold()).split()
    return " ".join(w for w in words if w not in ("of", "the"))


def number_word(n: int) -> str | None:
    if 0 <= n < 20:
        return ONES[n]
    if n in TENS:
        return TENS[n]
    if 20 < n < 100:
        return f"{TENS[n // 10 * 10]} {ONES[n % 10]}"
    return None


def ordinal_word(n: int) -> str | None:
    if n in ORDINALS:
        return ORDINALS[n]
    if n < 20 or n in TENS:
        return (number_word(n) or "") + "th" or None
    if 20 < n < 100 and n % 10:
        return f"{TENS[n // 10 * 10]} {ordinal_word(n % 10)}"
    return None


def spoken_forms(value: str) -> tuple[list[str], str]:
    """Needles a voice agent would plausibly speak for this stored value, plus its digit run.

    ponytail: a bounded renderer — ISO dates, whole numbers under 100, emails and literals. A form
    it does not know reads as "not spoken"; add the form when a false negative turns up.
    """
    v = str(value).strip()
    forms = {norm(v)} if len(v) >= 3 else set()
    digits = re.sub(r"\D", "", v)
    m = ISO_DATE_RX.match(v)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        month = MONTHS[mo - 1]
        days = {str(d), f"{d}th", f"{d}st", f"{d}nd", f"{d}rd", ordinal_word(d) or str(d)}
        forms = {norm(f"{month} {x}") for x in days} | {norm(f"{x} {month}") for x in days}
        forms |= {norm(f"{month[:3]} {x}") for x in days}
        digits = ""  # a date is judged by month+day words, never by its digit run
        forms = {f for f in forms if f} | {norm(v)}
        _ = y
    elif EMAIL_RX.fullmatch(v):
        forms |= {norm(v.replace("@", " at ").replace(".", " dot "))}
    else:  # a bare or prefixed amount: 40, 40.0, GBP 40.0
        num = NUMERIC_RX.search(v)
        if num:
            f = float(num.group())
            forms |= {norm(f"{f:g}")}
            if f.is_integer() and 0 <= f < 100:
                forms |= {number_word(int(f)) or ""}
    # a phone is judged on its last ten digits, as the router stores it with a country prefix
    return sorted(f for f in forms if f), digits[-10:] if len(digits) >= 6 else ""


def squash(text: str) -> str:
    """A value spelled out loud, run back together: 'K X R four five six' -> 'kxr456', '9 8 7' -> '987',
    'r a h u l at g-mail dot com' -> 'rahulatgmaildotcom'."""
    return "".join(DIGIT_WORD.get(w, w) for w in norm(text).split())


def year_forms(value: str) -> list[str]:
    """How a date's YEAR is spoken - digits and words. Empty for anything but an ISO date."""
    m = ISO_DATE_RX.match(str(value).strip())
    if not m:
        return []
    y = int(m[1])
    out = [str(y)]
    head, rest = ("nineteen", y - 1900) if 1900 <= y < 2000 else \
                 ("twenty", y - 2000) if 2000 <= y < 2100 else ("", 0)
    if head:
        out.append(f"{head} {number_word(rest) or 'hundred'}")
    return [norm(f) for f in out]


def has_year(hay: str) -> bool:
    """Does this (normalised) line name a year at all?"""
    return bool(YEAR_RX.search(hay) or YEAR_SPOKEN_RX.search(hay))


def say_count(text: str, value: str) -> int:
    """How many times this line speaks this value. 0 = not spoken.

    A count, not a flag, because a value stated twice inside ONE sentence is the same defect as
    one stated in two (rule 1 used to split on '.!?' and miss it).
    """
    v = str(value)
    forms, digits = spoken_forms(v)
    hay, squashed = norm(text), None
    years = year_forms(v)
    if years and has_year(hay) and not any(
            re.search(rf"(?<![a-z0-9]){re.escape(y)}(?![a-z0-9])", hay) for y in years):
        return 0  # the line names a year and it is not this date's: a different date was spoken
    best = 0
    for f in forms:
        best = max(best, len(re.findall(rf"(?<![a-z0-9@]){re.escape(f)}(?![a-z0-9@])", hay)))
        tight = f.replace(" ", "")
        # only a digit/@ shape gets spelled out letter by letter, and only it may skip word
        # boundaries: 'fifteen' inside 'fifteenth' is not the number fifteen
        if len(tight) >= 6 and (any(c.isdigit() for c in tight) or "@" in tight or EMAIL_RX.search(v)):
            squashed = squash(text) if squashed is None else squashed
            best = max(best, squashed.count(tight))
    if not best and digits and digits in re.sub(r"\D", "", text):
        best = 1
    return best


def says(text: str, value: str) -> bool:
    """Does this line speak this value?"""
    return say_count(text, value) > 0


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+|\n+", text or "") if s.strip()]


def amount(s: str) -> float | None:
    """The one number a value carries, if it is a number at all — 'GBP 40.0' and '40' are one value,
    an ISO date and an email are not numbers."""
    s = str(s).strip()
    if EMAIL_RX.search(s) or ISO_DATE_RX.match(s) or not NUMBER_SHAPED_RX.fullmatch(s):
        return None
    found = NUMERIC_RX.findall(s)
    return float(found[0]) if len(found) == 1 else None


def same_value(a: str, b: str) -> bool:
    """Value equality as the flow carries it: exact, then numeric, then a long-digit suffix (phones)."""
    if norm(a) == norm(b):
        return True
    fa, fb = amount(a), amount(b)
    if fa is not None and fb is not None and fa == fb:
        return True
    da, db = re.sub(r"\D", "", str(a)), re.sub(r"\D", "", str(b))  # phones: the last ten digits decide
    return len(da) >= 7 and len(db) >= 7 and (da.endswith(db[-10:]) or db.endswith(da[-10:]))


VALUE_KEYS = ("value", "new_value", "phone_number", "email", "choice", "text", "amount", "number")
CURRENCY_AMOUNT_KEYS = ("min_amount", "max_amount")  # collect_currency.py:326 - the amount, not a bound


def primary_value(args: dict, vals: list[str], name: str = "") -> str:
    """The value a collector's update tool carries — its own value key, never a correction fragment."""
    if "currency" in name and args.get("min_amount") is not None:
        lo, hi = float(args["min_amount"]), args.get("max_amount")
        amt = f"{lo:g}" if hi in (None, "", lo) else f"{lo:g}-{float(hi):g}"
        return f"{args.get('currency') or ''} {amt}".strip()
    if all(k in args for k in ("year", "month", "day")) or any(
            isinstance(args.get(k), str) and args.get(k) for k in ("first_name", "last_name")):
        return vals[0]  # arg_scalars puts the joined date / name first
    for k in VALUE_KEYS:
        if isinstance(args.get(k), (str, int, float)) and not isinstance(args.get(k), bool):
            return str(args[k]).strip()
    return vals[0] if vals else ""


def arg_scalars(args: dict, keep: tuple[str, ...] = ()) -> list[str]:
    """Every value-shaped leaf of a tool call's arguments — the evidence that a value existed."""
    out = []
    if all(k in args for k in ("year", "month", "day")):
        out.append(f"{int(args['year']):04d}-{int(args['month']):02d}-{int(args['day']):02d}")
    parts = [str(args[k]).strip() for k in ("first_name", "middle_name", "last_name")
             if isinstance(args.get(k), str) and args.get(k)]
    if parts:
        out.append(" ".join(parts))
    for k, v in args.items():
        if (k in SKIP_ARG_KEYS and k not in keep) or isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out.append(f"{v:g}" if isinstance(v, float) else str(v))
        elif isinstance(v, str) and len(v.strip()) >= 2:
            out.append(v.strip())
    return out


def facts(walk: dict) -> dict:
    """Everything the rules read: the store, the per-field value timeline, evidence and reopens.

    `after_end` turns are excluded — they were spoken to a call that had already ended and are not
    production-faithful (engine.run_scripted).
    """
    turns = [t for t in walk.get("turns", []) if not t.get("after_end")]
    stored: dict[str, str] = {}
    timeline: dict[str, list[tuple[int, str]]] = defaultdict(list)
    evidence: list[tuple[int, str]] = []
    opens: Counter = Counter()
    first_open: dict[str, int] = {}
    seeded: dict[str, bool] = {}
    active = None
    for i, t in enumerate(turns, 1):
        for tc in t.get("tool_calls", []):
            name = tc.get("name") or tc.get("tool_name") or ""
            args = tc.get("arguments") or tc.get("args") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            vals = arg_scalars(args, CURRENCY_AMOUNT_KEYS if "currency" in name else ())
            evidence += [(i, v) for v in vals]
            if name.startswith("collect_"):
                active = slug(args.get("name") or active or "")
                opens[active] += 1
                first_open.setdefault(active, i)
                seeded.setdefault(active, bool(str(args.get("known_value") or "").strip()))
            elif name.startswith("record_"):
                field, value = slug(name[len("record_"):]), str(args.get("value", "")).strip()
                stored[field] = value
                timeline[field].append((i, value))
            elif name == "change_earlier_value":
                field, value = slug(args.get("name") or ""), str(args.get("new_value", "")).strip()
                stored[field] = value
                timeline[field].append((i, value))
            elif name.startswith(("update_", "confirm_")) and active and vals:
                if (value := primary_value(args, vals, name)):
                    timeline[active].append((i, value))
    # which field a value belongs to, so a line spoken BEFORE that collector opened is not its
    # acknowledgement ("Good afternoon" is not the choice `Afternoon`)
    field_of = {norm(v): field for field, vs in timeline.items() for _, v in vs}
    field_of.update({norm(v): field for field, v in stored.items()})
    return {"turns": turns, "stored": stored, "timeline": timeline, "evidence": evidence,
            "opens": opens, "first_open": first_open, "seeded": seeded, "field_of": field_of}


def completed(walk: dict, expect: dict) -> list[str]:
    """Ended as the scenario declared, or its declared exit reached."""
    turns = [t for t in walk.get("turns", []) if not t.get("after_end")]
    if not turns:
        return ["incomplete: no turns"]
    last = turns[-1]
    bad = []
    want_end = expect.get("ended")
    if want_end is None and not expect:
        want_end = True  # a scenario that declares NOTHING: completion is the call ending
    if want_end is not None and bool(last.get("ended")) != bool(want_end):
        bad.append(f"turn {len(turns)}: ended {bool(last.get('ended'))}, scenario declared {want_end}")
    if expect.get("stop_reason") and last.get("stop_reason") != expect["stop_reason"]:
        bad.append(f"turn {len(turns)}: stop_reason {last.get('stop_reason')!r}, "
                   f"declared {expect['stop_reason']!r}")
    if expect.get("intent") and not any(t.get("intent") == expect["intent"] for t in turns):
        bad.append(f"declared exit {expect['intent']!r} never reached "
                   f"(intents: {sorted({t.get('intent') for t in turns if t.get('intent')})})")
    if expect.get("not_intent"):
        hit = [i for i, t in enumerate(turns, 1) if t.get("intent") == expect["not_intent"]]
        if hit:
            bad.append(f"turn {hit[0]}: forbidden exit {expect['not_intent']!r} fired")
    return bad


def variable_failures(f: dict, expect: dict, known: dict[str, list[str]]) -> list[str]:
    """Every expected variable correct BY VALUE under any key; declined fields absent by value too."""
    bad = []
    stored = f["stored"]
    for field, want in (expect.get("variables") or {}).items():
        held = stored.get(slug(field))
        if held is not None:
            # the node DECLARES its ten Inputs, so `record_<field>` is the runtime's key, not the
            # model's choice: a value under some other key is not this field's value
            if not same_value(held, want):
                bad.append(f"{field}: {want!r} not stored — {slug(field)}={held!r}")
            continue
        if not any(same_value(v, want) for v in stored.values()):
            under = ", ".join(f"{k}={v}" for k, v in stored.items()) or "nothing stored"
            bad.append(f"{field}: {want!r} stored under no key ({under})")
    for field in expect.get("variables_absent") or []:
        held = stored.get(slug(field), "")
        if held:
            bad.append(f"{field}: declined but stored as {held!r}")
            continue
        for want in known.get(slug(field), []):
            if norm(want) in BOOLISH:
                continue  # a yes/no is every boolean field's value: it proves nothing about this one
            leak = [k for k, v in stored.items() if v and same_value(v, want)]
            if leak:
                bad.append(f"{field}: declined value {want!r} stored under {', '.join(leak)}")
    return bad


def candidate_values(f: dict) -> list[str]:
    """The values in play this walk — what a prepared line could state."""
    seen, out = set(), []
    for v in [v for vs in f["timeline"].values() for _, v in vs] + list(f["stored"].values()):
        n = norm(v)
        # a two-digit answer (an age, a journey time) is a value too — it just has to be a number
        if n in BOOLISH or n in seen or len(n) < (2 if amount(v) is not None else 3):
            continue
        if any(same_value(v, kept) for kept in out):  # two spellings of one answer are one candidate
            continue
        seen.add(n)
        out.append(v)
    return out


def speech_failures(f: dict, retries: int, absent: dict[str, list[str]] | None = None) -> list[str]:
    """The five prepared-speech rules, read off the transcript."""
    bad = []
    turns = f["turns"]
    spoke_turns = [i for i, t in enumerate(turns, 1) if (t.get("agent") or "").strip()]
    cands = candidate_values(f)
    spoken = {i: {v for v in cands if says(turns[i - 1]["agent"], v)} for i in spoke_turns}
    # a turn that states most of the record — or the closing line carrying more than one value — is
    # a recap, not an acknowledgement of one answer
    recap = {i for i, vs in spoken.items() if len(vs) >= RECAP_VALUES}
    if spoke_turns and len(spoken[spoke_turns[-1]]) >= 2:
        recap.add(spoke_turns[-1])
    for v in cands:
        # only from the turn this value's own collector opened: a choice label that is also an
        # ordinary word ("Good afternoon") is not an acknowledgement of the answer
        floor = f["first_open"].get(f["field_of"].get(norm(v), ""), 0)
        said = [i for i in spoke_turns if i >= floor and v in spoken[i]]
        # 1. no acknowledgement line spoken twice for one answer
        for i in said:
            if i not in recap and say_count(turns[i - 1]["agent"], v) >= 2:
                bad.append(f"turn {i}: double acknowledgement — {v!r} stated twice in one turn")
        for a, b in zip(said, said[1:]):
            if {a, b} & recap:
                continue
            if spoke_turns.index(b) == spoke_turns.index(a) + 1 and not says(turns[b - 1].get("user") or "", v):
                bad.append(f"turn {b}: double acknowledgement — {v!r} stated again after turn {a}, "
                           f"with no new answer for it")
        # 3. no prepared line spoken before the answer it acknowledges
        first_ev = min([i for i, e in f["evidence"] if same_value(e, v)]
                       + [i for i in spoke_turns if says(turns[i - 1].get("user") or "", v)]
                       + [i for i, t in enumerate(turns, 1) if says(t.get("user") or "", v)], default=None)
        if said and first_ev is not None and said[0] < first_ev:
            bad.append(f"turn {said[0]}: prepared line spoke {v!r} before the answer "
                       f"(first given at turn {first_ev})")
    # 2. no read-back of a value that was later corrected without a new read-back of the corrected one
    for field, writes in f["timeline"].items():
        for (_, old), (t, new) in zip(writes, writes[1:]):
            if same_value(old, new) or norm(new) in BOOLISH:
                continue
            read_old = [i for i in spoke_turns if i <= t and says(turns[i - 1]["agent"], old)]
            if read_old and not any(i >= t and says(turns[i - 1]["agent"], new) for i in spoke_turns):
                bad.append(f"turn {read_old[-1]}: stale read-back — {old!r} was read back on {field}, "
                           f"corrected to {new!r} at turn {t}, and the correction was never read back")
    # 3b. a value for a DECLINED field, spoken though nothing carried it: rule 3 sees only values
    # that reached a tool, and a date put in the caller's mouth never does
    for field, wants in (absent or {}).items():
        for want in wants:
            if norm(want) in BOOLISH or any(same_value(want, c) for c in cands):
                continue
            said = [i for i in spoke_turns if says(turns[i - 1]["agent"], want)]
            if said and not any(says(t.get("user") or "", want) for t in turns):
                bad.append(f"turn {said[0]}: spoke {want!r} for {field}, which the caller never gave")
    # 4. no spoken Python literal, bracketed placeholder or variable name
    for i, t in enumerate(turns, 1):
        for label, rx in BAD_SPEECH:
            m = rx.search(t.get("agent") or "")
            if m:
                bad.append(f"turn {i}: spoken {label} {m.group().strip()!r}")
    # 5. at most one re-ask per field beyond the configured retry
    cap = 1 + retries + MAX_OPENS_OVER_RETRY
    for field, n in sorted(f["opens"].items()):
        if n > cap:
            bad.append(f"{field}: collector opened {n} times (cap {cap} = 1 ask + {retries} "
                       f"configured retry + {MAX_OPENS_OVER_RETRY} re-ask)")
    return bad


def required_inputs() -> set[str]:
    """The node's REQUIRED Inputs, read off the built workspace. Empty when there is no workspace."""
    global _REQUIRED
    if _REQUIRED is None:
        _REQUIRED = set()
        try:
            flow = json.loads((pathlib.Path(__file__).parent / "ws" / "flow.json").read_text())
        except (OSError, ValueError):
            return _REQUIRED
        for node in flow.get("nodes", []):
            for v in (node.get("data", {}).get("config") or {}).get("extract_variables") or []:
                if ((v.get("collection") or {}).get("required")):
                    _REQUIRED.add(slug(v["variable_name"]))
    return _REQUIRED


def floor_failures(f: dict, expect: dict) -> list[str]:
    """What a COMPLETED walk must have done at all: speak, and hold what it booked on."""
    turns, bad = f["turns"], []
    if turns and not any((t.get("agent") or "").strip() for t in turns):
        return ["incomplete: the agent never spoke"]
    intents = {t.get("intent") for t in turns if t.get("intent")}
    last = turns[-1] if turns else {}
    booked = "Reschedule Booked" in intents or (
        bool(last.get("ended")) and last.get("stop_reason") == "end_conversation" and not intents)
    missing = sorted(required_inputs() - set(f["stored"])
                     - {slug(x) for x in expect.get("variables_absent") or []})
    if booked and missing:
        bad.append(f"booked with required Inputs never stored: {', '.join(missing)}")
    return bad


def _redone(line: str, failed: set[str]) -> bool:
    """An engine by-KEY variable line this judge redid BY VALUE and passed (X8: the engine compares
    literally, so a phone with a country prefix or an uninferred currency fails it and is right)."""
    m = re.search(r"variables(?:_absent)?\[([^\]]+)\]", line)
    return bool(m) and slug(m.group(1)) not in failed


def judge(walk: dict, expect: dict, known: dict[str, list[str]] | None = None,
          retries: int = RETRIES_DEFAULT) -> list[str]:
    f = facts(walk)
    variables = variable_failures(f, expect, known or {})
    failed = {slug(b.split(":", 1)[0]) for b in variables}
    engine = [x for x in (walk.get("failures") or []) if not _redone(x, failed)]
    if walk.get("failures") is None:
        engine.append("incomplete: the walk has no scenario_finished event")
    absent = {x: (known or {}).get(slug(x), []) for x in expect.get("variables_absent") or []}
    seed = SEEDED_FIELDS.get(walk.get("scenario", ""))
    seeded = [] if not seed or f["seeded"].get(seed) else [
        f"{seed}: its collector was opened with no known_value, though the caller had already said it"]
    return engine + completed(walk, expect) + floor_failures(f, expect) + variables + seeded \
        + speech_failures(f, retries, absent)


# ---------------------------------------------------------------- loading

def load_report(path: pathlib.Path) -> list[dict]:
    walks, cur = [], None
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        kind = rec.get("type")
        if kind == "scenario_started":
            cur = {"scenario": rec["name"], "run": rec.get("run", 1), "turns": [],
                   "failures": None, "t0": rec.get("ts", 0.0)}
            walks.append(cur)
        elif cur is None:
            continue
        elif kind == "turn":
            cur["turns"].append(rec)
        elif kind == "scenario_finished":
            cur["failures"] = rec.get("failures") or []
    return walks


def load_expects(dirs: list[pathlib.Path]) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Scenario expectations, plus the campaign-wide value per field — the union of every
    `expect.variables` in the pack is what an absence check looks for."""
    import yaml
    expects: dict[str, dict] = {}
    for d in dirs:
        for y in sorted(d.glob("*.yaml")):
            expects.setdefault(y.stem, (yaml.safe_load(y.read_text()) or {}).get("expect") or {})
    known: dict[str, list[str]] = {slug(k): list(v) for k, v in VALUE_HINTS.items()}
    for e in expects.values():
        for field, value in (e.get("variables") or {}).items():
            known.setdefault(slug(field), [])
            if value not in known[slug(field)]:
                known[slug(field)].append(value)
    return expects, known


def llm_requests(logs: list[pathlib.Path]) -> dict[str, list[tuple[float, str]]]:
    """One entry per PHYSICAL LLM request, per call_uuid: (timestamp, speech_id).

    Plus `__attempts__`: the call_uuids the engine ran more than once (a throttled attempt is
    rerun under the same run_idx, engine.run_suite:481-489, so its discarded requests land under
    the same uuid and inflate that walk's count).

    `LLM metrics collected` is emitted once per completed chat completion (it carries the provider's
    own request_id), so it is the physical count — the collectors' own requests included, and those
    carry no speech_id. `LLM request started` is the debug-tracing marker on the main agent path
    only, used when the metrics line is absent.
    """
    out: dict[str, list[tuple[float, str]]] = defaultdict(list)
    attempts: Counter = Counter()
    for log in logs:
        text = log.read_text(errors="replace")
        marker = "LLM metrics collected" if "LLM metrics collected" in text else "LLM request started"
        for line in text.splitlines():
            if ATTEMPT_MARKER in line:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if str(rec.get("message", "")).startswith(ATTEMPT_MARKER):
                    attempts[rec.get("call_uuid", "")] += 1
                continue
            if marker not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            # startswith, not `in`: "Scribe LLM metrics collected" is a different request
            if not str(rec.get("message", "")).startswith(marker):
                continue
            found = re.search(r"speech_id='([^']*)'", rec["message"])
            speech = found.group(1) if found else rec.get("speech_id", "")
            try:
                when = datetime.fromisoformat(rec["timestamp"]).timestamp()
            except (ValueError, KeyError):
                continue
            out[rec.get("call_uuid", "")].append((when, speech))
    out["__attempts__"] = [(float(n), uuid) for uuid, n in attempts.items() if n > 1]
    return out


def resolve(spec: str) -> tuple[str, list[pathlib.Path], list[pathlib.Path], list[pathlib.Path]]:
    """`[arm=]path,path` -> (arm, report files, stderr logs, RUN-INFO files).

    An arm directory written by run_arm.sh carries its own copy of EVERY report it produced (one
    per `--scenario` name), so judge them all; anywhere else, newest wins.
    """
    arm, _, rest = spec.rpartition("=")
    tiers: list[list[pathlib.Path]] = [[], []]  # a reports/ file outranks a stray .jsonl
    logs: list[pathlib.Path] = []
    paths = [pathlib.Path(p).expanduser().resolve() for p in rest.split(",") if p]
    for p in paths:
        if p.is_file():
            if p.suffix == ".jsonl":
                tiers[p.parent.name != "reports"].append(p)
        else:
            tiers[0] += sorted(p.rglob("reports/*.jsonl"))
            tiers[1] += sorted(p.rglob("*.jsonl"))
        logs += [p] if p.suffix == ".err" else sorted(p.rglob("*.err"))
    infos = [q for p in paths if p.is_dir() for q in sorted(p.rglob("RUN-INFO.txt"))]
    found = tiers[0] or tiers[1]
    reports = sorted(found) if infos else ([max(found, key=lambda c: c.stat().st_mtime)] if found else [])
    if not arm:
        parts = [q for p in paths for q in (*p.parts, p.stem)]
        arm = next((a for a in ("prepared", "off") for q in parts
                    if q == a or q.endswith(f"-{a}")), paths[0].name if paths else "arm")
    return arm, reports, logs, infos


def env_digest(infos: list[pathlib.Path]) -> str:
    """The `env sha256 …` line run_arm.sh writes, so two arms can be proven to share an env file."""
    for info in infos:
        m = re.search(r"env sha256 ([0-9a-f]{64})", info.read_text(errors="replace"))
        if m:
            return m.group(1)
    return ""


def main(argv: list[str]) -> int:
    here = pathlib.Path(__file__).parent
    scen_dirs, retries, specs = [], RETRIES_DEFAULT, []
    it = iter(argv)
    for a in it:
        if a == "--scenarios":
            scen_dirs.append(pathlib.Path(next(it)))
        elif a == "--retries":
            retries = int(next(it))
        elif not a.startswith("-"):
            specs.append(a)
    specs = specs or [str(here / "ws")]
    expects, known = load_expects(scen_dirs or [here / "scenarios", here / "ws" / "scenarios"])
    arms: dict[str, dict] = {}
    owner: dict[pathlib.Path, str] = {}
    for spec in specs:
        arm, reports, logs, infos = resolve(spec)
        if not reports:
            sys.exit(f"no reports/*.jsonl under {spec}")
        for r in reports:
            if r in owner:  # M1: `prepared=X off=X` used to compare a file with itself in silence
                sys.exit(f"REFUSED: {r} is already the {owner[r]!r} arm — two arms, one file")
            owner[r] = arm
        for r in reports:
            print(f"# {arm}: {r}")
        for log in logs:
            print(f"#   stderr log: {log}")
        llm = llm_requests(logs)
        arms[arm] = {"walks": [w for r in reports for w in load_report(r)], "llm": llm,
                     "logs": logs, "env": env_digest(infos),
                     "prepared_events": sum(t.count(m) for log in logs
                                            for t in [log.read_text(errors="replace")]
                                            for m in PREPARED_MARKERS),
                     "retried": [u for _, u in llm.get("__attempts__", [])]}

    missing = sorted({w["scenario"] for a in arms.values() for w in a["walks"]} - set(expects))
    if missing:
        print(f"! no scenario YAML for: {', '.join(missing)} — judged on the speech rules only")
    for arm, data in arms.items():
        if data["logs"] and arm.endswith("prepared") and not data["prepared_events"]:
            print(f"! {arm}: its log carries no prepared.* event — that arm did NOT run prepared")
        if data["logs"] and arm.endswith("off") and data["prepared_events"]:
            print(f"! {arm}: its log carries {data['prepared_events']} prepared.* events — not the off arm")
        if data["retried"]:
            print(f"! {arm}: {len(data['retried'])} walk(s) were retried by the engine; their LLM "
                  f"counts include the discarded attempt ({', '.join(data['retried'][:3])}…)")
    digests = {a: d["env"] for a, d in arms.items() if d["env"]}
    if len(set(digests.values())) > 1:
        print(f"! the arms did not run the same env file: {digests}")
    elif len(arms) > 1 and len(digests) < len(arms):
        print("! no env digest in RUN-INFO.txt for every arm: the arms are not proven comparable")

    names = sorted(arms, key=lambda a: (0 if a.endswith("prepared") else 1 if a.endswith("off") else 2, a))
    rows: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    fails: list[str] = []
    stats = {a: Counter() for a in names}
    for arm, data in arms.items():
        for walk in data["walks"]:
            expect = expects.get(walk["scenario"], NO_YAML)
            f = facts(walk)
            bad = judge(walk, expect, known, retries)
            ok, n = rows[walk["scenario"]].get(arm, (0, 0))
            rows[walk["scenario"]][arm] = (ok + (not bad), n + 1)
            stats[arm]["walks"] += 1
            stats[arm]["turns"] += len(f["turns"])
            stats[arm]["pass"] += not bad
            for kind in ("double acknowledgement", "stale read-back", "prepared line spoke",
                         "spoken python literal", "spoken bracketed placeholder",
                         "spoken variable name", "collector opened"):
                stats[arm][kind] += sum(1 for b in bad if kind in b)
            stats[arm]["variables"] += sum(1 for b in bad if "stored under no key" in b
                                            or "not stored" in b or "declined" in b
                                            or "never gave" in b)
            stats[arm]["completion"] += sum(1 for b in bad if "ended " in b or "stop_reason " in b
                                            or "forbidden exit" in b or "declared exit" in b
                                            or b.startswith("incomplete") or "booked with" in b)
            total_llm, per_speech = turn_llm_counts(walk, data["llm"])
            if total_llm:
                stats[arm]["llm"] += total_llm
                stats[arm]["llm_turns"] += len(f["turns"])
                stats[arm]["llm_walks"] += 1
            if bad:
                head = (f"{walk['scenario']} run {walk['run']} [{arm}] — {len(f['turns'])} turns"
                        + (f", {total_llm} LLM requests (per speech {per_speech})" if total_llm else ""))
                fails.append("\n".join([head] + [f"   - {b}" for b in bad]))

    width = max((len(s) for s in rows), default=10) + 2
    print("\n## pass rate (x/N per arm)\n")
    print("scenario".ljust(width) + "".join(a.ljust(12) for a in names))
    for scenario in sorted(rows):
        cells = "".join(f"{rows[scenario].get(a, (0, 0))[0]}/{rows[scenario].get(a, (0, 0))[1]}".ljust(12)
                        for a in names)
        print(scenario.ljust(width) + cells)
    print("TOTAL".ljust(width) + "".join(f"{stats[a]['pass']}/{stats[a]['walks']}".ljust(12) for a in names))

    print(f"\n## failing walks ({len(fails)})\n")
    print("\n".join(fails) if fails else "none")

    print("\n## prepared vs off\n")
    keys = ["walks", "pass", "completion", "variables", "double acknowledgement", "stale read-back",
            "prepared line spoke", "spoken python literal", "spoken bracketed placeholder",
            "spoken variable name", "collector opened"]
    if names[:1] != ["prepared"] and len(names) == 2:
        print(f"(delta is {names[0]} minus {names[1]})")
    print("measure".ljust(32) + "".join(a.ljust(12) for a in names) + "delta")
    for k in keys:
        vals = [stats[a][k] for a in names]
        delta = f"{vals[0] - vals[1]:+d}" if len(vals) == 2 else ""
        print(k.ljust(32) + "".join(str(v).ljust(12) for v in vals) + delta)
    mean = [stats[a]["turns"] / max(1, stats[a]["walks"]) for a in names]
    print("turns / walk".ljust(32) + "".join(f"{m:.1f}".ljust(12) for m in mean)
          + (f"{mean[0] - mean[1]:+.1f}" if len(mean) == 2 else ""))
    if any(stats[a]["llm_walks"] for a in names):
        for label, top, bottom in (("LLM requests / walk", "llm", "llm_walks"),
                                   ("LLM requests / turn (walk mean)", "llm", "llm_turns")):
            vals = [stats[a][top] / max(1, stats[a][bottom]) for a in names]
            print(label.ljust(32) + "".join(f"{v:.2f}".ljust(12) for v in vals)
                  + (f"{vals[0] - vals[1]:+.2f}" if len(vals) == 2 else ""))
        print("   over the "
              + ", ".join(f"{stats[a]['llm_walks']}/{stats[a]['walks']} {a} walks the log covers"
                          for a in names)
              + ". Per-turn is a walk MEAN, not an attribution: the report's turn ts is the flush "
                "time (engine._EventBuffer), so no request can be bound to one turn.")
    else:
        print("LLM requests: NOT AVAILABLE — the report carries no LLM request field at all, and no "
              "*.err log was given. Pass the arm's log (run_arm.sh writes run-<label>.err) for the "
              "runner's own 'LLM metrics collected' lines, one per physical request.")
    return 1 if fails else 0


def turn_llm_counts(walk: dict, llm: dict[str, list[tuple[float, str]]]) -> tuple[int, list[int]]:
    """This walk's physical LLM requests: (total, per agent speech, oldest speech first).

    NOT per report turn, and it cannot be: the report's turn `ts` is the flush timestamp —
    engine._EventBuffer holds a whole scenario's events and RunRecorder.event stamps them all at
    replay — so turns cannot be separated in time. `speech_id` is the finest grain the log offers,
    and a speech spans several turns; requests with no speech_id (the collectors' own) are in the
    total only.
    """
    reqs = llm.get(f"sim-cli-{walk['scenario']}-{walk['run']}") or []
    counts: Counter = Counter()
    order: list[str] = []
    for _, speech in sorted(reqs):
        if not speech:
            continue
        if speech not in counts:
            order.append(speech)
        counts[speech] += 1
    return len(reqs), [counts[s] for s in order]


# ---------------------------------------------------------------- selftest

def _walk(turns, failures=(), scenario="plain-walk", run=1):
    """turns: (user, agent, [(tool, args), ...]) triples."""
    recs = [{"ts": float(i), "user": u, "agent": a, "after_end": False, "intent": None,
             "ended": False, "stop_reason": "",
             "tool_calls": [{"name": n, "arguments": json.dumps(x)} for n, x in (tc or [])]}
            for i, (u, a, tc) in enumerate(turns, 1)]
    if recs:
        recs[-1].update(ended=True, stop_reason="end_conversation")
    return {"scenario": scenario, "run": run, "turns": recs, "failures": list(failures), "t0": 0.0}


def selftest() -> None:
    global _REQUIRED
    _REQUIRED = set()  # the toy walks below are not campaign walks; the floor is checked on its own
    assert spoken_forms("2028-03-12")[0] and "march 12" in spoken_forms("2028-03-12")[0]
    assert says("Let's say the twelfth of March, then.", "2028-03-12")
    assert says("So that's March 12th.", "2028-03-12")
    assert not says("So that's March 19th.", "2028-03-12")
    assert says("Thirty-five minutes, noted.", "35") and not says("Forty minutes.", "35")
    assert says("that's ruth.okafor@example.com", "ruth.okafor@example.com")
    assert says("oh seven seven double oh 900123 — sorry, 07700 900123", "07700900123")
    assert same_value("GBP 40.0", "40") and same_value("+447700900123", "07700900123")
    assert not same_value("2028-03-12", "2028-03-19")

    clean = _walk([
        ("", "Hello, this is the Ridgeway Clinic desk. Can I take your name?",
         [("collect_name", {"name": "patient_full_name"})]),
        ("Ruth Okafor.", "Thank you, Ruth. What is your date of birth?",
         [("update_name", {"first_name": "Ruth", "last_name": "Okafor"}),
          ("collect_dob", {"name": "date_of_birth"})]),
        ("Ninth of June nineteen sixty-two.", "The ninth of June 1962. Which day would you like?",
         [("update_dob", {"year": 1962, "month": 6, "day": 9}),
          ("collect_date", {"name": "new_appointment_date"})]),
        ("The twelfth of March twenty twenty-eight.", "The twelfth of March. You are all set.",
         [("update_date", {"year": 2028, "month": 3, "day": 12}),
          ("record_patient_full_name", {"value": "Ruth Okafor"}),
          ("record_date_of_birth", {"value": "1962-06-09"}),
          ("record_new_appointment_date", {"value": "2028-03-12"})]),
    ])
    expect = {"ended": True, "stop_reason": "end_conversation",
              "variables": {"new_appointment_date": "2028-03-12", "date_of_birth": "1962-06-09"}}
    assert judge(clean, expect) == [], judge(clean, expect)

    # a value stored under a key the model chose itself still passes: judged BY VALUE
    free_key = json.loads(json.dumps(clean))
    free_key["turns"][3]["tool_calls"][-1]["name"] = "record_appt_day"
    assert judge(free_key, expect) == [], judge(free_key, expect)
    # ... a different value under the right-looking key does not
    wrong = json.loads(json.dumps(clean))
    wrong["turns"][3]["tool_calls"][-1]["arguments"] = json.dumps({"value": "2028-03-19"})
    got = judge(wrong, expect)
    assert got[0] == "new_appointment_date: '2028-03-12' not stored — new_appointment_date='2028-03-19'", got
    # ... and the same walk trips rule 2: what was read back is not what was stored
    assert got[1].startswith("turn 4: stale read-back — '2028-03-12'"), got

    # declined field: absent by key AND by value, wherever the value landed
    declined = _walk([
        ("", "What is your mobile?", [("collect_phone", {"name": "mobile_number"})]),
        ("I don't give that out.", "Understood. Goodbye.",
         [("decline_phone_number_capture", {"reason": "refused"}),
          ("record_notes", {"value": "07700 900123"})]),
    ])
    _, known = {}, {"mobile_number": ["07700900123"]}
    got = judge(declined, {"variables_absent": ["mobile_number"]}, known)
    assert got == ["mobile_number: declined value '07700900123' stored under notes"], got
    assert judge(_walk([("", "What is your mobile?", [("collect_phone", {"name": "mobile_number"})]),
                        ("I don't give that out.", "Understood. Goodbye.",
                         [("decline_phone_number_capture", {"reason": "refused"})])]),
                 {"variables_absent": ["mobile_number"]}, known) == []
    # a yes/no is every boolean field's value, so it never proves the declined one leaked
    boolean_leak = _walk([("No interpreter.", "Noted.", [("record_callback", {"value": "no"})])])
    assert judge(boolean_leak, {"variables_absent": ["interpreter_needed"]},
                 {"interpreter_needed": ["no"]}) == []

    # RULE 1 — the same answer acknowledged twice, in one turn and across two turns
    twice_one_turn = _walk([
        ("The twelfth of March.", "The twelfth of March. Got it — the twelfth of March it is.",
         [("collect_date", {"name": "new_appointment_date"}),
          ("update_date", {"year": 2028, "month": 3, "day": 12})]),
    ])
    got = judge(twice_one_turn, {})
    assert got == ["turn 1: double acknowledgement — '2028-03-12' stated twice in one turn"], got
    twice_two_turns = _walk([
        ("The twelfth of March.", "The twelfth of March. Which part of the day?",
         [("collect_date", {"name": "new_appointment_date"}),
          ("update_date", {"year": 2028, "month": 3, "day": 12})]),
        ("Late morning.", "Late morning on the twelfth of March. Thank you.",
         [("collect_choice", {"name": "preferred_time_of_day"})]),
    ])
    got = judge(twice_two_turns, {})
    assert got == ["turn 2: double acknowledgement — '2028-03-12' stated again after turn 1, "
                   "with no new answer for it"], got
    # ... unless the caller said it again themselves
    licensed = json.loads(json.dumps(twice_two_turns))
    licensed["turns"][1]["user"] = "Late morning on the twelfth of March, yes."
    assert judge(licensed, {}) == [], judge(licensed, {})

    # RULE 2 — a read-back that went stale when the value was corrected
    stale = _walk([
        ("The twelfth of March.", "The twelfth of March. Which part of the day?",
         [("collect_date", {"name": "new_appointment_date"}),
          ("update_date", {"year": 2028, "month": 3, "day": 12})]),
        ("Sorry, the nineteenth.", "Right. Which part of the day?",
         [("update_date", {"year": 2028, "month": 3, "day": 19})]),
        ("Late morning.", "Late morning, thank you.", [("record_new_appointment_date", {"value": "2028-03-19"})]),
    ])
    got = judge(stale, {})
    assert got == ["turn 1: stale read-back — '2028-03-12' was read back on new_appointment_date, "
                   "corrected to '2028-03-19' at turn 2, and the correction was never read back"], got
    fixed = json.loads(json.dumps(stale))
    fixed["turns"][1]["agent"] = "The nineteenth of March. Which part of the day?"
    assert judge(fixed, {}) == [], judge(fixed, {})

    # RULE 3 — a prepared line spoken before the answer it acknowledges
    early = _walk([
        ("Hello.", "The twelfth of March, then. What day would you like?",
         [("collect_date", {"name": "new_appointment_date"})]),
        ("The twelfth of March.", "Thank you.",
         [("update_date", {"year": 2028, "month": 3, "day": 12})]),
    ])
    got = judge(early, {})
    assert got == ["turn 1: prepared line spoke '2028-03-12' before the answer (first given at turn 2)"], got

    # RULE 4 — a spoken placeholder, a Python literal and a variable name
    placeholder = _walk([("Ruth Okafor.", "Thank you, [patient_full_name]. Noted.",
                          [("collect_name", {"name": "patient_full_name"}),
                           ("record_patient_full_name", {"value": "Ruth Okafor"})])])
    got = judge(placeholder, {})
    assert got == ["turn 1: spoken bracketed placeholder '[patient_full_name]'",
                   "turn 1: spoken variable name 'patient_full_name'"], got
    literal = _walk([("Ninth of June nineteen sixty-two.", "I have 1962-06-09, is that right?",
                      [("collect_dob", {"name": "dob"}), ("update_dob", {"year": 1962, "month": 6, "day": 9})])])
    assert "spoken python literal '1962-06-09'" in judge(literal, {})[0], judge(literal, {})
    assert "spoken python literal 'None'" in judge(
        _walk([("x.", "Your access note is None.", [])]), {})[0]

    # RULE 5 — one re-ask beyond the configured retry
    reask = _walk([(f"...", "What is your mobile?", [("collect_phone", {"name": "mobile_number"})])] * 4)
    got = [b for b in judge(reask, {}) if "collector opened" in b]
    assert got == ["mobile_number: collector opened 4 times (cap 3 = 1 ask + 1 configured retry "
                   "+ 1 re-ask)"], got
    assert not [b for b in judge(_walk([("...", "What is your mobile?",
                                         [("collect_phone", {"name": "mobile_number"})])] * 3), {})
                if "collector opened" in b]

    # completion: declared exit, forbidden exit, and a walk the engine never finished
    ended_false = _walk([("Hi.", "Hello.", [])])
    ended_false["turns"][-1].update(ended=False, stop_reason="")
    assert judge(ended_false, {"ended": True, "stop_reason": "end_conversation"}) == [
        "turn 1: ended False, scenario declared True",
        "turn 1: stop_reason '', declared 'end_conversation'"]
    assert judge(ended_false, {"ended": False}) == []
    exits = _walk([("Take me off the list.", "You will not be contacted again.", [])])
    exits["turns"][-1]["intent"] = "Do Not Contact"
    assert judge(exits, {"intent": "Do Not Contact"}) == []
    assert judge(exits, {"not_intent": "Do Not Contact", "ended": True}) == [
        "turn 1: forbidden exit 'Do Not Contact' fired"]
    unfinished = _walk([("Hi.", "Hello.", [])])
    unfinished["failures"] = None
    assert judge(unfinished, {"ended": True})[0] == "incomplete: the walk has no scenario_finished event"
    # the engine's own verdict is carried, except the by-key variable checks this judge redoes
    carried = _walk([("Hi.", "Hello.", [])], failures=(
        "final: intent: expected 'X', got 'Y'", "final: variables[mobile_number]: expected 'a', got 'b'"))
    assert judge(carried, {"ended": True}) == ["final: intent: expected 'X', got 'Y'"]

    # physical LLM requests, grouped by the log's own speech_id, oldest speech first
    log = {"sim-cli-plain-walk-1": [(0.5, "a"), (0.9, "a"), (1.5, "b"), (2.5, "c"), (3.9, "c"),
                                    (3.5, "c"), (4.0, "")]}  # the last is a collector's own request
    assert turn_llm_counts(clean, log) == (7, [2, 1, 3]), turn_llm_counts(clean, log)
    assert turn_llm_counts(clean, {}) == (0, [])
    # H1 — the value is in the walk, but under a key that is not this Input's: the engine's own
    # by-key line survives, because this judge failed the field too
    misfiled = json.loads(json.dumps(clean))
    misfiled["turns"][3]["tool_calls"][-1]["arguments"] = json.dumps({"value": "2028-03-19"})
    misfiled["turns"][3]["tool_calls"].append(
        {"name": "record_access_notes", "arguments": json.dumps({"value": "2028-03-12"})})
    misfiled["failures"] = ["final: variables[new_appointment_date]: expected 'x', got 'y'"]
    got = judge(misfiled, expect)
    assert got[0].startswith("final: variables[new_appointment_date]"), got
    assert any("not stored" in b for b in got), got

    # H3 — a date is judged with its YEAR: a year correction is visible, and a correct one is clean
    assert not says("The ninth of June nineteen twenty-six.", "1962-06-09")
    assert says("The ninth of June nineteen sixty-two.", "1962-06-09")
    assert says("The ninth of June, then.", "1962-06-09")  # no year named: month and day decide
    year_fix = _walk([
        ("Ninth of June nineteen twenty-six.", "The ninth of June nineteen twenty-six. Which day?",
         [("collect_dob", {"name": "date_of_birth"}), ("update_dob", {"year": 1926, "month": 6, "day": 9})]),
        ("Sorry, nineteen sixty-two.", "The ninth of June nineteen sixty-two, thank you. Which day?",
         [("update_dob", {"year": 1962, "month": 6, "day": 9})]),
        ("The twelfth of March.", "The twelfth of March. All set.",
         [("collect_date", {"name": "new_appointment_date"}),
          ("update_date", {"year": 2028, "month": 3, "day": 12}),
          ("record_date_of_birth", {"value": "1962-06-09"})]),
    ])
    fix_expect = {"ended": True, "variables": {"date_of_birth": "1962-06-09"}}
    assert judge(year_fix, fix_expect) == [], judge(year_fix, fix_expect)
    left_stale = json.loads(json.dumps(year_fix))
    left_stale["turns"][1]["agent"] = "The ninth of June nineteen twenty-six, thank you. Which day?"
    assert any("stale read-back" in b for b in judge(left_stale, {})), judge(left_stale, {})

    # M4 — a choice label that is also an ordinary word, spoken before its collector opened
    greeting = _walk([
        ("", "Good afternoon, this is Maya. Can I take your name?",
         [("collect_name", {"name": "patient_full_name"})]),
        ("Ruth Okafor.", "Thanks. Which part of the day suits you?",
         [("update_name", {"first_name": "Ruth", "last_name": "Okafor"}),
          ("collect_choice", {"name": "preferred_time_of_day"})]),
        ("Afternoon.", "Afternoon it is. Thank you.",
         [("update_choice", {"choice": "Afternoon"}),
          ("record_preferred_time_of_day", {"value": "Afternoon"})]),
    ])
    assert judge(greeting, {"ended": True, "variables": {"preferred_time_of_day": "Afternoon"}}) == [], \
        judge(greeting, {})

    # M5 — update_currency_value carries the amount as min_amount, not as a bound to skip
    fee = facts(_walk([("Forty pounds.", "Forty pounds, noted.",
                        [("collect_currency", {"name": "outstanding_fee"}),
                         ("update_currency_value", {"min_amount": 40.0, "max_amount": None,
                                                    "currency": "GBP", "period": ""})])]))
    assert [v for _, v in fee["timeline"]["outstanding_fee"]] == ["GBP 40"], fee["timeline"]

    # M7 — the same value twice inside ONE sentence is still a double acknowledgement
    one_sentence = _walk([("The twelfth of March.",
                           "The twelfth of March, yes, the twelfth of March it is, and the time?",
                           [("collect_date", {"name": "new_appointment_date"}),
                            ("update_date", {"year": 2028, "month": 3, "day": 12})])])
    assert any("double acknowledgement" in b for b in judge(one_sentence, {})), judge(one_sentence, {})

    # M3 — a scenario that declares only what must NOT happen does not demand an ending
    halted = _walk([("I won't give it.", "I do need it, though.",
                     [("collect_phone", {"name": "mobile_number"})])])
    halted["turns"][-1].update(ended=False, stop_reason="")
    assert judge(halted, {"not_intent": "Reschedule Booked", "variables_absent": ["mobile_number"]}) == []

    # L1 — a value for a declined field, spoken though nothing ever carried it
    put_words = _walk([("Ruth Okafor.", "Thank you. So the twelfth of March, late morning?",
                        [("collect_name", {"name": "patient_full_name"}),
                         ("record_patient_full_name", {"value": "Ruth Okafor"})])])
    got = judge(put_words, {"ended": True, "variables_absent": ["new_appointment_date"]},
                {"new_appointment_date": ["2028-03-12"]})
    assert got and "which the caller never gave" in got[0], got

    # L2 — a number inside stored free text is not the declined field's value
    assert judge(_walk([("", "ok", [("record_access_notes",
                                     {"value": "it takes me 35 minutes to get anywhere"})])]),
                 {"ended": True, "variables_absent": ["journey_time_minutes"]},
                 {"journey_time_minutes": ["35"]}) == []
    # L3 — "True," is English
    assert judge(_walk([("x", "True, that is the case. Goodbye.", [])]), {"ended": True}) == []

    # H2 — a completed walk must have spoken, and must hold what it booked on
    _REQUIRED = {"mobile_number"}
    silent = _walk([("Hello?", "", []), ("Hello??", "", [])])
    assert judge(silent, {"ended": True}) == ["incomplete: the agent never spoke"]
    empty_booking = _walk([("", "Hello, this is Maya. Goodbye.", [])])
    empty_booking["turns"][-1]["intent"] = "Reschedule Booked"
    assert judge(empty_booking, {"ended": True}) == [
        "booked with required Inputs never stored: mobile_number"]
    assert judge(empty_booking, {"ended": True, "variables_absent": ["mobile_number"]}) == []
    _REQUIRED = set()

    # rule 6 — the two seeded scenarios: the first collect for the field carries the known_value
    seeded = _walk([("Ruth Okafor, born the ninth of June nineteen sixty-two.", "Ruth Okafor?",
                     [("collect_dob", {"name": "date_of_birth", "known_value": "1962-06-09"})])],
                   scenario="two-fields-one-breath-opening")
    assert judge(seeded, {"ended": True}) == [], judge(seeded, {"ended": True})
    seeded["turns"][0]["tool_calls"][0]["arguments"] = json.dumps({"name": "date_of_birth"})
    assert judge(seeded, {"ended": True}) == [
        "date_of_birth: its collector was opened with no known_value, though the caller had "
        "already said it"]

    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        raise SystemExit(main(sys.argv[1:]))
