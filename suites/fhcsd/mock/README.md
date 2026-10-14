# FHCSD vendor-API mock

Stands in for `https://service.fhcsd.org` so the outbound flow can be built and tested without
touching a live EHR. **The real endpoint holds real patient records and is never a test target.**

Why a Cloudflare Worker and not zrok or localhost: D-005. Short version — the flow embeds the base
URL in each action's `code_body`, zrok shares die with the process, and the E2B sandbox that runs
`CUSTOM_CODE` actions cannot reach localhost (`src/tools/action_handler.py:282-284`).

## Deploy

`wrangler` is not installed here; node 24 and npx are. One interactive login, once:

```bash
npx wrangler login          # opens a browser
npx wrangler deploy         # from this directory
```

Then check the deployment with the same assertions the logic already passes offline:

```bash
node selfcheck.mjs                                   # in-process, no network
node selfcheck.mjs https://fhcsd-mock-mk.<acct>.workers.dev
```

Exit 0 iff all 24 assertions hold. Put the resulting URL in `../Decisions.md` and in the five action
bodies of the flow.

## Endpoints

Contracts are from `Admin/Flows/new fhcsd outbound flow.md` §7.

| method | path | notes |
|---|---|---|
| POST | `/api/ExternalAccess/AuthenticateVendor` | header `fhcsd-external-passcode`; returns `[{VendorToken}]` |
| GET | `/api/Druid/GetPatients` | `FirstName`, `LastName`, `DOB` (**MM/DD/YYYY**), `Phone` |
| GET | `/api/Druid/GetPatientAppointments` | `MasterId` |
| GET | `/api/Druid/GetAvailableAppointments` | `StartDate`/`EndDate` (**MM-DD-YYYY**) |
| POST | `/api/Druid/SaveAppointment` | `AppointmentDate` **MM-DD-YYYY** |

Every `/api/Druid/*` call needs the token on **both** headers, `fhcsd-external-access-token` and
`x-my-authentication-token` — the written spec names the first, the worked examples use the second.

## Three deliberate properties

**1. Branches are chosen by the patient's own last name.** A scenario selects its own path; nothing
in this file is edited between runs. (Pattern lifted from `Vapi Flow/mock-clinic/server.py`.)

| `LastName` | what happens | exercises |
|---|---|---|
| `Notfound` | `GetPatients` → `[]` | Verification Failed |
| `Ambiguous` | `GetPatients` → 2 patients | Verification Failed |
| `Twoappts` | 2 appointments, same date | the disambiguation branch (spec Step 3) |
| `Noslots` | `GetAvailableAppointments` → `[]` | No Slots Available |
| `Down` | `SaveAppointment` → `200` + `Error: 1` | API Failure |
| anything else | happy path | Reschedule Complete |

`SaveAppointment` and the two GETs never receive a name, so the steer travels in the `MasterId`:
it is a stable hash of the last name, and the handler recovers the steer from it.

**2. The token really expires after 30 seconds.** A flow that authenticates once at call start and
reuses the token fails here with an explicit message. That is the point — the 08-10 notes call it
the most likely silent breakage, and it is why every existing FHCSD action is named `*_fresh_auth`.
A mock that tolerated caching would let a broken flow pass.

**3. It never returns 5xx.** An internal error becomes a valid FHCSD failure body, so a bug in the
mock can never be read as a defect in the agent. The one exception is an unrouted path, which
returns 404 — that is our mistake, not the flow's, and it should be loud.

## The success convention this exists to test

```json
{ "Id": 100177654, "Error": 0, "ErrorMsg": "Appointment created successfully" }   // success
{ "Id": 0,         "Error": 1, "ErrorMsg": "Selected slot is no longer available" } // failure
```

Success is **a 2xx AND `Error == 0`**, compared numerically. Prod flow `5207aaf5` instead gates on
`status_code == 202`, which is why it books the appointment and then tells the patient it failed
(`Admin/findings/2026-08-09-fhcsd-bug-status-misread.md`). `LastName: Down` reproduces that exact
shape — a 2xx carrying a failure — so the new flow can be proven not to have the bug.

The mock also rejects a slash-formatted `AppointmentDate`, because `DOB` is `MM/DD/YYYY` while
`AppointmentDate`/`StartDate`/`EndDate` are `MM-DD-YYYY`, and mixing them is the other documented
silent breakage.

## Flow-facing endpoints (for HTTP Request nodes) — added 2026-08-29, D-018

Header `fhcsd-external-passcode: <passcode>` instead of the token dance; flat fields; the outcome is the
status code so a `success`/`failed` edge can route it. Same surname steering as the Druid routes.

| endpoint | 200 | non-2xx |
|---|---|---|
| `GET /api/Flow/Lookup?FirstName&LastName&DOB&Phone` | `MasterId, Count (always 1), Disclosure, Selected, Id1, When1, Provider1, Facility1` (Id2/When2/… kept empty for the published response_format) | 404 Tran (no match) · 409 Delacroix (two matches) |
| `GET /api/Flow/Slots?MasterId&StartDate&EndDate` | `Count, Slot{1..3}Id/When/Date/Provider/Facility` | 404 Kowalski (no slots) |
| `POST /api/Flow/Reschedule` `{MasterId, AppointmentId, Choice 1-3, Slot*Id, Slot*Date, Slot*When}` | `Error 0, BookedWhen, Provider, Facility` | 502 Ferreira (booking fails) · 400 bad choice |

The Druid routes are unchanged (custom-code path).

**2026-08-30 (D-026):** the multiple-missed-appointments case is out of scope — every patient has exactly one missed appointment; `Whitfield` no longer steers; `Which` is accepted and ignored.
