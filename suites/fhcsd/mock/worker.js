/**
 * FHCSD vendor-API mock — Cloudflare Worker.
 *
 * Mirrors the five endpoints the outbound missed-appointment flow calls, per the contracts in
 * Admin/Flows/new fhcsd outbound flow.md §7. Three properties are deliberate:
 *
 *   1. Every branch is selected by the PATIENT'S OWN LAST NAME, so a test scenario picks its own
 *      path and nothing here is edited between runs. (Pattern from Vapi Flow/mock-clinic/server.py.)
 *   2. It NEVER returns 5xx. An internal error becomes a valid FHCSD failure body, so a bug in the
 *      mock can never be read as a defect in the flow.
 *   3. The vendor token really does expire after TOKEN_TTL_SECONDS (default 30, the real value).
 *      A flow that authenticates once at call start and reuses the token WILL fail here — which is
 *      the point: that is the single most likely silent breakage, and a mock that tolerates it
 *      lets a broken flow pass.
 *
 * Success convention, which the flow must read correctly: a 2xx AND `Error == 0`. `Error: 1` is a
 * failure even on a 2xx. Prod flow 5207aaf5 gates on `status_code == 202` instead and therefore
 * books the appointment and tells the patient it failed — see
 * Admin/findings/2026-08-09-fhcsd-bug-status-misread.md. `LastName: Down` reproduces that shape.
 */

const PASSCODE = "change-me";   // matches the existing FHCSD mock; not a real secret
const TOKEN_TTL_SECONDS = 30;

// ---------------------------------------------------------------- steering

// Recognised last names, lower-cased. Anything else is the happy path.
// Each steer has a literal name (self-documenting) and a natural-sounding alias, so a Hunter
// persona can be a plausible patient instead of "Maria Notfound" while still picking its branch.
const STEER = {
  notfound: "no patient match",
  ambiguous: "two patient matches",
  noslots: "no availability",
  down: "booking returns Error: 1",
  already: "SaveAppointment returns HTTP 409",
  htmlfail: "SaveAppointment returns the 409 as text/html",
  expiredtoken: "every Druid call answers 401 token expired",
  noappt: "patient matches but has no appointments on file",
  oneslot: "availability returns exactly one slot",
  twoslots: "availability returns exactly two slots",
};
const ALIAS = {
  tran: "notfound",
  delacroix: "ambiguous",
  kowalski: "noslots",
  ferreira: "down",
  okonkwo: "already",
  oyelaran: "htmlfail",
  kaminski: "expiredtoken",
  achterberg: "noappt",
  bergstrom: "oneslot",
  nakamura: "twoslots",
};

function steerOf(lastName) {
  const k = String(lastName || "").trim().toLowerCase();
  const via = ALIAS[k] || k;
  return STEER[via] ? via : "happy";
}

/** Stable per-last-name MasterId, so SaveAppointment and the two GETs can recover the steer
 *  from the MasterId alone — those endpoints never receive a name. */
function masterIdFor(lastName) {
  const raw = String(lastName || "").trim().toLowerCase();
  const s = ALIAS[raw] || raw;
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  return String(100000000 + (h % 899999999));
}

const MASTER_TO_STEER = Object.fromEntries(
  Object.keys(STEER).map((k) => [masterIdFor(k), k]),
);
const steerOfMasterId = (m) => MASTER_TO_STEER[String(m || "").trim()] || "happy";

// ---------------------------------------------------------------- dates

const pad = (n) => String(n).padStart(2, "0");
const slashDate = (d) => `${pad(d.getUTCMonth() + 1)}/${pad(d.getUTCDate())}/${d.getUTCFullYear()}`;
const hyphenDate = (d) => `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}-${d.getUTCFullYear()}`;

/** Accepts MM-DD-YYYY, MM/DD/YYYY and YYYY-MM-DD. Returns null on anything else. */
function parseDate(s) {
  const t = String(s || "").trim();
  let m;
  if ((m = t.match(/^(\d{2})[-/](\d{2})[-/](\d{4})$/)))
    return new Date(Date.UTC(+m[3], +m[1] - 1, +m[2]));
  if ((m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/)))
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return null;
}

