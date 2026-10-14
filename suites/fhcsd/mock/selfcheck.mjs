/**
 * One check, two modes.
 *
 *   node selfcheck.mjs                      -> calls worker.js's fetch directly, no network
 *   node selfcheck.mjs https://x.workers.dev -> same assertions against the deployed Worker
 *
 * Same assertions either way, so "it passed locally" and "it passed deployed" mean the same thing.
 * Exit code is the result: 0 iff every assertion held.
 */
import worker from "./worker.js";

const BASE = process.argv[2] || null;
const PASS = "change-me";
let failures = 0;

async function call(method, path, { headers = {}, body } = {}) {
  const url = (BASE || "https://mock.local") + path;
  const init = { method, headers };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { ...headers, "content-type": "application/json" };
  }
  const res = BASE ? await fetch(url, init) : await worker.fetch(new Request(url, init));
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* leave null */ }
  return { status: res.status, json, text };
}

function check(name, cond, detail = "") {
  if (cond) { console.log(`  ok    ${name}`); return; }
  failures++;
  console.log(`  FAIL  ${name}${detail ? `\n          ${detail}` : ""}`);
}

async function auth() {
  const r = await call("POST", "/api/ExternalAccess/AuthenticateVendor", {
    headers: { "fhcsd-external-passcode": PASS },
  });
  return r.json?.[0]?.VendorToken;
}

const hdr = (t) => ({ "fhcsd-external-access-token": t, "x-my-authentication-token": t });

