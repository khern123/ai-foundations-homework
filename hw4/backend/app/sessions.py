"""Signed, expiring session tokens (stateless, so the course database schema stays unchanged).

Token: "<user_id>.<expires_unix>.<hex HMAC-SHA256(secret, 'user_id.expires')>"
It holds only the user id and expiry: no name, email or password. Tampering breaks the signature.
"""

import hashlib
import hmac
import time

from .config import settings

TOKEN_TTL_SECONDS = 7 * 24 * 3600


def _sign(payload: str) -> str:
    return hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: int, now: float | None = None) -> str:
    expires = int((now or time.time()) + TOKEN_TTL_SECONDS)
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str, now: float | None = None) -> int | None:
    """User id if the token is genuine and unexpired, else None."""
    try:
        user_id, expires, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(f"{user_id}.{expires}")):
            return None
        if int(expires) < (now or time.time()):
            return None
        return int(user_id)
    except (ValueError, AttributeError):
        return None
