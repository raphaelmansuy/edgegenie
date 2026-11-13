"""Which model serving endpoints this workspace actually serves, as the signed-in user sees them.

The model list the app offers must be the intersection of what the app allows and what the workspace
serves. The first deployment offered a Claude endpoint the workspace did not have; choosing it
failed the first prompt with "endpoint does not exist" (spec 001, RB-11).
"""
from __future__ import annotations

import time

from .http import DbxHttp

TTL_SECONDS = 300


class ServingBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._cache: tuple[float, frozenset[str]] | None = None

    async def served(self, token: str | None) -> frozenset[str] | None:
        """Names of chat endpoints that are ready, or None when the list cannot be read (then do not filter)."""
        if self._cache and time.monotonic() - self._cache[0] < TTL_SECONDS:
            return self._cache[1]
        try:
            d = await self._http.get("/api/2.0/serving-endpoints", token)
        except (PermissionError, RuntimeError):
            return None
        names = frozenset(
            e["name"] for e in d.get("endpoints", [])
            if e.get("task", "llm/v1/chat") == "llm/v1/chat"
            and (e.get("state") or {}).get("ready", "READY") == "READY")
        self._cache = (time.monotonic(), names)
        return names

    async def close(self):
        closer=getattr(self._http,'close',None)
        if closer:await closer()
