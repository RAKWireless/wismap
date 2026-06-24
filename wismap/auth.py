"""
WisMAP API authentication (spec 009-api-key-auth).

Pure verification + minting helpers. This module imports nothing from
``wismap.api`` / ``wismap.api_v1`` (in fact it needs no Flask import at all), so
the dependency direction stays strictly one-way: the v1 blueprint imports this
module, never the reverse. The gate itself — a ``before_request`` hook that
allowlists the two compute-bound endpoints — is wired in ``wismap/api_v1.py``
(Phase 2). Keeping the logic here framework-agnostic also makes it testable
without a live app context.

Two proofs are accepted by the gate:

  * ``Authorization: Bearer <key>`` — machine consumers. Keys live in a YAML
    file; only their SHA-256 hashes are held in memory (no plaintext retained).
  * ``wismap_session`` + ``X-CSRF-Token`` double-submit — the browser SPA. The
    session cookie carries an HMAC-signed session id; the CSRF token is itself
    HMAC-bound to that session id with the app secret, so the pair is verifiable
    without any server-side state (matches the "No external state" constitution
    rule).

Stdlib only (``hmac``, ``hashlib``, ``secrets``); no third-party auth library.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass

import yaml

logger = logging.getLogger(__name__)

# Cookie / header names (spec 009 §User-facing behavior).
SESSION_COOKIE = "wismap_session"
CSRF_COOKIE = "wismap_csrf"
CSRF_HEADER = "X-CSRF-Token"

_BEARER_PREFIX = "Bearer "
# token_urlsafe() output is [A-Za-z0-9_-], so "." never appears inside a token
# and is a safe separator between a signed value and its MAC.
_SEP = "."


class AuthConfigError(Exception):
    """Raised by :meth:`AuthConfig.from_env` when auth is enabled but required
    configuration is missing or unreadable. The app shell (Phase 2, ``api.py``)
    catches this at boot and exits non-zero — fail closed, never start insecure.
    """


# ---------------------------------------------------------------------------
# Keys file
# ---------------------------------------------------------------------------

def load_keys(path: str) -> dict[str, str]:
    """Load the YAML keys file into ``{sha256(key): label}``.

    The plaintext key is hashed on load and discarded; the returned map never
    contains a usable key. Raises ``FileNotFoundError`` (missing file) or
    ``ValueError`` (malformed / empty file).
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of {{key, label}} entries")
    keys: dict[str, str] = {}
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict) or "key" not in entry or "label" not in entry:
            raise ValueError(f"{path}: entry {i} must be a mapping with 'key' and 'label'")
        key = str(entry["key"]).strip()
        label = str(entry["label"]).strip()
        if not key or not label:
            raise ValueError(f"{path}: entry {i} has an empty 'key' or 'label'")
        keys[hashlib.sha256(key.encode()).hexdigest()] = label
    if not keys:
        raise ValueError(f"{path}: no keys loaded (file is empty)")
    return keys


# ---------------------------------------------------------------------------
# Signing helpers (stateless HMAC over a salt + value)
# ---------------------------------------------------------------------------

def _sign(secret_key: bytes, salt: str, value: str) -> str:
    """Return ``<value>.<hmac>`` so the server can later recover and authenticate
    ``value`` without storing it. ``salt`` domain-separates uses of the secret."""
    mac = hmac.new(secret_key, f"{salt}{_SEP}{value}".encode(), hashlib.sha256).hexdigest()
    return f"{value}{_SEP}{mac}"


