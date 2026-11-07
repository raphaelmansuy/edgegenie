"""Approval tokens for a human write that the fence sent to ASK.

An agent's out-of-fence write is approved through the turn's approval flow (`POST /approvals/...`),
because a turn is already a stateful conversation. A human save is not: it happens from the editor,
possibly with no session open, so binding its approval to session state would either require a
session or allow an approval to leak across documents.

So the approval is a **stateless, path-bound token**:

    token = HMAC(secret, path + "\n" + version + "\n" + exp)

Properties this buys, each of which is a test:

  * **Bound to one path.** An approval for `/a` cannot authorise `/b`.
  * **Bound to the version the user was shown.** An approval cannot be replayed onto a newer
    revision that the user never saw.
  * **Expires.** A token is good for `TTL` seconds; an approval is a decision about the present.
  * **Unforgeable without the secret**, and the secret never leaves the server.

This is deliberately *not* stored anywhere: there is nothing to clean up, nothing to leak between
users, and no session required. The trade-off is that a token cannot be revoked early — acceptable
because its lifetime is short and its scope is one path.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

#: How long an approval stays valid. Long enough to read the dialog and decide; short enough that a
#: leaked token is nearly worthless.
TTL = 120

#: In-process secret. A restart invalidates outstanding approvals, which is the right default: the
#: user re-approves. An env override keeps multiple app instances consistent.
_SECRET = os.environ.get("APP_APPROVAL_SECRET") or os.urandom(32)


def _sign(path: str, version: str, exp: int) -> str:
    msg = f"{path}\n{version}\n{exp}".encode()
    secret = _SECRET.encode() if isinstance(_SECRET, str) else _SECRET
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:40]


def issue(path: str, version: str, *, now: float | None = None, ttl: int = TTL) -> str:
    """Mint an approval for one path at one version."""
    exp = int((now if now is not None else time.time()) + ttl)
    return f"{exp}.{_sign(path, version, exp)}"


def verify(token: str | None, path: str, version: str, *, now: float | None = None) -> bool:
    """Is this token a live approval for this path at this version?

    Every failure is a plain `False`: the caller must not learn *why* a token failed, because
    distinguishing "expired" from "wrong path" tells an attacker which half they got right.
    """
    if not token or "." not in token:
        return False
    head, _, sig = token.partition(".")
    try:
        exp = int(head)
    except ValueError:
        return False
    if exp < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(sig, _sign(path, version, exp))
