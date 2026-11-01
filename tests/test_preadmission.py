import sqlite3

import pytest

from app import create_app
from app.db import create_db

A = {"x-hospital-id": "H1", "x-role": "staff"}
B = {"x-hospital-id": "H2", "x-role": "staff"}
URL = "/api/hospital/pre-admissions"


@pytest.fixture
def db():
    db = create_db()  # fresh in-memory database per test
    db.executemany(
        "INSERT INTO bookings (hospital_id, patient_name) VALUES (?, ?)",
        [("H1", "Test Patient One"), ("H2", "Test Patient Two")],  # booking 1 -> H1, 2 -> H2
    )
    db.commit()
    return db


@pytest.fixture
def client(db):
    return create_app(db).test_client()


def create(client, headers=A, body=None):
    body = {"booking_id": 1, "priority": 3} if body is None else body
    return client.post(URL, headers=headers, json=body)


def patch(client, pre_id, status, headers=A):
    return client.patch(f"{URL}/{pre_id}/status", headers=headers, json={"status": status})


# ---------- create ----------
def test_creates_entry_for_valid_booking(client):
    res = create(client, A, {"booking_id": 1, "priority": 5,
                             "expected_arrival_time": "2026-11-01T10:30:00Z"})
    assert res.status_code == 201
    body = res.get_json()
    assert body["booking_id"] == 1
    assert body["hospital_id"] == "H1"
    assert body["status"] == "expected"
    assert body["priority"] == 5
    assert body["expected_arrival_time"] == "2026-11-01T10:30:00Z"


def test_priority_and_arrival_time_are_optional(client):
    res = create(client, A, {"booking_id": 1})
    assert res.status_code == 201
    assert res.get_json()["priority"] is None


@pytest.mark.parametrize("body", [{"booking_id": "abc"}, {}, {"booking_id": -1},
                                  {"booking_id": True}, {"booking_id": 1.5}])
def test_rejects_invalid_booking_ids(client, body):
    assert create(client, A, body).status_code == 400


def test_rejects_non_json_body(client):
    res = client.post(URL, headers=A, data="not json", content_type="text/plain")
    assert res.status_code == 400


def test_unknown_booking_returns_404(client):
    assert create(client, A, {"booking_id": 999}).status_code == 404


@pytest.mark.parametrize("priority", [0, 6, 2.5, "high", True])
def test_rejects_invalid_priority(client, priority):
    assert create(client, A, {"booking_id": 1, "priority": priority}).status_code == 400


def test_rejects_invalid_arrival_time(client):
    assert create(client, A, {"booking_id": 1, "expected_arrival_time": "soon"}).status_code == 400


# ---------- duplicates ----------
def test_rejects_second_active_entry_for_same_booking(client):
    create(client)
    assert create(client).status_code == 409


def test_allows_new_entry_after_cancelled(client):
    first = create(client).get_json()
    patch(client, first["id"], "cancelled")
    assert create(client).status_code == 201


def test_database_unique_index_blocks_duplicates(db):
    sql = "INSERT INTO pre_admissions (booking_id, hospital_id) VALUES (1, 'H1')"
    db.execute(sql)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql)


def test_database_rejects_bad_priority_status_and_unknown_booking(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO pre_admissions (booking_id, hospital_id, priority) VALUES (1,'H1',9)")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO pre_admissions (booking_id, hospital_id, status) VALUES (1,'H1','bogus')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO pre_admissions (booking_id, hospital_id) VALUES (999,'H1')")


# ---------- transitions ----------
def test_valid_transitions_persist(client):
    pre = create(client).get_json()
    assert patch(client, pre["id"], "arrived").status_code == 200
    assert patch(client, pre["id"], "admitted").status_code == 200

    listed = client.get(f"{URL}?status=admitted", headers=A).get_json()
    assert len(listed) == 1
    assert listed[0]["id"] == pre["id"]


def test_expected_can_be_cancelled(client):
    pre = create(client).get_json()
    res = patch(client, pre["id"], "cancelled")
    assert res.status_code == 200
    assert res.get_json()["status"] == "cancelled"


