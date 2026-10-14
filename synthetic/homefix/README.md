# v2.10 logic flow, the v2.10 Stress Test

One made-up flow and 30 hard callers that try to break the stamped v2.10 engine: every collector type, actions, moves between AI steps, handoffs and a transfer. Local stack only. MK asked for the flow and 15 callers on 10 October 2026, and on 11 October for 30 callers under the Hunter name "v2.10 Stress Test". It is built from `V29-Hunter-Example` (24 September), which had the 12 collector types but no actions and ran on dev.

```
Start -> Call Customer -> Screen Customer -> Account Check -> Book Visit | Site Details | Contact Details | Payment -> an end step
```

## Files

| File | What it is |
|---|---|
| `spec.py` | The flow: steps, questions and their settings, the actions' code, ways out, wiring, and where each step sits on the canvas (`PLACE`) |
| `callers.py` | The 30 callers: what each says, what Hunter's judge checks, what the stack's log must show, planned seconds |
| `build.py` | Builds `out/flow.json`, `out/sim/<caller>/`, `out/hunter/<caller>.json`, then checks them. Run it on the day of a board |
| `sim.py` | Runs callers in the text simulator inside `v210-agent-runner`. Saves each conversation in `out/sim-results/` |
| `stack.py` | Puts the flow on the local stack through config-service, stamps it, publishes it, shows what was stored |
| `hunter.py` | Registers the callers in Hunter, starts a run, checks a run: Hunter's verdict next to the log check. `check` saves each run in `out/voice/` |
| `timeline.py` | One call as a readable timeline: who said what, each action, each move, and Jev's pick on every turn |
| `page.py` | Writes the two Glance pages of the suite (`out/stress`, `out/stress-questions`) from the files above |
| `cfg_call.py` | Runs inside `v210-config`: one request to config-service with its own token |

## How to run

```
python3 build.py                 # every date is worked out from today, India time
python3 sim.py                   # text: the 23 callers that reach an AI step, 3 at a time, about 9 minutes; each run is kept in its own folder
python3 sim.py --check           # count the saved text runs of each caller again, run nothing
ENGINE_DIR=/tmp/engine-old python3 sim.py 16-    # the same callers on another copy of the engine inside the container; saved under out/sim-results-other-engine/
python3 stack.py push            # only after spec.py changed
python3 hunter.py create --cookie ../../v2.9.1-jev/.hunter-cookie
python3 hunter.py run --cookie ../../v2.9.1-jev/.hunter-cookie 01         # first call: the shortest, no move between steps
python3 hunter.py run --cookie ../../v2.9.1-jev/.hunter-cookie 08         # second call: one move between two AI steps
python3 hunter.py run --cookie ../../v2.9.1-jev/.hunter-cookie            # the board: 28 callers at 4 at a time
python3 hunter.py run --cookie ../../v2.9.1-jev/.hunter-cookie --alone    # and callers 12 and 24 one at a time, they transfer
python3 hunter.py check --cookie ../../v2.9.1-jev/.hunter-cookie <run id> [<run id>]
python3 timeline.py <flow run uuid>      # the uuid of each call is in out/voice/<run id>.json
python3 page.py                          # the pages read out/voice/ and out/sim-results/
```

## Things to know

- The flow on the stack is local flow 18, `c9c4052c-4610-53dc-9acf-2b12175c3479`. Do not save it from the console: the console drops the screening exit.
- A call passes only when Hunter's judge and the log check both pass. Hunter cannot see actions or saved values.
- Handoffs: 20 of the 30 callers move from one AI step to another (callers 02 and 26 twice). The judge checks the agent does not start the call over after a move. `check` prints, for every entry into an AI step, the silence the caller heard, the step's first line and how many steps Jev picked there. A step that says nothing, or that Jev never led, fails the log check.
- A text run gets the same log check. The simulator's own PASS only says the planned way out was taken: caller 05 printed PASS after booking the wrong day.
- No caller walks the whole flow. The Hunter caller stops talking at about 290 seconds, and a turn took 17.5 seconds on 9 October.
- The test flow waits 20 seconds before "are you still there?", not the usual 15, because the Hunter caller is often slow to answer.
- The text simulator cannot move from screening into an AI step, so text runs start at Account Check. Callers 13, 14, 15, 19, 20, 21 and 22 and the opening of caller 04 are for voice only. In text a silent caller shows up as a bracketed line, and the agent sometimes answers it: ignore that.
- The two closings End Booked and End Paid read a value saved in an earlier step (the chosen time, the amount). On voice, read "End conversation with message=" in the `v210-agent-runner` log: it must hold the value and no braces. Hunter's verdict alone does not prove the value arrived.
- `out/found/` keeps the text runs of 10 October that showed an engine fault: the endless phone read-back (caller 09, first run), the old times after a new day (caller 05, `second-run`), the person asked for in the payment step (caller 04, both).
- The canvas layout is `PLACE` in `spec.py`, the left and top of each step. A step sent with no place is dropped into a three-column grid by the server, which is unreadable. The console draws the dial and the screening as one step, at the dial's place. The console's own arrange key (A) is worse on this flow: it runs lines through steps.
- Every action result has a way out of its step. If a call sits silent after an action, it is the engine, not a missing exit.
- The caller id, the transfer number and the voice settings are read from local flow 17 at build time. `out/` is local only.
- After the tunnels are re-made: `build.py`, then `hunter.py create`, then one call.
- Voice ran on 10 October 2026 for callers 01 to 15: 17 calls. Results in `out/voice/`, one timeline per call in `out/voice/timelines/`. The page of that run is frozen in `out/page/` and at the Glance name `v210-logic-flow`; `page.py` no longer writes it.
- The log check is strict since 11 October: a saved value must be the whole expected value ("INR 500.0", not anything that holds 500), what an action was sent is compared call by call, and an action that errors is a fault unless the caller lists it under `fails`. The rules are in the docstring of `callers.py`.
- The closings of End Site Saved, End Contact Saved, End Paid and End Booked say values saved in an earlier step, so Hunter's judge hears what was stored. One account (caller 29) makes the save fail, to test that way out.
- The text runs of the old flow (15 callers, one End Saved) are in `out/sim-results-1010/`. `out/sim-results/` holds runs of the flow as it is now.
- Caller 09 is strict since 10 October (MK): an exact repeat of the phone number must count as a yes. It fails until the engine does that.
