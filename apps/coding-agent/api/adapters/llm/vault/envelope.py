"""Envelope encryption: one DEK per row, wrapped by the KEK.

The shape is the security control (06 §The envelope scheme):

    ciphertext = AES-256-GCM(DEK, plaintext)   stored with its iv and auth tag
    wrapped_dek = KEK.wrap(DEK)                stored beside the ciphertext
    the KEK lives outside the database         so a dump is not a key dump

GCM rather than CBC+HMAC because GCM *authenticates*: a tampered row fails to decrypt instead of
yielding garbage that is then sent to a provider. A DEK per row means rotating the KEK costs one
unwrap/wrap per row, and one row's compromise is bounded to that row.

Pure apart from `os.urandom`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .kek import KekProvider

DEK_BYTES = 32
IV_BYTES = 12
TAG_BYTES = 16


@dataclass(frozen=True, slots=True)
class Sealed:
    """One encrypted row. Every field is opaque; the plaintext is nowhere in here."""

    ciphertext: bytes
    iv: bytes
    auth_tag: bytes
    wrapped_dek: bytes
    kek_key_id: str


class Tampered(RuntimeError):
    """A row that does not authenticate. An incident, never a retry: the ciphertext was altered."""


def seal(plaintext: str, kek: KekProvider) -> Sealed:
    """Encrypt one secret under a fresh DEK. Never returns the plaintext in any field."""
    dek = os.urandom(DEK_BYTES)
    iv = os.urandom(IV_BYTES)
    sealed = AESGCM(dek).encrypt(iv, plaintext.encode("utf-8"), None)
    # `cryptography` returns ciphertext||tag; splitting it keeps the column shape the schema
    # documents, and makes the tag a thing a reader can see is verified.
    body, tag = sealed[:-TAG_BYTES], sealed[-TAG_BYTES:]
    wrapped, key_id = kek.wrap(dek)
    return Sealed(body, iv, tag, wrapped, key_id)


def open_sealed(row: Sealed, kek: KekProvider) -> str:
    """Decrypt one row. Raises `Tampered` when the ciphertext or the tag was altered."""
    dek = kek.unwrap(row.wrapped_dek, row.kek_key_id)
    try:
        return AESGCM(dek).decrypt(row.iv, row.ciphertext + row.auth_tag, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - every failure here means "do not trust this row"
        raise Tampered("the credential row did not authenticate: tampered, or the wrong KEK") from exc
