#!/usr/bin/env python3
"""Run the guide's example flows through the real v2.10 Variables path on dev, and score them.

    python3 bench.py run flows.json results.json [--runs 3] [--only id,id]
    python3 bench.py score flows.json results.json

Per flow and run: a first fill (Jev reads the whole text), a describe (gpt-5.6-luna writes each brief and name),
then every edit on its own against that filled node (Jev's edit answer). The calls are the ones the builder makes,
to the dev runner's suggest endpoint (needs the Primary VPN). Expected variables are matched by type, in order.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request

URL = "https://dev-agent-runner-internal-us-east-1.contactodev.com/v1/collection-configuration/suggest"
AUTH = "MA_BENCH_GUIDE"
WIRE = ("type", "options", "choices", "choices_from_call", "num_digits", "spell_back", "fresh_question", "required",
        "instructions")
PLACEHOLDER = re.compile(r"^[a-z]+(_\d+)?$")


def post(body: dict, tries: int = 3) -> dict:
    data = json.dumps({"auth_id": AUTH, **body}).encode()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())
        except Exception as error:  # noqa: BLE001 - recorded, retried
            if attempt == tries - 1:
                return {"fault": f"{type(error).__name__}: {error}"[:300]}
            time.sleep(2 + attempt * 3)
    return {"fault": "unreachable"}


def wire(collection: dict) -> dict:
    return {**{k: collection[k] for k in WIRE if k in collection and collection[k] is not None}, "version": None}


def fill(instructions: str) -> dict:
    """A first fill, then the describe step on its rows: what the builder shows after one blur."""
    filled = post({"instructions": instructions, "propose_inputs": True, "engine": "jev", "inputs": [], "existing": {}})
    if "fault" in filled:
        return {"fault": filled["fault"]}
    rows = [{"name": p["variable_name"], "collection": p.get("collection") or {}} for p in filled.get("proposed") or []]
    described = post({"instructions": instructions, "describe": True,
                      "inputs": [{"variable_name": r["name"], "variable_instructions": ""} for r in rows],
                      "existing": {r["name"]: wire(r["collection"]) for r in rows if r["collection"].get("type")}})
    if "fault" in described:
        return {"fault": described["fault"], "rows": rows}
    names, briefs = described.get("names") or {}, described.get("descriptions") or {}
    for r in rows:
        r["default_name"] = r["name"]
        r["brief"] = briefs.get(r["name"], "")
        r["name"] = names.get(r["name"], r["name"])
    return {"rows": rows, "errors": {**(filled.get("errors") or {}), **(described.get("errors") or {})}}


def edit(before: str, after: str, rows: list[dict]) -> dict:
    return post({"instructions": after, "previous_instructions": before, "propose_inputs": True, "engine": "jev",
                 "inputs": [{"variable_name": r["name"], "variable_instructions": r["brief"], "authored": []} for r in rows],
                 "existing": {r["name"]: wire(r["collection"]) for r in rows if r["collection"].get("type")}})


def run(flows_path: str, out_path: str, runs: int, only: set[str]) -> None:
    flows = [f for f in json.load(open(flows_path)) if not only or f["id"] in only]
    results: dict[str, list] = {}

    def one(flow: dict, n: int) -> tuple[str, dict]:
        filled = fill(flow["instructions"])
        record = {"run": n, "fill": filled, "edits": {}}
        if "rows" in filled and not filled.get("fault"):
            for e in flow.get("edits", []):
                record["edits"][e["label"]] = edit(flow["instructions"], e["after"], filled["rows"])
        return flow["id"], record

    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, f, n) for f in flows for n in range(runs)]
        for done, fut in enumerate(cf.as_completed(futures), 1):
            fid, record = fut.result()
            results.setdefault(fid, []).append(record)
            print(f"\r{done}/{len(futures)} runs", end="", flush=True)
    print()
    previous = {}
    try:
        previous = json.load(open(out_path))
    except (OSError, ValueError):
        pass
    json.dump({**previous, **results}, open(out_path, "w"), indent=1)
    print(f"kept in {out_path}")


# what the runtime does with a setting the fill left unset (collector default, then router override)
DEFAULTS = {
    "name": {"first_name": True, "last_name": True, "middle_name": False, "spell_back": False},
    "phone": {"vanity": True},
    "text": {"uppercase": False},
    "choice": {"multiple": False, "present_options": True, "ask_before_update": False, "require_confirmation": False},
    "date": {"accept_past": True, "accept_today": True, "require_time": False},
    "currency": {"required_currency": False, "required_period": False},
    "boolean": {"require_confirmation": False},
    "number": {"allow_negative": False, "require_confirmation": False, "ask_before_update": False},
    "dob": {"require_time": False},
    "dtmf": {"ask_for_confirmation": False},
}


def settings_of(collection: dict) -> dict:
    flat = {"required": True, **DEFAULTS.get(collection.get("type"), {}), **(collection.get("options") or {})}
    for k in ("required", "num_digits", "choices_from_call", "spell_back", "readback", "fresh_question"):
        if collection.get(k) is not None:
            flat[k] = collection[k]
    return flat


def per_type(expected: list[dict]) -> list[dict]:
    """Jev reads settings once per type: a key two values of one type expect differently cannot be met, so it is not scored."""
    out = []
    for exp in expected:
        peers = [e for e in expected if e["type"] == exp["type"]]
        keys = {k: v for k, v in (exp.get("settings") or {}).items()
                if all((e.get("settings") or {}).get(k, v) == v for e in peers)}
        out.append({**exp, "settings": keys})
    return out


TYPES = {"name", "phone", "email", "address", "date", "dob", "currency", "number", "dtmf", "text", "choice", "boolean"}


def described(exp: dict, row: dict, others: list[dict] = ()) -> bool:
    """Luna's name says which value it is; for a placeholder name, its description does, and not two other values too."""
    if re.sub(r"_\d+$", "", row["name"]) not in TYPES:
        return bool(re.search(exp.get("about", ""), row["name"], re.I))
    brief = row.get("brief", "")
    return bool(re.search(exp.get("about", ""), brief, re.I)) and sum(bool(re.search(o["about"], brief, re.I)) for o in others) < 2


