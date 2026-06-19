"""Shared Flask extensions (security 012).

The rate limiter is created here, app-less, so both the app shell (`wismap/api.py`)
and the v1 blueprint (`wismap/api_v1.py`) can import it without a circular import.
It is bound to the application via ``limiter.init_app(app)`` in ``wismap/api.py``.

Storage stays ``memory://`` by design (constitution §Scope: "No Redis"). With more
than one gunicorn worker the per-IP buckets are per-worker, so limits are
approximate (≈ nominal × workers); accepted because the request-size caps in
``wismap/core.py`` are the real DoS defense. See
``.sdd/specs/012-security-assessment/`` for the rationale.
"""

import logging
import os

from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)

_default_limit = os.environ.get("RATELIMIT_DEFAULT", "120/minute")
_storage_uri = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
_enabled = os.environ.get("RATELIMIT_ENABLED", "true").lower() in ("1", "true", "yes")


def _on_breach(request_limit):
    logger.warning(
        "Rate limit exceeded: %s from %s on %s %s",
        request_limit.limit, get_remote_address(), request.method, request.path,
    )


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_default_limit],
    storage_uri=_storage_uri,
    enabled=_enabled,
    on_breach=_on_breach,
)
