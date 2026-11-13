"""Fail-closed qualification values for a future execution identity (spec 014 S13).

No runnable adapter is enabled until a platform spike establishes how to inspect both permission
boundaries. A declared but unqualified identity must fail deployment, never fall back to the app.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RunIsolation:
    principal: str
    app_principal: str
    key_secret_readable: bool | None
    app_database_readable: bool | None

    def require_isolated(self):
        if (not self.principal or not self.app_principal or self.principal == self.app_principal
                or self.key_secret_readable is not False or self.app_database_readable is not False):
            raise PermissionError("Execution identity isolation is unverified or can reach app secrets/database.")


def check_declaration(principal: str):
    if principal.strip():
        raise ValueError("A separate agent run identity was declared but has no qualified isolation adapter. "
                         "Complete spec 014 spike S13 before enabling it; app-identity fallback is forbidden.")
