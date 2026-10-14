#!/usr/bin/env python3
"""English + Indian language pairs: builds the cases, runs bench.py in the engine container on each wording, prints the tables.

    python3 run_en.py <wording name>=<system_one.json> [...] [--reads 3]

Cases per pair: English as our Deepgram writes it locked to that language (the test sentences only, never the prompt's),
English in Latin letters, the language with a few English words in its own letters (reviewed, held out from the prompt),
the language alone, and names, numbers and sounds (Unsure). For Hindi, English in Devanagari comes from the Marathi lock.
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import sentences

HERE = Path(__file__).parent
CONTAINER = "v210-agent-runner"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
READS = sys.argv[sys.argv.index("--reads") + 1] if "--reads" in sys.argv else "3"
variants = dict(a.split("=", 1) for a in args if "=" in a)
contrast = json.loads((HERE / "contrast.json").read_text(encoding="utf-8"))
stt = json.loads((HERE / "stt_english_indian.json").read_text(encoding="utf-8"))
NAMES = {"hi": "Hindi", **sentences.NAMES}
LATIN = re.compile(r"^[\x00-\x7F]+$")


def cases(code: str) -> list[list[str]]:
    name, lock = NAMES[code], ("mr" if code == "hi" else code)
    heard = [r["heard"].strip() for r in stt if r["lock"] == lock and r["kind"] == "test" and r["heard"].strip()]
    out = [[line, "English", "English in Indic letters"] for line in dict.fromkeys(h for h in heard if not LATIN.match(h))]
    if code in ("ml", "pa", "or"):
        out += [[s, "English", "English in Indic letters"] for s in contrast[code]["english_in_script"]]
    latin = [r["heard"].strip() for r in stt if r["lock"] == ("hi" if code == "hi" else code) and r["kind"] == "test" and LATIN.match(r["heard"].strip() or "x")]
    out += [[line, "English", "English in Latin letters"] for line in list(dict.fromkeys(latin))[:6] + sentences.ENGLISH]
    out += [[s["text"], name, f"{name} with English words"] for s in contrast[code]["test"]]
    out += [[line, name, f"{name} alone"] for line in sentences.LANGUAGES[code][0:10:2]]
    return out + [[line, "Unsure", "names, numbers, sounds"] for line in sentences.NEUTRAL]


codes = list(NAMES)
manifest_cases = {f"{v}|en+{code}": cases(code)
                  for v in variants for code in codes}
manifest_cases["old|en+hi"] = cases("hi")
for v, path in variants.items():
    subprocess.run(["docker", "cp", path, f"{CONTAINER}:/tmp/lp_{v}.json"], check=True)
old = subprocess.run(["git", "-C", str(HERE.parent / "agent-runner"), "show", "origin/main:src/prompts/system_one.json"],
                     capture_output=True, text=True, check=True).stdout
(HERE / "main_system_one.json").write_text(old)
subprocess.run(["docker", "cp", str(HERE / "main_system_one.json"), f"{CONTAINER}:/tmp/lp_old.json"], check=True)
manifest = {"variants": {**{v: f"/tmp/lp_{v}.json" for v in variants}, "old": "/tmp/lp_old.json"}, "cases": manifest_cases}
(HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
subprocess.run(["docker", "cp", str(HERE / "manifest.json"), f"{CONTAINER}:/tmp/lp_manifest.json"], check=True)
subprocess.run(["docker", "exec", "-i", "-w", "/app", CONTAINER, "sh", "-c",
                'export "$(tr "\\0" "\\n" < /proc/1/environ | grep "^TYPESAFE_API_KEY=")"; python - "$0"', READS],
               stdin=open(HERE / "bench.py"), check=True)
subprocess.run(["docker", "cp", f"{CONTAINER}:/tmp/lp_results.json", str(HERE / "results_en.json")], check=True)
results = json.loads((HERE / "results_en.json").read_text(encoding="utf-8"))
table, kinds = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0])
for r in results:
    s = table[r["job"]]
    s[0] += r["got"] == r["want"]
    s[1] += r["got"] not in (r["want"], "Unsure")  # a wrong switch, not just an unsure reading
    s[2] += 1
    kind = "Indian language with English words" if r["kind"].endswith("with English words") else "Indian language alone" if r["kind"].endswith(" alone") else r["kind"]
    kinds[(r["job"].split("|")[0], kind)][0] += r["got"] == r["want"]
    kinds[(r["job"].split("|")[0], kind)][1] += 1
for job, (ok, wrong, n) in table.items():
    print(f"{job:12} {ok:4}/{n:<4} wrong switches {wrong}")
for (variant, kind), (ok, n) in sorted(kinds.items()):
    print(f"{variant:4} {kind:36} {ok}/{n}")
