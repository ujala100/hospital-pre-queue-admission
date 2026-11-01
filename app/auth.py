"""STUB auth. The real portal already has auth that exposes the logged-in staff
member's hospital ID (Archit: user.hospital_id). Replace `require_staff` in
app/__init__.py with that existing middleware. This stub reads headers so the
hospital scoping can be tested without the real auth."""
from flask import g, jsonify, request


def require_staff():
    hospital_id = request.headers.get("x-hospital-id")
    role = request.headers.get("x-role")
    if not hospital_id or role != "staff":
        return jsonify({"error": "Forbidden"}), 403
    g.user = {"hospital_id": hospital_id, "role": role}
    return None
