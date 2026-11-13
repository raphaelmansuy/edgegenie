"""Legacy session-key compatibility for disabled internal execution routes.

No production caller grants this bridge. Even a retained grant is refused by the route; human
administrator execution is authorized independently and is never exposed to the agent.
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
        return {
            "NBMCP_RUN_URL": f"{self.url}/internal/run-notebook",
            "NBMCP_RUN_SESSION": session_id,
            "NBMCP_RUN_KEY": self.key_for(session_id),
        }
