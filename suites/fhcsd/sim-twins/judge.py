"""Judge a sim CLI report the way Hunter judges a call: the scenario's own evaluationPrompt, verbatim,
one verdict per numbered criterion with an accuracy in [0, 1], score = min accuracy, pass at threshold.
Run with the repo venv from any cwd:
  judge.py --report <cli report .json> --hunter <hunter scenario .json> [--out <dir>] [--model gpt-4.1]
Reads AZURE_OPENAI_* from --env-file (same file the CLI uses). Writes <out>/<scenario>-run<N>.judge.json
and prints one line per run: PASS/FAIL score, then the NOT MET criteria.
"""
import argparse
import asyncio
import json
import os
import re
import sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("STRESS_REPO") or os.path.abspath(os.path.join(HERE, "..", "..", "repo-dev"))
sys.path.insert(0, REPO)

JUDGE_SYSTEM = (
    "You are the evaluator of a recorded phone call between an AI voice agent (AGENT) and a person (CALLER). "
    "Apply the evaluation instructions exactly as written. Judge only the AGENT's behaviour and only the numbered "
    "criteria. Each criterion's own text governs its verdict: behaviour a criterion explicitly allows is not a "
    "violation of that criterion, and a rule stated elsewhere in the instructions applies only where the instructions "
    "say it does. For every numbered criterion write the reasoning first, citing transcript turns as [Tn], and only "
    "then the verdict: met (true/false) and an accuracy from 0.0 to 1.0 (1.0 fully met, 0.0 clearly violated, "
    "intermediate only for a partial miss the instructions leave to judgement); the verdict must follow from the "
    "reasoning. Answer in JSON: {\"criteria\": [{\"n\": 1, \"reason\": \"...\", \"met\": true, \"accuracy\": 1.0}, ...]}"
)


def transcript_lines(run: dict) -> list[str]:
    lines, n = [], 0
    for t in run["turns"]:
        if t.get("user") and t["user"] != "__END_CALL__":
            n += 1; lines.append(f"[T{n}] CALLER: {t['user']}")
        for line in (t.get("agent") or "").split("\n"):
            if line.strip():
                n += 1; lines.append(f"[T{n}] AGENT: {line.strip()}")
    return lines


_NON_SPEECH = re.compile(r"</?[a-z_]+(?:\s[^>]*)?/?>|(?<![\w.@/-])[a-z]+(?:_[a-z]+)+(?![\w.@/-])")


def non_speech(run: dict) -> list[str]:
    """Agent lines carrying a tag or a snake_case token: planning or tool syntax that TTS would read aloud."""
    hits = []
    for line in transcript_lines(run):
        if not line.split("] ", 1)[1].startswith("AGENT: "):
            continue
        m = _NON_SPEECH.search(re.sub(r"\S+@\S+", "", line))
        if m:
            hits.append(f"{line.split(']')[0]}] {m.group(0)!r}")
    return hits


def criteria_count(prompt: str) -> int:
    body = prompt.split("Evaluate these criteria:")[-1]
    return len(re.findall(r"^\s*\d+\. ", body, re.M))


VERIFY_SYSTEM = (
    "You check one verdict from a call evaluation. You are given the transcript, ONE criterion as written, and a "
    "judge's NOT MET reason. Decide whether the criterion, exactly as written, is violated by the transcript. "
    "Quote the sentence of the criterion that decides it. A behaviour the criterion explicitly allows, or a "
    "requirement the criterion does not state, can never make it NOT MET. Answer in JSON: "
    "{\"deciding_sentence\": \"...\", \"verdict\": \"NOT MET\"|\"MET\", \"why\": \"...\"}"
)


