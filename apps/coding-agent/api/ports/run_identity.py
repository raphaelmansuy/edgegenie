"""The run-identity spike must supply this authority before an isolated runner can be wired."""
from typing import Protocol
from ..domain.run_identity import RunIsolation
from .assets import Runnable


class RunIdentityVerifier(Protocol):
    async def inspect(self, principal: str, app_principal: str, secret_scope: str,
                      app_database: str) -> RunIsolation: ...


class IsolatedRunner(Runnable, Protocol):
    @property
    def principal(self) -> str: ...
