"""Key-encryption keys: two providers, one interface, and a visible downgrade.

The KEK is the one thing that must never be in the database, because the whole point of envelope
encryption is that reading the database does not yield keys (06 §The envelope scheme). Three
implementations, each with a stated failure behaviour:

| Implementation | When | Failure |
|---|---|---|
| `ScopeKek` | a Databricks secret scope is readable by the app's service principal | fail closed |
| `EnvKek` | local development, demo mode, a pilot without a scope | fail closed, **and announced at boot** |
| `NoneKek` | explicit opt-in for tests only | `put` refuses unless `APP_ENV=dev` |

A security posture that is silently weaker in production is the failure mode these classes exist to
prevent, so `mode` is a property every caller can read and the settings screen prints.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: A KEK is 32 bytes: AES-256. Anything else is a configuration error, not something to pad.
KEY_BYTES = 32


class KekError(RuntimeError):
    """No usable KEK. Fail closed: no key, no external models."""


class KekProvider(Protocol):
    @property
    def mode(self) -> str: ...
    @property
    def key_id(self) -> str: ...
    def wrap(self, dek: bytes) -> tuple[bytes, str]: ...
    def unwrap(self, wrapped: bytes, key_id: str) -> bytes: ...
    @property
    def usable(self) -> bool: ...


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


class EnvKek:
    """A KEK from `LLM_KEK` (base64, 32 bytes). Development and pilot mode; announced at boot."""

    mode = "env"

    def __init__(self, key: str, key_id: str = "env-1") -> None:
        try:
            raw = _unb64(key.strip())
        except (ValueError, TypeError) as exc:
            raise KekError(f"LLM_KEK is not valid base64: {exc}") from exc
        if len(raw) != KEY_BYTES:
            raise KekError(f"LLM_KEK must decode to {KEY_BYTES} bytes, got {len(raw)}")
        self._key = raw
        self._id = key_id

    @classmethod
    def generate(cls, key_id: str = "env-1") -> EnvKek:
        return cls(_b64(os.urandom(KEY_BYTES)), key_id)

    @property
    def key_id(self) -> str:
        return self._id

    @property
    def usable(self) -> bool:
        return True

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._key).encrypt(nonce, dek, self._id.encode()), self._id

    def unwrap(self, wrapped: bytes, key_id: str) -> bytes:
        if key_id != self._id:
            raise KekError(f"this KEK is {self._id!r}, the row was wrapped by {key_id!r}")
        return AESGCM(self._key).decrypt(wrapped[:12], wrapped[12:], self._id.encode())


class ScopeKek:
    """A KEK read from a Databricks secret scope by the app's service principal.

    The *value* is fetched once at boot and held in memory; nothing here calls the workspace API, so a
    later permission change cannot silently break decryption mid-session. `usable` is False when the
    value could not be read, and every caller then refuses to store a key rather than falling back to
    a weaker KEK.
    """

    mode = "scope"

    def __init__(self, value: str | None, key_id: str = "scope:llm/kek") -> None:
        self._id = key_id
        self._inner: EnvKek | None = None
        if value:
            try:
                self._inner = EnvKek(value, key_id)
            except KekError:
                self._inner = None

    @property
    def key_id(self) -> str:
        return self._id

    @property
    def usable(self) -> bool:
        return self._inner is not None

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        if self._inner is None:
            raise KekError("no readable KEK in the secret scope: keys cannot be saved")
        return self._inner.wrap(dek)

    def unwrap(self, wrapped: bytes, key_id: str) -> bytes:
        if self._inner is None:
            raise KekError("no readable KEK in the secret scope: keys cannot be opened")
        return self._inner.unwrap(wrapped, key_id)


class NoneKek:
    """No KEK at all. `put` is refused unless this is explicitly a development environment.

    This class exists so that "no key store" is a value with a reason, not a `None` that a caller
    forgets to check.
    """

    mode = "none"
    key_id = ""
    usable = False

    def __init__(self, reason: str = "no KEK configured") -> None:
        self.reason = reason

    def wrap(self, dek: bytes) -> tuple[bytes, str]:
        raise KekError(self.reason)

    def unwrap(self, wrapped: bytes, key_id: str) -> bytes:
        raise KekError(self.reason)


def from_settings(*, env: str | None = None, secret_scope_value: str | None = None,
                  env_kek: str | None = None, scope_name: str = "") -> KekProvider:
    """Choose the KEK the way 06 specifies: scope first, then env, then none.

    The order is the trust order, not the convenience order. A production app with neither refuses to
    store keys and says so — which is R-5's mitigation, implemented as a selection rule.
    """
    if secret_scope_value:
        scope = ScopeKek(secret_scope_value, key_id=f"scope:{scope_name or 'llm/kek'}")
        if scope.usable:
            return scope
    if env_kek:
        try:
            return EnvKek(env_kek, key_id="env-1")
        except KekError:
            return NoneKek("LLM_KEK is set but unreadable")
    return NoneKek("no KEK configured (set LLM_KEK or attach a secret scope)")


def dev_kek_from_env() -> KekProvider:
    """The process-wide default: the KEK configured for this deployment, or none."""
    import logging

    configured = os.environ.get("LLM_KEK", "")
    kek = from_settings(env_kek=configured or None)
    if kek.mode == "env":
        logging.getLogger("app.llm.vault").warning(
            "keys are protected by a development KEK from LLM_KEK; a container dump would yield it")
    return kek
