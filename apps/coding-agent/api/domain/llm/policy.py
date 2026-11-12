"""Authorisation: may this user use this model, and may this session use this key.

Two independent checks, both required (06 §Authorisation). This module is the first one — pure, so
the precedence rules are testable without a database:

1. an explicit deny for the exact user wins over everything;
2. an explicit user allow beats a group grant;
3. a group grant applies when the user is in the group;
4. an `all` grant applies;
5. no rows at all means open (the current product behaviour, stated so it is a decision).

The second check — credential scope — belongs to `CredentialService`, because it needs the vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import NotGranted
from .model import Grant, ModelSpec


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY_NOT_GRANTED = "not_granted"
    DENY_NO_CREDENTIAL = "no_credential"
    DENY_NOT_SELECTABLE = "not_selectable"
    DENY_UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class Decision:
    """One answer, with the copy that goes with it. Never a bare boolean."""

    verdict: Verdict
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW

    def raise_if_denied(self, spec: ModelSpec) -> None:
        """Turn the decision into the typed error the route maps to a status."""
        from .errors import NoCredential, NotSelectable, ProviderUnhealthy

        if self.allowed:
            return
        if self.verdict is Verdict.DENY_NOT_GRANTED:
            raise NotGranted(spec.id.value)
        if self.verdict is Verdict.DENY_NO_CREDENTIAL:
            raise NoCredential(spec.id.value, spec.provider_name)
        if self.verdict is Verdict.DENY_UNHEALTHY:
            raise ProviderUnhealthy(self.reason)
        raise NotSelectable(spec.id.value, self.reason or "this model cannot be used here")


def may_use(spec: ModelSpec, user: str, grant: Grant | None,
            groups: frozenset[str] = frozenset(), *, require_healthy: bool = False) -> Decision:
    """The full decision for one model and one user.

    Order matters and is the specification: a model the user was not granted is refused before its
    health is even considered, because "ask an admin" is the actionable message and "it is down" is
    not something the user can fix.
    """
    if grant is not None and not grant.allows(user, groups):
        return Decision(Verdict.DENY_NOT_GRANTED)
    if not spec.selectable:
        return Decision(Verdict.DENY_NOT_SELECTABLE,
                        spec.refusal or _not_selectable_reason(spec))
    if require_healthy and not spec.state.usable:
        return Decision(Verdict.DENY_UNHEALTHY, spec.detail or f"the model is {spec.state.value}")
    return Decision(Verdict.ALLOW)


def _not_selectable_reason(spec: ModelSpec) -> str:
    from .model import Capability, ModelState

    if spec.state is ModelState.NOT_ENABLED:
        return (f"Not enabled in this workspace. An account admin must enable it in the AI Gateway.")
    if spec.state is ModelState.NOT_SERVED:
        return "Not served in this workspace."
    if spec.capability is Capability.CHAT_ONLY:
        return "This model cannot call tools, which this agent needs."
    return f"{spec.display_name} is not available here."
