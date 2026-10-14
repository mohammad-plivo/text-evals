"""One scenario run in its own process: the sim CLI on the lane tree, the wire meter, a structured trace, the judge.

  <tree>/.venv/bin/python run_one.py --tree T --ws WS --scenario S [--node N] --env-file E --out DIR --budget USD --spec SPEC

Writes DIR/{meter.jsonl, trace.json, judge.json}; stdout/stderr go wherever the parent points them.
With --judge-only the scenario does not run: the stored trace and sim report are graded again, and the judge's
own requests go to DIR/rejudge-meter.jsonl so the run's wire proof stays as it was.
The trace is taken where the leader acts, not from the sim report (which keeps one speech segment per turn):
JevClient.ask (every question and pick), EffectExecutor.execute (every tool with arguments and result), the
AgentSession's conversation items (every spoken line, timed), the jev.* log lines, and DecisionLoop.publish for
delegate drafts (DELEGATE_SETTLED) and conflict tuples (DECISION_CONFLICT).
"""
import argparse
import asyncio
import glob
import json
import logging
import os
import sys
import time

LANE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()
TRACE: list[dict] = []


def rec(kind: str, **fields) -> dict:
    row = {"kind": kind, "t": round(time.time() - T0, 3), **fields}
    TRACE.append(row)
    return row


def load_env(path: str) -> None:
    """The lane env wins over anything inherited: settings are built at import, so this runs before any src import."""
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def warmed(start, warm_all):
    """SimSession.start that first warms the HTTP pools, once per process: the sim CLI runs no warmer, so a lane
    process would otherwise pay every first connection on its first call."""
    cold = True

    async def start_warm(self):
        nonlocal cold
        if cold:
            cold = False
            await warm_all()
        return await start(self)
    return start_warm


def hooks(ws: str) -> None:
    from livekit.agents import AgentSession

    from src.jev_leader import client as jev_client
    from src.jev_leader import effects

    ask = jev_client.JevClient.ask

    async def traced_ask(self, state, questions, *, deadline):
        row = rec("jev", state_chars=len(state or ""),
                  heads={h: sorted((q.get("criteria") or {}).keys()) for h, q in questions.items()})
        t = time.time()
        try:
            answers = await ask(self, state, questions, deadline=deadline)
            row["picks"] = {h: {"choice": a.choice, "confidence": round(a.confidence, 3)} for h, a in answers.valid.items()}
            row["invalid"] = list(answers.invalid)
            return answers
        except Exception as exc:
            row["error"] = getattr(exc, "kind", type(exc).__name__)
            raise
        finally:
            row["ms"] = round((time.time() - t) * 1000)

    jev_client.JevClient.ask = traced_ask

    execute = effects.EffectExecutor.execute

    async def traced_execute(self, bound, logical_identity, freshness):
        action = getattr(bound, "action", None)
        row = rec("tool", action=getattr(action, "action_id", None), effect_kind=getattr(action, "effect_kind", None),
                  transport=getattr(action, "transport", None),
                  arguments=bound.arguments if isinstance(bound, effects.BoundAction) else None)
        t = time.time()
        out = await execute(self, bound, logical_identity, freshness)
        row.update(status=out.status, ms=round((time.time() - t) * 1000), result=json.dumps(out.result, default=str)[:3000])
        return out

    effects.EffectExecutor.execute = traced_execute

    init = AgentSession.__init__

    def traced_init(self, *args, **kwargs):
        init(self, *args, **kwargs)

        def added(ev):
            item = ev.item
            text = getattr(item, "text_content", None) or ""
            if getattr(item, "role", "") in ("user", "assistant") and text.strip():
                rec("line", role="caller" if item.role == "user" else "agent", text=text,
                    interrupted=bool(getattr(item, "interrupted", False)))
        self.on("conversation_item_added", added)

    AgentSession.__init__ = traced_init

    class Capture(logging.Handler):
        def emit(self, record):
            try:
                msg = record.getMessage()
            except Exception:
                return
            if msg.startswith("jev."):
                rec("log", msg=msg[:20000])  # jev.request and the probs on jev.decision run long

    handler = Capture(level=logging.INFO)
    for name in ("cx-agent-runner", "cx-agent-runner.event", ""):
        logging.getLogger(name).addHandler(handler)

    import yaml

    from src.simulation.runner import SimSession
    params = (yaml.safe_load(open(os.path.join(ws, "params.yaml"))) or {}).get("params") or {}
    start = SimSession.start

    async def seeded_start(self):
        # The CLI only substitutes {{Start.*}} text; leader contracts read Start's node variables by uuid
        # (node_var), so a call's trigger payload is seeded the way verify_exact_flow.py does it.
        node = next((n for n in self.graph.nodes_by_id.values() if n.type == "start"), None)
        if node is not None and node.id not in self.variables:
            self.variables[node.id] = {"http": {"params": {k: str(v) for k, v in params.items()}}}
            rec("seed", start_node=node.id, keys=sorted(params))
        return await start(self)

    from src.utils import http_pool

    async def warm_pools():
        # Jev registers its pool only at the first selected call, after this; a tree without register_pool has none
        getattr(jev_client, "register_pool", lambda: None)()
        await http_pool.warm_all()

    SimSession.start = warmed(seeded_start, warm_pools)

    from src.jev_leader import loop as leader
    from src.jev_leader.events import EventType
    from src.jev_leader.loop import leader_loop
    publish = leader.DecisionLoop.publish

    def traced_publish(self, type_, source_id, **payload):
        event = publish(self, type_, source_id, **payload)
        if type_ is EventType.DELEGATE_SETTLED:
            rec("delegate", job=str(payload.get("job")), outcome=payload.get("outcome"), text=str(payload.get("text") or "")[:3000],
                job_id=source_id, kept=event is not None)
        elif type_ is EventType.DECISION_CONFLICT:
            rec("conflict", decision=source_id, reason=payload.get("reason"), conflict=payload.get("conflict"), kept=event is not None)
        return event

    leader.DecisionLoop.publish = traced_publish

    drain = SimSession._drain_pending_speech

    async def drain_after_leader(self, timeout: float = 15.0):
        # runner.py waits for the leader (loop.idle) only BEFORE the flow settles, so the V2.9 opener Jev starts
        # on the screening->V2.9 handoff lands after the turn serialized and the CLI elicits it with an empty
        # turn. Waiting here only covers work the leader already started; it cannot create speech.
        loop = leader_loop(self.session.userdata) if self.session else None
        if loop is not None:
            try:
                await loop.idle(timeout=max(10.0, loop.state.snap.episode_seconds))
            except (TimeoutError, asyncio.TimeoutError):
                rec("leader_idle_timeout")
        await drain(self, timeout)

    SimSession._drain_pending_speech = drain_after_leader

    import src.simulation.cli.engine as engine
    suite = engine.run_suite

    async def one_attempt(*args, **kwargs):  # a throttle retry would re-run and re-bill the whole scenario
        kwargs["max_retries"] = 0
        try:
            return await suite(*args, **kwargs)
        finally:  # the sandbox dies with the run instead of idling out its keep-alive
            from src.services.e2b_sandbox import e2b_sandbox
            try:
                await e2b_sandbox.shutdown()
                rec("e2b_shutdown")
            except Exception as exc:
                rec("e2b_shutdown_failed", error=type(exc).__name__)

    engine.run_suite = one_attempt