def _unsign(secret_key: bytes, salt: str, signed: str) -> str | None:
    """Inverse of :func:`_sign`. Returns the original ``value`` if the MAC checks
    out (constant-time), else ``None``."""
    value, sep, mac = signed.rpartition(_SEP)
    if not sep or not value or not mac:
        return None
    expected = hmac.new(secret_key, f"{salt}{_SEP}{value}".encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(mac, expected):
        return value
    return None


def _csrf_salt(sid: str) -> str:
    """CSRF salt binds the token to a specific session id."""
    return f"csrf{_SEP}{sid}"


def bearer_present(request) -> bool:
    """True when the request carries an ``Authorization: Bearer`` header.

    The gate uses this to honour RQ-03: a *present* bearer header decides the
    request on the bearer path alone — a present-but-invalid key is an outright
    deny and must NOT fall through to the session/CSRF path.
    """
    return request.headers.get("Authorization", "").startswith(_BEARER_PREFIX)


# ---------------------------------------------------------------------------
# Auth configuration (loaded once at boot) + verification / minting
# ---------------------------------------------------------------------------

@dataclass
class AuthConfig:
    """Boot-time auth configuration. Created once via :meth:`from_env`, stashed on
    ``app.config["WISMAP_AUTH"]`` (Phase 2), and used by the gate hook."""

    enabled: bool
    keys: dict[str, str]   # {sha256(key): label}; empty when disabled
    secret_key: bytes      # signs session cookies + derives CSRF tokens

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Build from environment variables.

        * ``WISMAP_AUTH_ENABLED`` (default ``true``) — ``false`` disables the gate
          for local dev: an ephemeral secret is generated and no keys file is
          required (preserves "No external state required to run the server").
        * ``WISMAP_API_KEYS_FILE`` — required when enabled. Missing/unreadable →
          raise (caller exits at boot).
        * ``WISMAP_SECRET_KEY`` — required when enabled. Missing → raise.
        """
        enabled = os.environ.get("WISMAP_AUTH_ENABLED", "true").lower() in ("1", "true", "yes")
        if not enabled:
            logger.warning(
                "WISMAP_AUTH_ENABLED=false — API auth is DISABLED (dev mode); "
                "/validate and /solve are open and a random ephemeral session secret is used."
            )
            return cls(enabled=False, keys={}, secret_key=secrets.token_bytes(32))

        keys_file = os.environ.get("WISMAP_API_KEYS_FILE")
        secret = os.environ.get("WISMAP_SECRET_KEY")
        missing = [
            name for name, val in (
                ("WISMAP_API_KEYS_FILE", keys_file),
                ("WISMAP_SECRET_KEY", secret),
            ) if not val
        ]
        if missing:
            raise AuthConfigError(
                "Auth is enabled but required environment variable(s) missing: "
                + ", ".join(missing)
                + ". Set them, or set WISMAP_AUTH_ENABLED=false for local dev."
            )

        keys = load_keys(keys_file)  # may raise FileNotFoundError / ValueError
        logger.info("API auth enabled: %d key(s) loaded from %s", len(keys), keys_file)
        return cls(enabled=True, keys=keys, secret_key=secret.encode())

    # -- bearer -------------------------------------------------------------

    def verify_bearer(self, request) -> str | None:
        """Return the consumer ``label`` for a valid bearer key, else ``None``
        (header absent *or* key invalid).

        The presented key is hashed and compared (constant-time) against every
        stored hash — the raw key is never compared, and the loop runs over all
        keys so timing does not reveal which key matched.
        """
        header = request.headers.get("Authorization", "")
        if not header.startswith(_BEARER_PREFIX):
            return None
        presented = header[len(_BEARER_PREFIX):].strip()
        if not presented:
            return None
        presented_hash = hashlib.sha256(presented.encode()).hexdigest()
        match: str | None = None
        for stored_hash, label in self.keys.items():
            if hmac.compare_digest(stored_hash, presented_hash):
                match = label
        return match

    # -- session + CSRF -----------------------------------------------------

    def mint_session(self, response, *, secure: bool) -> None:
        """Set the ``wismap_session`` (HttpOnly) and ``wismap_csrf`` (JS-readable)
        cookies on ``response``. Both are SameSite=Strict, Path=/, and ``Secure``
        when ``secure`` (i.e. ``request.is_secure``).
        """
        sid = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        session_value = _sign(self.secret_key, "session", sid)
        csrf_value = _sign(self.secret_key, _csrf_salt(sid), csrf)
        response.set_cookie(
            SESSION_COOKIE, session_value,
            httponly=True, secure=secure, samesite="Strict", path="/",
        )
        response.set_cookie(
            CSRF_COOKIE, csrf_value,
            httponly=False, secure=secure, samesite="Strict", path="/",
        )

    def verify_session(self, request) -> bool:
        """True iff the request carries a valid ``wismap_session`` + matching
        ``X-CSRF-Token`` double-submit pair bound to the same session id."""
        signed_session = request.cookies.get(SESSION_COOKIE)
        if not signed_session:
            return False
        sid = _unsign(self.secret_key, "session", signed_session)
        if sid is None:
            return False
        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        header_token = request.headers.get(CSRF_HEADER, "")
        if not cookie_token or not header_token:
            return False
        # Double-submit: the JS-sent header must equal the cookie value...
        if not hmac.compare_digest(cookie_token, header_token):
            return False
        # ...and that value must be a CSRF token this server bound to this sid.
        return _unsign(self.secret_key, _csrf_salt(sid), cookie_token) is not None

    def has_valid_session_cookie(self, request) -> bool:
        """True iff a validly-signed ``wismap_session`` cookie is present (ignores
        CSRF). Used by ``serve_spa`` to decide whether to (re)mint: minting must be
        sticky across plain navigations, which carry the session cookie but not the
        ``X-CSRF-Token`` header — so :meth:`verify_session` (which requires the full
        double-submit pair) is the wrong check there. A tampered/absent cookie is
        treated as "no session", so it self-heals on the next page load (RQ-05).
        """
        signed = request.cookies.get(SESSION_COOKIE)
        return bool(signed) and _unsign(self.secret_key, "session", signed) is not None