async function main() {
  console.log(BASE ? `checking deployed ${BASE}` : "checking worker.js in-process");

  console.log("\nauth");
  const bad = await call("POST", "/api/ExternalAccess/AuthenticateVendor", {
    headers: { "fhcsd-external-passcode": "wrong" },
  });
  check("wrong passcode is rejected", bad.status === 401 && bad.json?.Error === 1);
  const tok = await auth();
  check("token is minted", typeof tok === "string" && tok.startsWith("MOCK."), `got ${tok}`);
  const stale = await call("GET", "/api/Druid/GetPatients?FirstName=A&LastName=B", {
    headers: hdr("MOCK.1"),
  });
  check("an expired token is rejected", stale.status === 401,
        `status ${stale.status} ${stale.text.slice(0, 90)}`);
  const noTok = await call("GET", "/api/Druid/GetPatients?FirstName=A&LastName=B");
  check("a missing token is rejected", noTok.status === 401);

  console.log("\nGetPatients — steered by LastName");
  const p = async (last, dob = "02/18/1977") =>
    (await call("GET",
      `/api/Druid/GetPatients?FirstName=Carlos&LastName=${last}&DOB=${encodeURIComponent(dob)}&Phone=6195551001`,
      { headers: hdr(await auth()) })).json;
  const happy = await p("Rivera");
  check("happy path returns exactly one patient", Array.isArray(happy) && happy.length === 1,
        JSON.stringify(happy)?.slice(0, 120));
  check("that patient carries a MasterId", !!happy?.[0]?.MasterId);
  check("Notfound returns zero patients", (await p("Notfound")).length === 0);
  check("Ambiguous returns two patients", (await p("Ambiguous")).length === 2);
  check("an unparseable DOB returns zero patients", (await p("Rivera", "Feb 18th")).length === 0);

  console.log("\nGetPatientAppointments");
  const appts = async (last) => {
    const one = (await p(last))[0] ?? (await p("Rivera"))[0];
    const mid = last.toLowerCase() === "notfound"
      ? (await call("GET", `/api/Druid/GetPatients?FirstName=X&LastName=Rivera&DOB=02/18/1977`,
          { headers: hdr(await auth()) })).json[0].MasterId
      : one.MasterId;
    return { mid, list: (await call("GET", `/api/Druid/GetPatientAppointments?MasterId=${mid}`,
      { headers: hdr(await auth()) })).json };
  };
  const a1 = await appts("Rivera");
  check("happy path returns one appointment", a1.list.length === 1, JSON.stringify(a1.list).slice(0, 140));
  check("AppointmentDate is MM/DD/YYYY", /^\d{2}\/\d{2}\/\d{4}$/.test(a1.list[0]?.AppointmentDate),
        a1.list[0]?.AppointmentDate);
  check("it carries the ids the reschedule reuses",
        ["AppointmentId", "FacilityId", "DepartmentId", "ProviderId", "AttributeId"]
          .every((k) => a1.list[0]?.[k] !== undefined));
  const a2 = await appts("Twoappts");
  // D-026: the multiple-appointment case is out of scope — every patient has exactly one.
  check("Whitfield (formerly two appointments) now returns exactly one", a2.list.length === 1);

  console.log("\nGetAvailableAppointments");
  const slots = async (mid) => (await call("GET",
    `/api/Druid/GetAvailableAppointments?MasterId=${mid}&FacilityId=126&DepartmentId=11` +
    `&ProviderId=7&StartDate=09-01-2026&EndDate=09-30-2026&AttributeId=6&ApptTypeId=0&AppointmentId=900001`,
    { headers: hdr(await auth()) })).json;
  const s1 = await slots(a1.mid);
  check("happy path returns three slots", s1.length === 3, `got ${s1.length}`);
  check("ApptDate is MM-DD-YYYY, not MM/DD/YYYY", /^\d{2}-\d{2}-\d{4}$/.test(s1[0]?.ApptDate),
        s1[0]?.ApptDate);
  check("slots are weekdays only",
        s1.every((s) => { const [m, d, y] = s.ApptDate.split("-").map(Number);
          const w = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); return w !== 0 && w !== 6; }),
        s1.map((s) => s.ApptDate).join(" "));
  const sNone = await slots((await appts("Noslots")).mid);
  check("Noslots returns zero slots", sNone.length === 0);

  console.log("\nSaveAppointment — the success-reading contract");
  const save = async (mid, over = {}) => call("POST", "/api/Druid/SaveAppointment", {
    headers: hdr(await auth()),
    body: { AppointmentId: 900001, AppointmentDate: "09-03-2026", DepartmentId: 11, FacilityId: 126,
            FromSlotId: 103, MasterId: mid, ProvScheduleId: 249669,
            Notes: "Appointment rescheduled via Plivo voicebot", AttributeId: 6, VisitTypeId: 0,
            AppointmentReminder: 1, ...over },
  });
  const ok = await save(a1.mid);
  check("a good booking is 2xx with Error 0",
        ok.status >= 200 && ok.status < 300 && ok.json?.Error === 0, `${ok.status} ${ok.text.slice(0, 90)}`);
  const down = await save((await appts("Down")).mid);
  check("Down is 200 with Error 1 — a 2xx that is NOT a success",
        down.status === 200 && down.json?.Error === 1, `${down.status} ${down.text.slice(0, 90)}`);
  const slash = await save(a1.mid, { AppointmentDate: "09/03/2026" });
  check("a slash AppointmentDate is rejected (the two-date-format trap)", slash.json?.Error === 1,
        slash.text.slice(0, 110));
  const short = await save(a1.mid, { ProvScheduleId: "" });
  check("a missing required field is rejected", short.json?.Error === 1);

  console.log("\nnever 5xx");
  const nope = await call("GET", "/api/Druid/Nope", { headers: hdr(await auth()) });
  check("an unknown route is 404 with a valid failure body",
        nope.status === 404 && nope.json?.Error === 1);
  const badBody = await call("POST", "/api/Druid/SaveAppointment", { headers: hdr(await auth()) });
  check("a bodyless POST does not 5xx", badBody.status < 500, `status ${badBody.status}`);

  console.log(`\n${failures === 0 ? "PASS" : `FAIL — ${failures} assertion(s)`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("selfcheck crashed:", e); process.exit(2); });
