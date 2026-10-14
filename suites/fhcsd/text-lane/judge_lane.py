"""Grade one lane run: validity first (is this evidence at all), then deterministic checks, then the Hunter rubric.

Verdict: INVALID when the run cannot count (Jev not proven, a Jev fault let Gemma carry the call, Gemma not proven,
a refused or unmetered request, a harness crash); otherwise PASS only when the rubric passes (Hunter: every
criterion returned, min accuracy >= threshold, via sim-fh/judge.py judge_run) AND every deterministic check holds.
A criterion the judge's own second pass overturned is reported (overturned) and does not change the verdict.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import date, datetime

SIMFH = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v29-revamp/stress-evals/sim-fh"
RAN = {"SUCCEEDED", "REJECTED", "UNKNOWN"}  # the effect reached its transport; DENIED/STALE/PENDING never did
ACK = re.compile(r"^(?:(?:okay|ok|alright|all right|got it|thanks|thank you|sure|great|perfect|understood|right|"
                 r"noted|mm-?hmm|i see|of course|certainly|no problem|sounds good)[\s,.!]*)+$", re.I)
RULES = ("eq", "ci", "date", "digits", "contains_all")  # the ops arg_ok grades; lane preflight refuses any other
JUDGE_TRIES, JUDGE_RETRY_PAUSE_S = 3, 10.0  # the client already retries at once; a pause outlasts a short outage


class JudgeUnreachable(RuntimeError):
    """The judge's transport failed before any answer came back, so asking again is safe."""


def mock_bypass(trace: dict) -> list[str]:
    """A denied request to a reserved .invalid host is a tool that skipped its sim mock: a defect, not a harness fault."""
    return [r for r in trace.get("refusals") or [] if r.startswith("denied host ") and r.endswith(".invalid")]
SLOT_RECORD = "<<SLOT RECORD>>"  # lane.py convert leaves this in the rubric; judge() fills it from the trace


def lines(trace: dict) -> list[dict]:
    return [e for e in trace["events"] if e["kind"] == "line"]


def logs(trace: dict, prefix: str) -> list[str]:
    return [e["msg"] for e in trace["events"] if e["kind"] == "log" and e["msg"].startswith(prefix)]


def turns_from_lines(trace: dict, run: dict | None) -> list[dict]:
    """Every spoken line, grouped as caller line -> agent lines, for the rubric transcript."""
    turns: list[dict] = [{"user": "", "agent": []}]
    for e in lines(trace):
        if e["role"] == "caller":
            turns.append({"user": e["text"], "agent": []})
        else:
            turns[-1]["agent"].append(e["text"])
    out = [{"user": t["user"], "agent": "\n".join(t["agent"])} for t in turns if t["user"] or t["agent"]]
    report_turns = (run or {}).get("turns") or []
    if out:
        out[-1]["intent"] = final_intent(run)
        out[0]["elicited"] = sum(int(t.get("elicited") or 0) for t in report_turns)
    return out


def _date(value) -> date | None:
    s = str(value or "").strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def exits(spec: dict) -> list[str]:
    want = spec.get("expect_exit")
    return want if isinstance(want, list) else [want] if want else []


def final_intent(run: dict | None) -> str:
    return next((t["intent"] for t in reversed((run or {}).get("turns") or []) if t.get("intent")), "")


def searches(trace: dict, spec: dict) -> list[dict]:
    return [t for t in trace["events"] if t["kind"] == "tool" and t["action"] == spec.get("search_tool") and t.get("status") in RAN]


def result_of(tool: dict) -> dict:
    try:
        out = json.loads(tool.get("result") or "{}")
    except ValueError:  # run_one caps the stored result at 3000 chars
        return {}
    return out if isinstance(out, dict) else {}


def offers(tool: dict) -> list[dict]:
    return result_of(tool).get("offers") or [] if tool.get("status") == "SUCCEEDED" else []


