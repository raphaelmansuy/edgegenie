"""One place that talks HTTP to the workspace with the *user's* token and maps failures.

Error mapping is the contract every Databricks adapter shares:
    401/403 -> PermissionError   (Unity Catalog / workspace ACL said no: report it, never work around it)
    404     -> LookupError       (the object is not there)
    other   -> RuntimeError      (carries the first 200 chars of the platform's message)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import logging
import re

import httpx

from ...domain.redact import token_scopes

log = logging.getLogger("app.dbx.http")

TIMEOUT = 20.0

#: The platform's own words when the app's token lacks an OAuth scope, e.g.
#: "Provided OAuth token does not have required scopes: workspace". Matched loosely on purpose.
_SCOPE_RE = re.compile(r"(?:required\s+)?scopes?\b[^:]*:\s*([A-Za-z0-9_.:\- ,]+)", re.I)


class ScopeMissing(PermissionError):
    """The app was not granted an OAuth scope. That is an app setting, **not** the user's permissions.

    It is a `PermissionError` (callers already map that to 403) but it carries a different sentence,
    because the remedy differs: a denied ACL is fixed by the object's owner, a missing scope by the
    app's owner. Telling a user "you do not have access" when the app is mis-configured sends them to
    the wrong person.
    """

    def __init__(self, scopes: str = "") -> None:
        self.scopes = scopes.strip()
        what = f" (`{self.scopes}`)" if self.scopes else ""
        super().__init__(
            f"this app has not been granted the permission it needs{what}. This is an app setting, "
            "not your access. If you signed in before the app's permissions changed, sign in again; "
            "otherwise ask the app's owner to add the scope and redeploy.")


def denial(status: int, text: str, where: str) -> PermissionError:
    """401/403 -> the right sentence. A scope problem names the scope; an ACL problem names the path."""
    lowered = text.lower()
    # The platform says "Invalid scope, required scopes: workspace" (no word "token"), so the word
    # "scope" next to a refusal is the signal. A path or an ACL message never contains it.
    if re.search(r"\bscopes?\b", lowered):
        match = _SCOPE_RE.search(text)
        return ScopeMissing(match.group(1) if match else "")
    return PermissionError(f"you do not have access to {where}")


def normalize_host(host: str | None) -> str:
    """Databricks Apps may provide DATABRICKS_HOST as a bare hostname; every client needs a URL."""
    h = (host or "").strip().rstrip("/")
    if h and not h.startswith(("http://", "https://")):
        h = f"https://{h}"
    return h


class DbxHttp:
    def __init__(self, host: str, token_provider: Callable[[], str | None]) -> None:
        self._host = normalize_host(host)
        self._token_provider = token_provider

    def _headers(self, token: str | None) -> dict[str, str]:
        tok = token or self._token_provider()
        if not tok:
            raise PermissionError(
                "no user token: this needs user authorization (x-forwarded-access-token) "
                "or DATABRICKS_TOKEN in development")
        return {"Authorization": f"Bearer {tok}"}

    async def request(self, method: str, path: str, token: str | None, *, params: dict | None = None,
                      body: dict | None = None, timeout: float = TIMEOUT) -> Any:
        if not self._host:
            raise RuntimeError("DATABRICKS_HOST is not set: the app cannot reach the workspace")
        headers = self._headers(token)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, f"{self._host}{path}", params=params, json=body, headers=headers)
        if r.status_code == 404:
            raise LookupError(f"not found: {(params or {}).get('path') or path}")
        if r.status_code in (401, 403):
            # The platform's own words are the only way to tell a missing scope from an ACL, and the UI
            # sentence may be a summary of them. Logged for the operator; never carries a token.
            # `token scopes` are the NAMES in the caller's own token: they show whether a refusal is a stale
            # sign-in (token older than the app's scopes) or an app that was never granted the scope.
            log.warning("workspace call refused: %s %s -> %s %s | token scopes: %s", method, path,
                        r.status_code, r.text[:300], " ".join(token_scopes(headers["Authorization"][7:])) or "none")
            raise denial(r.status_code, r.text, (params or {}).get("path") or path)
        if r.status_code >= 400:
            raise RuntimeError(f"{path} failed ({r.status_code}): {r.text[:200]}")
        return r.json() if r.content else {}

    async def get(self, path: str, token: str | None, params: dict | None = None) -> Any:
        return await self.request("GET", path, token, params=params)

    async def post(self, path: str, token: str | None, body: dict | None = None, timeout: float = TIMEOUT) -> Any:
        return await self.request("POST", path, token, body=body, timeout=timeout)
