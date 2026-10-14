#!/usr/bin/env python3
"""Every caller turn of a board with the language Jev read in it and the language the agent then spoke, from the merged timelines.

    python3 language_turns.py <folder of call folders> [--all]

A line counts as Hindi when more than half of its words are in Hindi letters (the agent: more than a fifth, as the suite's check).
"""
import ast, re, sys
from pathlib import Path


def hindi(text: str) -> float:
    words = re.findall(r"[^\W\d_]+", text)
    return sum(bool(re.search(r"[ऀ-ॿ]", word)) for word in words) / len(words) if words else 0.0


rows = []
for folder in sorted(Path(sys.argv[1]).iterdir()):
    caller = jev = heard_by_hunter = None
    for line in (folder / "timeline.txt").read_text().splitlines():
        text = line[12:]
        if text.startswith("HUNTER: its caller said"):
            heard_by_hunter = text.split("said", 1)[1].strip()
        elif text.startswith("CALLER"):
            said = text.split("   ", 1)[1]
            stamp = re.search(r"\[Language: (\w+)\]", said)
            caller, jev = (re.sub(r"\[Language: \w+\]", "", said).strip(), stamp.group(1) if stamp else "", heard_by_hunter), None
        elif caller and "system_one: step=" in text and jev is None and "'language':" in text:
            found = re.search(r"'language': (\{[^}]*\})", text)
            jev = ast.literal_eval(found.group(1)) if found else {}
        elif caller and text.startswith("AGENT"):
            agent = text[9:]
            rows.append((folder.name, caller[0], caller[1], caller[2], jev, agent))
            caller = None
wrong = 0
for call, said, stamp, hunter, jev, agent in rows:
    words_say = "Hindi" if hindi(said) > 0.5 else "English"
    agent_spoke = "Hindi" if hindi(agent) > 0.2 else "English"
    picked = ("Hindi" if jev.get("Hindi", 0) > 0.5 else "English") if jev else "(Jev not asked)"
    bad = agent_spoke != words_say
    wrong += bad
    if bad or "--all" in sys.argv:
        print(f"{call[-2:]} | heard: {said[:46]!r:50s} | Hunter's caller said: {str(hunter)[:40]!r:44s} | stamp {stamp or '-':7s} | Jev {picked:16s} {jev or ''} | agent spoke {agent_spoke}: {agent[:60]!r}")
print(f"\n{wrong} of {len(rows)} agent replies were not in the language of the words we heard")
asked = [row for row in rows if row[4]]
agree = sum((("Hindi" if row[4].get("Hindi", 0) > 0.5 else "English") == ("Hindi" if hindi(row[1]) > 0.5 else "English")) for row in asked)
print(f"Jev was asked the language on {len(asked)} of these turns; its answer matched the letters of the words on {agree}")
follow = sum((("Hindi" if row[4].get("Hindi", 0) > 0.5 else "English") == ("Hindi" if hindi(row[5]) > 0.2 else "English")) for row in asked)
print(f"the agent's next line was in the language Jev picked on {follow} of {len(asked)}")
