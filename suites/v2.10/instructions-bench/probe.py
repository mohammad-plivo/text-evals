"""Jev's fill reads for each text, N times: the value counts per type, and the sure setting picks.

Runs inside the local engine container, which has the same code for this path as main and dev and calls the same Jev model.
Put the texts to read in a JSON object {label: instructions} at /tmp/probe_texts.json in the container, then:

    docker cp texts.json v210-agent-runner:/tmp/probe_texts.json
    docker exec -i -w /app v210-agent-runner sh -c \
      'export "$(tr "\0" "\n" < /proc/1/environ | grep "^TYPESAFE_API_KEY=")"; python - 5 -s' < probe.py

The second line borrows the engine's own Jev key from its process and never prints it. 5 is the reads per text; -s adds settings.
"""
import asyncio, json, sys
from collections import Counter, defaultdict
from src.collection_configuration_suggest import _JEV_QUESTIONS, _JEV_SETTINGS, _ASKED_WORDINGS, _HOW_MANY, _UNSTATED
from src.system_one import ask_jev, sure_pick, SURE_FLOOR, PROMPTS

texts = json.load(open("/tmp/probe_texts.json"))
runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
sem = asyncio.Semaphore(8)

def read(shares):
    counts, sets = {}, {}
    for t, keys in _JEV_SETTINGS.items():
        said = [shares[k].get("yes", 0.0) for h in _ASKED_WORDINGS if (k := f"{h}_{t}") in shares]
        many = sure_pick(shares.get(f"many_{t}", {}), SURE_FLOOR) or "one"
        counts[t] = 1 + list(_HOW_MANY).index(many) if said and sum(said) / len(said) >= (0.7 if t == "text" else 0.5) else 0
        sets[t] = {k: p for k in keys if (p := sure_pick(shares.get(f"{t}_{k}", {}), SURE_FLOOR)) not in (None, _UNSTATED)}
    if sure_pick(shares.get("dtmf_num_digits", {}), SURE_FLOOR) in (None, _UNSTATED):
        counts["text"], counts["dtmf"] = counts["text"] + counts["dtmf"], 0
    return {t: c for t, c in counts.items() if c}, {t: s for t, s in sets.items() if counts.get(t)}

async def one(text):
    async with sem:
        return read(await ask_jev(PROMPTS["state"].format(policy=text, transcript=""), _JEV_QUESTIONS, (20.0, 20.0)) or {})

async def main():
    keys = list(texts)
    got = await asyncio.gather(*(one(texts[k]) for k in keys for _ in range(runs)))
    for i, k in enumerate(keys):
        mine = got[i * runs:(i + 1) * runs]
        seen = Counter(json.dumps(c, sort_keys=True) for c, _ in mine)
        print(f"## {k}: " + " | ".join(f"{n}x {c}" for c, n in seen.most_common()))
        if "-s" in sys.argv:
            agg = defaultdict(Counter)
            for _, s in mine:
                for t, kv in s.items():
                    agg[t][json.dumps(kv, sort_keys=True)] += 1
            for t, c in agg.items():
                print(f"     {t}: " + " | ".join(f"{n}x {v}" for v, n in c.most_common()))
asyncio.run(main())
