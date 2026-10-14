"""One board from one launch. The launch manifest is the authority for what was attempted, the
audited judge grades the observed transcript, and Python gates the structure the rubric cannot see:
the declared exit route, one clean close, and the scenario's declared callback variables.

Score is Hunter's: the MINIMUM criterion accuracy, an integer 0 through 100, at the scenario's own
threshold. A run that did not reach its declared end node FAILs whatever the rubric said.

Usage: uv run --frozen python Sigma/hunter-sim/board.py <worktree> <launch-manifest.json> <out-name>
       [--env-file f] [--deployment gpt-4.1] [--reuse-judged]
Writes Sigma/hunter-sim/boards/<out-name>.manifest.json, .judged.json and .md. Exits 1 unless the
board is clean: every attempt accounted for, every run routed, every declared variable matched.
"""
import re
import hashlib, json, os, subprocess, sys

WT, LAUNCH_PATH, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
ENV = sys.argv[sys.argv.index("--env-file") + 1] if "--env-file" in sys.argv else ""
DEP = sys.argv[sys.argv.index("--deployment") + 1] if "--deployment" in sys.argv else "gpt-4.1"
REUSE = "--reuse-judged" in sys.argv  # grade an already written .judged.json, for offline checks
ROOT = os.path.join(WT, "eval_tests", "sigma_v29_hunter")
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "boards"); os.makedirs(OUT, exist_ok=True)
SCENARIOS = os.path.join(os.path.dirname(HERE), "hunter", "scenarios")
# build.py writes each expected exit as "<stage>:<handle>"; these are the two stages of the dev flow
STAGE = {"screening": "c2e8bf31-06ec-42db-8a60-a72874b1ceb5", "agent": "f66906be-0fc9-43e5-bcf7-20117357082c"}
TERMINALS = {"end_conversation", "call_forward", "queue_and_route"}
if ENV:
    for line in open(ENV):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))


def flow_index(ws):
    """Node name and type by id, and edge target by (source, handle), from the workspace's own flow."""
    flow = json.load(open(os.path.join(ROOT, ws, "flow.json")))
    nodes = {n["id"]: ((n.get("data", {}).get("meta") or {}).get("name") or n["id"], n.get("type")) for n in flow["nodes"]}
    edges = {(e["source"], e.get("sourceHandle")): e["target"] for e in flow.get("edges") or []}
    return nodes, edges


def reachable(edges, start):
    seen, queue = {start}, [start]
    while queue:
        cur = queue.pop()
        for (src, _), target in edges.items():
            if src == cur and target not in seen:
                seen.add(target); queue.append(target)
    return seen


def expectations(ws, h):
    """The scenario's declared exits and callback variables, plus a reason they cannot be trusted.

    The converter keeps only the scenario's name in hunter.json, so fall back to the authored file
    and refuse to grade against a source that has changed since the workspace was written.
    """
    block, payload = h.get("_expected_variables"), h.get("payload")
    if block is None or payload is None:
        path = os.path.join(SCENARIOS, h.get("source") or "")
        if not os.path.exists(path):
            return [], {}, f"authored scenario {h.get('source')!r} not found beside the board"
        raw = open(path, "rb").read()
        if h.get("source_sha256") and hashlib.sha256(raw).hexdigest() != h["source_sha256"]:
            return [], {}, f"{h['source']} changed since this workspace was converted"
        doc = json.loads(raw)
        block, payload = doc.get("_expected_variables") or {}, doc.get("payload") or {}
    return list((block or {}).get("_exits") or []), dict((payload or {}).get("expectedCallbackVariables") or {}), ""


NON_SPEECH = re.compile(r"</?[a-z_][\w.:-]*(?:\s[^>\n]*)?/?>|\b[a-z]+_[a-z_]+\b")  # a tag, or a snake_case name


