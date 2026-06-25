"""
WisMAP Flask REST API.

The canonical API lives under /api/v1 (see wismap/api_v1.py).
This module wires the blueprint, applies rate limits, exposes the
image-proxy utility, and serves the React SPA.
"""

import logging
import os
import sys

import requests as http_requests
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from wismap.auth import AuthConfig, AuthConfigError
from wismap.core import load_data_v1
from wismap.api_v1 import bp as api_v1_bp, gate as auth_gate
from wismap.extensions import limiter

# ---------------------------------------------------------------------------
# Logging — surface the app's INFO logs (the boot key-load line and the
# per-request auth-success `label`, RQ-13) in the container logs. gunicorn
# captures stderr, but `wismap.*` loggers default to WARNING with no handler,
# so configure the namespace explicitly here, before AuthConfig.from_env() runs.
# Quiet it with WISMAP_LOG_LEVEL=WARNING (denials stay at WARNING regardless).
# ---------------------------------------------------------------------------
_log_level = os.environ.get("WISMAP_LOG_LEVEL", "INFO").upper()
_wismap_logger = logging.getLogger("wismap")
if not _wismap_logger.handlers:
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _wismap_logger.addHandler(_log_handler)
_wismap_logger.setLevel(_log_level)
_wismap_logger.propagate = False

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

# Resolve data folder relative to project root (one level up from this file)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_data_folder = os.path.join(_project_root, "data")
_frontend_dist = os.path.join(_project_root, "frontend", "dist")

definitions, config, rules, compat_slots_index = load_data_v1(_data_folder)

app = Flask(__name__, static_folder=_frontend_dist, static_url_path="")
app.json.sort_keys = False

# Honor X-Forwarded-* from a single trusted front proxy/CDN so rate limiting keys
# on the real client IP, not the proxy (security 012). No effect when accessed
# directly; assumes exactly one proxy hop in the public deployment.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Reject oversized request bodies before JSON parsing (security 012 RQ-05).
# Werkzeug returns its default 413 page (not the v1 JSON envelope) for this case.
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", 256 * 1024))

CORS(app)

# ---------------------------------------------------------------------------
# Auth (spec 009) — load the key/secret config once at boot. Fail closed: if
# auth is enabled but misconfigured (missing secret or keys file), exit rather
# than start in an insecure state (RQ-11). `WISMAP_AUTH_ENABLED=false` is the
# explicit local-dev escape hatch.
# ---------------------------------------------------------------------------
try:
    auth_config = AuthConfig.from_env()
except (AuthConfigError, FileNotFoundError, ValueError) as exc:
    logging.getLogger(__name__).critical("API auth misconfigured at boot: %s", exc)
    sys.exit(1)

app.secret_key = auth_config.secret_key
app.config["WISMAP_AUTH"] = auth_config

# Stash the loaded data on the app so the v1 blueprint can access it.
app.config["WISMAP_DATA"] = (definitions, config, rules, compat_slots_index)
app.register_blueprint(api_v1_bp)

# ---------------------------------------------------------------------------
# Rate limiting — the limiter lives in wismap/extensions.py (shared with the v1
# blueprint so it can decorate /solve); env-configurable. Bind it to this app.
# ---------------------------------------------------------------------------

_proxy_limit = os.environ.get("RATELIMIT_PROXY", "60/minute")

# Register the auth gate as an APP-LEVEL before_request BEFORE the limiter binds
# its own (also app-level) before_request. App-level hooks run in registration
# order, so this guarantees auth is evaluated before any rate-limit check: an
# unauthenticated /validate or /solve gets a 403 without consuming a limiter
# bucket (RQ-14). NOTE: a blueprint-level (`@bp.before_request`) gate would run
# *after* the limiter's app-level check, so registering here — ahead of
# init_app — is load-bearing, not stylistic.
app.before_request(auth_gate)

limiter.init_app(app)


@app.after_request
def set_security_headers(response):
    # Swagger UI's bootstrap is an inline <script> in our vendored index.html.
    # Loosen `script-src` with 'unsafe-inline' for /api/v1/docs* only.
    # SECURITY: do NOT render any user-controlled content into the Swagger UI
    # page or its assets — the carve-out below assumes the page contains only
    # static HTML that boots SwaggerUIBundle against /api/v1/openapi.yaml.
    is_docs = request.path.startswith("/api/v1/docs")
    script_src = "script-src 'self' 'unsafe-inline'; " if is_docs else "script-src 'self'; "
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        + script_src +
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://images.docs.rakwireless.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

# ---------------------------------------------------------------------------
# Image proxy — frontend utility for PDF export (not part of the v1 contract)
# ---------------------------------------------------------------------------

_IMAGE_PROXY_PREFIX = "https://images.docs.rakwireless.com/"
_IMAGE_MAX_BYTES = int(os.environ.get("IMAGE_PROXY_MAX_BYTES", 10 * 1024 * 1024))

@app.route("/api/image-proxy")
@limiter.limit(_proxy_limit)
def api_image_proxy():
    """Proxy remote RAK CDN images to avoid CORS issues in PDF export.

    Security (012): allowlist the exact host prefix, do NOT follow redirects (the
    allowlist only vetted the initial URL — a redirect could reach internal hosts),
    require an image/* upstream, and cap the streamed body so a large or hostile
    response can't exhaust memory.
    """
    url = request.args.get("url", "")
    if not url.startswith(_IMAGE_PROXY_PREFIX):
        return jsonify({"error": "URL not allowed"}), 403
    try:
        with http_requests.get(
            url, timeout=15, allow_redirects=False, stream=True
        ) as resp:
            # raise_for_status() ignores 3xx, so reject redirects explicitly.
            if resp.is_redirect or resp.is_permanent_redirect:
                return jsonify({"error": "Redirects are not allowed"}), 502
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                return jsonify({"error": "Upstream is not an image"}), 502
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > _IMAGE_MAX_BYTES:
                    return jsonify({"error": "Image too large"}), 502
                chunks.append(chunk)
            return Response(b"".join(chunks), content_type=content_type)
    except Exception:
        return jsonify({"error": "Failed to fetch image"}), 502

# ---------------------------------------------------------------------------
# SPA fallback — serve React index.html for non-API routes
# ---------------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
@limiter.exempt
def serve_spa(path):
    # If the file exists in the static folder, serve it
    if path and os.path.isfile(os.path.join(_frontend_dist, path)):
        return send_from_directory(_frontend_dist, path)
    # Otherwise serve index.html (SPA routing). This is the one surface that mints
    # the browser's session+CSRF cookies (RQ-05/RQ-07) — and only when no valid
    # session cookie is already present, so they stay sticky across reloads.
    index = os.path.join(_frontend_dist, "index.html")
    if os.path.isfile(index):
        resp = send_from_directory(_frontend_dist, "index.html")
        if auth_config.enabled and not auth_config.has_valid_session_cookie(request):
            auth_config.mint_session(resp, secure=request.is_secure)
        return resp
    return jsonify({"error": "Frontend not built. Run: make frontend-build"}), 404

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug)