def _long(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def slot_record(trace: dict, spec: dict) -> str:
    """THE CLINIC RECORD's slot lines, from the searches this call actually ran."""
    body, days, any_found = "", [_date(spec.get("clinic_day"))], False
    for t in searches(trace, spec):
        start = _date((t.get("arguments") or {}).get("start_date"))
        head = f"- the search from {_long(start)}" if start else "- a search"
        found = offers(t)
        if found:
            body += head + " returned only these slots: " + "; ".join(
                f"option {i + 1}, {o.get('display') or o.get('label')}" for i, o in enumerate(found)) + ".\n"
            days += [_date(o.get("appointment_date")) for o in found]
            any_found = True
        else:
            body += head + f" returned NO slots ({result_of(t).get('status') or t['status']}): any option the agent reads out from it is invented.\n"
        days.append(start)
    if any_found:
        body += "These are the only appointment slots that exist on this call; any other slot is invented. The clinic books weekdays only.\n"
    elif not body:
        body = "- no appointment slots are looked up on this call, so any slot, day or time the agent states as open or available is invented.\n"
    wd = ", ".join(f"{d:%B} {d.day} is a {d:%A}" for d in sorted({d for d in days if d}))
    return body + ("The record gives each date with no weekday, so a date said without a weekday is complete and correct, "
                   f"and stating the year is optional. {wd}: a weekday the agent names that matches its date is not an invented date.")


def arg_ok(actual, rule: dict) -> bool:
    (op, want), = rule.items()
    if op == "date":
        return _date(actual) is not None and _date(actual) == _date(want)
    if op == "digits":
        return re.sub(r"\D", "", str(actual))[-10:] == re.sub(r"\D", "", str(want))[-10:]
    if op == "ci":
        return str(actual).strip().casefold() == str(want).strip().casefold()
    if op == "contains_all":  # free text such as an address: every fragment appears, case-folded
        return all(str(w).casefold() in str(actual).casefold() for w in (want if isinstance(want, list) else [want]))
    return str(actual) == str(want)


def checks(trace: dict, run: dict | None, spec: dict) -> list[dict]:
    tools = [e for e in trace["events"] if e["kind"] == "tool"]
    ran = [t for t in tools if t.get("status") in RAN]
    out = []

    def add(name, ok, detail=""):
        out.append({"check": name, "ok": bool(ok), "detail": detail})

    for exp in spec.get("expect_tools") or []:
        calls = [t for t in ran if t["action"] == exp["tool"]]
        if not calls:
            add(f"tool {exp['tool']} ran", False, "never ran")
            continue
        if "caller_dates" in exp:  # each search starts on a date the caller gave, in the caller's order
            got = [_date((t.get("arguments") or {}).get("start_date")) for t in calls]
            want = [_date(d) for d in exp["caller_dates"]]
            at = [want.index(d) if d in want else -1 for d in got]
            add(f"tool {exp['tool']} started on the caller's dates, in order", -1 not in at and at == sorted(at),
                f"searched from {[str(d) for d in got]}, caller gave {exp['caller_dates']}")
            continue
        last = next((t for t in reversed(calls) if t["status"] == "SUCCEEDED"), calls[-1])
        rules = exp.get("args") or {}
        if "option" in exp:  # the write carries offers[option-1] of the last SUCCEEDED search
            found = next((offers(t) for t in reversed(searches(trace, spec)) if t["status"] == "SUCCEEDED"), [])
            offer = found[exp["option"] - 1] if len(found) >= exp["option"] else {}
            rules = {k: {"date" if _date(offer.get(k)) else "eq": offer.get(k)} for k in exp["offer_keys"]}
        bad = {k: (last.get("arguments") or {}).get(k) for k, r in rules.items()
               if not arg_ok((last.get("arguments") or {}).get(k), r)}
        add(f"tool {exp['tool']} ran with the right arguments", not bad,
            f"{len(calls)} call(s), last {last['status']}" + (f"; wrong {bad} want {rules}" if bad else ""))
    writes = {}
    for t in ran:
        if t.get("effect_kind") == "write":
            writes[t["action"]] = writes.get(t["action"], 0) + 1
    add("writes at most once", all(n <= 1 for n in writes.values()), json.dumps(writes))
    forbidden = [t["action"] for t in ran if t["action"] in (spec.get("forbid_tools") or [])]
    add("no forbidden tool ran", not forbidden, ",".join(forbidden))
    if bypass := mock_bypass(trace):
        add("every tool answered from its mock", False, f"reached the real transport: {bypass}")
    final, want = final_intent(run), exits(spec)
    ended = any(t.get("ended") for t in (run or {}).get("turns") or [])
    if want:
        add("expected exit fired", final in want, f"want {want} got {final!r}")
    else:
        add("call reached an exit", ended, f"final intent {final!r}")
    saved = (run or {}).get("variables") or {}  # Hunter grades variables too: one check per expected field
    for field, rule in (spec.get("expect_saved") or {}).items():
        got = saved.get(field)
        add(f"saved {field}", got not in (None, "") and arg_ok(got, rule), f"got {got!r} want {rule}")
    if spec.get("expect_unsaved"):
        early = {f: saved[f] for f in spec["expect_unsaved"] if saved.get(f) not in (None, "")}
        add("unsaved fields stay unset", not early, json.dumps(early, default=str))
    acks = [e["text"] for e in lines(trace) if e["role"] == "agent" and ACK.match(e["text"].strip())]
    add("no ack-only spoken line", not acks, " | ".join(acks))
    # a repeated question gets the same answer every time; only the same answer twice on ONE caller turn is a defect
    answered = [re.search(r"entry=(\S+)(?:.*? turn=(\S+))?", m).groups()
                for m in logs(trace, "jev.sensitive entry=") if "skipped=" not in m]
    twice = sorted({entry for entry, turn in answered if answered.count((entry, turn)) > 1})
    add("no catalogue answer twice", not twice,
        "; ".join(f"{entry} on {turn}" for entry, turn in answered) if answered else "none asked")
    limit = float(spec.get("idle_limit_s") or 15)
    gaps, seq = [], lines(trace)
    for i, e in enumerate(seq):
        if e["role"] != "caller":
            continue
        reply = next((x for x in seq[i + 1:] if x["role"] == "agent"), None)
        if i + 1 < len(seq) and seq[i + 1]["role"] == "caller":
            gaps.append(f"no reply to {e['text'][:40]!r} before the caller spoke again")
        elif reply is None and not ended:
            gaps.append(f"caller line {e['text'][:40]!r} got no reply")
        elif reply is not None and reply["t"] - e["t"] > limit:
            gaps.append(f"{reply['t'] - e['t']:.1f}s after {e['text'][:40]!r}")
    elicited = sum(int(t.get("elicited") or 0) for t in (run or {}).get("turns") or [])
    add(f"no dead air over {limit:.0f}s", not gaps and not elicited, "; ".join(gaps) + (f" elicited={elicited}" if elicited else ""))
    return out


def validity(trace: dict, run: dict | None, meter_log: str) -> tuple[list[str], dict]:
    wire = [json.loads(x) for x in open(meter_log)] if os.path.exists(meter_log) else []
    done = {e["id"]: e for e in wire if e["ev"] == "done"}
    sent = [e for e in wire if e["ev"] == "sent"]
    jev_ok = [e for e in sent if e["dest"] == "jev" and done.get(e["id"], {}).get("status") == 200]
    gemma = [done[e["id"]] for e in sent if e["dest"] == "gemma" and e["id"] in done]
    served = sorted({d.get("model") or "?" for d in gemma})
    e2b_exec = sum(1 for e in wire if e["ev"] == "count" and e.get("dest") == "e2b" and e.get("path") == "/execute")
    code_ran = sum(1 for t in trace["events"] if t["kind"] == "tool" and t.get("status") in RAN and t.get("transport") == "custom_code")
    pre = logs(trace, "jev.preflight")
    faults = logs(trace, "jev.fault_recorded")
    asks = [e for e in trace["events"] if e["kind"] == "jev"]
    proof = {"jev_preflight": pre[:1], "jev_asks": len(asks), "jev_wire_200": len(jev_ok),
             "jev_errors": sorted({e["error"] for e in asks if e.get("error")}), "jev_faults": faults,
             "gemma_requests": len(gemma), "gemma_served_by": served, "e2b_executions": e2b_exec,
             "custom_code_tools_ran": code_ran, "refusals": trace.get("refusals") or [],
             "wire": {d: sum(1 for e in sent if e["dest"] == d) for d in sorted({e["dest"] for e in sent})}}
    why = []
    if not pre or any("ok=False" in p for p in pre) or not any("ok=True" in p for p in pre):
        why.append("jev.preflight ok=True missing")
    if not asks or not jev_ok:
        why.append("no Jev request answered 200")
    if faults:
        why.append(f"{len(faults)} jev.fault_recorded: Gemma may have carried the call")
    if not gemma or not all(re.search("gemma", m or "", re.I) for m in served):
        why.append(f"Gemma not proven (served_by {served})")
    if refused := [r for r in proof["refusals"] if r not in mock_bypass(trace)]:
        why.append(f"refused requests {refused[:3]}")
    if e2b_exec < code_ran:
        why.append(f"{code_ran} custom-code tools ran but {e2b_exec} E2B executions seen")
    if run is None:
        why.append("the simulator wrote no report")
    elif aborted := [f for f in run.get("failures") or [] if str(f).startswith("error:") or "user-simulator" in str(f)]:
        why.append(f"harness or persona abort: {str(aborted[0])[:160]}")
    return why, proof


def judge_input(run: dict, slug: str, turns: list[dict]) -> dict:
    """What the rubric judge reads of a run. An empty reply is the dead-air check's to measure, so the simulator's
    "throttled" label for it stays out: the judge would count it as a simulator failure and fail the rubric on it."""
    return {"scenario": slug, "run": 1, "turns": turns,
            "failures": [f for f in run.get("failures") or [] if not str(f).startswith("throttled:")],
            "variables": run.get("variables") or {}, "nodes_visited": run.get("nodes_visited") or []}


async def ask_judge(view: dict, rubric: str, spec: dict, expect_intent: str) -> dict:
    """One verdict from sim-fh/judge.py: Hunter's min-criterion rule on the verbatim prompt, then its verify pass."""
    os.environ["STRESS_REPO"] = os.getcwd()
    sys.path.insert(0, SIMFH)
    import judge as simfh
    from openai import APIConnectionError
    from src.simulation.cli import azure_chat
    try:
        return await simfh.judge_run(view, rubric, float(spec.get("threshold", 0.8)), spec.get("judge_model", "gpt-4.1"),
                                     verify=True, ecv={}, expect_intent=expect_intent)
    except APIConnectionError as exc:
        raise JudgeUnreachable(f"{type(exc).__name__}: {exc}") from exc
    finally:
        await azure_chat.aclose()


async def judge_verdict(view: dict, rubric: str, spec: dict, expect_intent: str) -> dict:
    """The judge's verdict, asked again after a pause when only its transport failed."""
    for attempt in range(1, JUDGE_TRIES + 1):
        try:
            return await ask_judge(view, rubric, spec, expect_intent)
        except JudgeUnreachable:
            if attempt == JUDGE_TRIES:
                raise
            await asyncio.sleep(JUDGE_RETRY_PAUSE_S * attempt)


async def judge(trace: dict, run: dict | None, spec: dict, out_dir: str) -> dict:
    why, proof = validity(trace, run, os.path.join(out_dir, "meter.jsonl"))
    result = {"scenario": spec["slug"], "proof": proof, "invalid_reasons": why}
    result["checks"] = checks(trace, run, spec)
    result["checks_failed"] = [c["check"] for c in result["checks"] if not c["ok"]]
    turns = turns_from_lines(trace, run)
    result["transcript"] = turns
    final, want = final_intent(run), exits(spec)
    result["slot_record"] = slot_record(trace, spec)
    rubric = None
    if run is not None and turns:
        try:
            rubric = await judge_verdict(judge_input(run, spec["slug"], turns),
                                         spec["rubric"].replace(SLOT_RECORD, result["slot_record"]), spec,
                                         final if final in want else want[0] if want else "")
        except Exception as exc:  # a judge that cannot answer leaves the run ungraded, never green
            why.append(f"judge failed: {type(exc).__name__}: {str(exc)[:120]}")
    if rubric:
        result.update(score=rubric["score"], verified_score=rubric["verified_score"], rubric_pass=rubric["rubric_pass"],  # gitleaks:allow
                      rubric_verdict=rubric["verdict"], criteria=rubric["criteria"], judge_evidence=rubric["evidence"],
                      overturned=rubric["overturned"])
    result["verdict"] = ("INVALID" if why else
                         "PASS" if rubric and rubric["verdict"] == "PASS" and not result["checks_failed"] else "FAIL")
    return result
