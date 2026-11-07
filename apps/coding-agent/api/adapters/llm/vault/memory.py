"""The in-memory vault: tests, demo mode, and the shape every other vault must match.

It performs the **real** envelope encryption — the same DEK/KEK/AES-GCM path as the Postgres vault —
because a test double that skipped encryption would let a plaintext-leak bug pass every test. What it
does not do is survive a restart, which is the only difference that matters.

Two security rules are structural here, not conventions:

* a revoked row is checked and refused **before** any crypto work, so it is never decrypted (S7);
* the scope `(scope_kind, scope_id)` is checked before decryption, so a cross-user request is refused
  and recorded rather than decrypting somebody else's key (TH-10 / E-12).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from ....domain.llm import CredentialKind, CredentialParsed, ProviderKind, validate
from ....domain.redact import redact
from ....ports import CredentialRef, Secret
from .envelope import Sealed, Tampered, open_sealed, seal
from .kek import EnvKek, KekError, KekProvider


class VaultRefused(RuntimeError):
    """A key cannot be stored or opened, with a reason a person can act on."""


@dataclass
class _Row:
    ref_id: str
    provider: ProviderKind
    kind: str
    scope_kind: str
    scope_id: str
    parsed: CredentialParsed
    sealed: Sealed
    created_at: float = field(default_factory=time.time)
    last_used_at: float | None = None
    revoked_at: float | None = None


class MemoryVault:
    """A dict of encrypted rows, keyed by an opaque ref."""

    def __init__(self, kek: KekProvider | None = None) -> None:
        self._kek = kek or EnvKek.generate()
        self._rows: dict[str, _Row] = {}
        #: Refused operations, so a test can assert an attempt was refused *and recorded* (E-5/TH-10).
        self.refusals: list[str] = []

    @property
    def available(self) -> bool:
        return self._kek.usable

    @property
    def mode(self) -> str:
        return self._kek.mode

    # -- writes ---------------------------------------------------------------
    async def put(self, provider: ProviderKind, kind: str, secret: str, *,
                  user_id: str, scope: str = "user") -> CredentialRef:
        if not self._kek.usable:
            raise VaultRefused("keys cannot be saved: no key-encryption key is configured")
        parsed = validate(_credential_kind(kind), secret)
        # Rotation is insert + revoke, never update, so `last_used_at` history survives (E-11).
        previous = self._live(provider, scope, _scope_id(scope, user_id), kind)
        sealed = seal(parsed.secret, self._kek)
        row = _Row(uuid.uuid4().hex, provider, kind, scope, _scope_id(scope, user_id), parsed, sealed)
        self._rows[row.ref_id] = row
        if previous is not None:
            previous.revoked_at = time.time()
        return _ref(row)

    async def revoke(self, ref: str, *, user_id: str) -> None:
        row = self._rows.get(ref)
        if row is None or (row.scope_kind == "user" and row.scope_id != user_id):
            # A miss is recorded, not distinguished: a cross-user revoke must not confirm a ref.
            self.refusals.append(redact(f"revoke {ref} by {user_id}"))
            return
        row.revoked_at = time.time()

    # -- reads ----------------------------------------------------------------
    async def open(self, ref: str, *, user_id: str, session_id: str = "") -> Secret:
        row = self._rows.get(ref)
        if row is None:
            self.refusals.append(f"open {ref}: no such credential")
            raise VaultRefused("no such credential")
        # Revoked means never decrypted again, before any crypto work is done (S7).
        if row.revoked_at is not None:
            self.refusals.append(f"open {ref}: revoked")
            raise VaultRefused("this key was revoked")
        # TH-10: the scope is the boundary. A user-scoped key is usable only by that user.
        if row.scope_kind == "user" and row.scope_id != user_id:
            self.refusals.append(redact(f"open {ref}: {user_id} asked for {row.scope_id}'s key"))
            raise VaultRefused("this key belongs to another user")
        try:
            value = open_sealed(row.sealed, self._kek)
        except (Tampered, KekError) as exc:
            self.refusals.append(f"open {ref}: {type(exc).__name__}")
            raise VaultRefused(str(exc)) from exc
        row.last_used_at = time.time()
        return Secret(value=value, kind=row.kind, ref=row.ref_id)

    async def list(self, *, user_id: str) -> list[CredentialRef]:
        return [_ref(r) for r in self._rows.values()
                if r.revoked_at is None and r.scope_kind == "user" and r.scope_id == user_id]

    async def find(self, provider: ProviderKind, *, user_id: str) -> CredentialRef | None:
        """The most specific live key: this user's, else a workspace key. Never somebody else's."""
        row = self._live(provider, "user", user_id, None) or self._live(provider, "workspace", "", None)
        return _ref(row) if row else None

    # -- test affordances -----------------------------------------------------
    def rows(self) -> list[_Row]:
        """Every row, ciphertext included, so a test can assert the plaintext is not in any field."""
        return list(self._rows.values())

    def _live(self, provider: ProviderKind, scope_kind: str, scope_id: str,
              kind: str | None) -> _Row | None:
        hits = [r for r in self._rows.values()
                if r.revoked_at is None and r.provider is provider
                and r.scope_kind == scope_kind and r.scope_id == scope_id
                and (kind is None or r.kind == kind)]
        return hits[-1] if hits else None


def _ref(row: _Row) -> CredentialRef:
    return CredentialRef(id=row.ref_id, provider=row.provider, kind=row.kind,
                         scope_kind=row.scope_kind, scope_id=row.scope_id,
                         last4=row.parsed.last4, project_hint=row.parsed.project_hint,
                         fingerprint=row.parsed.fingerprint)


def _scope_id(scope: str, user_id: str) -> str:
    return user_id if scope == "user" else ""


def _credential_kind(kind: str) -> CredentialKind:
    try:
        return CredentialKind(kind)
    except ValueError:
        raise VaultRefused(f"{kind!r} is not a credential kind") from None
