"""How Jev's leading went in a finished campaign, read from the stored traces. Runs nothing, pays nothing.

  python lead_stats.py <campaign dir>

Counts the moments where the small version's own rule decided what the caller heard:
  split     Jev was not sure of any step and speech was not its favourite either, so the request went out speech-only
  silent    ... and the model then said nothing
  leak      an agent line that carries a tool's name: a step the model wanted, written out as words
  other     the model named another step than Jev picked (it is asked again and must take Jev's)
"""
import ast
import collections
import glob
import json
import os
import re
import sys

STEP = re.compile(r"s1\.step=(.*?) about_agent=(\S+) jev=(.*)$", re.S)
TOOL_ID = re.compile(r"\b[a-z]+(?:_[a-z0-9]+){1,}\b")


def stats(campaign: str) -> dict:
    asks, split, silent, other, leaks, runs = 0, [], [], [], [], 0
    for path in sorted(glob.glob(os.path.join(campaign, "*", "trace.json"))):
        slug, events = os.path.basename(os.path.dirname(path)), json.load(open(path))["events"]
        runs += 1
        names = {option for event in events if event["kind"] == "jev" for option in (event.get("heads") or {}).get("step", []) if "_" in option and " " not in option}
        for index, event in enumerate(events):
            if event["kind"] == "line" and event["role"] == "agent":
                named = sorted(set(TOOL_ID.findall(event["text"])) & names)
                if named:
                    leaks.append((slug, round(event["t"], 1), event["text"].strip()[:90]))
            if event["kind"] != "log":
                continue
            if event["msg"].startswith("s1.dropped"):
                other.append((slug, round(event["t"], 1), event["msg"][11:90]))
            match = STEP.match(event["msg"])
            if not match:
                continue
            asks += 1
            shares = ast.literal_eval(match.group(3)).get("step", {})
            if match.group(1) != "only speak" or shares.get("only speak", 0.0) >= max(shares.values(), default=0.0):
                continue
            top = dict(sorted(shares.items(), key=lambda item: -item[1])[:3])
            split.append((slug, round(event["t"], 1), top))
            spoke = False
            for later in events[index + 1:]:
                if later["kind"] == "line" and later["role"] == "agent":
                    spoke = True
                    break
                if later["kind"] == "jev" or (later["kind"] == "line" and later["role"] == "caller"):
                    break
            if not spoke:
                silent.append((slug, round(event["t"], 1), top))
    return {"runs": runs, "asks": asks, "split": split, "silent": silent, "leak": leaks, "other": other}


def main() -> None:
    found = stats(sys.argv[1])
    per_run = lambda rows: len({row[0] for row in rows})  # noqa: E731
    print(f"{found['runs']} runs, {found['asks']} requests led by Jev")
    for key, label in (("split", "Jev split between steps, request went speech-only"), ("silent", "of those, the agent then said nothing"),
                       ("leak", "an agent line carried a tool's name"), ("other", "the model named another step than Jev picked")):
        print(f"\n{label}: {len(found[key])} times in {per_run(found[key])} runs")
        for row in found[key][:40]:
            print("  ", *row)
    by_run = collections.Counter(row[0] for row in found["silent"])
    print("\nsilent requests per run:", dict(by_run))


if __name__ == "__main__":
    main()
