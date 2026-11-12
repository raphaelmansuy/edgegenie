"""A token for the APP's service principal, for the APIs that cannot run as the user.

Why this exists. `[RB-1]` says the identity is the boundary, and for most of this app it is: every
workspace read uses the user's forwarded token, so Unity Catalog decides what they see. But two APIs
in this product cannot work that way, and Databricks says so:

    "`postgres` — Lakebase (always bound to the SP, not OBO)"
    "`secret`, Lakebase (`database` / `postgres`), and MLflow (`experiment`) resources are always
     bound to the service principal and cannot run OBO, even under `--auth-mode obo`."
                                    — databricks-agent-skills, skills/databricks-apps, platform-guide

So declaring `postgres` in `user_api_scopes` does NOT put it in the user's token. The scope appears
in `effective_user_api_scopes` (the app requested it) while the forwarded token carries only what the
OAuth consent issued. Every Lakebase call then answers 403, and no amount of signing in changes it —
which is exactly the dead end the deployed app showed: a "Sign in again" button that could not work.

`databricks.sdk.WorkspaceClient()` authenticates as the service principal here, because a Databricks
App injects `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`. That is the same mechanism the
app's own Lakebase connection already relies on (`adapters/llm/store/lakebase.py::TokenSource`), which
is why the model registry has always worked while this page did not.

A token is minted once and reused until shortly before it expires. It is never logged, never returned
to a browser, and never written to disk.
"""

from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger("app.dbx.sp")

#: Re-mint this long before the token expires. OAuth tokens last about an hour.
REFRESH_EARLY_SECONDS = 45 * 60


class ServicePrincipalToken:
    """Mints and caches an OAuth token for the app's own identity.

    `available()` is false when the app is running outside a Databricks App (a laptop, a test): there
    is no injected client id, so `WorkspaceClient()` would authenticate as whoever the developer is.
    Callers use it to decide whether to attempt an SP call at all, rather than discovering it with a
    confusing 403.
    """

    def __init__(self, client=None, clock=time.monotonic) -> None:
        self._client = client
        self._clock = clock
        self._token = ""
        self._at = 0.0
        self._lock = threading.Lock()

    def available(self) -> bool:
        """True when this process has a service principal to authenticate as."""
        return bool(os.environ.get("DATABRICKS_CLIENT_ID") or self._client is not None)

    def _workspace(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient

            # NAME the identity instead of letting the SDK's default auth chain choose one. The chain
            # tries a PAT (DATABRICKS_TOKEN) before oauth-m2m, so a container that happens to define
            # DATABRICKS_TOKEN would silently authenticate as a person here — the same class of
            # implicit-identity bug this module exists to remove. A Databricks App injects
            # DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET; when both are present, use them.
            client_id = os.environ.get("DATABRICKS_CLIENT_ID", "")
            client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET", "")
            host = os.environ.get("DATABRICKS_HOST", "")
            if client_id and client_secret:
                self._client = WorkspaceClient(host=host or None, client_id=client_id,
                                               client_secret=client_secret, auth_type="oauth-m2m")
            else:
                self._client = WorkspaceClient()
        return self._client

    def get(self) -> str:
        """The token, refreshed when it is old. Raises when the app has no identity to use."""
        with self._lock:
            if self._token and self._clock() - self._at < REFRESH_EARLY_SECONDS:
                return self._token
            if not self.available():
                # Fail loudly rather than minting whatever the SDK's chain finds. A personal token
                # here would make the panes show one person's projects while claiming to show the
                # app's, which is a worse failure than an honest refusal (spec 013 [RB-10]).
                raise RuntimeError(
                    "this process has no service principal (DATABRICKS_CLIENT_ID is unset); the "
                    "Lakebase and Apps panes need the app's own identity, not a user's")
            client = self._workspace()
            auth = getattr(client.config, "authenticate", None)
            if auth is None:                       # pragma: no cover - SDK shape guard
                raise RuntimeError("this SDK cannot mint a service-principal token")
            headers = auth() or {}
            token = ""
            for key, value in headers.items():
                if key.lower() == "authorization" and value.lower().startswith("bearer "):
                    token = value[7:].strip()
                    break
            if not token:
                raise RuntimeError(
                    "the app has no service-principal token; is DATABRICKS_CLIENT_ID/SECRET missing?")
            self._token, self._at = token, self._clock()
            return token


def provider(source: ServicePrincipalToken):
    """A `token_provider` callable for `DbxHttp`, in the shape the adapters expect.

    The adapters call `token_provider()` expecting a string or None; this returns the SP token
    synchronously and lets an exception surface as a clear sentence instead of a silent empty call.
    """
    def provide() -> str | None:
        try:
            return source.get()
        except Exception as exc:  # noqa: BLE001 - a missing identity is a configuration fact
            log.warning("no service-principal token: %s", exc)
            return None
    return provide
