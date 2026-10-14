"""Offline self-check of the money path and the deterministic checks: python3 test_lane.py (no network, no spend)."""
import asyncio
import glob
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge_lane
import meter
import run_one

with tempfile.TemporaryDirectory() as d:
    meter.LEDGER, meter.LANE = os.path.join(d, "ledger.json"), d
    a = meter.reserve("c1", "a", 150.0)
    try:
        meter.reserve("c2", "b", 60.0)
        raise AssertionError("cap not enforced")
    except meter.Refused:
        pass
    try:
        meter.reserve("c1", "b", 1.0, campaign_cap=150.5)
        raise AssertionError("campaign cap not enforced")
    except meter.Refused:
        pass
    meter.settle(a, 0.25)
    assert meter.reserve("c2", "b", 60.0)  # the settle freed the reservation
    led = json.load(open(meter.LEDGER))
    assert (led["spent_usd"], led["reserved_usd"]) == (0.25, 60.0), led
    log = os.path.join(d, "m.jsonl")
    with open(log, "w") as fh:
        for ev in ({"ev": "sent", "id": 1, "dest": "jev", "bound_usd": 0.01}, {"ev": "done", "id": 1, "actual_usd": 0.001},
                   {"ev": "sent", "id": 2, "dest": "azure", "bound_usd": 0.05},  # no response: settles at the bound
                   {"ev": "count", "id": 3, "dest": "e2b", "path": "/execute"}):
            fh.write(json.dumps(ev) + "\n")
    total, by = meter.settle_from_meter(log)
    assert abs(total - (0.001 + 0.05 + meter.E2B_RUN_USD)) < 1e-9 and by["azure"]["unsettled"] == 1, (total, by)

    # A request settles to its real cost, so the next one fits; with no usage returned its bound stays committed.
    GEMMA = ("gemma", "agent-gateway.livekit.cloud", "/v1/chat/completions")
    body, usage = b'{"max_tokens": 1024}', b'{"usage": {"prompt_tokens": 500, "completion_tokens": 20}}'
    wire = meter._Meter(os.path.join(d, "wire.jsonl"), 1.5 * meter.cost("gemma", len(body) + 512, 1024, meter.CONSERVATIVE_FACTOR))
    wire.after(wire.before(*GEMMA, body), "gemma", 200, usage)
    assert abs(wire.committed - meter.cost("gemma", 500, 20)) < 1e-12, wire.committed
    wire.after(wire.before(*GEMMA, body), "gemma", 200, b"{}")
    try:
        wire.before(*GEMMA, body)
        raise AssertionError("a bound with no usage returned must stay committed")
    except meter.Refused:
        pass
    # a GET sends no prompt (a pool warm-up, a listing): counted on the wire, never priced or held against the budget
    held = wire.committed
    assert wire.before("gemma", GEMMA[1], "/v1/models", b"", "GET") is None and wire.committed == held
    assert json.loads(open(wire.path).readlines()[-1])["ev"] == "count"
    # the eval runner starts each case on a new wire log with a fresh budget: an old request never settles into it
    fresh = meter._Meter(os.path.join(d, "case-1.jsonl"), 1.0)
    late = fresh.before(*GEMMA, body)
    fresh.path, fresh.committed = os.path.join(d, "case-2.jsonl"), 0.0
    fresh.after(late, "gemma", 200, usage)
    assert fresh.committed == 0.0, fresh.committed

assert meter.dest_of("api.typesafe.ai") == "jev" and meter.dest_of("x.openai.azure.com") == "azure"
assert meter.dest_of("49999-abc.e2b.app") == "e2b" and meter.dest_of("evil.example.com") is None
assert meter._usage(b'data: {"model":"google/gemma-4-31B-it","usage":null}\n\ndata: {"usage":{"prompt_tokens":9,"completion_tokens":2}}\n\ndata: [DONE]') == ({"prompt_tokens": 9, "completion_tokens": 2}, "google/gemma-4-31B-it")

