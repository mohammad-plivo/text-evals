# FHCSD mock API — everything you need to write a Hunter test against it

Base URL: `https://fhcsd-mock.<your-account>.workers.dev`
Stands in for the FHCSD vendor API (`service.fhcsd.org` — the real EHR; never test against that).
It is a Cloudflare Worker, always on, no state. Every response below was captured live on
2026-08-28.

## The one idea that matters

**The patient's LAST NAME picks the backend branch.** No setup, no data seeding — a test chooses
its scenario by the surname it sends:

| LastName | GetPatients returns | downstream effect |
|---|---|---|
| **anything else** (Rivera, Alvarez, …) | 1 patient | happy path — appointment found, 3 slots, booking succeeds |
| **Tran** (or `Notfound`) | `[]` | verification can never succeed |
| **Delacroix** (or `Ambiguous`) | 2 patients | no unique match — agent must not guess |
| **Whitfield** (or `Twoappts`) | 1 patient, **2 appointments same day** | agent must disambiguate |
| **Kowalski** (or `Noslots`) | 1 patient, but **0 available slots** | no availability path |
| **Ferreira** (or `Down`) | 1 patient, but **SaveAppointment returns `Error: 1`** | booking-failure path (the prod bug shape) |

First names are free; any DOB that parses is accepted (a nonsense DOB like "Feb 18th" → `[]`).
MasterId is a stable hash of the surname, so the steering survives across the whole call chain.

## Auth — two quirks a test must respect

```
POST /api/ExternalAccess/AuthenticateVendor
Header: fhcsd-external-passcode: change-me
→ 200  [{"VendorToken":"MOCK.1787939956812"}]        (a JSON ARRAY — read [0].VendorToken)
```

1. **The token expires in 30 seconds** (same as the real vendor API). Authenticate fresh before
   every request; a cached token gets an explicit 401.
2. Send the token on **both** headers, same value:
   `fhcsd-external-access-token: <token>` and `x-my-authentication-token: <token>`.

## Endpoints, with live request → response pairs

### 1. GET /api/Druid/GetPatients?FirstName=&LastName=&DOB=&Phone=
DOB format **MM/DD/YYYY**. Phone: 10 digits, optional.

```
?FirstName=Carlos&LastName=Rivera&DOB=02/18/1977&Phone=6195551001
→ [{"MasterId":"437638752","FirstName":"Carlos","LastName":"Rivera","DOB":"02/18/1977",
    "Phone":"6195551001","Gender":"U"}]

?FirstName=Linda&LastName=Tran&DOB=03/09/1980          → []            (no match)
?FirstName=Sophie&LastName=Delacroix&DOB=01/22/1970    → [ {...}, {...} ]   (two matches)
```

### 2. GET /api/Druid/GetPatientAppointments?MasterId=
The missed appointment is always dated **TODAY** (the flow's brief is "missed earlier the same
day") — so a Hunter scenario's `missed_appointment_date` must be today's date, MM/DD/YYYY.

```
?MasterId=437638752
→ [{"AppointmentId":900001,"MasterId":"437638752","AppointmentDate":"08/28/2026",
    "AppointmentTime":"10:30 AM","Provider":"Dr. Rismiller","ProviderId":7,
    "Facility":"Logan Heights Family Health Center","FacilityId":126,
    "Department":"General Medicine","DepartmentId":11,"AttributeId":6}]
```

Whitfield returns TWO on the same date — the second is `02:15 PM, Dr. Adams, Chase Avenue FHC`.

### 3. GET /api/Druid/GetAvailableAppointments?MasterId=&FacilityId=&DepartmentId=&ProviderId=&StartDate=&EndDate=&AttributeId=&ApptTypeId=0&AppointmentId=
StartDate/EndDate format **MM-DD-YYYY** — hyphens. ⚠️ This deliberately differs from the DOB
format; mixing them is the documented silent breakage in the real API.

Returns the next 3 weekday slots from StartDate, all `Dr. Rismiller` at `Logan Heights Family
Health Center`, TimeSlots `09:30 AM`, `11:00 AM`, `03:45 PM`. Kowalski → `[]`.

### 4. POST /api/Druid/SaveAppointment   (Content-Type: application/json)

```json
{"AppointmentId":900001,"AppointmentDate":"08-31-2026","DepartmentId":11,"FacilityId":126,
 "FromSlotId":103,"MasterId":"437638752","ProvScheduleId":249669,"Notes":"...",
 "AttributeId":6,"VisitTypeId":0,"AppointmentReminder":1}
```

```
happy    → 200 {"Id":437638752,"Error":0,"ErrorMsg":"Appointment created successfully"}
Ferreira → 200 {"Id":0,"Error":1,"ErrorMsg":"Selected slot is no longer available"}
```

🚨 **Success = a 2xx AND `Error == 0`. The Ferreira response is a 200 that is NOT a success.**
This is deliberate: the live prod agent gates on HTTP status alone and reports bookings backwards.
Any judge criterion about booking must key off what the agent CLAIMS vs this body, never the HTTP
code. A slash-formatted `AppointmentDate` (08/31/2026) is rejected with `Error: 1` on purpose.

The mock never returns 5xx — an internal error comes back as a valid `{"Error":1}` body, so a mock
bug can never be mistaken for an agent failure.

## Using it from a Hunter scenario

The flow under test is **FHCSD OB** `7dd1a9aa-b1a4-4a10-9ba5-f5ba135abfdc` on dev; its actions
already point at this mock. A Hunter outbound scenario only needs:

```
POST https://dev-runner-service.contactodev.com/v1/account/<AUTH_ID>/flow/7dd1a9aa-b1a4-4a10-9ba5-f5ba135abfdc
{
  "from_number": "+12813056522",              ← must be E.164 AND owned by the Plivo account
  "phone_number": "{{INBOUND_NUMBER}}",
  "patient_first_name": "Carlos",
  "patient_last_name": "Rivera",              ← the steering knob (table above)
  "missed_appointment_date": "MM/DD/YYYY of TODAY"
}
```

No Authorization header — the flow's trigger has auth off. Existing worked examples: the 18
scenarios in Hunter category **"FHCSD v2.5 tests"** (ids 17728–17745).

Verify the mock any time: `node selfcheck.mjs https://fhcsd-mock.<your-account>.workers.dev`
(24 assertions, exit 0 = healthy). Source: `FHCSD/mock/worker.js`.
