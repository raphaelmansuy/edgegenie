"""The env vault: keys come from the environment, so an app with no database still works.

This is C-5's credential half. `LLM_<PROVIDER>_KEY` (for example `LLM_OPENAI_KEY`) is read once and
held in memory; nothing can be stored, because there is nowhere to put it. That is the honest answer
rather than a pretend key store: the settings screen says keys cannot be saved *here*, and the
picker still opens.

A service-account JSON may be long and contain newlines, so a value that starts with `{` is parsed
rather than treated as a token — that is the shape a deployment's env var really takes.
"""

from __future__ import annotations

import os

from ....domain.llm import CredentialKind, ProviderKind, validate, with_project
from ....ports import CredentialRef, Secret
from .memory import VaultRefused

_ENV_SUFFIX = {
    ProviderKind.OPENAI: "OPENAI",
    ProviderKind.ANTHROPIC: "ANTHROPIC",
    ProviderKind.GOOGLE_VERTEX: "VERTEX",
    ProviderKind.DATABRICKS: "DATABRICKS",
}


class EnvVault:
    """Read-only credentials from the process environment. Never writable."""

    mode = "env-only"

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    @property
    def available(self) -> bool:
        """Storing is unavailable by definition; reading may still work for the environment's keys."""
        return False

    def env_name(self, provider: ProviderKind) -> str:
        return f"LLM_{_ENV_SUFFIX.get(provider, provider.value.upper())}_KEY"

    def _raw(self, provider: ProviderKind) -> str:
        return (self._env.get(self.env_name(provider)) or "").strip()

    def _kind(self, provider: ProviderKind, raw: str) -> CredentialKind:
        return CredentialKind.SERVICE_ACCOUNT_JSON if raw.startswith("{") else CredentialKind.API_KEY

    def _parsed(self, provider: ProviderKind, raw: str):
        """Validate one env value. `LLM_<PROVIDER>_PROJECT` names the project for a key that omits it."""
        kind = self._kind(provider, raw)
        project = (self._env.get(self.env_name(provider).replace("_KEY", "_PROJECT")) or "").strip()
        return validate(kind, with_project(kind, raw, project))

    async def put(self, provider: ProviderKind, kind: str, secret: str, *,
                  user_id: str, scope: str = "user") -> CredentialRef:
        raise VaultRefused("keys cannot be saved: the model database is unreachable")

    async def revoke(self, ref: str, *, user_id: str) -> None:
        raise VaultRefused("keys cannot be revoked: the model database is unreachable")

    async def open(self, ref: str, *, user_id: str, session_id: str = "") -> Secret:
        """`ref` is `env:<provider>`, so a resolved model can still name where its key came from."""
        provider = ProviderKind(ref.split(":", 1)[-1])
        raw = self._raw(provider)
        if not raw:
            raise VaultRefused(f"no {self.env_name(provider)} in the environment")
        parsed = self._parsed(provider, raw)
        return Secret(value=parsed.secret, kind=parsed.kind.value, ref=ref)

    async def list(self, *, user_id: str) -> list[CredentialRef]:
        out: list[CredentialRef] = []
        for provider in (ProviderKind.OPENAI, ProviderKind.ANTHROPIC, ProviderKind.GOOGLE_VERTEX):
            raw = self._raw(provider)
            if not raw:
                continue
            parsed = self._parsed(provider, raw)
            out.append(CredentialRef(id=f"env:{provider.value}", provider=provider,
                                     kind=parsed.kind.value, scope_kind="workspace",
                                     last4=parsed.last4, project_hint=parsed.project_hint,
                                     fingerprint=parsed.fingerprint))
        return out

    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None:
        raw = self._raw(provider)
        if not raw:
            return None
        parsed = self._parsed(provider, raw)
        return CredentialRef(id=f"env:{provider.value}", provider=provider,
                             kind=parsed.kind.value, scope_kind="workspace",
                             last4=parsed.last4, project_hint=parsed.project_hint,
                             fingerprint=parsed.fingerprint)
