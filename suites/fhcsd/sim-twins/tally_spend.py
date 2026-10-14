"""Token and USD tally for one simulation CLI run.

Usage source: the engine logs every agent and Scribe LLM response as an INFO line on stderr,
  src/units/base.py:456  event_logger.info(f"LLM metrics collected: {event}")
  src/units/base.py:471  event_logger.info(f"Scribe LLM metrics collected: {event}")
formatted as one JSON object per line by src/logging_config.py:39-65 (JsonFormatter, stderr handler at :111).
The CLI disables INFO logging unless --verbose (src/simulation/cli/__main__.py:158-159), so the run must add
--verbose and redirect stderr to a file. The simulated caller (src/simulation/cli/azure_chat.py:38-46) logs
no usage anywhere, so its tokens are estimated from the run report (<ws>/reports/<stamp>.json) at 4 chars/token,
times each run's throttle attempts. Every JSON line carries call_uuid sim-cli-<scenario>-<run> (engine.py:100).

Run: .venv/bin/python tally_spend.py <stderr.log> [--report <ws>/reports/<stamp>.json]   |   --self-test
"""
import json
import math
import os
import re
import sys

import yaml

LINE = re.compile(r"(Scribe |AMD )?LLM metrics collected: (type='llm_metrics'.*)")
FIELD = r"(?<![a-z_]){}=(?:'([^']*)'|(-?[\d.]+|True|False|None))"
PRICES = {"standard": (2.0, 0.5, 8.0), "conservative": (10.0, 10.0, 40.0)}  # USD per 1M: prompt, cached, completion
CALLER_SYSTEM_CHARS = 811  # engine.py:45-61 template without persona and goal
CHARS_PER_TOKEN = 4  # ponytail: rough estimate, patch azure_chat to log response.usage if the caller share matters
CALLER_GAP = ("caller estimate: x attempts per run; it excludes the empty-reply retry and the END_CALL push-back calls "
              "(engine.py _next_user_message), because the report does not record them")
PRICE_LINE = "prices per 1M tokens: standard 2 / 0.5 / 8, conservative 10 / 10 / 40 (prompt / cached / completion)"


def field(text, name):
    m = re.search(FIELD.format(name), text)
    return None if m is None else (m.group(1) if m.group(1) is not None else m.group(2))


def parse_log(path, by_call=False):
    """Rows keyed '<kind> <model>', or (call_uuid, '<kind> <model>') when by_call."""
    rows, seen, stats = {}, set(), {"lines": 0, "duplicates": 0, "cancelled": 0, "no_usage": 0}
    with open(path, errors="replace") as f:
        for raw in f:
            m = LINE.search(raw)
            if not m:
                continue
            body, call = m.group(2), ""
            try:
                rec = json.loads(raw)
                body, call = LINE.search(rec["message"]).group(2), rec.get("call_uuid") or ""  # unescape JSON lines
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
            stats["lines"] += 1
            request_id = field(body, "request_id") or ""
            if request_id and request_id in seen:
                stats["duplicates"] += 1
                continue
            seen.add(request_id)
            stats["cancelled"] += field(body, "cancelled") == "True"
            prompt, cached = int(field(body, "prompt_tokens") or 0), int(field(body, "prompt_cached_tokens") or 0)
            completion = int(field(body, "completion_tokens") or 0)
            stats["no_usage"] += prompt == 0
            kind = (m.group(1) or "Agent ").strip().lower()
            key = f"{kind} {field(body, 'model_name') or '?'}"
            r = rows.setdefault((call, key) if by_call else key, [0, 0, 0, 0])
            for i, v in enumerate((1, prompt, cached, completion)):
                r[i] += v
    return rows, stats


