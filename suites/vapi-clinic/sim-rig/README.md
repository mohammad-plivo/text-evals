# sim-rig — the TeleCRM/Hunter local measurement rig

Kept here, not on `main`. It is local A/B tooling: it measured the fixes in PRs #321 and #322 and it
is how the next A/B gets run, but prod does not need a customer's exported flow, and shipping ~3,800
lines of generated JSON to the production line to enable two unit tests is a bad trade.

```
hunter-telecrm-p0/    Hunter's own conversationPrompt + initiationVariables for scenario 16536.
                      The blanks in params.yaml are load-bearing — Hunter sent COMPANY_NAME,
                      INDUSTRY and SALES_TEAM_SIZE empty and the node branches on that.
  scripts/tally_claims.py     the criterion-7 scorer
  scripts/validate_claims.py  its 42-case table — a scorer that disagrees with the judge it
                              stands in for is not a measurement
hunter-telecrm-v3/    the rebuilt TeleCRM flow, choice field in first position
```

To use: copy the workspace into `repo/examples/simulation/` and run the CLI. Do not commit it.

```bash
cp -R "…/Vapi Flow/sim-rig/hunter-telecrm-p0" repo/examples/simulation/
uv run python -m src.simulation.cli run examples/simulation/hunter-telecrm-p0 \
  --scenario terminal-boolean-no-promised-action --repeat 5 --no-open --env-file <dotenv>
```
