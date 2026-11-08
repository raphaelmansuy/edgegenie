"""A vault that stores keys AND still honours the keys the operator put in the environment.

An operator attaches a provider key to the app as a secret resource (`LLM_VERTEX_KEY`) so everyone can
use that provider without bringing a key of their own. Users and administrators may also save keys in
the app, which needs a writable vault. These are two sources of one thing, and choosing a writable
vault must not silently drop the other: when it did, enabling the key store made every model that
relied on the operator's key fail with "needs a key" on a deployment where nothing about that key had
changed.

Order of precedence, for one provider: the caller's own saved key, then a saved workspace key, then
the operator's environment key. Writes go only to the writable vault; the environment is read-only.
"""

from __future__ import annotations

from ....domain.llm import ProviderKind
from ....ports import CredentialRef, Secret

ENV_PREFIX = "env:"


class LayeredVault:
    def __init__(self, writable, environment) -> None:
        self._writable = writable
        self._env = environment

    @property
    def mode(self) -> str:
        return getattr(self._writable, "mode", "layered")

    @property
    def available(self) -> bool:
        return bool(getattr(self._writable, "available", False))

    async def put(self, provider: ProviderKind, kind: str, secret: str, *,
                  user_id: str, scope: str = "user") -> CredentialRef:
        return await self._writable.put(provider, kind, secret, user_id=user_id, scope=scope)

    async def revoke(self, ref: str, *, user_id: str) -> None:
        # The environment's key is the operator's: it cannot be revoked from the screen.
        await (self._env if ref.startswith(ENV_PREFIX) else self._writable).revoke(ref, user_id=user_id)

    async def open(self, ref: str, *, user_id: str, session_id: str = "") -> Secret:
        target = self._env if ref.startswith(ENV_PREFIX) else self._writable
        return await target.open(ref, user_id=user_id, session_id=session_id)

    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None:
        return (await self._writable.find(provider, user_id=user_id)
                or await self._env.find(provider, user_id=user_id))

    async def list(self, *, user_id: str) -> list[CredentialRef]:
        saved = list(await self._writable.list(user_id=user_id))
        have = {c.provider for c in saved}
        return saved + [c for c in await self._env.list(user_id=user_id) if c.provider not in have]

    def __getattr__(self, name: str):  # anything else the writable vault offers (rotate, counts, ...)
        return getattr(self._writable, name)