function nextWeekdays(from, count) {
  const out = [];
  const d = new Date(from.getTime());
  while (out.length < count) {
    d.setUTCDate(d.getUTCDate() + 1);
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(new Date(d.getTime()));
  }
  return out;
}

// ---------------------------------------------------------------- responses

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

const fail = (msg, status = 200) => json({ Id: 0, Error: 1, ErrorMsg: msg }, status);

// ---------------------------------------------------------------- auth

function mintToken() {
  return `MOCK.${Date.now()}`;
}

/** Returns null when the token is good, or a Response when it is not. */
function checkToken(req) {
  const tok =
    req.headers.get("fhcsd-external-access-token") ||
    req.headers.get("x-my-authentication-token");
  if (!tok) return fail("Missing authentication token", 401);
  const m = String(tok).match(/^MOCK\.(\d+)$/);
  if (!m) return fail("Malformed authentication token", 401);
  const ageSec = (Date.now() - Number(m[1])) / 1000;
  if (ageSec > TOKEN_TTL_SECONDS)
    return fail(
      `Vendor token expired (${ageSec.toFixed(1)}s old, TTL ${TOKEN_TTL_SECONDS}s) — ` +
        `authenticate immediately before every request`,
      401,
    );
  return null;
}

// ---------------------------------------------------------------- fixtures

/** The doc's example Phone is 10 digits and MK's trigger payload is 11: strip a leading 1 and any
 *  punctuation so both match the same patient. */
const norm10 = (p) => String(p || "").replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");

function patient(first, last, dob, phone) {
  return {
    MasterId: masterIdFor(last),
    FirstName: first || "Pat",
    LastName: last || "Patient",
    DOB: dob || "01/01/1970",
    Phone: norm10(phone) || "6195551001",
    Gender: "U",
    PreferredProviderId: 7,
    PreferredFacilityId: 126,
    // The doc shows a per-patient AuthenticationToken alongside the vendor token. Whether the later
    // Druid calls require it is question 8 for FHCSD; returning it costs nothing and lets the flow
    // switch on PATIENT_TOKEN_HEADER without another mock change.
    AuthenticationToken: `PT.${masterIdFor(last)}.${Date.now()}`,
  };
}

function appointment(masterId, when, overrides = {}) {
  return {
    AppointmentId: 900001,
    MasterId: String(masterId),
    AppointmentDate: slashDate(when),      // MM/DD/YYYY — NOT the slot format
    AppointmentTime: "10:30 AM",
    Provider: "Dr. Rismiller",
    ProviderId: 7,
    Facility: "Logan Heights Family Health Center",
    FacilityAddress: "1809 National Avenue, San Diego, CA 92113",
    FacilityId: 126,
    Department: "General Medicine",
    DepartmentId: 11,
    AttributeId: 6,
    ...overrides,
  };
}

// ---------------------------------------------------------------- handlers

function getPatients(url) {
  const q = url.searchParams;
  const first = q.get("FirstName") ?? q.get("firstName") ?? "";
  const last = q.get("LastName") ?? q.get("lastName") ?? "";
  const dob = q.get("DOB") ?? q.get("dob") ?? "";
  const phone = q.get("Phone") ?? q.get("phone") ?? "";
  const steer = steerOf(last);

  if (steer === "notfound") return json([]);
  if (steer === "ambiguous")
    return json([
      patient(first, last, dob || "01/01/1970", phone),
      { ...patient(first, last, dob || "01/01/1970", phone), MasterId: "100000001", Gender: "F" },
    ]);
  // A DOB that does not parse is a failed verification, not a match.
  if (dob && !parseDate(dob)) return json([]);
  return json([patient(first, last, dob, phone)]);
}

function getPatientAppointments(url) {
  const mid = url.searchParams.get("MasterId") ?? url.searchParams.get("masterId") ?? "";
  const steer = steerOfMasterId(mid);
  if (steer === "notfound" || steer === "noappt") return json([]);

  // The brief is "missed earlier the SAME DAY", so the appointment is dated today.
  const today = clinicToday();
  return json([appointment(mid, today)]);
}

