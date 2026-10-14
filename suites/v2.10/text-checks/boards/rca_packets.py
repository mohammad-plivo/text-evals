#!/usr/bin/env python3
"""One folder per failed call of a saved board: our log and Hunter's transcript merged on one clock, the judge's words, what the caller was told.

    python3 rca_packets.py <suite folder> <out folder> <board json> [<board json> ...]
"""
import datetime, json, re, subprocess, sys
from pathlib import Path

suite, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(suite))
import hunter  # noqa: E402

cookie = hunter.cookie_from(str(suite.parent.parent / "v2.9.1-jev/.hunter-cookie"))
stack = getattr(hunter, "STACK", "v210")
logs = subprocess.run(["docker", "logs", f"{stack}-agent-runner"], capture_output=True, text=True)
engine = [line for line in (logs.stdout + logs.stderr).splitlines() if line.startswith("{")]
keep = re.compile(r"system_one|Jev did not lead|Tool call tool=|handoff|Handoff|fixed answer|collect|carried|seeded|required|ERROR|Traceback|exception|ToolError|declin|refus|REJECTED|change refused", re.I)
at = lambda text: datetime.datetime.fromisoformat(text[:26]).replace(tzinfo=datetime.timezone.utc).timestamp()   # our stamps are UTC
clock = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%H:%M:%S.%f")[:-4]

for board_file in [arg for arg in sys.argv[3:] if arg != "--all"]:
    board = json.load(open(board_file))
    for call in board["calls"]:
        if call["words"] == "pass" and not call["log"] and "--all" not in sys.argv:
            continue
        number = re.search(r"(\d\d)-", call["caller"]).group(1)
        folder = out / f"{suite.name}-{number}"
        folder.mkdir(parents=True, exist_ok=True)
        run = call.get("flow_run")
        rows = json.loads(subprocess.run(["docker", "exec", f"{stack}-postgres", "psql", "-U", "contacto_user", "-d", "contacto", "-At", "-c",
            f"SELECT json_agg(log_data ORDER BY id) FROM conversation_run_logs WHERE flow_run_uuid = '{run}'"], capture_output=True, text=True).stdout or "[]") if run else []
        events = []
        for r in rows or []:
            t, kind, ty = at(r["timestamp"]), r.get("event_name"), r.get("type")
            if kind == "NODE_EXECUTED":
                events.append((t, f"NODE     {r.get('previous_node')} -> {r.get('current_node')}  (way out: {r.get('chosen_path')})"))
            elif ty in ("USER_STARTED_SPEAKING", "USER_STOPPED_SPEAKING", "BOT_STARTED_SPEAKING", "BOT_STOPPED_SPEAKING"):
                events.append((t, "  " + ty.lower().replace("_", " ")))
            elif ty == "TOOL_CALL_EVENT":
                events.append((t, f"TOOL     {r.get('tool_name')} {json.dumps(r.get('tool_input'), ensure_ascii=False)[:300]} -> {str(r.get('tool_response'))[:300]}"))
            elif ty == "text" and (r.get("text") or "").strip():
                events.append((t, ("CALLER (as our speech-to-text heard it)   " if r.get("sender") == "user" else "AGENT    ") + " ".join(r["text"].split())))
            elif ty == "text" and (r.get("node_config") or {}).get("variables"):
                events.append((t, "saved    " + json.dumps(r["node_config"]["variables"], ensure_ascii=False)[:300]))
        for line in engine:
            if run and run in line:
                try:
                    doc = json.loads(line)
                except ValueError:
                    continue
                message = doc.get("message", "")
                if keep.search(message) and not message.startswith(("Agent system prompt", "LLM HTTP timing", "created citadel log", "STT metrics", "LLM metrics", "TTS metrics", "HTTP POST", "metrics_collected", "Failed to bill", "EOU metrics", "VAD metrics")):
                    events.append((at(doc["timestamp"].replace("+00:00", "")), "    engine: " + " ".join(message.split())[:900]))
        remote = hunter.dev.req("GET", f"/api/calls/{call['call']}", cookie)
        for turn in remote.get("transcript") or []:
            who = "HUNTER: its caller said        " if turn.get("speaker") == "assistant" else "HUNTER: it heard our agent say "
            events.append((float(turn["timestamp"]), who + " ".join(str(turn.get("text") or "").split())))
        events.sort(key=lambda item: item[0])
        (folder / "timeline.txt").write_text("\n".join(f"{clock(t)} {text}" for t, text in events) + "\n")
        (folder / "judge.txt").write_text(
            f"CALLER: {call['caller']}\nRESULT: words {call['words']}, our log check: {call['log'] or 'pass'}\nSECONDS: {call['seconds']}\n\n"
            f"JUDGE COMMENT:\n{remote.get('comments')}\n\nJUDGE, EVERY CRITERION:\n" + "\n".join((remote.get("eval_breakdown") or {}).get("criteria") or []) +
            f"\n\nFAILURE TAGS: {remote.get('failure_tags')}\n\nWHAT THE CALLER WAS TOLD (Hunter's persona prompt):\n{remote.get('conversation_prompt')}\n\n"
            f"WHAT THE JUDGE WAS TOLD:\n{remote.get('evaluation_prompt')}\n")
        print(folder.name, len(events), "lines,", call["seconds"], "s, words", call["words"], "| log", "pass" if not call["log"] else "FAIL")
