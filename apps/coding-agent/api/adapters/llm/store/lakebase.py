"""Connecting to Lakebase: a Postgres whose password is a short-lived OAuth token.

A static DSN works for a minute and then fails (the token lives about an hour), which is why the
registry cannot simply be handed `postgresql://user:password@host/db`. This module gives the pool a
connection class that asks for a fresh token each time it opens a connection; the pool's
`max_lifetime` keeps every connection younger than the token.

The token is minted for whoever the SDK authenticates as: the app's service principal in production,
the developer's own login locally. Nothing here is stored.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("app.llm.lakebase")

#: Tokens last about an hour. Refresh at 45 minutes and recycle connections before then.
TOKEN_REFRESH_SECONDS = 45 * 60
CONNECTION_MAX_LIFETIME = 40 * 60


@dataclass(frozen=True, slots=True)
class LakebaseTarget:
    host: str
    database: str
    user: str
    endpoint: str

    @property
    def conninfo(self) -> str:
        return f"host={self.host} port=5432 dbname={self.database} user={self.user} sslmode=require"


class TokenSource:
    """Mints and caches the OAuth password. Synchronous (the SDK is), so callers use `to_thread`."""

    def __init__(self, endpoint: str, client=None, clock: Callable[[], float] = time.monotonic) -> None:
        self._endpoint = endpoint
        self._client = client
        self._clock = clock
        self._token = ""
        self._at = 0.0

    def _workspace(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient

            self._client = WorkspaceClient()
        return self._client

    def get(self) -> str:
        if self._token and self._clock() - self._at < TOKEN_REFRESH_SECONDS:
            return self._token
        credential = self._workspace().postgres.generate_database_credential(endpoint=self._endpoint)
        self._token = credential.token
        self._at = self._clock()
        return self._token


def resolve_target(endpoint: str, database: str, user: str = "", client=None) -> LakebaseTarget:
    """Look up the endpoint's host and decide who we connect as (the service principal by default)."""
    from databricks.sdk import WorkspaceClient

    client = client or WorkspaceClient()
    ep = client.postgres.get_endpoint(name=endpoint)
    host = ((ep.status.hosts.host if ep.status and ep.status.hosts else "") or "").strip()
    if not host:
        raise RuntimeError(f"the Lakebase endpoint {endpoint!r} has no host yet")
    role = user or os.environ.get("DATABRICKS_CLIENT_ID", "") or client.current_user.me().user_name
    return LakebaseTarget(host=host, database=database, user=role, endpoint=endpoint)


def connection_class(source: TokenSource):
    """A psycopg connection class that supplies a fresh token as the password on every connect."""
    import psycopg

    class TokenConnection(psycopg.AsyncConnection):
        @classmethod
        async def connect(cls, conninfo: str = "", **kwargs):  # type: ignore[override]
            kwargs["password"] = await asyncio.to_thread(source.get)
            return await super().connect(conninfo, **kwargs)

    return TokenConnection