function getAvailableAppointments(url) {
  const q = url.searchParams;
  const mid = q.get("MasterId") ?? "";
  const steer = steerOfMasterId(mid);
  if (steer === "noslots") return json([]);
  const count = steer === "oneslot" ? 1 : steer === "twoslots" ? 2 : 3;

  const start = parseDate(q.get("StartDate")) || clinicToday();
  const facilityId = Number(q.get("FacilityId")) || 126;
  const departmentId = Number(q.get("DepartmentId")) || 11;
  const providerId = Number(q.get("ProviderId")) || 7;

  return json(
    nextWeekdays(start, count).map((d, i) => ({
      ProvScheduleId: 249669 + i,
      ApptDate: hyphenDate(d),             // MM-DD-YYYY — NOT the DOB format
      FromSlotId: 103 + i,
      ToSlotId: 104 + i,
      TimeSlot: ["09:30 AM – 09:45 AM", "11:00 AM – 11:15 AM", "03:45 PM – 04:00 PM"][i],
      FacilityId: facilityId,
      FacilityName: "Logan Heights Family Health Center",
      DepartmentId: departmentId,
      DepartmentName: "General Medicine",
      ProviderId: providerId,
      ProviderName: "Dr. Rismiller",
    })),
  );
}

async function saveAppointment(req) {
  let body = {};
  try {
    body = await req.json();
  } catch {
    return fail("Request body is not valid JSON");
  }
  const mid = body.MasterId ?? body.masterId ?? "";
  const steer = steerOfMasterId(mid);
  if (steer === "down")
    return json({ Id: 0, Error: 1, ErrorMsg: "Selected slot is no longer available" }, 200);

  // 409: the patient already has an appointment. Not in FHCSD's doc, observed in the wild. It is
  // the correct answer to a book-new with no AppointmentId, and the `already` steer forces it so a
  // reschedule can exercise the branch too.
  const alreadyBody = { Id: 0, Error: 1, ErrorMsg: "Patient already has an appointment" };
  const bookingNew = body.AppointmentId === undefined || body.AppointmentId === null ||
    body.AppointmentId === "" || Number(body.AppointmentId) === 0;
  if (steer === "htmlfail")
    // A non-JSON body on a JSON phlo node is rewritten to status 400 with an empty response, so the
    // flow must fall through to its generic failure rather than read the 409.
    return new Response(`<html><body>${alreadyBody.ErrorMsg}</body></html>`, {
      status: 409, headers: { "content-type": "text/html", "cache-control": "no-store" },
    });
  if (steer === "already" || bookingNew) return json(alreadyBody, 409);

  const missing = ["AppointmentId", "AppointmentDate", "ProvScheduleId", "FromSlotId"].filter(
    (k) => body[k] === undefined || body[k] === null || body[k] === "",
  );
  if (missing.length) return fail(`Missing required field(s): ${missing.join(", ")}`);

  // The flow must send MM-DD-YYYY here; a slash date is the documented silent breakage.
  if (!/^\d{2}-\d{2}-\d{4}$/.test(String(body.AppointmentDate)))
    return fail(
      `AppointmentDate must be MM-DD-YYYY, got "${body.AppointmentDate}" ` +
        `(DOB is MM/DD/YYYY — the two formats differ)`,
    );

  return json({ Id: Number(mid) || 100177654, Error: 0, ErrorMsg: "Appointment created successfully" });
}

/** POST /api/Druid/CancelAppointment?intCancelUserId=11 — body {AppointmentId, CancelNotes, UserId}.
 *  The flow is reschedule-only today; this exists so it can grow without another mock change. */
async function cancelAppointment(req) {
  let body = {};
  try {
    body = await req.json();
  } catch {
    return fail("Request body is not valid JSON");
  }
  if (!body.AppointmentId) return fail("Missing required field(s): AppointmentId");
  return json({ Id: Number(body.AppointmentId), Error: 0, ErrorMsg: "Appointment cancelled successfully" });
}


// ---------------------------------------------------------------- flow-facing endpoints
// One call per flow step for HTTP Request nodes (no token dance, flat fields, the outcome in the
// status code so a success/failed edge can route it). Passcode header instead of the token.

