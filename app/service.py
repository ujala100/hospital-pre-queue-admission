"""Business logic, kept separate from Flask so it is easy to test.
Every function returns (http_status, body)."""
import sqlite3
from datetime import datetime

from .transitions import STATUSES, can_transition

ACTIVE = ("expected", "arrived", "admitted")


def _is_int(value):
    # bool is a subclass of int in Python, so exclude it explicitly
    return isinstance(value, int) and not isinstance(value, bool)


def _same_hospital(a, b):
    return str(a) == str(b)


def _valid_datetime(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _row(db, pre_admission_id):
    row = db.execute("SELECT * FROM pre_admissions WHERE id = ?", (pre_admission_id,)).fetchone()
    return dict(row) if row else None


def create_pre_admission(db, user, data):
    data = data if isinstance(data, dict) else {}
    booking_id = data.get("booking_id")
    priority = data.get("priority")
    arrival = data.get("expected_arrival_time")

    if not _is_int(booking_id) or booking_id < 1:
        return 400, {"error": "booking_id must be a positive integer"}
    if priority is not None and not (_is_int(priority) and 1 <= priority <= 5):
        return 400, {"error": "priority must be an integer from 1 to 5"}
    if arrival is not None and not _valid_datetime(arrival):
        return 400, {"error": "expected_arrival_time must be a valid date-time string"}

    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    # Same 404 for "missing" and "other hospital's" so existence is not leaked.
    if booking is None or not _same_hospital(booking["hospital_id"], user["hospital_id"]):
        return 404, {"error": "Booking not found"}

    placeholders = ",".join("?" * len(ACTIVE))
    dup = db.execute(
        f"SELECT id FROM pre_admissions WHERE booking_id = ? AND status IN ({placeholders})",
        (booking_id, *ACTIVE),
    ).fetchone()
    if dup:
        return 409, {"error": "Active pre-admission already exists for this booking"}

    try:
        cur = db.execute(
            "INSERT INTO pre_admissions (booking_id, hospital_id, priority, expected_arrival_time) "
            "VALUES (?, ?, ?, ?)",
            (booking_id, str(user["hospital_id"]), priority, arrival),
        )
        db.commit()
    except sqlite3.IntegrityError:
        # The unique index is the safety net if two requests race.
        db.rollback()
        return 409, {"error": "Active pre-admission already exists for this booking"}
    return 201, _row(db, cur.lastrowid)


def list_pre_admissions(db, user, status=None):
    if status is not None and status not in STATUSES:
        return 400, {"error": "invalid status filter"}
    hospital = str(user["hospital_id"])
    if status:
        rows = db.execute(
            "SELECT * FROM pre_admissions WHERE hospital_id = ? AND status = ? ORDER BY id",
            (hospital, status),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM pre_admissions WHERE hospital_id = ? ORDER BY id", (hospital,)
        ).fetchall()
    return 200, [dict(r) for r in rows]


def update_status(db, user, pre_admission_id, data):
    if not _is_int(pre_admission_id) or pre_admission_id < 1:
        return 400, {"error": "id must be a positive integer"}
    data = data if isinstance(data, dict) else {}
    new_status = data.get("status")
    if new_status not in STATUSES:
        return 400, {"error": "invalid status"}

    row = _row(db, pre_admission_id)
    if row is None or not _same_hospital(row["hospital_id"], user["hospital_id"]):
        return 404, {"error": "Pre-admission not found"}
    if not can_transition(row["status"], new_status):
        return 422, {"error": f"Cannot move from {row['status']} to {new_status}"}

    db.execute(
        "UPDATE pre_admissions SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (new_status, pre_admission_id),
    )
    db.commit()
    return 200, _row(db, pre_admission_id)


def get_pre_admission(db, user, pre_admission_id):
    if not _is_int(pre_admission_id) or pre_admission_id < 1:
        return 400, {"error": "id must be a positive integer"}
    row = _row(db, pre_admission_id)
    if row is None or not _same_hospital(row["hospital_id"], user["hospital_id"]):
        return 404, {"error": "Pre-admission not found"}
    return 200, row


EDITABLE = ("priority", "expected_arrival_time")
EDITABLE_WHILE = ("expected", "arrived")


def update_pre_admission(db, user, pre_admission_id, data):
    """Edit priority / expected_arrival_time. Status has its own endpoint."""
    if not _is_int(pre_admission_id) or pre_admission_id < 1:
        return 400, {"error": "id must be a positive integer"}
    if not isinstance(data, dict) or not data or set(data) - set(EDITABLE):
        return 400, {"error": "send priority and/or expected_arrival_time only"}
    if "priority" in data and data["priority"] is not None and \
            not (_is_int(data["priority"]) and 1 <= data["priority"] <= 5):
        return 400, {"error": "priority must be an integer from 1 to 5"}
    if "expected_arrival_time" in data and data["expected_arrival_time"] is not None and \
            not _valid_datetime(data["expected_arrival_time"]):
        return 400, {"error": "expected_arrival_time must be a valid date-time string"}

    row = _row(db, pre_admission_id)
    if row is None or not _same_hospital(row["hospital_id"], user["hospital_id"]):
        return 404, {"error": "Pre-admission not found"}
    if row["status"] not in EDITABLE_WHILE:
        return 422, {"error": f"Cannot edit an entry that is {row['status']}"}

    # column names come from the fixed EDITABLE tuple, never from user input
    sets = ", ".join(f"{col} = ?" for col in data)
    db.execute(
        f"UPDATE pre_admissions SET {sets}, updated_at = datetime('now') WHERE id = ?",
        (*data.values(), pre_admission_id),
    )
    db.commit()
    return 200, _row(db, pre_admission_id)


def cancel_pre_admission(db, user, pre_admission_id):
    """DELETE = cancel. The row is kept for the hospital's records."""
    return update_status(db, user, pre_admission_id, {"status": "cancelled"})


def replace_pre_admission(db, user, pre_admission_id, data):
    """PUT: replace the editable fields (priority, expected_arrival_time).
    Fields left out are reset to null. booking_id and status cannot be changed
    here (status changes go through PATCH)."""
    if not _is_int(pre_admission_id) or pre_admission_id < 1:
        return 400, {"error": "id must be a positive integer"}
    if not isinstance(data, dict):
        return 400, {"error": "JSON body required"}
    priority = data.get("priority")
    arrival = data.get("expected_arrival_time")
    if priority is not None and not (_is_int(priority) and 1 <= priority <= 5):
        return 400, {"error": "priority must be an integer from 1 to 5"}
    if arrival is not None and not _valid_datetime(arrival):
        return 400, {"error": "expected_arrival_time must be a valid date-time string"}

    row = _row(db, pre_admission_id)
    if row is None or not _same_hospital(row["hospital_id"], user["hospital_id"]):
        return 404, {"error": "Pre-admission not found"}
    if row["status"] in ("admitted", "cancelled"):
        return 422, {"error": f"Cannot edit an entry that is {row['status']}"}

    db.execute(
        "UPDATE pre_admissions SET priority = ?, expected_arrival_time = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (priority, arrival, pre_admission_id),
    )
    db.commit()
    return 200, _row(db, pre_admission_id)