def match(expected: list[dict], rows: list[dict]) -> tuple[dict[int, int], list[str]]:
    """Expected index -> row index, by type, the row described as that value first; and the problems found."""
    problems, used, mapping = [], set(), {}
    for i, exp in enumerate(expected):
        same = [j for j, r in enumerate(rows) if j not in used and r["collection"].get("type") == exp["type"]]
        j = next((j for j in same if described(exp, rows[j], [e for e in expected if e is not exp])), same[0] if same else None)
        if j is None:
            problems.append(f"missing {exp['type']}")
            continue
        used.add(j)
        mapping[i] = j
        got = settings_of(rows[j]["collection"])
        for key, want in (exp.get("settings") or {}).items():
            if got.get(key) != want:
                problems.append(f"{exp['type']}.{key}={got.get(key)!r} want {want!r}")
    for j, r in enumerate(rows):
        if j not in used:
            problems.append(f"extra {r['collection'].get('type') or '?'} ({r['default_name']})")
    return mapping, problems


def score(flows_path: str, results_path: str) -> None:
    flows = {f["id"]: f for f in json.load(open(flows_path))}
    results = json.load(open(results_path))
    totals = {"fill": [0, 0], "names": [0, 0], "briefs": [0, 0], "labels": [0, 0], "edits": [0, 0]}
    for fid, runs in results.items():
        flow = flows[fid]
        lines = []
        for record in sorted(runs, key=lambda r: r["run"]):
            filled = record["fill"]
            if filled.get("fault"):
                lines.append(f"  run {record['run']}: FAULT {filled['fault'][:120]}")
                continue
            rows = filled["rows"]
            mapping, problems = match(per_type(flow["expect"]), rows)
            totals["fill"][0] += not problems
            totals["fill"][1] += 1
            names = [r["name"] for r in rows]
            bad_names = [n for n in names if PLACEHOLDER.match(n) and n in {r["collection"].get("type") for r in rows}]
            name_ok = not bad_names and len(set(names)) == len(names)
            totals["names"][0] += name_ok
            totals["names"][1] += 1
            brief_ok = all(r["brief"] for r in rows)
            totals["briefs"][0] += brief_ok
            totals["briefs"][1] += 1
            mislabeled = [flow["expect"][i]["about"] for i, j in mapping.items()
                          if not described(flow["expect"][i], rows[j], [e for k, e in enumerate(flow["expect"]) if k != i])]
            totals["labels"][0] += len(mapping) - len(mislabeled)
            totals["labels"][1] += len(flow["expect"])
            edit_notes = []
            for e in flow.get("edits", []):
                got = record["edits"].get(e["label"]) or {}
                if got.get("fault"):
                    edit_notes.append(f"{e['label']}: FAULT")
                    totals["edits"][1] += 1
                    continue
                want = e["expect"]
                by_name = {rows[j]["name"]: i for i, j in mapping.items()}
                affected = sorted(by_name.get(n, -1) for n in got.get("affected") or [])
                dropped = sorted(by_name.get(n, -1) for n in got.get("dropped") or [])
                added = sorted((p.get("collection") or {}).get("type") or "?" for p in got.get("proposed") or [])
                ok = (affected == sorted(want.get("affected", [])) and dropped == sorted(want.get("dropped", []))
                      and added == sorted(want.get("added", [])))
                totals["edits"][0] += ok
                totals["edits"][1] += 1
                if not ok:
                    edit_notes.append(f"{e['label']}: affected {affected} dropped {dropped} added {added}"
                                      f" (want {want.get('affected', [])} {want.get('dropped', [])} {want.get('added', [])})")
            status = "ok" if not problems and name_ok and brief_ok and not mislabeled and not edit_notes else "MISS"
            lines.append(f"  run {record['run']} {status}: " + "; ".join(
                problems + ([f"names {names}"] if not name_ok else []) + ([] if brief_ok else ["empty brief"])
                + [f"described as something else: {mislabeled}"] * bool(mislabeled) + edit_notes)
                if status == "MISS" else f"  run {record['run']} ok: {', '.join(names)}")
        print(f"{fid}")
        print("\n".join(lines))
    print()
    for k, (good, total) in totals.items():
        print(f"{k:7} {good}/{total}")