def test_rejects_invalid_transitions_with_422(client):
    pre = create(client).get_json()
    assert patch(client, pre["id"], "admitted").status_code == 422   # skips arrived
    assert patch(client, pre["id"], "expected").status_code == 422   # same status
    patch(client, pre["id"], "cancelled")
    assert patch(client, pre["id"], "arrived").status_code == 422    # cancelled is final


def test_admitted_is_final(client):
    pre = create(client).get_json()
    patch(client, pre["id"], "arrived")
    patch(client, pre["id"], "admitted")
    assert patch(client, pre["id"], "cancelled").status_code == 422
    assert patch(client, pre["id"], "arrived").status_code == 422


def test_rejects_unknown_status_bad_id_and_missing_id(client):
    pre = create(client).get_json()
    assert patch(client, pre["id"], "discharged").status_code == 400
    assert client.patch(f"{URL}/abc/status", headers=A, json={"status": "arrived"}).status_code == 404
    assert patch(client, 9999, "arrived").status_code == 404


# ---------- list ----------
def test_lists_entries_and_filters_by_status(client):
    pre = create(client).get_json()
    patch(client, pre["id"], "arrived")
    assert len(client.get(URL, headers=A).get_json()) == 1
    assert len(client.get(f"{URL}?status=expected", headers=A).get_json()) == 0
    assert len(client.get(f"{URL}?status=arrived", headers=A).get_json()) == 1


def test_rejects_invalid_status_filter(client):
    assert client.get(f"{URL}?status=bogus", headers=A).status_code == 400


# ---------- hospital scoping and auth ----------
def test_other_hospital_cannot_create_see_or_change(client):
    pre = create(client).get_json()                       # H1's entry
    assert create(client, B, {"booking_id": 1}).status_code == 404
    assert client.get(URL, headers=B).get_json() == []
    assert patch(client, pre["id"], "arrived", B).status_code == 404
    # H1's entry is untouched
    assert len(client.get(f"{URL}?status=expected", headers=A).get_json()) == 1


def test_rejects_requests_without_staff_headers(client):
    assert client.get(URL).status_code == 403
    assert client.post(URL, json={"booking_id": 1}).status_code == 403
    not_staff = {"x-hospital-id": "H1", "x-role": "patient"}
    assert client.get(URL, headers=not_staff).status_code == 403


