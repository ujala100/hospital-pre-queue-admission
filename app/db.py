import sqlite3

# Schema follows what Archit confirmed:
#   bookings: id (PK), hospital_id, patient_name
#   pre_admissions.booking_id -> bookings.id (FK), max 1 active entry per booking
#   priority is 1-5, expected_arrival_time exists
# The bookings table below is a STAND-IN so this module runs on its own.
# In the real portal, drop it and use the existing bookings table.
SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id   TEXT NOT NULL,
    patient_name  TEXT NOT NULL            -- synthetic data only
);

CREATE TABLE IF NOT EXISTS pre_admissions (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id             INTEGER NOT NULL REFERENCES bookings(id),
    hospital_id            TEXT NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'expected'
        CHECK (status IN ('expected','arrived','admitted','cancelled')),
    priority               INTEGER CHECK (priority BETWEEN 1 AND 5),
    expected_arrival_time  TEXT,
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- max 1 active pre-admission per booking (enforced by the database too)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_pre_admission
    ON pre_admissions(booking_id)
    WHERE status IN ('expected','arrived','admitted');

CREATE INDEX IF NOT EXISTS idx_pre_admissions_hospital
    ON pre_admissions(hospital_id, status);
"""


def create_db(path=":memory:"):
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    db.commit()
    return db
