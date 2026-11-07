"""Credential storage. One package, three implementations of one port."""

from __future__ import annotations

from .envelope import Sealed, Tampered, open_sealed, seal
from .kek import EnvKek, KekError, KekProvider, NoneKek, ScopeKek, dev_kek_from_env, from_settings
from .local import EnvVault
from .memory import MemoryVault, VaultRefused

__all__ = [
    "EnvKek",
    "EnvVault",
    "KekError",
    "KekProvider",
    "MemoryVault",
    "NoneKek",
    "ScopeKek",
    "Sealed",
    "Tampered",
    "VaultRefused",
    "dev_kek_from_env",
    "from_settings",
    "open_sealed",
    "seal",
]