def simulate(a, m) -> None:
    """Run the scenario through the sim CLI and store its trace."""
    hooks(a.ws)
    from src.simulation.cli import __main__ as cli

    sys.argv = ["sim", "run", a.ws, "--scenario", a.scenario, "--env-file", a.env_file, "--no-open", "--repeat", "1",
                "--max-parallel", "1", "--stagger", "0", "--verbose"] + (["--node", a.node] if a.node else [])
    rec("start", scenario=a.scenario, node=a.node or "flow entry")
    code = None
    try:
        cli.main()
    except SystemExit as exc:
        code = exc.code
    rec("end", cli_exit=code)
    reports = sorted(glob.glob(os.path.join(a.ws, "reports", "*.json")))
    trace = {"scenario": a.scenario, "cli_exit": code, "report": reports[-1] if reports else None,
             "events": TRACE, "refusals": m.refusals}
    json.dump(trace, open(os.path.join(a.out, "trace.json"), "w"), indent=1, default=str)


def main() -> int:
    ap = argparse.ArgumentParser()
    for flag in ("--tree", "--ws", "--scenario", "--env-file", "--out", "--spec"):
        ap.add_argument(flag, required=True)
    ap.add_argument("--node", default="")
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--judge-only", action="store_true", help="grade the stored trace again; the scenario does not run")
    a = ap.parse_args()
    load_env(a.env_file)
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, a.tree)
    os.chdir(a.tree)
    sys.path.insert(0, LANE)
    import meter
    m = meter.install(os.path.join(a.out, "rejudge-meter.jsonl" if a.judge_only else "meter.jsonl"), a.budget)
    if not a.judge_only:
        simulate(a, m)
    # graded from what is on disk, so a later regrade reads exactly what the first grade read
    trace = json.load(open(os.path.join(a.out, "trace.json")))
    reports = sorted(glob.glob(os.path.join(a.ws, "reports", "*.json")))
    run = json.load(open(reports[-1]))[0] if reports else None
    import judge_lane
    verdict = asyncio.run(judge_lane.judge(trace, run, json.load(open(a.spec)), a.out))
    json.dump(verdict, open(os.path.join(a.out, "judge.json"), "w"), indent=1, default=str)
    print(f"LANE VERDICT {verdict['verdict']} score={verdict.get('score')} checks_failed={verdict.get('checks_failed')} "
          f"invalid={verdict.get('invalid_reasons')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
