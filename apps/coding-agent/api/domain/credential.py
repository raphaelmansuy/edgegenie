"""Credential failures shared by vault ports and their implementations."""


class VaultRefused(RuntimeError):
    """A key cannot be stored or opened, with a reason a person can act on."""