def caller_run(run, ws):
    """Caller estimate [calls, prompt, 0, completion] for one report run, times its attempts; scripted runs are zero."""
    if run.get("mode") != "simulated":
        return [0, 0, 0, 0]
    calls = prompt = completion = 0
    user = {}
    scenario = os.path.join(ws, "scenarios", run["scenario"] + ".yaml")
    if os.path.isfile(scenario):
        user = (yaml.safe_load(open(scenario)) or {}).get("simulated_user") or {}
    system_chars = CALLER_SYSTEM_CHARS + len(user.get("persona", "")) + len(user.get("goal", ""))
    history = 0
    for i, turn in enumerate(run.get("turns", [])):
        if i > 0:  # the opening line is scripted, every later caller line is one LLM call
            calls += 1
            prompt += system_chars + history + len("Conversation so far:\n\n\nWhat does the caller say next?")
            completion += len(turn.get("user") or "")
        history += len(f"Caller: {turn.get('user') or ''}\nAgent: {turn.get('agent') or ''}\n")
    n = run.get("attempts", 1)  # throttle reruns replay the call; only the kept attempt is in the report
    return [calls * n, math.ceil(prompt * n / CHARS_PER_TOKEN), 0, math.ceil(completion * n / CHARS_PER_TOKEN)]


def estimate_caller(report_path):
    """(summed caller row, attempts total) over every run in a report."""
    ws = os.path.dirname(os.path.dirname(os.path.abspath(report_path)))
    runs = json.load(open(report_path))
    rows = [caller_run(run, ws) for run in runs]
    return [sum(col) for col in zip([0, 0, 0, 0], *rows)], sum(run.get("attempts", 1) for run in runs)


def usd(row, prices):
    _, prompt, cached, completion = row
    p, c, o = prices
    return ((prompt - cached) * p + cached * c + completion * o) / 1e6


def render(rows, stats):
    out = [f"{'source':<28}{'calls':>7}{'prompt':>12}{'cached':>12}{'completion':>12}{'std USD':>10}{'cons USD':>10}"]
    total = [0, 0, 0, 0]
    for key, row in sorted(rows.items()):
        total = [a + b for a, b in zip(total, row)]
        out.append(f"{key:<28}{row[0]:>7}{row[1]:>12}{row[2]:>12}{row[3]:>12}"
                   f"{usd(row, PRICES['standard']):>10.4f}{usd(row, PRICES['conservative']):>10.4f}")
    out.append(f"{'TOTAL':<28}{total[0]:>7}{total[1]:>12}{total[2]:>12}{total[3]:>12}"
               f"{usd(total, PRICES['standard']):>10.4f}{usd(total, PRICES['conservative']):>10.4f}")
    out.append(f"metrics lines {stats['lines']}, duplicate request_ids skipped {stats['duplicates']}, "
               f"cancelled {stats['cancelled']}, lines with zero prompt tokens {stats['no_usage']}"
               + (f", run attempts total {stats['attempts']}" if "attempts" in stats else ""))
    return "\n".join(out), total


def tally(log, report=None):
    """(printed text, TOTAL row, stats) for one stderr log and its optional run report."""
    rows, stats = parse_log(log)
    if report:
        rows["caller (estimate) gpt-4.1"], stats["attempts"] = estimate_caller(report)
        note = CALLER_GAP
    else:
        note = "WARNING: no --report given, simulated-caller tokens are NOT included"
    table, total = render(rows, stats)
    return f"{table}\n{PRICE_LINE}\n{note}", total, stats


