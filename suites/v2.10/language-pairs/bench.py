"""Jev's language reading per pair and wording, run inside the local engine (same Jev model as dev and main).

/tmp/lp_manifest.json names the prompt file of each wording and the cases of each "wording|pair"; the question is built the
way src/system_one.py builds it. "old" is main's English and Hindi wording. A reading counts as the language whose share is
over 0.5, else Unsure, as on a call.
"""
import asyncio
import json
import sys

from src.system_one import PROMPTS as LIVE, ask_jev

MANIFEST = json.load(open("/tmp/lp_manifest.json"))
FILES = {variant: json.load(open(path)) for variant, path in MANIFEST["variants"].items()}
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
sem = asyncio.Semaphore(8)


def question(job: str, said: str) -> dict:
    variant, pair = job.split("|")
    asked = FILES[variant]["language"]
    if variant == "old":
        return {**asked, "instructions": asked["instructions"].format(said=said)}
    words = FILES[variant]["language_pairs"][pair]
    return {**asked, "instructions": asked["instructions"].format(said=said, rule=words["rule"]),
            "criteria": {**{name: text for name, text in words.items() if name != "rule"}, **asked["criteria"]}}


async def read(job: str, said: str) -> tuple[str, dict]:
    state = LIVE["state"].format(policy="Help the caller with their order and their payment.", transcript=f"Caller: {said}")
    async with sem:
        answers = await ask_jev(state, {"language": question(job, said)}, (20.0, 20.0)) or {}
    shares = answers.get("language") or {}
    return next((name for name, share in shares.items() if name != "Unsure" and share > 0.5), "Unsure"), shares


async def main() -> None:
    jobs = [(job, said, want, kind) for job, cases in MANIFEST["cases"].items() for said, want, kind in cases for _ in range(RUNS)]
    got = await asyncio.gather(*(read(job, said) for job, said, _, _ in jobs))
    out = [{"job": job, "said": said, "want": want, "kind": kind, "got": reading, "shares": {k: round(v, 2) for k, v in shares.items()}}
           for (job, said, want, kind), (reading, shares) in zip(jobs, got)]
    json.dump(out, open("/tmp/lp_results.json", "w"), ensure_ascii=False, indent=1)
    print(len(out), "readings")

asyncio.run(main())