trace = {"events": [
    {"kind": "line", "role": "agent", "text": "Hi, this is the clinic.", "t": 0},
    {"kind": "line", "role": "caller", "text": "yes", "t": 1},
    {"kind": "line", "role": "agent", "text": "Okay.", "t": 2},
    {"kind": "line", "role": "caller", "text": "hello?", "t": 3},
    {"kind": "line", "role": "agent", "text": "What is your date of birth?", "t": 30},
    {"kind": "tool", "action": "book", "effect_kind": "write", "status": "SUCCEEDED", "arguments": {"d": "10-13-2026"}},
    {"kind": "tool", "action": "book", "effect_kind": "write", "status": "SUCCEEDED", "arguments": {"d": "10-13-2026"}},
    {"kind": "tool", "action": "search", "effect_kind": "read_only", "status": "DENIED", "arguments": {}},
    {"kind": "log", "msg": "jev.sensitive entry=bot_or_human language=en turn=1"},
    {"kind": "log", "msg": "jev.sensitive entry=bot_or_human language=en turn=1 probing_hits=0 offer=False reask=False"}]}
run = {"turns": [{"intent": "Rescheduled", "ended": True}]}
spec = {"expect_exit": "Rescheduled", "forbid_tools": ["search"], "idle_limit_s": 15,
        "expect_tools": [{"tool": "book", "args": {"d": {"date": "2026-10-13"}}}]}
got = {c["check"]: c["ok"] for c in judge_lane.checks(trace, run, spec)}
assert got == {"tool book ran with the right arguments": True, "writes at most once": False, "no forbidden tool ran": True,
               "expected exit fired": True, "no ack-only spoken line": False, "no catalogue answer twice": False,
               "no dead air over 15s": False}, got
turns = judge_lane.turns_from_lines(trace, run)
assert [t["user"] for t in turns] == ["", "yes", "hello?"] and turns[-1]["intent"] == "Rescheduled"
# C4: a question the caller repeats gets the same answer on each turn; only the same answer twice on ONE turn fails
trace["events"][-1]["msg"] = "jev.sensitive entry=bot_or_human language=en turn=4"
assert {c["check"]: c["ok"] for c in judge_lane.checks(trace, run, spec)}["no catalogue answer twice"]

# B1: the write books offers[option-1] of the LAST succeeded search; every search starts on a caller date, in order.
def search(start, first_day):
    offers = [{"appointment_date": f"10-{first_day + i}-2026", "from_slot_id": 103 + i, "display": f"October {first_day + i} slot"}
              for i in range(3)]
    return {"kind": "tool", "action": "search", "status": "SUCCEEDED", "arguments": {"start_date": start},
            "result": json.dumps({"offers": offers})}


def book(day, slot):
    return {"kind": "tool", "action": "book", "effect_kind": "write", "status": "SUCCEEDED",
            "arguments": {"appointment_date": f"10-{day}-2026", "from_slot_id": slot, "master_id": 1}}


spec = {"search_tool": "search", "expect_tools": [
    {"tool": "search", "caller_dates": ["2026-10-12", "2026-10-19"]},
    {"tool": "book", "option": 2, "offer_keys": ["appointment_date", "from_slot_id"]}]}
for events, dates_ok, book_ok in (
        ([search("2026-10-12", 13), search("2026-10-19", 20), book(21, 104)], True, True),
        ([search("2026-10-12", 13), search("2026-10-19", 20), book(14, 104)], True, False),  # option 2 of the first search
        ([search("2026-10-19", 20), search("2026-10-12", 13), book(14, 104)], False, True),  # caller order reversed
        ([search("2026-10-13", 14), book(15, 104)], False, True)):  # a date the caller never gave
    got = {c["check"]: c["ok"] for c in judge_lane.checks({"events": events}, run, spec)}
    assert (got["tool search started on the caller's dates, in order"], got["tool book ran with the right arguments"]) == (dates_ok, book_ok), got