def self_test():
    import logging
    import tempfile

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "repo")))
    from livekit.agents.metrics import LLMMetrics
    from livekit.agents.metrics.base import Metadata
    from src.logging_config import JsonFormatter

    def line(prefix, rid, prompt, cached, completion, model, cancelled=False, as_json=True, call=""):
        m = LLMMetrics(label="livekit.plugins.openai.llm.LLM", request_id=rid, timestamp=1.0, duration=1.0, ttft=0.3,
                       cancelled=cancelled, completion_tokens=completion, prompt_tokens=prompt,
                       prompt_cached_tokens=cached, total_tokens=prompt + completion, tokens_per_second=1.0,
                       speech_id="speech_x", metadata=Metadata(model_name=model, model_provider="Azure OpenAI"))
        msg = f"{prefix}LLM metrics collected: {m}"  # src/units/base.py:456 and :471
        rec = logging.LogRecord("cx-agent-runner.event", logging.INFO, "base.py", 456, msg, (), None)
        rec.call_uuid = call  # stamped by ContextCapturingQueueHandler on a real run
        return JsonFormatter().format(rec) if as_json else msg

    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "run.stderr.log")
        with open(log, "w") as f:
            f.write("\n".join([
                line("", "chatcmpl-A", 9000, 8000, 40, "gpt-4.1", call="sim-cli-sim-a-1"),
                line("", "chatcmpl-A", 9000, 8000, 40, "gpt-4.1", call="sim-cli-sim-a-1"),
                line("Scribe ", "chatcmpl-S", 3000, 0, 100, "gpt-4.1-mini"),
                line("", "", 0, 0, 0, "gpt-4.1", cancelled=True),
                '{"level": "INFO", "message": "TTS response complete"}',
                "Traceback (most recent call last): harmless noise",
                line("", "chatcmpl-B", 1000, 0, 10, "gpt-4.1", as_json=False),
            ]) + "\n")
        print("synthetic line:", open(log).readline().strip())
        rows, stats = parse_log(log)
        assert rows == {"agent gpt-4.1": [3, 10000, 8000, 50], "scribe gpt-4.1-mini": [1, 3000, 0, 100]}, rows
        assert stats == {"lines": 5, "duplicates": 1, "cancelled": 1, "no_usage": 1}, stats
        by_call, _ = parse_log(log, by_call=True)
        assert by_call == {("sim-cli-sim-a-1", "agent gpt-4.1"): [1, 9000, 8000, 40], ("", "agent gpt-4.1"): [2, 1000, 0, 10],
                           ("", "scribe gpt-4.1-mini"): [1, 3000, 0, 100]}, by_call
        _, total = render(rows, stats)
        assert math.isclose(usd(total, PRICES["standard"]), 0.0152) and math.isclose(usd(total, PRICES["conservative"]), 0.136)

        os.makedirs(os.path.join(tmp, "scenarios"))
        os.makedirs(os.path.join(tmp, "reports"))
        with open(os.path.join(tmp, "scenarios", "sim-a.yaml"), "w") as f:
            yaml.safe_dump({"simulated_user": {"persona": "p" * 40, "goal": "g" * 60}}, f)
        turns = [{"user": "Hello?", "agent": "a" * 100}, {"user": "u" * 20, "agent": "b" * 50}, {"user": "END_CALL", "agent": ""}]
        report = os.path.join(tmp, "reports", "x.json")
        json.dump([{"scenario": "sim-a", "mode": "simulated", "turns": turns},
                   {"scenario": "scr", "mode": "scripted", "turns": turns, "attempts": 2}], open(report, "w"))
        (calls, prompt, cached, completion), attempts = estimate_caller(report)
        overhead = 811 + 100 + len("Conversation so far:\n\n\nWhat does the caller say next?")
        h1 = len("Caller: Hello?\nAgent: " + "a" * 100 + "\n")
        h2 = h1 + len("Caller: " + "u" * 20 + "\nAgent: " + "b" * 50 + "\n")
        assert [calls, cached] == [2, 0] and prompt == math.ceil((2 * overhead + h1 + h2) / 4), (calls, prompt)
        assert completion == math.ceil((20 + len("END_CALL")) / 4) and attempts == 3, (completion, attempts)
        json.dump([{"scenario": "sim-a", "mode": "simulated", "turns": turns, "attempts": 3}], open(report, "w"))
        (calls3, prompt3, _, completion3), attempts = estimate_caller(report)
        assert [calls3, prompt3, completion3, attempts] == [6, math.ceil(3 * (2 * overhead + h1 + h2) / 4),
                                                           math.ceil(3 * (20 + len("END_CALL")) / 4), 3]
        text, _, _ = tally(log, report)
        assert "run attempts total 3" in text and CALLER_GAP in text, text
    print("self-test OK: JSON and plain lines parsed, duplicate request_id skipped, noise ignored, USD math, caller estimate x attempts, per-call grouping")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        sys.exit(0)
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    report = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
    text, _, stats = tally(sys.argv[1], report)
    if not stats["lines"]:
        sys.exit(f"{sys.argv[1]}: no LLM metrics lines; run with --verbose and redirect stderr (2>) to this file")
    print(text)
