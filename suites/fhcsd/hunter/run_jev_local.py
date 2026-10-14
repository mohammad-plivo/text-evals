"""Start or read a Hunter run of the local jev FHCSD category.

  python3 run_jev_local.py start --cookie <file> --name "Jev v2.9.1 FHCSD ..." --parallel N <scenario id> [...]
  python3 run_jev_local.py show --cookie <file> <run id>
"""
import argparse
import json

import align_dev_board as dev


def cookie_from(path):
    c = open(path).read().strip()
    return c if c.startswith("hunter_session=") else "hunter_session=" + c


def show(cookie, run_id):
    run = dev.req("GET", f"/api/runs/{run_id}", cookie)
    items = run.get("items") or []
    print(f"{run['name']} | {run['status']} | passed {run.get('passed')} failed {run.get('failed')} of {run.get('total_tests')}")
    for it in sorted(items, key=lambda it: it.get("scenario_name") or ""):
        tags = ",".join(json.loads(it.get("failure_tags_json") or "[]"))
        secs = round(int(it["duration_ms"]) / 1000) if str(it.get("duration_ms") or "").isdigit() else "-"
        print(f"  {it.get('result') or it.get('status'):>9} {it.get('score') or '-':>5} {it.get('turn_count') or '-':>3}t {secs:>4}s "
              f"{(it.get('scenario_name') or '').replace('FHCSD dev test — ', '').replace(' (jev)', '')[:80]} {tags}")
    return run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("start", "show"))
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--name")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("ids", nargs="+")
    a = ap.parse_args()
    cookie = cookie_from(a.cookie)
    if a.cmd == "start":
        assert a.name and a.name.startswith(("Jev v2.9.1 FHCSD", "v2.10 FHCSD")), "run names start with 'Jev v2.9.1 FHCSD' or 'v2.10 FHCSD'"
        dev.req("POST", "/api/runs", cookie, {"name": a.name, "scenarioIds": [str(i) for i in a.ids], "maxParallel": a.parallel})
        run = next(r for r in dev.req("GET", "/api/runs?limit=5", cookie)["runs"] if r["name"] == a.name)  # the POST answer carries no id
        print(run["id"], run["status"])
    else:
        show(cookie, a.ids[0])


if __name__ == "__main__":
    main()
