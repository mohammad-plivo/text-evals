"""One lane scenario run on the small System One version: the lane's run_one.py with its engine hooks swapped for main's.

Same command line and outputs as text-evals/text-lane/run_one.py (meter.jsonl, trace.json, judge.json), so the lane's
judge and board read a run unchanged. Only where the trace is taken differs, because this tree has no engine:

  jev rows    src.system_one.ask_jev: every question, its pick and its probabilities
  tool rows   the session's function_tools_executed event, for the flow's own actions
  line rows   the session's conversation items, as in the lane
  log rows    "jev.sensitive entry=..." when a fixed answer is said, "jev.fault_recorded ..." when Jev did not lead a
              request, and one "jev.preflight ok=True" row, because the small version has no start check to report

Validity differs from the engine lane in one place: Gemma must be proven only when the call reached a V2.9 node. On
main's path a screening step speaks with main's own model for that step, so a call that ends there sends Gemma nothing.

Two things the engine's simulator did are done here for main's: a real custom-code tool gets the scenario's
action_envs, and a screening span that exits to an AI node is switched the way main's run store switches it, so a
whole flow walks in one run.

S1_JUDGE_FLOW names the engine-shaped twin of the flow under test. The lane's judge reads tool results in the shape
that twin's tool code returns, so each raw result is passed through the twin's own result layer for the trace row.
The model always sees the raw result.
"""
import argparse
import asyncio
import glob
import json
import logging
import os
import sys
import time

LANE = "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev/text-evals/text-lane"
T0 = time.time()
TRACE: list[dict] = []
TRANSPORT = {"CUSTOM_CODE": "custom_code", "HTTP": "http", "EXECUTE_ACTION": "mcp"}
JUDGE_FLOW = os.environ.get("S1_JUDGE_FLOW", "")
RESULT_LAYER = "# Selected-leader result normalization"


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


def flow_actions(ws: str) -> dict[str, dict]:
    """The flow's own actions by tool name: how each is sent, whether it writes, and what its contract calls a success."""
    from src.tools import sanitize_tool_name

    found = {}
    for node in json.load(open(JUDGE_FLOW or os.path.join(ws, "flow.json")))["nodes"]:
        for action in (node["data"].get("config") or {}).get("actions") or []:
            name = action.get("code_name") or action.get("http_tool_name") or action.get("name") or ""
            contract = action.get("leader_contract") or {}
            found[sanitize_tool_name(name)] = {"transport": TRANSPORT.get(action.get("action_type"), "other"),
                                               "effect_kind": contract.get("effect_kind"), "success": contract.get("success"),
                                               "judged": judge_view(action.get("code_body") or "") if JUDGE_FLOW else None}
    return found


def judge_view(code_body: str):
    """The twin's result layer for one tool: given the call's arguments and main's raw result, the result the judge knows."""
    if RESULT_LAYER not in code_body:
        return None
    scope: dict = {}
    exec(code_body, scope)  # the lane's own flow file; this only defines functions, nothing is sent

    def view(arguments: dict, raw: dict) -> dict:
        import judge_lane

        scope["_leader_original_main"] = lambda **_: raw
        born = judge_lane._date((arguments or {}).get("date_of_birth"))  # the twin's layer takes this one date in ISO form
        try:
            return scope["main"](**{**(arguments or {}), **({"date_of_birth": born.isoformat()} if born else {})})
        except Exception as exc:
            return {"status": "unknown", "judge_view_error": type(exc).__name__}

    return view


def status_of(output, result, success) -> str:
    """The lane's status word for a tool that ran: a tool error or a result its contract does not call a success is REJECTED."""
    if output is None or output.is_error:
        return "REJECTED"
    if isinstance(success, dict) and "path" in success:
        at = result
        for key in success["path"]:
            at = at.get(key) if isinstance(at, dict) else None
        return "SUCCEEDED" if at == success.get("value") else "REJECTED"
    # an HTTP action with no such rule: the engine's transport calls a body that says it failed a rejection
    refused = isinstance(result, dict) and (result.get("success") is False or result.get("ok") is False or "error" in result)
    return "REJECTED" if refused else "SUCCEEDED"