// "Today" is the clinic's calendar day (America/Los_Angeles), not the Worker's UTC clock — the suite
// stamps its dates in the same zone (D-027).
const clinicToday = () => {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const g = (t) => Number(p.find((x) => x.type === t).value);
  return new Date(Date.UTC(g("year"), g("month") - 1, g("day")));
};
const spoken = (d, time) =>
  `${d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" })} at ${time}`;
const flowFail = (msg, status) => json({ Error: 1, ErrorMsg: msg }, status);

function flowLookup(url) {
  const q = url.searchParams;
  const first = q.get("FirstName") ?? "", last = q.get("LastName") ?? "", dob = q.get("DOB") ?? "";
  const steer = steerOf(last);
  if (steer === "notfound") return flowFail("No patient matched the name, date of birth and phone", 404);
  if (steer === "ambiguous") return flowFail("More than one patient matched; cannot verify", 409);
  const p = patient(first, last, dob);
  const today = clinicToday();
  const a1 = appointment(p.MasterId, today);
  const a2 = null; // one missed appointment per patient — the multiple-appointment case is out of scope (D-026)
  const say = (a) => `${spoken(today, a.AppointmentTime)} with ${a.Provider} at ${a.Facility}`;
  return json({
    Error: 0, MasterId: String(p.MasterId), FirstName: p.FirstName, LastName: p.LastName,
    Count: a2 ? 2 : 1,
    // One verbatim sentence for the disclosure, and the pre-selected appointment ("" when the caller must choose).
    Disclosure: a2 ? `your appointment on ${say(a1)}, and another one on ${say(a2)}` : `your appointment on ${say(a1)}`,
    Selected: a2 ? "" : "1",
    Id1: a1.AppointmentId, When1: spoken(today, a1.AppointmentTime), Provider1: a1.Provider, Facility1: a1.Facility,
    Id2: a2 ? a2.AppointmentId : "", When2: a2 ? spoken(today, a2.AppointmentTime) : "", Provider2: a2 ? a2.Provider : "", Facility2: a2 ? a2.Facility : "",
    FacilityId: a1.FacilityId, DepartmentId: a1.DepartmentId, ProviderId: a1.ProviderId, AttributeId: a1.AttributeId,
  });
}

// Which missed appointment: "2" or the caller's own words for the second one; anything else is the first.
const pickWhich = (v) => (/^\s*2\s*$|second|2:15|two fifteen|afternoon|adams|chase|later/i.test(String(v || "")) ? 2 : 1);

function flowSlots(url) {
  const q = url.searchParams;
  const mid = q.get("MasterId") ?? "";
  if (steerOfMasterId(mid) === "noslots") return flowFail("No appointment slots available in that range", 404);
  const start = parseDate(q.get("StartDate")) || clinicToday();
  // Which=2 means the second missed appointment (Dr. Adams at Chase Avenue): slots follow that provider.
  const second = false; // Which is accepted for the published flow but no longer selects anything (D-026)
  const provider = second ? "Dr. Adams" : "Dr. Rismiller", facility = second ? "Chase Avenue FHC" : "Logan Heights Family Health Center";
  const times = second ? ["01:30 PM", "02:15 PM", "04:00 PM"] : ["09:30 AM", "11:00 AM", "03:45 PM"];
  const out = { Error: 0, Count: 3, Provider: provider, Facility: facility };
  const days = nextWeekdays(start, 3);
  // One verbatim sentence for the collector to speak; choices are then just 1, 2, 3.
  out.SlotsSpoken = days.map((d, i) => `option ${i + 1}, ${spoken(d, times[i])}`).join("; ");
  days.forEach((d, i) => {
    const n = i + 1;
    out[`Slot${n}Id`] = 249669 + i;
    out[`Slot${n}When`] = spoken(d, times[i]);
    out[`Slot${n}Date`] = hyphenDate(d);
    out[`Slot${n}Provider`] = provider;
    out[`Slot${n}Facility`] = facility;
  });
  return json(out);
}

