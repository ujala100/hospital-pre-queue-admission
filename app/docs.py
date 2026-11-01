"""Swagger UI at /docs, backed by an OpenAPI spec at /openapi.json.
No extra Python packages: the spec is a plain dict and the Swagger UI
files load from a CDN (so the browser needs internet access)."""
from flask import Blueprint, jsonify, redirect

bp = Blueprint("docs", __name__)

PRE_ADMISSION = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "example": 1},
        "booking_id": {"type": "integer", "example": 1},
        "hospital_id": {"type": "string", "example": "H1"},
        "status": {"type": "string", "enum": ["expected", "arrived", "admitted", "cancelled"]},
        "priority": {"type": "integer", "minimum": 1, "maximum": 5, "nullable": True, "example": 4},
        "expected_arrival_time": {"type": "string", "nullable": True, "example": "2026-11-01T10:30:00Z"},
        "created_at": {"type": "string", "example": "2026-11-01 12:00:00"},
        "updated_at": {"type": "string", "example": "2026-11-01 12:00:00"},
    },
}


def _err(description):
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


ID_PARAM = {"name": "id", "in": "path", "required": True,
            "schema": {"type": "integer", "example": 1}}

SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Hospital Portal - Pre-admission Queue API",
        "version": "1.0.0",
        "description": (
            "Click **Authorize** and enter `x-hospital-id` (e.g. H1) and `x-role` "
            "(`staff`) first. Demo bookings 1 and 2 belong to H1, booking 3 to H2. "
            "Synthetic data only."
        ),
    },
    "security": [{"HospitalId": [], "Role": []}],
    "paths": {
        "/api/hospital/pre-admissions": {
            "post": {
                "summary": "Add a booking to the pre-admission queue",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["booking_id"],
                        "properties": {
                            "booking_id": {"type": "integer", "example": 1},
                            "priority": {"type": "integer", "minimum": 1, "maximum": 5, "example": 4},
                            "expected_arrival_time": {"type": "string", "example": "2026-11-01T10:30:00Z"},
                        },
                    }}},
                },
                "responses": {
                    "201": {"description": "Created", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "400": _err("Invalid body"),
                    "403": _err("Not authorized staff"),
                    "404": _err("Booking not found (or belongs to another hospital)"),
                    "409": _err("Active pre-admission already exists for this booking"),
                },
            },
            "get": {
                "summary": "List this hospital's queue",
                "parameters": [{
                    "name": "status", "in": "query", "required": False,
                    "schema": {"type": "string", "enum": ["expected", "arrived", "admitted", "cancelled"]},
                }],
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {"schema": {
                        "type": "array", "items": {"$ref": "#/components/schemas/PreAdmission"}}}}},
                    "400": _err("Invalid status filter"),
                    "403": _err("Not authorized staff"),
                },
            },
        },
        "/api/hospital/pre-admissions/{id}": {
            "get": {
                "summary": "Get one entry",
                "parameters": [ID_PARAM],
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "403": _err("Not authorized staff"),
                    "404": _err("Not found (or another hospital's)"),
                },
            },
            "patch": {
                "summary": "Edit priority and/or expected arrival time",
                "description": "Only while status is expected or arrived. Use the /status "
                               "endpoint to change status.",
                "parameters": [ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "priority": {"type": "integer", "minimum": 1, "maximum": 5,
                                         "nullable": True, "example": 2},
                            "expected_arrival_time": {"type": "string", "nullable": True,
                                                      "example": "2026-11-01T14:00:00Z"},
                        },
                    }}},
                },
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "400": _err("Invalid body"),
                    "403": _err("Not authorized staff"),
                    "404": _err("Not found (or another hospital's)"),
                    "422": _err("Entry is admitted or cancelled"),
                },
            },
            "delete": {
                "summary": "Remove from the queue (cancels the entry)",
                "description": "The row is kept with status cancelled. Not allowed once admitted.",
                "parameters": [ID_PARAM],
                "responses": {
                    "200": {"description": "Cancelled entry", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "403": _err("Not authorized staff"),
                    "404": _err("Not found (or another hospital's)"),
                    "422": _err("Already admitted or cancelled"),
                },
            },
            "put": {
                "summary": "Replace an entry's priority and expected arrival time",
                "description": "Fields left out are reset to null. Status changes use PATCH. "
                               "Admitted and cancelled entries cannot be edited.",
                "parameters": [ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "priority": {"type": "integer", "minimum": 1, "maximum": 5, "example": 2},
                            "expected_arrival_time": {"type": "string", "example": "2026-11-02T09:00:00Z"},
                        },
                    }}},
                },
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "400": _err("Invalid body"),
                    "403": _err("Not authorized staff"),
                    "404": _err("Not found (or another hospital's)"),
                    "422": _err("Entry is admitted or cancelled"),
                },
            },
        },
        "/api/hospital/pre-admissions/{id}/status": {
            "patch": {
                "summary": "Change an entry's status",
                "description": "expected -> arrived/cancelled; arrived -> admitted/cancelled; "
                               "admitted and cancelled are final.",
                "parameters": [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "integer", "example": 1}}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {
                            "type": "string",
                            "enum": ["expected", "arrived", "admitted", "cancelled"],
                            "example": "arrived"}},
                    }}},
                },
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/PreAdmission"}}}},
                    "400": _err("Invalid status"),
                    "403": _err("Not authorized staff"),
                    "404": _err("Not found (or another hospital's)"),
                    "422": _err("Invalid status transition"),
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "HospitalId": {"type": "apiKey", "in": "header", "name": "x-hospital-id"},
            "Role": {"type": "apiKey", "in": "header", "name": "x-role"},
        },
        "schemas": {
            "PreAdmission": PRE_ADMISSION,
            "Error": {"type": "object", "properties": {"error": {"type": "string"}}},
        },
    },
}

PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Pre-admission Queue API</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({ url: "/openapi.json", dom_id: "#swagger-ui" });
  </script>
</body>
</html>
"""


@bp.get("/openapi.json")
def openapi():
    return jsonify(SPEC)


@bp.get("/docs")
def docs():
    return PAGE


@bp.get("/")
def index():
    return redirect("/docs")