def hooks(ws: str) -> None:
    from livekit.agents import AgentSession, llm

    from src import system_one

    actions = flow_actions(ws)
    rec("log", msg="jev.preflight ok=True note=the small version has no start check; this row only says the run started")
    ask = system_one.ask_jev

    async def traced_ask(state, questions):
        row = rec("jev", state_chars=len(state or ""),
                  heads={h: sorted((q.get("criteria") or {}).keys()) for h, q in questions.items()})
        if os.environ.get("S1_DUMP_ASKS"):  # the whole request, so one ask can be put to Jev again with other option texts
            row.update(state=state, questions=questions)
        t = time.time()
        try:
            answers = await ask(state, questions)
            floors = {"step": system_one.STEP_FLOOR}
            row["picks"] = {h: {"choice": system_one.sure_pick(a, floors.get(h, system_one.SURE_FLOOR)) or "unsure",
                                "confidence": round(max(a.values(), default=0.0), 3)} for h, a in answers.items()}
            row["probs"] = {h: {o: round(p, 3) for o, p in a.items() if p >= 0.01} for h, a in answers.items()}
            row["invalid"] = sorted(set(questions) - set(answers))
            return answers
        except Exception as exc:
            row["error"] = type(exc).__name__
            raise
        finally:
            row["ms"] = round((time.time() - t) * 1000)

    system_one.ask_jev = traced_ask

    if os.environ.get("S1_DUMP_ASKS"):  # every piece of model text main's speech cut is fed, to read a reply that was cut whole
        from src import cx_agent

        feed = cx_agent._SpeechCut.feed

        def seen_feed(self, piece):
            kept = feed(self, piece)
            rec("fed", piece=str(piece)[:400], kept=str(kept or "")[:400])
            return kept

        cx_agent._SpeechCut.feed = seen_feed

    lead = system_one.SystemOneLLM.lead
    entries = list(system_one.ENTRIES.values()) if hasattr(system_one, "ENTRIES") else system_one.ANSWERS["entries"]
    said_by_text = {entry[key]: entry["id"] for entry in entries for key in ("answer_en", "answer_hi")}

    async def traced_lead(self, chat_ctx, tools, tool_choice):
        out = await lead(self, chat_ctx, tools, tool_choice)
        if os.environ.get("S1_DUMP_ASKS"):  # what the request offered and what the lead let the model do
            notes = [item.text_content for item in out.chat_ctx.items[-4:] if getattr(item, "role", None) == "system"]
            rec("lead", offered=sorted(llm.ToolContext(tools).function_tools), choice=str(tool_choice),
                kept=sorted(llm.ToolContext(out.tools).function_tools), kept_choice=str(out.tool_choice),
                passing=sorted(out.passing) if out.passing is not None else None, say_first=out.say_first, fire=out.fire,
                insist=out.insist, notes=[str(note)[:300] for note in notes])
        if out.say_first:
            caller_turns = sum(1 for e in TRACE if e["kind"] == "line" and e["role"] == "caller")
            turn = getattr(self, "_turn", None)  # the approved-questions build records the answer on the caller turn
            if hasattr(system_one, "fixed_answers"):
                answers, _ = system_one.fixed_answers(self.node, chat_ctx)
                entry = next((key for key, text in answers.items() if text == out.say_first), None) or said_by_text.get(out.say_first, "?")
            else:
                entry = getattr(turn, "said", "") or "?"
            rec("log", msg=f"jev.sensitive entry={entry} turn={caller_turns}")
        return out

    system_one.SystemOneLLM.lead = traced_lead

    led_run, in_flight = system_one._LedStream._run, [0]

    async def counted_run(self):
        in_flight[0] += 1
        try:
            return await led_run(self)
        finally:
            in_flight[0] -= 1

    system_one._LedStream._run = counted_run

    if os.environ.get("S1_DUMP_ASKS"):  # what the node's model wrote back on each led request, after Jev's filter
        relay = system_one._LedStream._relay

        async def traced_relay(self, led, tool_choice, *, words=True):
            send, text, calls = self._event_ch.send_nowait, [], []

            def kept(chunk):
                if chunk.delta:
                    text.append(chunk.delta.content or "")
                    calls.extend(f"{call.name}({call.arguments})" for call in chunk.delta.tool_calls or [])
                return send(chunk)

            self._event_ch.send_nowait = kept
            try:
                return await relay(self, led, tool_choice, words=words)
            finally:
                self._event_ch.send_nowait = send
                rec("model", choice=str(tool_choice), text="".join(text)[:500], calls=[call[:300] for call in calls])

        system_one._LedStream._relay = traced_relay

    init = AgentSession.__init__

    def traced_init(self, *args, **kwargs):
        init(self, *args, **kwargs)

        def added(ev):
            item = ev.item
            text = getattr(item, "text_content", None) or ""
            if getattr(item, "role", "") in ("user", "assistant") and text.strip():
                rec("line", role="caller" if item.role == "user" else "agent", text=text,
                    interrupted=bool(getattr(item, "interrupted", False)))

        def ran(ev):
            for call, output in ev.zipped():
                about = actions.get(call.name)
                if about is None:  # collectors, exits and holds are main's own steps, not the flow's tools
                    rec("step", name=call.name, arguments=(call.arguments or "")[:600],
                        result=str(getattr(output, "output", ""))[:600], error=bool(getattr(output, "is_error", False)))
                    continue
                try:
                    arguments = json.loads(call.arguments or "{}")
                except ValueError:
                    arguments = None
                text = str(getattr(output, "output", "") or "")
                try:
                    result = json.loads(text)
                except ValueError:
                    result = {"text": text}
                raw = result
                if about["judged"] is not None and not getattr(output, "is_error", False):
                    result = about["judged"](arguments, raw)
                rec("tool", action=call.name, effect_kind=about["effect_kind"], transport=about["transport"],
                    arguments=arguments, status=status_of(output, result, about["success"]),
                    result=json.dumps(result, default=str)[:3000],
                    **({"raw": json.dumps(raw, default=str)[:1500]} if result is not raw else {}))

        self.on("conversation_item_added", added)
        self.on("function_tools_executed", ran)

    AgentSession.__init__ = traced_init

    class Capture(logging.Handler):
        def emit(self, record):
            try:
                msg = record.getMessage()
            except Exception:
                return
            if msg.startswith("system_one: Jev did not lead"):
                rec("log", msg="jev.fault_recorded " + msg[:600])
            elif msg.startswith("system_one:"):
                rec("log", msg="s1." + msg[len("system_one:"):].strip()[:20000])

    handler = Capture(level=logging.INFO)
    for name in ("cx-agent-runner", "cx-agent-runner.event", ""):
        logging.getLogger(name).addHandler(handler)

    import yaml

    from src.simulation import run_store
    from src.simulation.context import get_simulation_context
    from src.simulation.runner import SimSession
    from src.tools import action_handler
    from src.utils import http_pool

    async def scenario_envs(auth_id, **_):  # main now also passes the names the code reads
        # a real custom-code tool would ask PlivoCX for its app variables; a simulation has only the scenario's
        return dict(getattr(get_simulation_context(), "action_envs", None) or {})

    action_handler.get_variables_as_envs = scenario_envs

    params = (yaml.safe_load(open(os.path.join(ws, "params.yaml"))) or {}).get("params") or {}
    start = SimSession.start
    cold = True

    async def seeded_start(self):
        nonlocal cold
        if cold:  # the sim CLI runs no warmer, so a lane process would pay every first connection on its first call
            cold = False
            await http_pool.warm_all()
        node = next((n for n in self.graph.nodes_by_id.values() if n.type == "start"), None)
        if node is not None and node.id not in self.variables:
            self.variables[node.id] = {"http": {"params": {k: str(v) for k, v in params.items()}}}
            rec("seed", start_node=node.id, keys=sorted(params))
        return await start(self)

    SimSession.start = seeded_start

    turn = SimSession.turn

    async def heard_turn(self, req):
        # main's sim reports one speech segment per turn; the caller heard every line the agent said in it
        before = {item.id for item in self.session.history.items} if self.session is not None else set()
        resp = await turn(self, req)
        items = self.session.history.items if self.session is not None else []
        said = [item.text_content for item in items
                if item.id not in before and getattr(item, "role", "") == "assistant" and item.text_content]
        if said:
            resp.message = "\n".join(said)
        return resp

    SimSession.turn = heard_turn

    from src.simulation import runner as sim_runner

    reconcile = sim_runner.reconcile_scribe_history

    def busy(session) -> bool:
        """Whether the agent's turn is still going: a request, a tool, a line or a change of floor is in flight."""
        activity = getattr(session, "_activity", None)
        if in_flight[0] > 0 or activity is None or getattr(session, "_next_activity", None) is not None:
            return True
        agent = getattr(activity, "agent", None)
        finished = callable(getattr(agent, "done", None)) and agent.done()  # a collector that is done still holds the floor for a moment
        return bool(finished or getattr(activity, "scheduling_paused", False) or activity._current_speech is not None
                    or activity._speech_q or activity._speech_tasks)

    async def settled_reconcile(state):
        # main's sim serializes a CXAgent span when run() resolves. A step taken after a collector finished (the next
        # action, the next collector's question) is still in flight then, so the caller would answer a stale line.
        sim, quiet, deadline = get_simulation_context(), 0, time.time() + 30
        while sim is not None and not sim.flow_session and sim.session is not None and quiet < 6 and time.time() < deadline:
            quiet = 0 if busy(sim.session) else quiet + 1
            await asyncio.sleep(0.05)
        if sim is not None and quiet < 6 and not sim.flow_session:
            rec("settle_timeout")
        return await reconcile(state)

    sim_runner.reconcile_scribe_history = settled_reconcile

    import src.simulation.cli.engine as engine

    sim_turn = engine.ScenarioRun._sim_turn

    async def spanning_turn(self, user_message, action_mocks, **kwargs):
        sim = self.sim
        if sim.flow_session and not getattr(self, "opened", False):
            self.opened = True
            hello = rec("line", role="caller", text=user_message, interrupted=False) if self.scenario.turns is None else None
            # a screening step waits for the callee and then opens; a text line sent before that lands on its silent coordinator
            deadline = time.time() + 20
            while not run_store._capture_opener(sim) and time.time() < deadline:
                await asyncio.sleep(0.1)
            await sim._drain_pending_speech()
            if hello is not None:
                # the opener is the answer to the callee's hello, as in main's run store; a second reply to it is a text-sim artifact
                first = next(i for i, row in enumerate(TRACE) if row["kind"] == "line")
                if TRACE[first] is not hello:
                    TRACE.remove(hello)
                    TRACE.insert(first, {**hello, "t": TRACE[first]["t"]})
                return run_store._opener_response(sim)
        resp = await sim_turn(self, user_message, action_mocks, **kwargs)
        sim = self.sim
        await run_store._fold_late_exit(sim, resp)  # a task unit can finish its exit just after its turn is serialized
        landing = sim.graph.nodes_by_id.get(sim.node_uuid)
        if sim.flow_session and sim.flow_ended and not sim.ended and landing is not None:
            # a task-unit span exited to a node the CLI does not walk into: start the next span as main's run store does
            flow_session = run_store.is_task_unit(landing)
            span = SimSession(
                phlo_run_uuid=sim.phlo_run_uuid, auth_id=sim.auth_id, node_uuid=landing.id, node_run_uuid=sim.node_run_uuid,
                graph=sim.graph, world_state=sim.world_state, max_turns=sim.max_turns, turn_count=sim.turn_count,
                action_mocks=sim.action_mocks, real_actions=sim.real_actions, action_envs=sim.action_envs, kb_mock=sim.kb_mock,
                variables=sim.variables, context_items=sim.context_items, flow_session=flow_session,
                raw_message_recovery=flow_session)
            await sim.end()
            await run_store._start_span(span)
            self.sim, self.flow_session = span, flow_session
            rec("span", to=landing.id, node_type=landing.type, flow_session=flow_session)
            if flow_session:
                resp.message = run_store._capture_opener(span)
            if resp.node_uuid != landing.id and landing.id in self.bundle.agent_configs:
                self._pending_transitions.append({"from": self.bundle.name_of(self.node_id), "to": self.bundle.name_of(landing.id)})
                self.node_id = landing.id
                self.result["nodes_visited"].append(self.bundle.name_of(landing.id))
            if not flow_session:
                # an AI node greets on entry on a live call; main's run store draws that with an empty caller line
                opener = await sim_turn(self, "", action_mocks)
                resp.message, resp.tool_calls = opener.message, resp.tool_calls + opener.tool_calls
                resp.ended, resp.stop_reason, resp.intent = opener.ended, opener.stop_reason, opener.intent or resp.intent
        return resp

    engine.ScenarioRun._sim_turn = spanning_turn

    from src.tools import intent_handler

    legacy_exit = intent_handler._handle_intent_legacy

    async def spoken_exit(context, intent):
        # a live call takes every exit through the flow-session handler, which says the exit's saved line before it
        # leaves; main's text sim takes a V2.9 span through the legacy handler, which does not
        speech = intent.intent_speech
        if speech and speech.speech_enabled and speech.intent_speech_text:
            try:
                async with asyncio.timeout(10):
                    await context.session.say(speech.intent_speech_text, allow_interruptions=False)
            except Exception as exc:
                rec("exit_line_failed", intent=intent.intent_name, error=type(exc).__name__)
        return await legacy_exit(context, intent)

    intent_handler._handle_intent_legacy = spoken_exit

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
    types = {node["data"]["config"].get("name"): node["type"] for node in json.load(open(os.path.join(a.ws, "flow.json")))["nodes"]}
    on_v29 = any(types.get(name) == "ai_agent_v29" for name in (run or {}).get("nodes_visited") or [])
    lane_validity = judge_lane.validity

    def validity(trace, run, meter_log):
        # main gives a screening step its own model, so a call that never reaches a V2.9 node has no Gemma request to prove
        why, proof = lane_validity(trace, run, meter_log)
        return [reason for reason in why if on_v29 or not reason.startswith("Gemma not proven")], {**proof, "reached_v29": on_v29}

    judge_lane.validity = validity
    verdict = asyncio.run(judge_lane.judge(trace, run, json.load(open(a.spec)), a.out))
    json.dump(verdict, open(os.path.join(a.out, "judge.json"), "w"), indent=1, default=str)
    print(f"LANE VERDICT {verdict['verdict']} score={verdict.get('score')} checks_failed={verdict.get('checks_failed')} "
          f"invalid={verdict.get('invalid_reasons')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