# B2: the clinic record lists what this call's searches returned, and "no slots looked up" only when none ran.
rec = judge_lane.slot_record({"events": [search("2026-10-12", 13), search("2026-10-16", 19)]}, {"search_tool": "search", "clinic_day": "2026-09-30"})
assert "October 12, 2026" in rec and "October 16, 2026" in rec and "October 21 slot" in rec and "no appointment slots" not in rec, rec
assert "no appointment slots" in judge_lane.slot_record({"events": []}, {"search_tool": "search", "clinic_day": "2026-09-30"})

# C1: a reviewed list of exits
got = {c["check"]: c["ok"] for c in judge_lane.checks({"events": []}, {"turns": [{"intent": "Do Not Call", "ended": True}]},
                                                       {"expect_exit": ["Patient Upset", "Do Not Call"]})}
assert got["expected exit fired"], got

# B3: a persona abort is not evidence
why, _ = judge_lane.validity({"events": []}, {"failures": ["user-simulator returned empty message after retry"]}, os.devnull)
assert any("user-simulator" in w for w in why), why

# A tool that skipped its sim mock (denied .invalid host) fails a check; a budget refusal still voids the run.
for refusals, invalid, bypassed in ((["denied host example.invalid"], False, True), (["budget azure"], True, False)):
    why, _ = judge_lane.validity({"events": [], "refusals": refusals}, {}, os.devnull)
    got = {c["check"]: c["ok"] for c in judge_lane.checks({"events": [], "refusals": refusals}, {}, {})}
    assert (any("refused" in w for w in why), got.get("every tool answered from its mock") is False) == (invalid, bypassed), (why, got)

# B5: preflight fails closed on an unreviewed local intent and on an expected exit the local flow lacks
import lane  # noqa: E402

flow = {"nodes": [{"data": {"config": {"intents": [{"intent_name": "Rescheduled"}, {"intent_name": "Brand New"}]}}}, {"data": {"config": {}}}]}
for specs, want in (([{"expect_exit": "Rescheduled"}, {"expect_exit": None}], ["Brand New"]),
                    ([{"expect_exit": ["Rescheduled", "Gone Exit"]}], ["Brand New", "Gone Exit"])):
    fails = lane.intent_failures(flow, specs)
    assert len(fails) == len(want) and all(w in f for w, f in zip(want, fails)), fails
assert lane.intent_failures({"nodes": [{"data": {"config": {"intents": [{"intent_name": "Rescheduled"}]}}}]},
                            [{"expect_exit": "Rescheduled"}]) == []

# General flows: one saved-value check per expected field, unset fields, and the preflight gate that skips FHCSD parts.
run = {"turns": [{"intent": "Done", "ended": True}],
       "variables": {"dob": "1990-02-03", "phone": "+1 (202) 555-0101", "addr": "12 Main St, Springfield", "note": ""}}
spec = {"expect_exit": "Done", "expect_unsaved": ["note", "dob"], "expect_saved": {
    "dob": {"date": "02/03/1990"}, "phone": {"digits": "2025550101"}, "addr": {"contains_all": ["12 main", "springfield"]}, "name": {"ci": "Al"}}}