async function flowReschedule(req) {
  let b = {};
  try { b = await req.json(); } catch { return flowFail("Request body is not valid JSON", 400); }
  const mid = b.MasterId ?? "";
  if (steerOfMasterId(mid) === "down") return flowFail("Selected slot is no longer available", 502);
  // Which missed appointment is being moved: 1 or 2 (defaults to 1). Echoed back so the flow can speak it.
  const which = 1; // single appointment (D-026)
  // Choice is an index (1-3) or the chosen slot's own text (a choice collector records the label).
  let n = Number(b.Choice);
  if (!(n >= 1 && n <= 3)) n = [1, 2, 3].find((i) => b[`Slot${i}When`] && String(b.Choice).trim().toLowerCase() === String(b[`Slot${i}When`]).trim().toLowerCase()) || 0;
  if (!n) return flowFail(`Choice must be 1, 2, 3 or one of the offered slots, got "${b.Choice}"`, 400);
  if (!b[`Slot${n}Id`] || !b[`Slot${n}Date`]) return flowFail(`Slot${n}Id and Slot${n}Date are required`, 400);
  return json({
    Error: 0, Id: Number(mid) || 100177654,
    BookedWhen: b[`Slot${n}When`] || "", BookedDate: b[`Slot${n}Date`], Moved: which,
    Provider: which === 2 ? "Dr. Adams" : "Dr. Rismiller", Facility: which === 2 ? "Chase Avenue FHC" : "Logan Heights Family Health Center",
  });
}

// ---------------------------------------------------------------- router

export default {
  async fetch(request) {
    try {
      const url = new URL(request.url);
      const path = url.pathname.replace(/\/+$/, "");
      const method = request.method.toUpperCase();

      if (method === "POST" && path === "/api/ExternalAccess/AuthenticateVendor") {
        if (request.headers.get("fhcsd-external-passcode") !== PASSCODE)
          return fail("Invalid vendor passcode", 401);
        return json([{ VendorToken: mintToken() }]);
      }

      // Flow-facing routes: passcode header, no token; outcome in the status code.
      if (path.startsWith("/api/Flow/")) {
        if (request.headers.get("fhcsd-external-passcode") !== PASSCODE)
          return flowFail("Invalid vendor passcode", 401);
        if (method === "GET" && path === "/api/Flow/Lookup") return flowLookup(url);
        if (method === "GET" && path === "/api/Flow/Slots") return flowSlots(url);
        if (method === "POST" && path === "/api/Flow/Reschedule") return flowReschedule(request);
      }

      // Everything below is token-gated.
      if (path.startsWith("/api/Druid/")) {
        const bad = checkToken(request);
        if (bad) return bad;
        // Negative control for the auth path: this steer 401s a Druid call whose token is fresh, so
        // a flow that routes it as "no availability" or "no patient" is caught. Real expiry needs no
        // steer — TOKEN_TTL_SECONDS enforces it on any flow that caches.
        const who = url.searchParams.get("LastName") ?? url.searchParams.get("MasterId") ?? "";
        const steer = STEER[ALIAS[who.trim().toLowerCase()] || who.trim().toLowerCase()]
          ? steerOf(who) : steerOfMasterId(who);
        if (steer === "expiredtoken")
          return fail("Vendor token expired — authenticate immediately before every request", 401);
      }

      if (method === "GET" && path === "/api/Druid/GetPatients") return getPatients(url);
      if (method === "GET" && path === "/api/Druid/GetPatientAppointments")
        return getPatientAppointments(url);
      if (method === "GET" && path === "/api/Druid/GetAvailableAppointments")
        return getAvailableAppointments(url);
      if (method === "POST" && path === "/api/Druid/SaveAppointment")
        return saveAppointment(request);
      if (method === "POST" && path === "/api/Druid/CancelAppointment")
        return cancelAppointment(request);

      // Unrouted paths are the one place a non-2xx is correct: it is our bug, not the flow's.
      return fail(`No mock route for ${method} ${path}`, 404);
    } catch (err) {
      // Never 5xx: a mock crash must not read as an agent failure.
      return fail(`Mock internal error: ${err && err.message ? err.message : String(err)}`);
    }
  },
};
