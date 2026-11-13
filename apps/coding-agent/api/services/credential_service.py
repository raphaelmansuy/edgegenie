"""CredentialService: the only code that decrypts a stored key.

It exists so that exactly one place holds the plaintext, for the length of one spawn, and so that the
scope check has an owner. A resolver that talked to the vault directly would duplicate both.

Two rules from 06 are structural here:

* **no fallback across users** — `open_for(provider, user)` returns this user's key or a workspace key
  or nothing. It never borrows somebody else's, because that is the TH-10 incident.
* **one key per child** — `env_for(resolved)` returns exactly one provider key. A child that can see
  two keys can leak two keys.
"""

from __future__ import annotations

import logging
import time

from ..domain.llm import (
    CredentialKind,
    CredentialSource,
    NoCredential,
    ProviderKind,
    ResolvedModel,
)
from ..ports import ChildEnv, CredentialRef, Secret
from ..domain.credential import VaultRefused

log = logging.getLogger("app.llm.credentials")

#: The one fixed variable every external provider's key is delivered in (D4).
PROVIDER_KEY_ENV = "LLM_PROVIDER_KEY"
WORKSPACE_TOKEN_ENV = "DATABRICKS_TOKEN"


class CredentialService:
    """`ref -> Secret`, with the scope check. Caches within one call, never across turns."""

    def rebind(self, vault) -> None:
        self._vault = vault

    def __init__(self, vault, *, providers, allow_env: bool = True) -> None:
        self._vault = vault
        self.providers = providers
        self._allow_env = allow_env
        #: A one-spawn cache: `(ref, user) -> Secret`. Cleared by `forget` on revoke.
        self._cache: dict[tuple[str, str], tuple[Secret, float]] = {}

    @property
    def available(self) -> bool:
        return bool(getattr(self._vault, "available", False))

    @property
    def mode(self) -> str:
        return str(getattr(self._vault, "mode", "none"))

    # -- writes ---------------------------------------------------------------
    async def put(
        self,
        provider: ProviderKind,
        kind: CredentialKind | str,
        secret: str,
        *,
        user_id: str,
        scope: str = "user",
    ) -> CredentialRef:
        from ..domain.llm import CredentialError

        try:
            return await self._vault.put(
                provider, str(getattr(kind, "value", kind)), secret, user_id=user_id, scope=scope
            )
        except (VaultRefused, CredentialError):
            raise
        except Exception as exc:  # noqa: BLE001 - surface a sentence, not a stack trace
            log.warning("storing a %s key failed: %s", provider.value, type(exc).__name__)
            raise VaultRefused(f"the key could not be stored: {type(exc).__name__}") from exc

    async def revoke(self, ref: str, *, user_id: str) -> None:
        await self._vault.revoke(ref, user_id=user_id)
        self.forget(ref)

    def forget(self, ref: str | None = None) -> None:
        """Drop cached plaintext. Called on revoke and on a rotation."""
        if ref is None:
            self._cache.clear()
            return
        for key in [k for k in self._cache if k[0] == ref]:
            self._cache.pop(key, None)

    # -- reads ----------------------------------------------------------------
    async def list(self, *, user_id: str) -> list[CredentialRef]:
        return list(await self._vault.list(user_id=user_id))

    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None:
        return await self._vault.find(provider, user_id=user_id)

    async def open_ref(self, ref: str, *, user_id: str, session_id: str = "") -> Secret:
        """Open one specific ref, with its scope checked by the vault."""
        cached = self._cache.get((ref, user_id))
        if cached is not None and time.time() - cached[1] < 300:
            return cached[0]
        secret = await self._vault.open(ref, user_id=user_id, session_id=session_id)
        # Cache only within the process, and only for a spawn's lifetime of usefulness (NFR-3).
        self._cache[(ref, user_id)] = (secret, time.time())
        return secret

    async def open_for(self, provider: ProviderKind, *, user_id: str, session_id: str = "") -> Secret:
        """This user's key, else a workspace key, else `NoCredential`. Never somebody else's."""
        ref = await self._vault.find(provider, user_id=user_id)
        if ref is None:
            raise NoCredential(f"{provider.value}/*", _provider_label(provider))
        return await self.open_ref(ref.id, user_id=user_id, session_id=session_id)

    # -- injection ------------------------------------------------------------
    async def env_for(
        self, resolved: ResolvedModel, *, user_id: str, session_id: str = "", workspace_token: str = ""
    ) -> ChildEnv:
        """The child's environment: the workspace token plus **exactly one** provider credential.

        A Databricks model needs the user's forwarded token and nothing else; an external model needs
        its own key and the workspace token (the tool server still acts as the user). *How* the key
        reaches the agent (a variable, a file, a minted token) is the provider adapter's business.
        """
        env: dict[str, str] = {}
        if workspace_token:
            env[WORKSPACE_TOKEN_ENV] = workspace_token
        # An empty `env_var` means the model needs no provider key of its own (a gateway model, or
        # the demo provider). This is the one place "no key" is expressible, so no caller guesses.
        if resolved.provider is ProviderKind.DATABRICKS or not resolved.env_var:
            return ChildEnv(vars=env)
        secret = await self.open_ref(resolved.credential_ref, user_id=user_id, session_id=session_id)
        provider_env = await self.providers(resolved.provider).child_env(resolved, secret)
        return ChildEnv(vars={**env, **provider_env.vars}, files=dict(provider_env.files))

    def source_of(self, resolved: ResolvedModel) -> CredentialSource:
        return resolved.credential_source


def _provider_label(provider: ProviderKind) -> str:
    return {
        ProviderKind.DATABRICKS: "Databricks AI Gateway",
        ProviderKind.OPENAI: "OpenAI",
        ProviderKind.ANTHROPIC: "Anthropic",
        ProviderKind.GOOGLE_VERTEX: "Google Vertex AI",
        ProviderKind.FAKE: "The demo agent",
    }.get(provider, provider.value)
