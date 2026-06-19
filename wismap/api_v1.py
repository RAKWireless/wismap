"""
WisMAP v1 REST API.

Endpoints (all mounted under /api/v1 by the host Flask app):
  GET  /healthz
  GET  /cores
  GET  /cores/<id>
  GET  /bases
  GET  /bases/<id>
  GET  /modules
  GET  /modules/<id>
  POST /validate

  GET  /openapi.yaml          → canonical contract (hand-authored)
  GET  /docs                  → Swagger UI browser (vendored assets)
  GET  /docs/<asset>          → vendored Swagger UI CSS/JS

Error responses follow the spec's envelope:
  { "error": { "code": "<code>", "message": "<msg>", "details": {...} } }
"""

import os

from flask import Blueprint, jsonify, request, current_app, send_from_directory, Response

from wismap import __version__
from wismap.core import (
    get_cores, get_core,
    get_bases, get_base,
    get_modules_v1, get_module_v1,
    validate_v1, solve_v1,
)

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

_HERE = os.path.dirname(os.path.abspath(__file__))
_OPENAPI_FILE = os.path.join(_HERE, "openapi.yaml")
_SWAGGER_DIR = os.path.join(_HERE, "static", "swagger-ui")


def _error(code, message, status, details=None):
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status


def _data():
    """Pull the loaded data tuple stashed on the app at startup."""
    return current_app.config["WISMAP_DATA"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

# /healthz is also exposed at the app root for liveness probes; Phase 2 adds the
# v1-prefixed alias only. The blueprint owns the v1-prefixed path.
@bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "version": __version__})


# ---------------------------------------------------------------------------
# Cores
# ---------------------------------------------------------------------------

@bp.route("/cores")
def list_cores():
    definitions, config, _, _ = _data()
    return jsonify({"cores": get_cores(definitions, config)})


@bp.route("/cores/<core_id>")
def get_one_core(core_id):
    definitions, config, _, _ = _data()
    show_nc = request.args.get("show_nc", "false").lower() == "true"
    core = get_core(definitions, config, core_id, show_nc=show_nc)
    if core is None:
        return _error(
            "core_not_found",
            f"Core '{core_id}' is not known to WisMAP.",
            404,
            details={"core": core_id},
        )
    return jsonify(core)


# ---------------------------------------------------------------------------
# Bases
# ---------------------------------------------------------------------------

@bp.route("/bases")
def list_bases():
    definitions, _, _, _ = _data()
    return jsonify({"bases": get_bases(definitions)})


@bp.route("/bases/<base_id>")
def get_one_base(base_id):
    definitions, config, _, _ = _data()
    show_nc = request.args.get("show_nc", "false").lower() == "true"
    base = get_base(definitions, config, base_id, show_nc=show_nc)
    if base is None:
        return _error(
            "base_not_found",
            f"Base '{base_id}' is not known to WisMAP.",
            404,
            details={"base": base_id},
        )
    return jsonify(base)


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

@bp.route("/modules")
def list_modules_v1():
    definitions, _, _, compat_idx = _data()
    mods = get_modules_v1(
        definitions,
        compat_idx,
        type=request.args.get("type"),
        category=request.args.get("category"),
        interface=request.args.get("interface"),
        compatible_with_core=request.args.get("compatible_with_core"),
    )
    return jsonify({"modules": mods})


@bp.route("/modules/<module_id>")
def get_one_module(module_id):
    definitions, _, _, compat_idx = _data()
    show_nc = request.args.get("show_nc", "false").lower() == "true"
    mod = get_module_v1(definitions, compat_idx, module_id, show_nc=show_nc)
    if mod is None:
        return _error(
            "module_not_found",
            f"Module '{module_id}' is not known to WisMAP.",
            404,
            details={"module": module_id},
        )
    return jsonify(mod)


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

@bp.route("/validate", methods=["POST"])
def validate():
    definitions, config, rules, _ = _data()
    body = request.get_json(silent=True)
    if body is None:
        return _error("invalid_request", "Request body must be valid JSON.", 400)

    response, err, status = validate_v1(definitions, config, rules, body)
    if err is not None:
        code, message = err
        return _error(code, message, status)
    return jsonify(response), status


# ---------------------------------------------------------------------------
# Solve (slot placement)
# ---------------------------------------------------------------------------

@bp.route("/solve", methods=["POST"])
def solve():
    definitions, config, rules, compat_idx = _data()
    body = request.get_json(silent=True)
    if body is None:
        return _error("invalid_request", "Request body must be valid JSON.", 400)

    response, err, status = solve_v1(definitions, config, rules, compat_idx, body)
    if err is not None:
        code, message = err
        return _error(code, message, status)
    return jsonify(response), status


# ---------------------------------------------------------------------------
# OpenAPI doc + Swagger UI
# ---------------------------------------------------------------------------

@bp.route("/openapi.yaml")
def openapi_doc():
    """Serve the canonical OpenAPI 3.1 document (hand-authored)."""
    with open(_OPENAPI_FILE, encoding="utf-8") as f:
        return Response(f.read(), mimetype="application/yaml")


@bp.route("/docs")
def swagger_docs():
    """Swagger UI single-page browser, loads /api/v1/openapi.yaml."""
    return send_from_directory(_SWAGGER_DIR, "index.html")


@bp.route("/docs/<path:filename>")
def swagger_assets(filename):
    """Serve vendored Swagger UI static assets (css/js)."""
    return send_from_directory(_SWAGGER_DIR, filename)
