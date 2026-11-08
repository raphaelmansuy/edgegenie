"""A development-only token refresher. Lives here because it knows a vendor command.

In a deployed app the Databricks proxy forwards a fresh user token with every request, so none of
this runs. Locally there is one configured token, it expires after an hour, and when it does the
symptoms are an empty file tree and a search that never finishes — which reads as a bug in the app and
costs an afternoon to diagnose. This re-mints it shortly before it expires.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import time
from typing import Any

log = logging.getLogger("app.dbx.devtoken")

#: Below this many seconds of remaining life, ask for a new token.
RENEW_WITHIN = 300
#: Do not shell out more than once a minute, however many requests arrive.
MIN_INTERVAL = 60

_last_check = 0.0


def _expires_at(token: str) -> int:
    """The `exp` claim, or 0 when the token is not a readable JWT. Never raises."""
    parts = (token or "").split(".")
    if len(parts) != 3:
        return 0
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, TypeError):
        return 0
    exp = claims.get("exp", 0) if isinstance(claims, dict) else 0
    return int(exp) if isinstance(exp, (int, float)) else 0


def refresh_if_stale(state: Any, host: str) -> str | None:
    """Return the state's dev token, re-minted when it is close to expiry.

    A convenience for local work: every failure path returns the token we already had, because a
    refresh that breaks a request would be worse than a token that expires.
    """
    global _last_check
    token = getattr(state, "dev_token", None)
    if not token or not getattr(state, "dev_token_auto", False):
        return token
    now = time.time()
    if now - _last_check < MIN_INTERVAL:
        return token
    _last_check = now
    exp = _expires_at(token)
    if exp and exp - now > RENEW_WITHIN:
        return token
    try:
        # `check=False`: a refusal is handled by the empty-stdout path, not by an exception.
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
            ["databricks", "auth", "token", "--host", host, "-o", "json"],
            capture_output=True, text=True, timeout=25, check=False)
        fresh = json.loads(done.stdout or "{}").get("access_token")
    except (OSError, ValueError):
        return token
    if fresh:
        state.dev_token = fresh
        log.info("development token refreshed")
        return fresh
    return token
