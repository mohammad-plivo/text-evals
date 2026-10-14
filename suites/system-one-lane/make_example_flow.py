"""The Northwind example flow for main's path: the lane's flow with one sentence changed.

The go-ahead question says "The summary was just spoken; do not repeat it." Only the engine speaks that summary by
code. On main's path the question itself has to carry it, as the FHCSD flow's booking question does.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "text-evals", "example-flow", "ws", "flow.json")
OUT = os.path.join(HERE, "flows", "example-main-shaped", "flow.json")
OLD = "Ask: Shall I go ahead and book this visit for you? The summary was just spoken; do not repeat it."
NEW = "State the service, the visit date and the address in one sentence, then ask: Shall I go ahead and book this visit for you?"

text = open(SOURCE).read()
assert text.count(OLD) == 1, text.count(OLD)
flow = json.loads(text.replace(OLD, NEW))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(flow, open(OUT, "w"), indent=1)
print(f"wrote {OUT}")
