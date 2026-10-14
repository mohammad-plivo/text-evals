"""Mock of the pulmonology clinic backend (voice-agent-service), for Flow testing.

Same paths and payload shapes as the real service, so switching is a base-URL change.
Every branch the Scheduler prompt depends on is reachable from the CALLER'S OWN INPUT —
no editing this file between runs:

    last name "Notfound"    -> identify_patient  not_found
    last name "Ambiguous"   -> identify_patient  ambiguous
    last name "Down"        -> identify_patient  system_unavailable
    last name "Referral"    -> check_insurance   on_file + referral_required=true
    last name "Noins"       -> check_insurance   none_on_file
    last name "Insdown"     -> check_insurance   system_unavailable
    anything else           -> the happy path

Stdlib only. python3 server.py [port]
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAYERS = ["Aetna", "Cigna", "UnitedHealthcare", "Blue Cross Blue Shield", "Humana"]
NPS = ["Sam", "Steven"]


def _steer(body: dict) -> str:
    """The steering token: the caller's LAST word of name, however the flow spells the field.

    The Flow sends a single `name`; the Vapi squad's schema used firstName/lastName. Both are
    accepted so the mock never fails a test for a field-name mismatch.
    """
    last = body.get("lastName") or body.get("last_name")
    if not last:
        parts = str(body.get("name") or "").strip().split()
        last = parts[-1] if parts else ""
        # STT renders "Notfound" as "Not Found": a steer may span the last two words.
        tail = "".join(parts[-2:]).lower()
        tail = tail.replace("nemo", "notfound")  # "Nemo": a natural surname the name collector accepts; steers not-found
        if tail.endswith(("notfound", "ambiguous", "down")):
            last = next(t for t in ("notfound", "ambiguous", "down") if tail.endswith(t))
    return str(last).strip().lower()


def _pid(body: dict) -> str:
    """A stable id per caller, so the same person gets the same record across calls."""
    seed = (
        f"{body.get('name','')}{body.get('firstName','')}"
        f"{body.get('lastName','')}{body.get('dob','')}"
    ).lower().strip()
    return f"PT-{abs(hash(seed)) % 900000 + 100000}" if seed else "PT-100000"


def verify_patient(b):
    steer = _steer(b)
    if steer == "notfound":
        return {"status": "not_found"}
    if steer == "ambiguous":
        return {"status": "ambiguous", "candidates": 2}
    if steer == "down":
        return {"status": "system_unavailable"}
    pid = _pid(b)
    return {
        "status": "matched",
        "patient_id": pid,
        "patient_guid": f"{pid}-GUID",
        "name": b.get("name") or f"{b.get('firstName','')} {b.get('lastName','')}".strip(),
        "dob": b.get("dob"),
    }


def check_insurance(b):
    pid = str(b.get("patientId") or "")
    steer = _steer(b)
    # patientId carries no name, so allow steering by either field
    if steer == "referral" or pid.endswith("R"):
        return {"status": "on_file", "payer": "Culinary Health Fund", "referral_required": True}
    if steer == "noins":
        return {"status": "none_on_file", "payer": None, "referral_required": False}
    if steer == "insdown":
        return {"status": "system_unavailable"}
    payer = PAYERS[abs(hash(pid)) % len(PAYERS)]
    return {"status": "on_file", "payer": payer, "referral_required": False}


def find_slots(b):
    """Three slots from fromDate (or tomorrow), skipping weekends."""
    raw = b.get("fromDate")
    try:
        start = datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        start = date.today() + timedelta(days=1)
    if start <= date.today():
        start = date.today() + timedelta(days=1)
    provider = b.get("provider")
    who = "Dr. Sayal" if str(provider).lower() in ("dr_sayal", "sayal") else NPS[0]
    slots, d, times = [], start, ["9:00 AM", "11:30 AM", "2:15 PM"]
    while len(slots) < 3:
        if d.weekday() < 5:
            slots.append({"date": d.isoformat(), "time": times[len(slots)], "provider": who})
        d += timedelta(days=1)
    return {"status": "ok", "slots": slots, "location": b.get("location")}


def _deny_unknown(b):
    """Producers refuse an unknown identity, as a real clinic API would; None when the caller is known."""
    return {"status": "not_found", "message": "No patient record matches that name and date of birth."} if _steer(b) == "notfound" else None


def book_appointment(b):
    if (d := _deny_unknown(b)):
        return d
    return {
        "status": "accepted",
        "confirmation_id": f"BK-{abs(hash(json.dumps(b, sort_keys=True))) % 900000 + 100000}",
        "provider": b.get("provider") if str(b.get("provider", "")).lower() == "dr_sayal" else NPS[0],
        "date": b.get("date"),
        "time": b.get("time"),
        "location": b.get("location"),
        "note": "Booking is queued and will be confirmed by the clinic.",
    }


def reschedule_appointment(b):
    if (d := _deny_unknown(b)):
        return d
    out = book_appointment(b)
    out["moved_from"] = {"date": b.get("currentDate"), "time": b.get("currentTime")}
    return out


def _next_weekday():
    d = date.today() + timedelta(days=7)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def cancel_appointment(b):
    if (d := _deny_unknown(b)):
        return d
    return {
        "status": "accepted",
        "confirmation_id": f"CX-{abs(hash(_pid(b))) % 900000 + 100000}",
        # The appointment's own slot, not an echo of whatever date the flow passed in.
        "cancelled": {"date": _next_weekday().isoformat(), "time": "10:00 AM"},
    }


def list_appointments(b):
    # An empty guid is expected: the Flow has no way to feed identify_patient's output back into
    # a collector variable, so it sends "". Returning not_found there would dead-end every review
    # call for a plumbing reason rather than a real one.
    d = date.today() + timedelta(days=7)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return {
        "status": "ok",
        "appointments": [
            {"date": d.isoformat(), "time": "10:00 AM", "type": "office_visit",
             "provider": NPS[0], "location": "henderson"}
        ],
    }


ROUTES = {
    "/tools/verify-patient": verify_patient,
    "/tools/check-insurance": check_insurance,
    "/tools/find-slots": find_slots,
    "/tools/book-appointment": book_appointment,
    "/tools/reschedule-appointment": reschedule_appointment,
    "/tools/cancel-appointment": cancel_appointment,
    "/tools/list-appointments": list_appointments,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/health"):
            return self._send(200, {"ok": True, "service": "mock-clinic",
                                    "routes": sorted(ROUTES)})
        self._send(404, {"error": "not_found", "routes": sorted(ROUTES)})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        fn = ROUTES.get(path)
        if fn is None:
            return self._send(404, {"error": "unknown_endpoint", "path": path,
                                    "routes": sorted(ROUTES)})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": "bad_request", "detail": str(e)})
        try:
            self._send(200, fn(body))
        except Exception as e:  # a mock must never 500 a test into a false failure
            self._send(200, {"status": "system_unavailable", "detail": str(e)})

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[mock-clinic] {self.address_string()} {fmt % args}\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"[mock-clinic] listening on :{port} — {len(ROUTES)} routes", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
