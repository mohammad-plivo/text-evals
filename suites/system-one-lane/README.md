# Text lanes on the small System One version

How the builder session's text boards (`text-evals/text-lane`, KT in its `PEER-NOTES.md`) are run on the small
version (`s1-thin`). Nothing in `text-evals/` is edited, apart from one note in `PEER-NOTES.md`. Everything here is a
wrapper around it. The results of 2 October are in `v2.9.1-jev/SYSTEM-ONE-THINKING-TEXT-TESTS-2026-10-02.md`.

## The pieces

| File | What it does |
|---|---|
| `s1_lane.py` | The lane's `lane.py` with the tree set to `s1-thin-lane` and the run command pointed at `run_one_s1.py`. Same sub-commands and flags. Adds `--main-shaped`, `--screening-as-main`, `--switch-off` and `--screening-only`. |
| `run_one_s1.py` | One scenario in its own process. The lane's `run_one.py` with the engine hooks swapped for hooks on `src/system_one.py` and on LiveKit's session events. Same outputs (`meter.jsonl`, `trace.json`, `judge.json`), so the lane's judge reads a run unchanged. |
| `board_s1.py` | One table from a finished campaign. Runs nothing, pays nothing. |
| `compare_s1.py` | The same scenarios on several campaigns side by side (main alone, the small version, the engine). |
| `lead_stats.py` | How Jev's leading went in a campaign: split votes, silent replies, a tool's name in the agent's words, the model naming another step. |
| `replay_ask.py` | Puts one saved Jev request to Jev again with other option texts. A text repro for a wrong pick, a fraction of a cent. |
| `replay_screening.py` | Puts the screening permission step to Jev again with other call texts and other option texts. No call is simulated. Used on 3 October to show that no wording moves Jev off "only speak" after an emergency (0.84, 0.72 at best). |
| `make_fhcsd_flow.py` | Writes `flows/fhcsd-main-shaped/flow.json`: the FHCSD flow as built for main (sim-fh, dev flow b363ccd7) plus the switch on its two nodes. With `--v29-only` the switch goes on the V2.9 node only. |
| `make_example_flow.py` | Writes `flows/example-main-shaped/flow.json`: the Northwind flow with one sentence changed. |
| `lane-tree-rev.txt` | The scratch commit the lane tree is on. |
| `fhcsd-side-by-side.md` | The 48 FHCSD callers on 2 October: main alone, the small version before and after the fixes, the engine. |

