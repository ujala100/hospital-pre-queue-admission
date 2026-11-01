from flask import Blueprint, current_app, g, jsonify, request

from . import service

bp = Blueprint("pre_admissions", __name__, url_prefix="/api/hospital/pre-admissions")


def _db():
    return current_app.config["DB"]


# POST /api/hospital/pre-admissions
@bp.post("")
def create():
    status, body = service.create_pre_admission(_db(), g.user, request.get_json(silent=True))
    return jsonify(body), status


# GET /api/hospital/pre-admissions?status=expected
@bp.get("")
def list_all():
    status, body = service.list_pre_admissions(_db(), g.user, request.args.get("status"))
    return jsonify(body), status


# PATCH /api/hospital/pre-admissions/<id>/status
@bp.patch("/<int:pre_admission_id>/status")
def change_status(pre_admission_id):
    status, body = service.update_status(
        _db(), g.user, pre_admission_id, request.get_json(silent=True)
    )
    return jsonify(body), status


# GET /api/hospital/pre-admissions/<id>
@bp.get("/<int:pre_admission_id>")
def get_one(pre_admission_id):
    status, body = service.get_pre_admission(_db(), g.user, pre_admission_id)
    return jsonify(body), status


# PATCH /api/hospital/pre-admissions/<id>   (edit priority / expected_arrival_time)
@bp.patch("/<int:pre_admission_id>")
def update(pre_admission_id):
    status, body = service.update_pre_admission(
        _db(), g.user, pre_admission_id, request.get_json(silent=True)
    )
    return jsonify(body), status


# DELETE /api/hospital/pre-admissions/<id>   (cancels the entry; row is kept)
@bp.delete("/<int:pre_admission_id>")
def delete(pre_admission_id):
    status, body = service.cancel_pre_admission(_db(), g.user, pre_admission_id)
    return jsonify(body), status


# PUT /api/hospital/pre-admissions/<id>
@bp.put("/<int:pre_admission_id>")
def replace(pre_admission_id):
    status, body = service.replace_pre_admission(
        _db(), g.user, pre_admission_id, request.get_json(silent=True)
    )
    return jsonify(body), status

