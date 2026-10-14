# The test bench: try a wording or a code change without a phone call

Everything here runs against the local stack's agent container (`v210-agent-runner`). Nothing is dialled. Nothing in git changes.
Python on the laptop is 3.9: put `from __future__ import annotations` at the top of a script that uses `X | None`.

```python
import sys
sys.path.insert(0, "/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.10/fixes-2026-10-11/wording")
import lab
```

## 1. Ask Jev again about a real turn, with other words (seconds)

Jev is the classifier that leads each request. A request is `{"state": <the call so far, as text>, "questions": {name: {"type": "choice",
"instructions": ..., "criteria": {option: text}}}}` and the answer is one share per option. Jev answers each question on its own, so you
can change one question's text and read only that question.

```python
answers = lab.ask({"today": request, "mine": changed_request}, times=5)   # {"today": [ {question: {option: share}}, ... 5 runs ], ...}
lab.mean(answers["mine"], "step_intent")                                  # the average shares, largest first
lab.sure(answers["mine"], "step_intent", 0.45, 0.1)                       # how many runs were sure of each option ("" = not sure)
```

The bars the engine uses: the reading (`step_intent`) is sure at 0.45 with a 0.1 lead; at a read-back a yes (`confirms_its_right`) or a
correction (`gives_a_correction`) needs 0.6 with a 0.15 lead; the step answer (`step`) is sure at 0.5 with a 0.15 lead and "likely" from
0.15; `repair_target` is sure at 0.35 with a 0.05 lead (a sure "none" hides the change step); a screening status needs 0.65 with 0.15.
Jev's answers move by 0.05 to 0.15 from run to run on a close call: never judge on one run, use 3 to 5.

Real requests are kept by a scratch engine (next section). `lab.kept(folder)` returns them:
`{"run", "kind", "values", "caller_line", "fresh", "state", "questions", "shares"}`. `fresh` is True on the first request of a caller turn,
the one that carries the questions about the caller's words. `lab.heard(row)` is the caller's last line as Jev saw it.

- `lab.reading(kind, values, heard, changes)` rebuilds the reading question exactly as the engine does (`step_question`), with library
  changes laid over it: `[{"kind": "collect:text", "intent": "gives_full_value", "new": "..."}, {"kind": "readback", "intent": "template", "new": "..."}]`.
  With `changes=[]` it equals what the engine sent (checked).
- `lab.reworded(row, {"texts": [{"old": ..., "new": ...}], "library": [...]}, caller="other words", agent="other agent line")` gives the same
  request with another caller line (and agent line). A swapped line keeps the engine's notes of the ORIGINAL line (for example the
  "# Date Hints" note worked out from the caller's words): strip or redo such notes, or better, get a real request for the new line by
  running it as a scripted call. Results on real requests count; results on swapped requests are only a hint.
- The step question's options are the tools' own descriptions as the engine sent them (`row["questions"]["step"]["criteria"]`), its
  instructions are `src/prompts/system_one.json` key `step`. `repair_target` comes from `src/prompts/jev/core-decide.json`.

Worked examples: `f_try.py`, `f_lines.py`, `f_round2.py` (problem F), `a_try.py` (problem A), `identity_languages.py` (problem C in 18 languages).

## 2. Run a scripted text call on your own copy of the engine (about a minute each)

```python
lab.engine("myname")                                           # /tmp/engine-myname in the container = commit 917ceca79, keeps every Jev request
lab.engine("myname", patch="/abs/my.diff")                     # ... with a unified diff applied (git apply, paths like src/system_one.py)
lab.engine("myname", overlay="/abs/overlay")                   # ... with whole files laid over it (overlay/src/prompts/jev/steps.json ...)
lab.engine("before", commit="24755e55a")                       # the engine before tonight's eight fixes
folder = lab.scripted("myname", {"X1": ("logic-flow", "05-", "Account Check", ["Hello?", "The twenty-second of May, nineteen eighty-two.", ...])}, times=5)
```

- A call is `(suite, start of the caller's folder name, step to start on, the caller's lines)`. Suites: `logic-flow` (the Stress Test flow)
  and `rapido-flow` (the two-language flow). The caller's folder gives the flow and its settings: `../../<suite>/out/sim/<NN>-<slug>/`.
  Step names are the flow's own (`spec.py`: for the Stress Test flow Account Check, Payment, Book Visit, Site Details, Contact Details;
  for the two-language flow Screen Captain, Captain Reactivation). A line that is `None` is a silence up to the check-in.
  The simulator cannot cross from a screening step into an AI step, so start on the AI step the fault happens in, or on Account Check.
- The folder holds `<label>-<n>.log` (the simulator's own printout: `USER :`, `AGENT:`, `TOOL : name({...})`, and the engine's log lines
  with `system_one: step=...`, `system_one: dropped ...`, `ToolError ...`) and `<label>-<n>.jev.jsonl` (every Jev request of that run).
  `text_evals.calls(log)`, `turns(log)`, `said(log, turn)`, `ran(log, tool, holds)`, `dropped(log)` read a log.
- A scripted caller says its lines in order whatever the agent says. If the agent asks something else, the run is off script: check
  what was really asked before you count it. Text does not show every voice fault (speech-to-text, silence and barge-in are not there).
- At most 3 text runs of yours go at once and 8 on the whole laptop; the bench queues the rest. A run is stopped after 5 minutes.
- Actions in these flows are real calls to a local sandbox. That is fine.

## 3. Rules

- Use your own engine name and your own scratch folder. Never edit `/app` in the container, the git worktrees, the flows, or the suites'
  files. Never restart or rebuild a container. Never dial, never call Hunter. Never print a key or a token; do not open `.env` files.
- A wording is tried on Jev first, on the real failing request AND on near-miss lines that must not change. Then in an engine copy.
- Report counts over at least 5 runs, before and after, and name every line that still goes wrong.