async def verify_criterion(transcript: str, criterion: str, reason: str, model: str) -> dict:
    from src.simulation.cli import azure_chat
    user = (f"TRANSCRIPT:\n{transcript}\n\nCRITERION:\n{criterion}\n\nTHE JUDGE MARKED IT NOT MET BECAUSE:\n{reason}")
    response = await azure_chat._get_client().chat.completions.create(
        model=model or azure_chat.DEFAULT_DEPLOYMENT, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": VERIFY_SYSTEM}, {"role": "user", "content": user}])
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


def criterion_text(prompt: str, n) -> str:
    body = prompt.split("Evaluate these criteria:")[-1]
    for num, txt in re.findall(r"^\s*(\d+)\. (.+)$", body, re.M):
        if str(num) == str(n):
            return txt
    return ""


VAR_SYSTEM = (
    "You check one callback variable recorded by a voice agent against what the test expected. The expected value "
    "describes the value that should have been captured; the actual value is what the agent recorded. Decide whether "
    "the actual value means the same thing as the expected one. Different wording, casing, date or time formatting is "
    "a match when the meaning is identical. A different date, a different time, a different slot, a different answer, "
    "an empty value or a missing value is not a match. Answer in JSON: {\"match\": true|false, \"why\": \"...\"}"
)


def norm(v) -> str:
    return re.sub(r"\s+", " ", str("" if v is None else v)).strip().casefold()


async def check_variable(key: str, expected, actual, model: str) -> dict:
    from src.simulation.cli import azure_chat
    user = f"VARIABLE: {key}\nEXPECTED: {expected}\nACTUAL: {actual}"
    response = await azure_chat._get_client().chat.completions.create(
        model=model or azure_chat.DEFAULT_DEPLOYMENT, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": VAR_SYSTEM}, {"role": "user", "content": user}])
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


async def grade_variables(run: dict, ecv: dict, model: str) -> list[dict]:
    """One verdict per expected callback variable. Hunter fails a scenario on a mismatch even when every
    criterion scores 1.0, so the text lane cannot predict Hunter without this."""
    if not ecv:
        return []
    got = run.get("variables") or {}
    # A twin that enters at the agent node never runs the screening unit, so its screening_* variables cannot
    # exist here. Skipping them keeps a lane artefact out of the verdict; it is also a real blind spot, and the
    # skipped keys are reported so a screening expectation is never silently treated as covered.
    screened = any("screen" in str(n).lower() for n in (run.get("nodes_visited") or []))
    rows, asked = [], []
    for key, expected in ecv.items():
        actual = got.get(key)
        row = {"key": key, "expected": expected, "actual": actual}
        if key.startswith("screening_") and not screened and actual is None:
            row.update(met=True, skipped=True, why="NOT COVERED by the text lane: this twin skips screening")
        elif actual is None or norm(actual) == "":
            row.update(met=False, why="not recorded")
        elif norm(actual) == norm(expected):
            row.update(met=True, why="exact match")
        else:
            asked.append(row)
        rows.append(row)
    checks = await asyncio.gather(*(check_variable(r["key"], r["expected"], r["actual"], model) for r in asked))
    for r, chk in zip(asked, checks):
        r.update(met=bool(chk.get("match")), why=chk.get("why") or "")
    return rows


async def judge_run(run: dict, prompt: str, threshold: float, model: str, verify: bool = True,
                    ecv=None, expect_intent="") -> dict:
    from src.simulation.cli import azure_chat
    transcript = "\n".join(transcript_lines(run))
    variables = await grade_variables(run, ecv or {}, model)
    vars_pass = all(v["met"] for v in variables)
    user = f"TRANSCRIPT:\n{transcript}\n\nEVALUATION INSTRUCTIONS:\n{prompt}"
    # the CLI helper's client, at temperature 0: a judge should not sample
    response = await azure_chat._get_client().chat.completions.create(
        model=model or azure_chat.DEFAULT_DEPLOYMENT, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}])
    raw = response.choices[0].message.content or ""
    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        verdict = {"criteria": [], "raw": raw}
    crits = verdict.get("criteria") or []
    expected = criteria_count(prompt)
    accs = [float(c.get("accuracy", 0.0 if not c.get("met") else 1.0)) for c in crits]
    score = min(accs) if accs and len(crits) >= expected else 0.0
    # Hunter judges once, so `score` is the parity number; a second pass re-reads the criterion behind every
    # NOT MET and overturns a verdict the criterion's own words do not support (judge error, not an agent defect).
    def acc_of(c):
        return float(c.get("accuracy", 0.0 if not c.get("met") else 1.0))

    if verify:
        # the score is the MINIMUM accuracy, so every criterion under the threshold decides the verdict —
        # whether the judge called it NOT MET or hedged a MET below 1.0
        doubtful = [c for c in crits if not c.get("met") or acc_of(c) < threshold]
        checks = await asyncio.gather(*(
            verify_criterion(transcript, criterion_text(prompt, c.get("n")), c.get("reason") or "", model)
            for c in doubtful))
        for c, chk in zip(doubtful, checks):
            c["verified"] = chk
            if str(chk.get("verdict", "")).upper() == "MET":
                c["overturned"] = True
    kept = [acc_of(c) for c in crits if not c.get("overturned")]
    verified_score = min(kept) if kept and len(crits) >= expected else (1.0 if crits and len(crits) >= expected else 0.0)
    rubric_pass = bool(accs) and score >= threshold
    # Evidence gate. The auditor reproduced three false passes on stubbed results: a judge reply that repeats
    # criterion 1 and omits 2, simulator failures ignored, and skipped coverage counted as satisfied. Each of
    # these now decides the verdict, and an elicited turn (the simulator sending an empty turn to make a silent
    # node speak) can never prove the agent spoke unprompted.
    ns = [c.get("n") for c in crits]
    numbering_ok = sorted(str(n) for n in ns) == sorted(str(i) for i in range(1, expected + 1))
    sim_failures = run.get("failures") or []
    elicited = sum(1 for t in run["turns"] if t.get("elicited"))
    partial = [v["key"] for v in variables if v.get("skipped")]
    final_intent = next((t["intent"] for t in reversed(run["turns"]) if t.get("intent")), "")
    intent_ok = (not expect_intent) or final_intent == expect_intent
    spoken_syntax = non_speech(run)
    evidence = {"numbering_ok": numbering_ok, "criteria_returned": len(crits), "criteria_expected": expected,
                "sim_failures": len(sim_failures), "elicited_turns": elicited, "not_covered": partial,
                "expected_intent": expect_intent, "intent_ok": intent_ok, "non_speech": spoken_syntax}
    evidence_ok = numbering_ok and not sim_failures and elicited == 0 and intent_ok and not spoken_syntax
    verdict = ("PASS" if (rubric_pass and vars_pass and evidence_ok and not partial)
               else "PARTIAL" if (rubric_pass and vars_pass and evidence_ok and partial) else "FAIL")
    return {"verdict": verdict, "evidence": evidence, "evidence_ok": evidence_ok,
            "scenario": run["scenario"], "run": run["run"], "score": round(score, 3),
            "verified_score": round(verified_score, 3),
            "verified_pass": bool(crits) and verified_score >= threshold and vars_pass and evidence_ok,
            "rubric_pass": rubric_pass, "variables_pass": vars_pass, "variables": variables,
            "overturned": [c.get("n") for c in crits if c.get("overturned")],
            "pass": verdict == "PASS", "expected_criteria": expected,
            "criteria": crits, "sim_failures": run.get("failures", []),
            "final_intent": final_intent,
            "turns": len(run["turns"])}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True); ap.add_argument("--hunter", required=True)
    ap.add_argument("--out"); ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--env-file", default=os.environ.get("SIM_ENV_FILE", ""))
    ap.add_argument("--no-verify", action="store_true", help="skip the second pass over NOT MET verdicts")
    ap.add_argument("--expect-intent", default="", help="the exit the twin asserts; a different final intent fails the run")
    a = ap.parse_args()
    if a.env_file:
        for line in open(a.env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); os.environ.setdefault(k, v.strip().strip('"'))
    hunter = json.load(open(a.hunter)); p = hunter["payload"]
    prompt, threshold = p["evaluationPrompt"], float(p.get("evaluationThreshold", 0.8))
    ecv = p.get("expectedCallbackVariables") or {}
    runs = json.load(open(a.report))
    out = a.out or os.path.dirname(a.report); os.makedirs(out, exist_ok=True)
    results = await asyncio.gather(*(judge_run(r, prompt, threshold, a.model, verify=not a.no_verify, ecv=ecv, expect_intent=a.expect_intent) for r in runs))
    for r in results:
        path = os.path.join(out, f"{r['scenario']}-run{r['run']}.judge.json")
        json.dump(r, open(path, "w"), indent=1)
        bad = [f"{c.get('n')}:{(c.get('reason') or '')[:110]}" for c in r["criteria"] if not c.get("met")]
        flag = "" if r["pass"] == r.get("verified_pass", r["pass"]) else f" (verified {r['verified_score']:.2f}, overturned {r.get('overturned')})"
        print(f"{r['verdict']} {r['score']:.2f} {r['scenario']} run{r['run']} intent={r['final_intent']!r} turns={r['turns']} sim_failures={len(r['sim_failures'])}{flag}")
        e = r["evidence"]
        if not e["numbering_ok"]:
            print(f"    EVIDENCE the judge returned criteria {[c.get('n') for c in r['criteria']]}, expected 1..{e['criteria_expected']}")
        if e["sim_failures"]:
            print(f"    EVIDENCE {e['sim_failures']} simulator failure(s): {r['sim_failures'][:2]}")
        if not e["intent_ok"]:
            print(f"    EVIDENCE wrong exit: expected {e['expected_intent']!r}, the simulator reported {r['final_intent']!r}")
        if e["elicited_turns"]:
            print(f"    EVIDENCE {e['elicited_turns']} elicited turn(s): the simulator prompted a silent node, so this run cannot prove the agent speaks unprompted")
        if e.get("non_speech"):
            print(f"    EVIDENCE the agent spoke non-speech (a tag or snake_case token) at {e['non_speech'][:3]}")
        for b in bad: print(f"    NOT MET {b}")
        for v in r.get("variables", []):
            if not v["met"]:
                print(f"    VAR MISMATCH {v['key']}: expected {v['expected']!r} got {v['actual']!r} ({v['why'][:80]})")
        skipped = [v["key"] for v in r.get("variables", []) if v.get("skipped")]
        if skipped: print(f"    VARS NOT COVERED (screening skipped in text): {','.join(skipped)}")
        if len(r["criteria"]) < r["expected_criteria"]:
            print(f"    judge returned {len(r['criteria'])}/{r['expected_criteria']} criteria")
    return 0 if all(r["verdict"] == "PASS" for r in results) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
