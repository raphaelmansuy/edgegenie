"""One place that talks HTTP to the workspace with the *user's* token and maps failures.

Error mapping is the contract every Databricks adapter shares:
    401/403 -> PermissionError   (Unity Catalog / workspace ACL said no: report it, never work around it)
    404     -> LookupError       (the object is not there)
    other   -> RuntimeError      (carries the first 200 chars of the platform's message)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

TIMEOUT = 20.0


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
            raise PermissionError(f"you do not have access to {(params or {}).get('path') or path}")
        if r.status_code >= 400:
            raise RuntimeError(f"{path} failed ({r.status_code}): {r.text[:200]}")
        return r.json() if r.content else {}

    async def get(self, path: str, token: str | None, params: dict | None = None) -> Any:
        return await self.request("GET", path, token, params=params)

    async def post(self, path: str, token: str | None, body: dict | None = None, timeout: float = TIMEOUT) -> Any:
        return await self.request("POST", path, token, body=body, timeout=timeout)
