#!/usr/bin/env python3
"""Create (or re-sync) the FHCSD v2.9 scenarios on Hunter, then read each one back and diff it.

    python3 FHCSD/hunter/v29/create.py --cookie <path> --auth <path>          # create the missing ones
    python3 FHCSD/hunter/v29/create.py --cookie <path> --auth <path> --sync   # PUT every changed one
    python3 FHCSD/hunter/v29/create.py --cookie <path> --auth <path> --diff   # read back only, change nothing

It NEVER triggers a run. Two secrets stay outside the repo and are never printed: the Hunter
session cookie and the local rig's Basic header, which is substituted into
`initiationRequest.headers.Authorization` in place of __FROM_SCRATCHPAD__ at POST time. The diff
applies the same substitution to the local file, so a clean diff means Hunter holds the file.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://hunter.contactodev.com"
CATEGORY = json.loads((HERE / "urls.json").read_text())["category"]
STATE = HERE / "created.json"
PLACEHOLDER = "__FROM_SCRATCHPAD__"


def call(cookie: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Cookie": cookie, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read()[:300].decode(errors='replace')}")


def with_auth(doc: dict, header: str) -> dict:
    """The one field the repo copy holds as a placeholder."""
    doc = json.loads(json.dumps(doc))
    h = doc["payload"].get("initiationRequest", {}).get("headers", {})
    if h.get("Authorization") == PLACEHOLDER:
        h["Authorization"] = header
    return doc


def differences(sent: dict, got: dict) -> list[str]:
    out = []
    for key in ("name", "description", "category"):
        if sent.get(key) != got.get(key):
            out.append(key)
    a, b = sent["payload"], got.get("payload") or {}
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"payload.{k}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", required=True, help="file holding hunter_session=...")
    ap.add_argument("--auth", required=True, help="file holding the local rig's Basic header")
    ap.add_argument("--sync", action="store_true", help="PUT scenarios whose file has changed")
    ap.add_argument("--diff", action="store_true", help="read back and diff only")
    ap.add_argument("--all", action="store_true",
                    help="include the parked category; without it only the kept board is touched")
    args = ap.parse_args()

    cookie = Path(args.cookie).read_text().strip()
    header = Path(args.auth).read_text().strip()
    if not cookie.startswith("hunter_session="):
        cookie = "hunter_session=" + cookie
    who = call(cookie, "GET", "/api/auth/me")
    print(f"as {who.get('email')}")

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    ids: dict[str, str] = dict(state.get("ids") or {})
    files = sorted(HERE.glob("scenarios/*.json"))
    report, parked = [], []

    for f in files:
        doc = json.loads(f.read_text())
        # Parked scenarios are frozen: skipped unless --all, so a routine sync costs 27 round trips
        # rather than 46. The one pass that MOVES them to the parked category needs --all.
        if doc.get("category") != CATEGORY and not args.all:
            parked.append(f.name)
            continue
        sent = with_auth(doc, header)
        sid = ids.get(f.name)
        if sid is None and not (args.diff or args.sync):
            sid = str(call(cookie, "POST", "/api/scenarios", sent)["id"])
            ids[f.name] = sid
            action = "created"
        elif sid is None:
            report.append((f.name, "-", "MISSING on Hunter (run without --diff/--sync to create)"))
            continue
        elif args.sync:
            got = call(cookie, "GET", f"/api/scenarios/{sid}")
            if differences(sent, got):
                call(cookie, "PUT", f"/api/scenarios/{sid}", sent)
                action = "updated"
            else:
                action = "unchanged"
        else:
            action = "checked"
        got = call(cookie, "GET", f"/api/scenarios/{sid}")
        diff = differences(sent, got)
        report.append((f.name, sid, action + ("  DIFF: " + ", ".join(diff) if diff else "  diff clean")))
        print(f"  {sid:<8} {f.name:<42} {report[-1][2]}")

    STATE.write_text(json.dumps({
        "category": CATEGORY,
        "kept": sorted(f.name for f in files if json.loads(f.read_text()).get("category") == CATEGORY),
        "parked": sorted(f.name for f in files if json.loads(f.read_text()).get("category") != CATEGORY),
        "note": "ids keyed by scenario file. initiationRequest.headers.Authorization is "
                f"{PLACEHOLDER} in the files and the real Basic header on Hunter, by design; "
                "every other field must diff clean. No run has been triggered from here.",
        "placeholders_remaining": {"initiationRequest.headers.Authorization": PLACEHOLDER},
        "ids": ids,
    }, indent=2) + "\n")
    bad = [r for r in report if "DIFF:" in r[2] or "MISSING" in r[2]]
    print(f"\n{len(report)} scenarios touched; {len(bad)} with a difference"
          + (f"; {len(parked)} parked and skipped (--all to include)" if parked else ""))
    print(f"ids -> {STATE}")


if __name__ == "__main__":
    main()
