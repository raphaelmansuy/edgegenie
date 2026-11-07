"""The durable vault: envelope-encrypted rows in `llm.llm_credential`.

It is the same encryption path as `MemoryVault` (`envelope.seal`/`open_sealed`), with the rows in
Postgres instead of a dict. The table enforces the shape (05): ciphertext and `wrapped_dek` are
`NOT NULL`, so a plaintext row cannot be written even by mistake.

Rotation is insert + revoke rather than update, so `last_used_at` history survives and an audit can
say which key a turn used (E-11). A revoked row is never decrypted because the SQL refuses it before
`open_sealed` is ever reached (S7).
"""

from __future__ import annotations

import logging

from ....domain.llm import CredentialKind, CredentialParsed, ProviderKind, validate
from ....domain.redact import redact
from ....ports import CredentialRef, Secret
from ..store.pg import PgRegistryStore
from .envelope import Sealed, Tampered, open_sealed, seal
from .kek import KekError, KekProvider
from .memory import VaultRefused

log = logging.getLogger("app.llm.vault.pg")


class PgVault:
    """Store, open, revoke against the credential table. No method returns plaintext except `open`."""

    def __init__(self, store: PgRegistryStore, kek: KekProvider) -> None:
        self._store = store
        self._kek = kek
        #: Refusals, so an incident is diagnosable without a secret in the log (TH-10).
        self.refusals: list[str] = []

    @property
    def available(self) -> bool:
        return self._kek.usable

    @property
    def mode(self) -> str:
        return self._kek.mode

    async def put(self, provider: ProviderKind, kind: str, secret: str, *,
                  user_id: str, scope: str = "user") -> CredentialRef:
        if not self._kek.usable:
            raise VaultRefused("keys cannot be saved: no key-encryption key is configured")
        parsed: CredentialParsed = validate(_kind(kind), secret)
        sealed = seal(parsed.secret, self._kek)
        ref = await self._store.insert_credential(
            provider=provider, kind=parsed.kind.value, scope_kind=scope,
            scope_id=user_id if scope == "user" else "", sealed=sealed,
            last4=parsed.last4, fingerprint=parsed.fingerprint, project_hint=parsed.project_hint)
        return CredentialRef(id=ref, provider=provider, kind=parsed.kind.value, scope_kind=scope,
                             scope_id=user_id if scope == "user" else "",
                             last4=parsed.last4, project_hint=parsed.project_hint,
                             fingerprint=parsed.fingerprint)

    async def open(self, ref: str, *, user_id: str, session_id: str = "") -> Secret:
        row = await self._store.open_credential(ref, user_id=user_id)
        if row is None:
            # One message for "absent", "revoked" and "somebody else's": a miss must not confirm a ref.
            self.refusals.append(f"open {ref}: refused for {user_id}")
            log.warning("credential open refused for %s (session %s)", user_id, session_id or "-")
            raise VaultRefused("this key is not available to you")
        sealed, meta = row
        try:
            value = open_sealed(sealed, self._kek)
        except (Tampered, KekError) as exc:
            self.refusals.append(f"open {ref}: {type(exc).__name__}")
            log.error("credential decrypt failed for ref %s: %s", ref, type(exc).__name__)
            raise VaultRefused(str(exc)) from exc
        await self._touch(ref)
        return Secret(value=value, kind=meta["kind"], ref=ref)

    async def revoke(self, ref: str, *, user_id: str) -> None:
        await self._store.revoke_credential(ref, user_id=user_id)

    async def list(self, *, user_id: str) -> list[CredentialRef]:
        out: list[CredentialRef] = []
        for row in await self._store.list_credentials(user_id=user_id):
            out.append(CredentialRef(id=row["id"], provider=ProviderKind(row["provider"]),
                                     kind=row["kind"], scope_kind=row.get("scope", "user"),
                                     last4=row.get("last4", ""),
                                     project_hint=row.get("projectHint", "")))
        return out

    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None:
        row = await self._store.live_credential(provider, user_id=user_id)
        if row is None:
            return None
        return CredentialRef(id=row["id"], provider=provider, kind=row["kind"],
                             scope_kind=row.get("scope_kind", "user"),
                             last4=row.get("last4", ""), project_hint=row.get("project_hint", ""))

    async def _touch(self, ref: str) -> None:
        """`last_used_at` is the only mutable column, and it is what rotation advice is based on."""
        try:
            await self._store._run(  # noqa: SLF001 - one statement, owned by this table
                "UPDATE llm.llm_credential SET last_used_at = now() WHERE id = %s::uuid", (ref,))
        except Exception:  # noqa: BLE001 - a failed touch must never fail a spawn
            log.debug("could not stamp last_used_at for %s", ref)


def _kind(kind: str) -> CredentialKind:
    try:
        return CredentialKind(kind)
    except ValueError:
        raise VaultRefused(redact(f"{kind!r} is not a credential kind")) from None


__all__ = ["PgVault"]
