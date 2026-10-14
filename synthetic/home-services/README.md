# V2.9 Hunter example flow

A small outbound V2.9 flow for stress-testing the collectors on Hunter: every Input type, and values handed node to node.

```
Start (API) → Screening Contact → Caller Check → Service Request → Booking Confirmation → Booking Complete End
```

| Node | Inputs | Reads from upstream | Exits |
|---|---|---|---|
| Caller Check | `caller_name` (name) | `{{Start.http.params.customer_name}}`, `city` | Caller Confirmed → Service Request · Wrong Person → Wrong Person End |
| Service Request | all 12 types: `service_type` choice · `issue_description` text · `rooms_affected` number · `preferred_visit_date` date · `max_budget` currency · `service_address` address · `gate_code` dtmf (4, optional) · `onsite_contact_name` name · `contact_email` email · `alternate_phone` phone (optional) · `pets_at_home` boolean · `date_of_birth` dob | `{{Caller Check.caller_name}}` | Request Captured → Booking Confirmation · Caller Declines → Declined End · Human Requested → Human Followup End |
| Booking Confirmation | `booking_confirmed` boolean · `reminder_preference` choice (optional) | `{{Service Request.service_type / preferred_visit_date / service_address / onsite_contact_name / contact_email}}` | Booking Confirmed → Booking Complete End · Booking Not Confirmed → Not Confirmed End |

Trigger payload: `caller_id`, `customer_name`, `customer_phone`, `city`. No actions (nothing external fires).

## Files
- `build_flow.py`: the source of truth. `python3 build_flow.py --clipboard` rebuilds and loads the paste. Ids are uuid5, so a rebuild keeps them stable.
- `v29-hunter-example-flow.json`: the builder paste. Node shapes mirror `Sigma/sigma-v29-two-node-flow.json`.
- `validate.py`: checks wiring, `{{…}}` refs and every Input's `collection` against the prod runtime's resolver. Run it as `PYTHONPATH=repos/agent-runner-main repos/agent-runner/.venv/bin/python V29-Hunter-Example/validate.py`. Mutation-checked: it catches a `verify_spelling` key, a typo'd ref and a name-for-id handle.
- `validate_console.ts`: the console's own `reactFlowContentSchema`. Run it from `repos/contacto-console/apps/web` (see the header).

Each Input's type and settings are written as the author's `overrides` with `stale: true`. A node Save or Detect lets the runner refresh the collector `instructions` but keeps every type and setting as built here. The runtime applies the rows as authored even without a node Save.

## After pasting (MK, dev console)
1. New flow → Cmd+V on the canvas → check 12 nodes / 18 edges → Settings → Timezone.
   Start node: **Require Authentication off** (the paste sets it; check it). With it on, every Hunter trigger
   gets `401 Could not verify your access level` and no call is placed (smoke run 56f9c200, 2026-09-24).
2. Flow settings → Event callbacks: HANGUP → Hunter `/webhook/cx/hangup`, RECORDING → `/webhook/cx/recording`. Without them, Hunter can't grade variables.
3. **Save each V2.9 node once in its sidebar, then Publish.** Publishing the raw paste fails with `Caller Check.caller_name is an invalid variable`
   (and the same for the `{{Service Request.…}}` refs): PHLO-core checks every `{{Node.input}}` against the upstream nodes' saved Inputs
   (`config_service/functions.py` `gen_allowed_variables`). A node Save fixed it on 2026-09-24; which field of the pasted node the check
   could not read is unverified.
4. Send the flow uuid; the Hunter scenarios are the next step.
