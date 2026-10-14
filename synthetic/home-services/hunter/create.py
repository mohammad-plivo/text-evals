#!/usr/bin/env python3
"""Create (or re-sync) the V2.9 example scenarios on Hunter, then read each one back and diff it.

    python3 V29-Hunter-Example/hunter/create.py --cookie <path>          # create the missing ones
    python3 V29-Hunter-Example/hunter/create.py --cookie <path> --sync   # PUT every changed one
    python3 V29-Hunter-Example/hunter/create.py --cookie <path> --diff   # read back only, change nothing

Never triggers a run. Refuses while urls.json still holds the flow uuid placeholder. `_expected_variables`
is stripped before POST (Hunter has no field for it). Adapted from Sigma/hunter/create.py.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://hunter.contactodev.com"
U = json.loads((HERE / "urls.json").read_text())
STATE = HERE / "created.json"
LOCAL_ONLY = "_expected_variables"


def call(cookie: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Cookie": cookie, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read()[:300].decode(errors='replace')}")


def refuse_stale_build(files) -> None:
    """Every date in a scenario is today's (IST); a file built on another day judges the wrong dates."""
    import datetime, zoneinfo
    today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date().isoformat()
    stale = sorted(f.name for f in files if json.loads(f.read_text()).get("_built_ist") != today)
    if stale:
        raise SystemExit(f"built on another IST day ({len(stale)} files, e.g. {stale[0]}); re-run build.py first")


def differences(sent: dict, got: dict) -> list[str]:
    out = [k for k in ("name", "description", "category") if sent.get(k) != got.get(k)]
    a, b = sent["payload"], got.get("payload") or {}
    return out + [f"payload.{k}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True, help="file holding the hunter_session JWT")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--diff", action="store_true")
    args = ap.parse_args()
    if "__SET_AFTER_PUBLISH__" in json.dumps(U):
        raise SystemExit("urls.json still has the flow uuid placeholder; set it and re-run build.py first")
    cookie = Path(args.cookie).read_text().strip()
    cookie = cookie if cookie.startswith("hunter_session=") else "hunter_session=" + cookie
    print("as", call(cookie, "GET", "/api/auth/me").get("email"))
    ids: dict[str, str] = dict((json.loads(STATE.read_text()) if STATE.exists() else {}).get("ids") or {})
    report = []
    files = sorted((HERE / "scenarios").glob("*.json"))
    refuse_stale_build(files)
    for f in files:
        doc = json.loads(f.read_text())
        doc.pop(LOCAL_ONLY, None)
        doc.pop("_built_ist", None)
        if U["flow_uuid"] not in doc["payload"]["initiationRequest"]["url"]:
            raise SystemExit(f"{f.name}: built for another flow uuid; re-run build.py")
        sid = ids.get(f.name)
        if sid is None and not (args.diff or args.sync):
            sid = ids[f.name] = str(call(cookie, "POST", "/api/scenarios", doc)["id"])
            action = "created"
        elif sid is None:
            print(f"  -  {f.name}: MISSING on Hunter"); continue
        elif args.sync and differences(doc, call(cookie, "GET", f"/api/scenarios/{sid}")):
            call(cookie, "PUT", f"/api/scenarios/{sid}", doc); action = "updated"
        else:
            action = "checked"
        diff = differences(doc, call(cookie, "GET", f"/api/scenarios/{sid}"))
        report.append(diff)
        print(f"  {sid:<8} {f.name:<34} {action}  {'DIFF: ' + ', '.join(diff) if diff else 'diff clean'}")
    STATE.write_text(json.dumps({"category": U["category"], "flow_uuid": U["flow_uuid"], "ids": ids}, indent=2) + "\n")
    print(f"{len(report)} scenarios; {sum(bool(d) for d in report)} with a difference; no run triggered")


if __name__ == "__main__":
    main()