got = {c["check"]: c["ok"] for c in judge_lane.checks({"events": []}, run, spec)}
assert [got[k] for k in ("saved dob", "saved phone", "saved addr", "saved name", "unsaved fields stay unset")] == [True, True, True, False, False], got
assert lane.intent_failures(flow, [{"expect_exit": "Rescheduled"}], None) == []  # a general flow's intents are its own
http = {"nodes": [{"id": "n1", "data": {"config": {"actions": [{"action_type": "HTTP", "http_url": "https://api.example.com"}]}}}]}
ok_spec = {"slug": "a", "rubric": "r", "entry": "flow", "expect_saved": {"dob": {"date": "2026-01-02"}}}
assert lane.general_failures(http, {"a": {"action_mocks": {}}}, [ok_spec]) == []
code = {"nodes": [{"id": "n2", "data": {"config": {"actions": [{"action_type": "CUSTOM_CODE"}]}}}]}
assert len(lane.general_failures(code, {"a": {"real_actions": ["x"]}}, [{**ok_spec, "expect_tools": [{"tool": "t", "args": {"x": {"row_has": {}}}}]}])) == 3
with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "pack", "a"))
    json.dump({**http, "flowId": "f-1"}, open(os.path.join(d, "flow.json"), "w"))
    json.dump(ok_spec, open(os.path.join(d, "pack", "a", "spec.json"), "w"))
    open(os.path.join(d, "pack", "a", "scenario.yaml"), "w").write("turns: []\n")
    lane.mock_get = lambda *a, **k: 1 / 0  # a general preflight must never reach the FHCSD mock
    res = lane.preflight(flow_ws=d, pack=os.path.join(d, "pack"))
    assert res["flow"]["id"] == "f-1" and res["canary"].startswith("skipped") and "ist" not in res, res
    assert all(f == "tree has uncommitted changes" for f in res["failures"]), res["failures"]

# C3, C5, C7: the judge is asked again after a transport error, never reads the "throttled" label (the dead-air check
# owns the empty turn), and a criterion its own re-read overturned reaches the row and the board; a stored run grades
# again to the same row.
RUBRIC = {"verdict": "FAIL", "score": 0.7, "verified_score": 1.0, "rubric_pass": False, "overturned": [1],
          "criteria": [{"n": 1, "met": False, "accuracy": 0.7}], "evidence": {}}
asked = []


async def judge_once_unreachable(view, rubric, spec, expect_intent):
    asked.append(view)
    if len(asked) == 1:
        raise judge_lane.JudgeUnreachable("APIConnectionError: Connection error.")
    return RUBRIC


def grade_in_process(argv, out, timeout, prefix=""):
    """What run_one.py --judge-only does, without the process."""
    assert argv[-1] == "--judge-only" and prefix == "rejudge.", argv
    stored_trace = json.load(open(os.path.join(out, "trace.json")))
    report = json.load(open(glob.glob(os.path.join(out, "ws", "reports", "*.json"))[-1]))[0]
    again = asyncio.run(judge_lane.judge(stored_trace, report, json.load(open(argv[argv.index("--spec") + 1])), out))
    json.dump(again, open(os.path.join(out, "judge.json"), "w"))