`s1-thin-lane` is a detached worktree: the small version plus a lane-only simulator patch (keypad turns,
`action_envs`, a screening node's saved task block). It is a scratch commit made with git plumbing and is never
pushed. The product files in it are byte-identical to `s1-thin`; check with `cmp` before a board.

## Commands

    V="/Users/mohammad.kadiri/Documents/Plivo - Projects/Agent Runner/v2.9.1-jev"; PY="$V/s1-thin-lane/.venv/bin/python"

    # FHCSD, 48 scenarios, switch on
    cd "$V" && ONLY=$(ls text-evals/text-lane/pack | tr '\n' ' ') && "$PY" s1-thin-audit/lane/s1_lane.py run --main-shaped \
      --campaign NAME --campaign-cap 20 --run-usd 1.0 --max-parallel 4 --timeout 540 --only ${=ONLY}

    # the same flow with the switch off: main alone, the baseline
    ... s1_lane.py run --switch-off --campaign NAME-off ...

    # callers that end inside screening, at any hour: add --screening-only (it waives the clinic-day checks)
    ... s1_lane.py run --main-shaped --screening-only --campaign NAME --only L-screening-emergency ...

    # the switch on the V2.9 node only: screening runs as on main
    ... s1_lane.py run --screening-as-main --campaign NAME-v29only ...

    # Example flow
    ... s1_lane.py run --flow-ws s1-thin-audit/lane/flows/example-main-shaped --pack text-evals/example-flow/pack \
      --campaign NAME --campaign-cap 16 --run-usd 1.2 --max-parallel 4 --timeout 900 --only ...

    # tables
    "$PY" s1-thin-audit/lane/board_s1.py text-evals/text-lane/runs/NAME --engine text-evals/text-lane/runs/s1t-cx-fhcsd
    "$PY" s1-thin-audit/lane/board_s1.py text-evals/text-lane/runs/NAME-off --switch-off
    "$PY" s1-thin-audit/lane/compare_s1.py --off text-evals/text-lane/runs/NAME-off --on "small version=text-evals/text-lane/runs/NAME"
    "$PY" s1-thin-audit/lane/lead_stats.py text-evals/text-lane/runs/NAME

A canary of one scenario first, every time. A happy FHCSD call costs about 20 cents, a screening-only call about 4.
One pass of the 48 costs about 6.50 dollars and takes about 15 minutes at four in parallel.

To stop a board early, do not kill it: reserve the rest of its campaign cap with `meter.reserve(campaign, label, usd,
cap)`. The lane then starts no new run, the runs in flight settle, and the hold is settled at 0 afterwards.

`S1_DUMP_ASKS=1` stores every Jev request whole in the run's `trace.json` (for `replay_ask.py`) and every piece of
model text main's speech filter is fed. It also stores a `lead` row per request (the tools offered, the tools kept, the
notes added) and a `model` row per reply (its words and calls after Jev's filter). `dumpline.py RUN_DIR [FROM_SECONDS]`
prints them as one timeline; `timeline.py RUN_DIR` does the same for a run without dumps.

Convert the pack after 12:30 IST on the day of a board (`lane.py convert`): the judge's clinic record is the pack's day.
On 3 October a board ran on the pack of 2 October and every stated date was marked invented. `s1_lane.py` now refuses
a pack converted for another clinic day. It also skips the lane's "local flow changed since the dump" check for the
`--main-shaped`, `--switch-off` and `--screening-as-main` runs: they read their own flow file, and the local stack's
cached copy of the lane's flow simply expires after about 30 hours.

## Why the lane's own FHCSD flow is not used

The lane's flow (`text-lane/flows/fhcsd-472875c4`) was rewritten for the engine in three places, and the small
version reads none of them:

1. Each tool's code has a layer added after the line `# Selected-leader result normalization`. It takes only the
   values the engine's code fills in. The patient lookup needs the birth date as 1977-02-18, while the tool's own
   description still tells the model MM/DD/YYYY. A model that follows the description gets `{"status": "unknown"}`.
2. The Task is written for the engine ("the runtime compares the accepted answer privately", "deliver the
   missed_appointment speech operation") and does not give the model the birth date on file.
3. Four endings exist only there: No Missed Appointment, Caller Requested End, Callback Requested, Do Not Call.

So `--main-shaped` runs the same 48 callers on the FHCSD flow as it was built for main. One scenario
(`L-reschedule-callback-later`) expects the ending Callback Requested, which that flow does not have.

The judge still reads tool results in the engine flow's shape (the offered slots, for one). `run_one_s1.py` passes
each raw result through that flow's own result layer for the trace row only (`S1_JUDGE_FLOW`). The model always
sees the raw result.

## The example flow

`make_example_flow.py` changes one sentence of the lane's Northwind flow: the go-ahead question said "The summary
was just spoken; do not repeat it", which only the engine does by code. Three things on this flow stay tied to the
engine and are not changed: the call note (`log_call_note`, fired by the engine's code, with a lead id the flow's
text does not carry), the sentence "the account lookup runs by itself", and the arrival of main's own receipt
repair at the booking step, which fails on Gemma about two calls in three with the switch on or off
("Collector receipt delivery failed; pending tool calls were not dispatched. (repair spoke nothing)").

## What differs from the engine lane, and must be said next to any number

- **Validity.** The small version has no start check, so the `jev.preflight` row only says the run started. Gemma
  must be proven only when the call reached a V2.9 node: on main's path a screening step speaks with main's own model
  for that step (GPT-4.1), so a call that ends in screening sends Gemma nothing.
- **The first line.** The callee's "Hello?" draws the screening step's opener and nothing else, as in main's run store.
  Main's text simulator would otherwise answer the hello a second time; on a real call it does not.
- **After screening.** The V2.9 node's greeting is drawn with an empty caller line, as main's run store does, after
  the same short wait for a late exit that the run store has (`_fold_late_exit`).
- **When a turn is over.** Main's text simulator hands the turn back when `run()` resolves. A step taken after a
  collector finished is still in flight then. The adapter waits until no request, tool, line or change of floor is
  in flight.
- **An exit's saved line.** A live call takes every exit through the flow-session handler, which says the exit's
  saved line ("Let me get someone from our team on the line for you.") before leaving. Main's text sim takes a V2.9
  span through the legacy handler, which says nothing. The adapter says the line the same way before that handler runs.
- **Two verdicts.** `board_s1.py` prints the lane's own verdict (strict) and one where an acknowledgement on its own
  line counts as a fault only when it is all the agent said in that turn. Main's collectors speak the receipt and the
  next question as two lines of one turn. `--set-aside` adds a third count without the named checks.