def route_check(run, ws, h, exits):
    """Did the run reach a declared exit, close exactly once, and never fall off the graph?"""
    turns = run.get("turns") or []
    nodes, edges = flow_index(ws)
    for i, t in enumerate(turns, 1):
        if t.get("stop_reason") == "no_matching_handoff":
            return "FAIL", f"no_matching_handoff at turn {i} on intent {t.get('intent') or 'none'}"
    closed = [i for i, t in enumerate(turns) if t.get("ended")]
    if len(closed) > 1 or (closed and closed[-1] != len(turns) - 1):
        return "FAIL", f"closed {len(closed)} times, last close at turn {closed[-1] + 1} of {len(turns)}"
    # Anything that is not speech in an agent line fails the run: a tag block or a variable name. The
    # 2026-09-21 Hunter board read "notice underscore period ... slash instructions" aloud on 5 calls;
    # the text boards had carried 26 and 49 such lines and nobody looked, because the sim does not speak.
    for i, t in enumerate(turns, 1):
        spoken = str(t.get("agent") or "")
        m = NON_SPEECH.search(spoken)
        if m:
            return "FAIL", f"spoke non-speech at turn {i}: {m.group(0)[:40]!r}"
    live = reachable(edges, h.get("entry_node") or STAGE["agent"])
    declared = [e for e in exits if STAGE.get(e.split(":", 1)[0]) in live]
    if not declared:
        return "INCOMPLETE", f"no exit reachable from the entry node is declared (authored: {exits or 'none'})"
    wanted, hops = [], []
    for e in declared:
        stage, handle = e.split(":", 1)
        target = edges.get((STAGE[stage], handle))
        if target is None:
            return "FAIL", f"the flow has no {handle!r} edge on the {stage} node"
        (wanted if nodes[target][1] in TERMINALS else hops).append((nodes[STAGE[stage]][0], handle, nodes[target][0]))
    for node, handle, target in hops:
        if {"from": node, "to": target} not in [x for t in turns for x in (t.get("transitions") or [])]:
            return "FAIL", f"never transitioned {node} -> {target} on {handle!r}"
    if not wanted:  # every declared exit lands on another node, so the hops above are the whole route
        return "OK", f"reached {', '.join(x for _, x, _ in hops)}"
    if not closed:
        return "FAIL", f"never closed; expected {' or '.join(x for _, _, x in wanted)}"
    last = turns[closed[-1]]
    for node, handle, target in wanted:
        if last.get("node") == node and last.get("intent") == handle:
            return "OK", f"{handle} -> {target}"
    return "FAIL", (f"ended at {last.get('node')!r} on intent {last.get('intent') or 'none'} "
                    f"({last.get('stop_reason') or 'no stop_reason'}), expected {' or '.join(x for _, x, _ in wanted)}")


def variable_check(run, want):
    """The declared callback variables against what the run actually recorded, per variable."""
    got = {k: v for k, v in (run.get("variables") or {}).items() if k != "http"}
    matched, wrong, missing = [], [], []
    for key, expected in want.items():
        actual = got.get(key)
        if actual in (None, ""):
            missing.append(key)
        elif str(actual).strip().casefold() == str(expected).strip().casefold():
            matched.append(key)
        else:
            wrong.append(f"{key}={actual!r} want {expected!r}")
    if not want:
        return "-", "no callback variables declared"
    if wrong:
        return "FAIL", f"{len(matched)} matched, mismatched: {'; '.join(wrong)}"
    if missing:
        return "INCOMPLETE", f"{len(matched)} matched, never recorded: {', '.join(missing)}"
    return "OK", f"{len(matched)} matched"


def accuracy(criterion, where):
    """The judge's one contract: an integer 0 through 100. Anything else is an error, not a guess."""
    if criterion["status"] != "MET":
        return 0.0  # Hunter fails a call on any NOT MET, so status outranks a contradictory number
    value = criterion.get("accuracy")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise SystemExit(f"{where} criterion {criterion.get('id')}: accuracy {value!r} is not an integer 0-100")
    return value / 100


launch = json.load(open(LAUNCH_PATH)) if LAUNCH_PATH.endswith(".json") else None
if not isinstance(launch, dict) or "reports" not in launch:
    raise SystemExit(f"{LAUNCH_PATH} is not a run_all.py launch manifest; a board is one launch, never the reports since a time")
REPEAT = int(launch.get("repeat") or 0)
EXIT_OF = launch.get("exit") or {}
attempted = sorted(launch.get("selected") or (set(launch["reports"]) | set(EXIT_OF)))
entries, unreported = [], []
for slug in attempted:
    reps = [p for p in (launch["reports"].get(slug) or []) if not p.endswith(".judged.json")]
    if reps:
        entries.append({"workspace": slug, "report": reps[-1]})
    else:
        unreported.append((slug, f"no report, child exit {EXIT_OF.get(slug, 'not recorded')}"))
stray = sorted(set(launch["reports"]) - set(attempted))
SINCE = (f"launch {launch['launch']} at {launch['worktree_head'][:8]}"
         f"{' (dirty src)' if launch.get('worktree_dirty') else ''}, repeat {REPEAT}")

manifest = os.path.join(OUT, f"{NAME}.manifest.json"); judged = os.path.join(OUT, f"{NAME}.judged.json")
json.dump({"reports": entries, "since": SINCE, "launch": LAUNCH_PATH, "attempted": attempted,
           "unreported": unreported, "stray": stray}, open(manifest, "w"), indent=1)
if not REUSE:
    if os.path.exists(judged): os.remove(judged)
    subprocess.run([sys.executable, os.path.join(HERE, "audited", "judge.py"), WT, ROOT, manifest, judged,
                    "--deployment", DEP], check=True)

sys.path.insert(0, HERE)
from audited.judge import gradable  # noqa: E402  the board and the judge must agree on what counts

