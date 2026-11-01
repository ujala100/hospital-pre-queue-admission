# Hospital Portal - Pre-admission Queue APIs (Python)

Manages the hospital's pre-admission queue and status changes for incoming
emergency cases. Individual backend task. Built with Python, Flask and SQLite.

> Synthetic/test data only. Never commit real patient data or secrets.

## Run

Windows (Command Prompt):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest        # run the tests
python run.py           # http://localhost:3000 (creates preadmission.db with 3 demo bookings)
```

macOS / Linux: use `source .venv/bin/activate` instead of the activate line above.

## Swagger UI

With `python run.py` running, open http://localhost:3000/docs (the root URL
redirects there). Click **Authorize**, enter `x-hospital-id` = `H1` and
`x-role` = `staff`, then use **Try it out** on any endpoint. The raw spec is at
`/openapi.json`. The Swagger UI files load from a CDN, so the browser needs
internet access. No extra Python packages are needed.

## Schema (confirmed with Archit)

- `bookings`: `id` (PK), `hospital_id`, `patient_name`
  (stand-in table in `app/db.py`; use the portal's real one when merging)
- `pre_admissions`: `id`, `booking_id` (FK to `bookings.id`), `hospital_id`,
  `status`, `priority` (1-5), `expected_arrival_time`, `created_at`, `updated_at`
- At most one active entry per booking (`expected`, `arrived`, `admitted`),
  enforced in the API and by a partial unique index.

## Status transitions

| From        | Allowed next            |
|-------------|-------------------------|
| `expected`  | `arrived`, `cancelled`  |
| `arrived`   | `admitted`, `cancelled` |
| `admitted`  | none (final)            |
| `cancelled` | none (final)            |

## Auth

The portal's real auth provides the logged-in staff member's hospital ID.
`app/auth.py` is a stub that reads headers for local testing. Replace
`require_staff` in `app/__init__.py` with the real middleware. Staff only ever
see and change their own hospital's data.

## API

All requests need `x-hospital-id: H1` and `x-role: staff` headers (stub auth).
The examples below are real responses from a running server.

### POST /api/hospital/pre-admissions

```
curl -X POST localhost:3000/api/hospital/pre-admissions \
  -H "x-hospital-id: H1" -H "x-role: staff" -H "Content-Type: application/json" \
  -d '{"booking_id":1,"priority":4,"expected_arrival_time":"2026-11-01T10:30:00Z"}'
```

`201 Created`
```json
{
  "booking_id": 1, "created_at": "2026-10-31 11:59:18",
  "expected_arrival_time": "2026-11-01T10:30:00Z", "hospital_id": "H1",
  "id": 1, "priority": 4, "status": "expected",
  "updated_at": "2026-10-31 11:59:18"
}
```

Errors: `400` invalid body, `404` booking not found (or belongs to another
hospital), `409` active entry already exists
(`{"error": "Active pre-admission already exists for this booking"}`),
`403` not authorized staff.

### GET /api/hospital/pre-admissions?status=expected

`status` is optional (`expected`, `arrived`, `admitted`, `cancelled`).

```
curl "localhost:3000/api/hospital/pre-admissions?status=expected" \
  -H "x-hospital-id: H1" -H "x-role: staff"
```

`200 OK`
```json
[
  {
    "booking_id": 1, "created_at": "2026-10-31 11:59:18",
    "expected_arrival_time": "2026-11-01T10:30:00Z", "hospital_id": "H1",
    "id": 1, "priority": 4, "status": "expected",
    "updated_at": "2026-10-31 11:59:18"
  }
]
```

Errors: `400` invalid status filter, `403` not authorized.

### PATCH /api/hospital/pre-admissions/:id/status

```
curl -X PATCH localhost:3000/api/hospital/pre-admissions/1/status \
  -H "x-hospital-id: H1" -H "x-role: staff" -H "Content-Type: application/json" \
  -d '{"status":"arrived"}'
```

`200 OK`
```json
{
  "booking_id": 1, "created_at": "2026-10-31 11:59:18",
  "expected_arrival_time": "2026-11-01T10:30:00Z", "hospital_id": "H1",
  "id": 1, "priority": 4, "status": "arrived",
  "updated_at": "2026-10-31 11:59:18"
}
```

Errors: `400` invalid status, `404` not found (or another hospital's, or a
non-numeric id), `422` invalid transition
(`{"error": "Cannot move from arrived to expected"}`).

### GET /api/hospital/pre-admissions/:id

Returns one entry (`200`), or `404` if it does not exist or belongs to another hospital.

### PATCH /api/hospital/pre-admissions/:id

Edit `priority` and/or `expected_arrival_time` (send `null` to clear one).
Only allowed while the status is `expected` or `arrived`.

```
curl -X PATCH localhost:3000/api/hospital/pre-admissions/1 \
  -H "x-hospital-id: H1" -H "x-role: staff" -H "Content-Type: application/json" \
  -d '{"priority":2}'
```

Errors: `400` empty body, unknown field (status and booking_id cannot be edited
here) or invalid value, `404` not found, `422` entry is `admitted` or `cancelled`.

### PUT /api/hospital/pre-admissions/:id

Replaces the editable fields (`priority`, `expected_arrival_time`). Fields left
out are reset to `null`. `booking_id` and `status` cannot be changed here
(use PATCH `/:id/status` for status). Only `expected` and `arrived` entries can
be edited. Use PATCH `/:id` instead if you want to change just one field.

```
curl -X PUT localhost:3000/api/hospital/pre-admissions/1 \
  -H "x-hospital-id: H1" -H "x-role: staff" -H "Content-Type: application/json" \
  -d '{"priority":2,"expected_arrival_time":"2026-11-02T09:00:00Z"}'
```

`200 OK` returns the updated entry. Errors: `400` invalid body, `404` not found
(or another hospital's), `422` entry is admitted or cancelled, `403` not authorized.

### DELETE /api/hospital/pre-admissions/:id

Removes the entry from the queue by **cancelling** it. The row is kept with
status `cancelled` (hospital records are not erased), and the booking can be
queued again afterwards.

```
curl -X DELETE localhost:3000/api/hospital/pre-admissions/1 \
  -H "x-hospital-id: H1" -H "x-role: staff"
```

`200 OK` returns the entry with `"status": "cancelled"`.
Errors: `404` not found, `422` already `admitted` or already `cancelled`.

## Open points to confirm

- `cancelled` allowed from both `expected` and `arrived`?
- Should `admitted` entries still block a new pre-admission for the same booking?
- Type of `hospital_id` in the real schema (stand-in uses TEXT; compared as strings).
- Queue ordering for GET (currently by `id`).
- DELETE currently cancels (soft delete). Does the team want a real row delete instead?
- The task plan lists only POST, GET and PATCH status; GET by id, PATCH edit and DELETE are additions, so agree them with Archit/Mam.