judge_lane.ask_judge, judge_lane.JUDGE_RETRY_PAUSE_S, lane.launch = judge_once_unreachable, 0, grade_in_process
with tempfile.TemporaryDirectory() as d:
    meter.LEDGER, meter.LANE = os.path.join(d, "ledger.json"), d
    out = os.path.join(d, "runs", "c", "s-r1")
    os.makedirs(os.path.join(out, "ws", "reports"))
    trace = {"events": [
        {"kind": "log", "msg": "jev.preflight ok=True nodes=1 reasons=[]"}, {"kind": "jev", "heads": {}},
        {"kind": "line", "role": "agent", "text": "Am I speaking with Pat?", "t": 0},
        {"kind": "line", "role": "caller", "text": "yes", "t": 1},
        {"kind": "line", "role": "caller", "text": "hello?", "t": 2},
        {"kind": "line", "role": "agent", "text": "What is your date of birth?", "t": 3}]}
    run = {"turns": [{"intent": "Done", "ended": True}], "failures": ["throttled: empty/rate-limited reply persisted after 0 retries"]}
    spec = {"slug": "s", "rubric": "1. r", "expect_exit": "Done"}
    for name, doc in (("trace.json", trace), ("spec.json", spec), (os.path.join("ws", "reports", "r.json"), [run])):
        json.dump(doc, open(os.path.join(out, name), "w"))
    with open(os.path.join(out, "meter.jsonl"), "w") as fh:
        for ev in ({"ev": "sent", "id": 1, "dest": "jev"}, {"ev": "done", "id": 1, "status": 200},
                   {"ev": "sent", "id": 2, "dest": "gemma"}, {"ev": "done", "id": 2, "model": "google/gemma-4-31b-it"},
                   {"ev": "count", "id": 3, "dest": "gemma", "path": "/v1/models"}):  # a warm GET proves and voids nothing
            fh.write(json.dumps(ev) + "\n")
    graded = asyncio.run(judge_lane.judge(trace, run, spec, out))
    assert len(asked) == 2 and graded["invalid_reasons"] == [] and asked[-1]["failures"] == [], (asked, graded)
    assert "no dead air over 15s" in graded["checks_failed"] and graded["proof"]["gemma_requests"] == 1, graded
    assert (graded["verdict"], graded["score"], graded["verified_score"], graded["overturned"]) == ("FAIL", 0.7, 1.0, [1])
    json.dump(graded, open(os.path.join(out, "judge.json"), "w"))
    row = lane.judged({"scenario": "s", "run": 1, "dir": out, "cost_usd": 0.02}, out, {"gemma_label": 1, "azure_label": 0})
    assert (row["verdict"], row["invalid_reasons"], row["overturned"]) == ("FAIL", [], [1]), row
    json.dump(row, open(os.path.join(out, "row.json"), "w"))
    camp = os.path.dirname(out)
    again = lane.rejudge(camp, "s", "env", SimpleNamespace(pack=d, judge_usd=1.0, timeout=5))
    assert again == [{**row, "rejudge_usd": 0.0}] == [json.load(open(os.path.join(out, "row.json")))], again
    assert os.path.exists(os.path.join(out, "judge.prev.json")) and json.load(open(meter.LEDGER))["reserved_usd"] == 0

    # A run whose first Jev fault lands before the caller's first line is run once more, and its row says so.
    FAULT, HELLO = {"kind": "log", "msg": "jev.fault_recorded kind=repeated_timeout"}, {"kind": "line", "role": "caller", "text": "Hello?"}
    attempts = []

    def faulted_at_start(slug, rep, camp, env_path, args):
        attempts.append(os.path.join(camp, f"{slug}-r{rep}"))
        os.makedirs(attempts[-1])
        json.dump({"events": [FAULT, HELLO]}, open(os.path.join(attempts[-1], "trace.json"), "w"))
        return {"scenario": slug, "run": rep, "dir": attempts[-1], "verdict": "INVALID", "cost_usd": 0.01}

    lane.attempt = faulted_at_start
    row = lane.one("s", 2, camp, "env", None)
    assert len(attempts) == 2 and row["rerun_after_start_fault"] and row["first_attempt"]["cost_usd"] == 0.01, (attempts, row)
    assert os.path.exists(os.path.join(row["first_attempt"]["dir"], "trace.json")) and os.path.exists(os.path.join(row["dir"], "trace.json"))
    json.dump({"events": [HELLO, FAULT]}, open(os.path.join(row["dir"], "trace.json"), "w"))
    assert not lane.start_fault(row["dir"])  # a fault after the caller spoke is the agent's own run
    json.dump(row, open(os.path.join(row["dir"], "row.json"), "w"))
    lane.board(camp)
    table = open(os.path.join(camp, "board.md")).read()
    assert "| s r1 | FAIL | 0.7 | criterion 1 |" in table and "| s r2 (rerun after a start-up fault) | INVALID |" in table, table

# A lane process warms the HTTP pools once, before its first call: the sim CLI runs no warmer.
order = []


async def warm_all():
    order.append("warm")


async def start(_session):
    order.append("start")


warm_start = run_one.warmed(start, warm_all)
asyncio.run(warm_start(None))
asyncio.run(warm_start(None))
assert order == ["warm", "start", "start"], order
print("test_lane: ok")