data = json.load(open(judged)); rows = []; counts = {"PASS": 0, "FAIL": 0, "INCOMPLETE": 0}
ungraded = 0; repairs = []; broken = []
REPORT_OF = {e["workspace"]: e["report"] for e in entries}
for rep in data["reports"]:
    ws = rep["workspace"]
    if ws not in REPORT_OF:  # a judged file from another launch grades runs this board never attempted
        broken.append(f"{ws}: judged but not attempted by this launch"); continue
    h = json.load(open(os.path.join(ROOT, ws, "hunter.json"))); thr = float(h.get("evaluationThreshold", 0.8))
    exits, want_vars, stale = expectations(ws, h)
    # the judge keeps verdicts only; turns and variables are structural facts, read from the report
    observed = {x.get("run"): x for x in json.load(open(os.path.join(ROOT, REPORT_OF[ws])))}
    for r in h.get("repairs", ["not recorded by the converter run that wrote this workspace"]) or []:
        if r not in repairs: repairs.append(r)  # the graded flow is not the deployed flow; say so on the board
    attempt = []
    if EXIT_OF.get(ws, 0) != 0: attempt.append(f"child exit {EXIT_OF.get(ws)}")
    if REPEAT and len(rep["runs"]) != REPEAT: attempt.append(f"{len(rep['runs'])} of {REPEAT} repeats")
    if attempt: broken.append(f"{ws}: {', '.join(attempt)}")
    for run in rep["runs"]:
        where = f"{ws} run {run.get('run')}"
        app = gradable(run["criteria"]); ungraded += len(run.get("ungraded_ids") or [])
        met = sum(c["status"] == "MET" for c in app)
        score = min((accuracy(c, where) for c in app), default=0.0)
        rubric = "PASS" if app and score >= thr else ("INCOMPLETE" if not app else "FAIL")
        actual = observed.get(run.get("run"))
        blind = stale or ("" if actual else "the judged run has no entry in its own report")
        route, route_why = ("INCOMPLETE", blind) if blind else route_check(actual, ws, h, exits)
        variables, var_why = ("INCOMPLETE", blind) if blind else variable_check(actual, want_vars)
        worst = next((f"{c['id']}: {c['evidence'][:90]}" for c in app if accuracy(c, where) < thr), "no gradable criterion")
        states = ((rubric, worst), (route, route_why), (variables, var_why))
        verdict = ("FAIL" if "FAIL" in [s for s, _ in states] else
                   "INCOMPLETE" if attempt or "INCOMPLETE" in [s for s, _ in states] else "PASS")
        counts[verdict] += 1
        why = (next((w for s, w in states if s == "FAIL"), "") or next((w for s, w in states if s == "INCOMPLETE"), "")
               or "; ".join(attempt) or route_why)
        rows.append((h["name"], run.get("run"), met, len(app), score, rubric, route, variables, verdict, why))

graded = {rep["workspace"] for rep in data["reports"]}
for slug in attempted:  # every attempt gets a row, whether it reported, stalled or went ungraded
    if slug in graded: continue
    counts["INCOMPLETE"] += 1
    rows.append((slug, "-", 0, 0, 0.0, "INCOMPLETE", "INCOMPLETE", "INCOMPLETE", "INCOMPLETE",
                 dict(unreported).get(slug, "reported by the launch but absent from the judged file")))
# an attempt with no report is a gap in the accounting, so the line must not read clean
unreported_now = [slug for slug in attempted if slug not in graded]
blocking = [f"{len(unreported_now)} attempt(s) with no graded report: {unreported_now}"] if unreported_now else []
blocking += [f"{len(stray)} report(s) for ids the launch did not attempt: {stray}"] if stray else []
blocking += [f"attempts not reconciled: {'; '.join(broken)}"] if broken else []
if not REPEAT: blocking.append("the launch manifest records no repeat count")
if launch.get("status", "COMPLETE") != "COMPLETE":
    blocking.append(f"launch status {launch['status']}: {launch.get('stop_reason') or 'no reason recorded'}")
clean = not blocking and counts["FAIL"] == 0 and counts["INCOMPLETE"] == 0

lines = [f"# Board {NAME} ({SINCE}, judge {DEP}, observed transcript only)", "",
         f"**BOARD {'CLEAN' if clean else 'NOT CLEAN'}. PASS {counts['PASS']}, FAIL {counts['FAIL']}, "
         f"INCOMPLETE {counts['INCOMPLETE']} of {sum(counts.values())} runs over {len(attempted)} attempts "
         f"({len(entries)} reported, {len(unreported)} without a report).**", "",
         f"A run passes only on all three: Hunter's rule (min criterion accuracy >= threshold), the declared "
         f"exit route, and the declared callback variables. Criteria ungraded for contradicting their own "
         f"evidence: {ungraded}.", ""]
lines += ["Accounting: " + ("; ".join(blocking) if blocking else "attempts, reports and repeats reconcile"), "",
          "Converter repairs applied to the graded flow: " + ("; ".join(repairs) if repairs else "none"), "",
          "| # | scenario | run | met/applicable | min accuracy | rubric | route | variables | verdict | why |",
          "|---|---|---|---|---|---|---|---|---|---|"]
for i, (n, run, m, a, score, rubric, route, variables, verdict, why) in enumerate(rows, 1):
    lines.append(f"| {i} | {n.replace('Sigma v2.9 - ', '')[:58]} | {run} | {m}/{a} | {score:.2f} | "
                 f"{rubric} | {route} | {variables} | {verdict} | {why[:150]} |")
open(os.path.join(OUT, f"{NAME}.md"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
sys.exit(0 if clean else 1)
