"""How the agent's tool server asks the app to run a notebook.

The agent's tools act with the signed-in user's token, and a Databricks App's user authorization has no
jobs or compute scope, so a tool cannot submit a run itself: the workspace answers "permission denied".
The app CAN run Python on serverless compute, as its own service principal (`PythonRuns`). This bridge
lets the tool ask for that, without making the app's endpoint a door anyone can knock on:

  - the endpoint lives under `/internal/` and accepts a request only with a key derived from the app's
    boot-time secret AND one session id, handed to that session's tool server alone (a key for one
    session opens no other);
  - the app records, when the session is created, whether its user may run Python as the app
    (administrators only, the same rule as the notebook's Run button); the endpoint refuses the rest.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets


class RunBridge:
    def __init__(self, url: str, secret: str | None = None) -> None:
        self.url = url.rstrip("/")
        self._secret = (secret or secrets.token_hex(32)).encode()
        self._granted: set[str] = set()

    def key_for(self, session_id: str) -> str:
        return hmac.new(self._secret, session_id.encode(), hashlib.sha256).hexdigest()

    def verify(self, session_id: str, key: str) -> bool:
        return bool(session_id and key) and hmac.compare_digest(self.key_for(session_id), key)

    def grant(self, session_id: str) -> None:
        """This session's user may run Python as the app."""
        self._granted.add(session_id)

    def granted(self, session_id: str) -> bool:
        return session_id in self._granted

    def env_for(self, session_id: str) -> dict[str, str]:
        """What the session's tool server needs to ask. The key is useless without the grant."""
        return {"NBMCP_RUN_URL": f"{self.url}/internal/run-notebook",
                "NBMCP_RUN_SESSION": session_id, "NBMCP_RUN_KEY": self.key_for(session_id)}
