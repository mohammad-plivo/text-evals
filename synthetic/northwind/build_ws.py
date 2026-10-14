"""spec.json -> ws/ (sim CLI workspace: flow.json, params.yaml, scenarios/<slug>.yaml), date tokens filled for the run day.

  python3 build_ws.py [--day YYYY-MM-DD]   # run day in America/New_York, default today; rebuild on the day you run
"""
import argparse
import hashlib
import json
import os
import shutil
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(HERE, "ws")


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def tokens(day: date) -> dict[str, str]:
    visit = day + timedelta(days=14)
    visit += timedelta(days=(1 - visit.weekday()) % 7)  # first Tuesday at least 14 days out
    visit2 = visit + timedelta(days=2)
    past = day - timedelta(days=1)
    past -= timedelta(days=past.weekday())  # last Monday strictly before the run day
    spoken = lambda d: f"{d:%A} the {ordinal(d.day)} of {d:%B}"  # noqa: E731
    return {"{VISIT_SPOKEN}": spoken(visit), "{VISIT_ISO}": visit.isoformat(),
            "{VISIT2_SPOKEN}": spoken(visit2), "{VISIT2_ISO}": visit2.isoformat(),
            "{PAST_SPOKEN}": f"{past:%A}, {past:%B} {ordinal(past.day)}, {past.year}", "{PAST_ISO}": past.isoformat()}


def fill(obj, toks: dict[str, str]):
    text = json.dumps(obj)
    for k, v in toks.items():
        text = text.replace(k, v)
    assert "{VISIT" not in text and "{PAST" not in text, "unfilled date token"
    return json.loads(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/New_York")).date())
    day = ap.parse_args().day
    spec = json.load(open(os.path.join(HERE, "spec.json")))
    assert json.load(open(os.path.join(HERE, "flow.json"))) == spec["flow"], "flow.json drifted from spec.json"
    params = {json.dumps(s["params"], sort_keys=True) for s in spec["scenarios"]}
    assert len(params) == 1, "scenarios disagree on Start params"
    toks = tokens(day)
    shutil.rmtree(os.path.join(WS, "scenarios"), ignore_errors=True)
    os.makedirs(os.path.join(WS, "scenarios"))
    shutil.copyfile(os.path.join(HERE, "flow.json"), os.path.join(WS, "flow.json"))
    with open(os.path.join(WS, "params.yaml"), "w") as fh:
        fh.write("# Start http params; run_one.py seeds them as start.http.params (the flow has no {{Start.*}} placeholders)\n")
        yaml.safe_dump({"params": json.loads(params.pop()), "substitutions": {}}, fh, sort_keys=False)
    for s in spec["scenarios"]:
        s = fill(s, toks)
        sc = {"description": f"{s['slug']} ({s['type']} / {s['facet']}): {s['title']}. Run day {day}.",
              "simulated_user": {k: s[k] for k in ("persona", "goal", "opening", "max_turns")},
              "action_mocks": s["action_mocks"], "expect": {"intent": s["expect_exit"], "ended": True}}
        with open(os.path.join(WS, "scenarios", s["slug"] + ".yaml"), "w") as fh:
            yaml.safe_dump(sc, fh, sort_keys=False, allow_unicode=True, width=110)
    json.dump({"run_day": day.isoformat(), "spec_sha256": hashlib.sha256(open(os.path.join(HERE, "spec.json"), "rb").read()).hexdigest(), "tokens": toks, "scenarios": len(spec["scenarios"])},
              open(os.path.join(WS, "build.json"), "w"), indent=1)
    print(json.dumps({"ws": WS, "run_day": day.isoformat(), **toks, "scenarios": len(spec["scenarios"])}, indent=1))


if __name__ == "__main__":
    main()