def edit_ok(flow: dict, rows: list[dict], mapping: dict[int, int], label: str, got: dict) -> bool:
    want = next(e["expect"] for e in flow["edits"] if e["label"] == label)
    by_name = {rows[j]["name"]: i for i, j in mapping.items()}
    return (not got.get("fault")
            and sorted(by_name.get(n, -1) for n in got.get("affected") or []) == sorted(want.get("affected", []))
            and sorted(by_name.get(n, -1) for n in got.get("dropped") or []) == sorted(want.get("dropped", []))
            and sorted((p.get("collection") or {}).get("type") or "?" for p in got.get("proposed") or []) == sorted(want.get("added", [])))


def examples(flows_path: str, results_path: str) -> None:
    """The guide's appendix: each flow's text, its values as dev read them, and its edits."""
    results = json.load(open(results_path))
    for n, flow in enumerate(json.load(open(flows_path)), 1):
        runs = sorted(results.get(flow["id"], []), key=lambda r: r["run"])
        matched = [(r, *match(per_type(flow["expect"]), r["fill"]["rows"])) for r in runs if r["fill"].get("rows")]
        print(f"### A{n}. {flow['id']}\n\n```md\n{flow['instructions']}\n```\n")
        print(f"First fill on dev: types and settings right in {sum(not p for _, _, p in matched)} of {len(runs)} runs.\n")
        print("| # | Type | Settings Jev should set | Names gpt-5.6-luna gave | Described right |\n|---|---|---|---|---|")
        for i, exp in enumerate(flow["expect"]):
            rows = [r["fill"]["rows"][m[i]] for r, m, _ in matched if i in m]
            settings = ", ".join(f"{k} {v}".replace("True", "on").replace("False", "off") for k, v in (exp.get("settings") or {}).items()) or "defaults"
            names = ", ".join(dict.fromkeys(f"`{row['name']}`" for row in rows)) or "missing"
            others = [e for k, e in enumerate(flow["expect"]) if k != i]
            print(f"| {i} | {exp['type']} | {settings} | {names} | {sum(described(exp, row, others) for row in rows)} of {len(runs)} |")
        print("\n| Edit | Expected | Right on dev |\n|---|---|---|")
        for e in flow["edits"]:
            verbs = {"affected": "changes", "dropped": "drops", "added": "adds"}
            want = "; ".join(f"{verbs[k]} " + ", ".join(f"#{v}" if isinstance(v, int) else v for v in vals)
                             for k, vals in e["expect"].items()) or "no change"
            ok = sum(edit_ok(flow, r["fill"]["rows"], m, e["label"], r["edits"].get(e["label"]) or {}) for r, m, _ in matched)
            print(f"| {e['label']} | {want} | {ok} of {len(runs)} |")
        print()


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "run":
        args = sys.argv[2:]
        runs = int(args[args.index("--runs") + 1]) if "--runs" in args else 3
        only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else set()
        run(args[0], args[1], runs, only)
    elif command == "examples":
        examples(sys.argv[2], sys.argv[3])
    else:
        score(sys.argv[2], sys.argv[3])