# ---------- swagger docs ----------
def test_swagger_docs_available_without_auth(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").get_json()
    assert spec["openapi"].startswith("3.")
    assert "/api/hospital/pre-admissions" in spec["paths"]
    assert "/api/hospital/pre-admissions/{id}/status" in spec["paths"]


def test_root_redirects_to_docs(client):
    res = client.get("/")
    assert res.status_code == 302 and res.headers["Location"].endswith("/docs")


# ---------- get one / edit / delete ----------
def edit(client, pre_id, body, headers=A):
    return client.patch(f"{URL}/{pre_id}", headers=headers, json=body)


def test_get_one_entry(client):
    pre = create(client).get_json()
    res = client.get(f"{URL}/{pre['id']}", headers=A)
    assert res.status_code == 200 and res.get_json()["id"] == pre["id"]
    assert client.get(f"{URL}/9999", headers=A).status_code == 404
    assert client.get(f"{URL}/{pre['id']}", headers=B).status_code == 404


def test_edit_priority_and_arrival_time_persist(client):
    pre = create(client).get_json()
    res = edit(client, pre["id"], {"priority": 1, "expected_arrival_time": "2026-11-02T08:00:00Z"})
    assert res.status_code == 200
    saved = client.get(f"{URL}/{pre['id']}", headers=A).get_json()
    assert saved["priority"] == 1
    assert saved["expected_arrival_time"] == "2026-11-02T08:00:00Z"
    assert saved["status"] == "expected"


def test_edit_can_clear_priority(client):
    pre = create(client).get_json()
    assert edit(client, pre["id"], {"priority": None}).get_json()["priority"] is None


@pytest.mark.parametrize("body", [{}, {"status": "arrived"}, {"booking_id": 2},
                                  {"priority": 0}, {"priority": 6}, {"priority": "x"},
                                  {"expected_arrival_time": "soon"}])
def test_edit_rejects_invalid_bodies(client, body):
    pre = create(client).get_json()
    assert edit(client, pre["id"], body).status_code == 400


def test_edit_not_allowed_once_admitted_or_cancelled(client):
    pre = create(client).get_json()
    patch(client, pre["id"], "arrived")
    assert edit(client, pre["id"], {"priority": 2}).status_code == 200   # arrived is editable
    patch(client, pre["id"], "admitted")
    assert edit(client, pre["id"], {"priority": 3}).status_code == 422


def test_edit_cancelled_entry_rejected(client):
    pre = create(client).get_json()
    patch(client, pre["id"], "cancelled")
    assert edit(client, pre["id"], {"priority": 3}).status_code == 422


def test_edit_other_hospital_and_missing(client):
    pre = create(client).get_json()
    assert edit(client, pre["id"], {"priority": 2}, B).status_code == 404
    assert edit(client, 9999, {"priority": 2}).status_code == 404
    assert client.get(f"{URL}/{pre['id']}", headers=A).get_json()["priority"] == 3  # unchanged


def test_delete_cancels_entry_and_keeps_row(client):
    pre = create(client).get_json()
    res = client.delete(f"{URL}/{pre['id']}", headers=A)
    assert res.status_code == 200 and res.get_json()["status"] == "cancelled"
    kept = client.get(f"{URL}?status=cancelled", headers=A).get_json()
    assert [r["id"] for r in kept] == [pre["id"]]
    assert create(client).status_code == 201          # booking can be queued again


def test_delete_rules(client):
    pre = create(client).get_json()
    assert client.delete(f"{URL}/{pre['id']}", headers=B).status_code == 404   # other hospital
    assert client.delete(f"{URL}/9999", headers=A).status_code == 404
    patch(client, pre["id"], "arrived")
    patch(client, pre["id"], "admitted")
    assert client.delete(f"{URL}/{pre['id']}", headers=A).status_code == 422   # admitted is final
    assert client.delete(URL + "/1", headers={}).status_code == 403            # no auth


def test_delete_twice_is_rejected(client):
    pre = create(client).get_json()
    client.delete(f"{URL}/{pre['id']}", headers=A)
    assert client.delete(f"{URL}/{pre['id']}", headers=A).status_code == 422


# ---------- PUT ----------
def put(client, pre_id, body, headers=A):
    return client.put(f"{URL}/{pre_id}", headers=headers, json=body)


def test_put_replaces_priority_and_arrival_time(client):
    pre = create(client, A, {"booking_id": 1, "priority": 3,
                             "expected_arrival_time": "2026-11-01T10:00:00Z"}).get_json()
    res = put(client, pre["id"], {"priority": 1, "expected_arrival_time": "2026-11-02T09:00:00Z"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["priority"] == 1
    assert body["expected_arrival_time"] == "2026-11-02T09:00:00Z"
    assert body["status"] == "expected" and body["booking_id"] == 1
    # persisted
    assert client.get(URL, headers=A).get_json()[0]["priority"] == 1


def test_put_omitted_fields_are_reset_and_status_ignored(client):
    pre = create(client, A, {"booking_id": 1, "priority": 3}).get_json()
    res = put(client, pre["id"], {"status": "admitted"})
    assert res.status_code == 200
    assert res.get_json()["priority"] is None
    assert res.get_json()["status"] == "expected"


def test_put_validation(client):
    pre = create(client).get_json()
    assert put(client, pre["id"], {"priority": 9}).status_code == 400
    assert put(client, pre["id"], {"expected_arrival_time": "soon"}).status_code == 400
    r = client.put(f"{URL}/{pre['id']}", headers=A, data="x", content_type="text/plain")
    assert r.status_code == 400
    assert put(client, 9999, {"priority": 2}).status_code == 404


def test_put_blocked_for_final_statuses(client):
    pre = create(client).get_json()
    patch(client, pre["id"], "cancelled")
    assert put(client, pre["id"], {"priority": 2}).status_code == 422


def test_put_other_hospital_and_no_auth(client):
    pre = create(client).get_json()
    assert put(client, pre["id"], {"priority": 2}, B).status_code == 404
    assert client.put(f"{URL}/{pre['id']}", json={"priority": 2}).status_code == 403


def test_swagger_lists_put_and_delete(client):
    paths = client.get("/openapi.json").get_json()["paths"]
    assert {"put", "delete"} <= set(paths["/api/hospital/pre-admissions/{id}"])
