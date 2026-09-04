"""Google (GIS) identity verification + the email allowlist.

The only place that talks to `google-auth`. Routers and the gate middleware
are thin wrappers.
"""
from __future__ import annotations

import backend.config as config


class AuthError(Exception):
    """A credential could not be verified, or the account is not allowed."""


def is_allowed(email: str) -> bool:
    return email.strip().lower() in config.ALLOWED_EMAILS


def verify_google_token(credential: str) -> dict:
    """Validate a Google ID token and return {email, name, sub}.

    Raises AuthError on any signature / audience / expiry / verification failure.
    """
    from google.auth.transport import requests as grequests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(
            credential,
            grequests.Request(),
            config.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except Exception as exc:  # noqa: BLE001 - normalise to AuthError
        raise AuthError(f"token inválido: {exc}") from exc

    if not info.get("email_verified"):
        raise AuthError("email no verificado por Google")

    email = info["email"].lower()
    return {"email": email, "name": info.get("name") or email, "sub": info["sub"]}
