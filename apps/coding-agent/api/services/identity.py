"""Identity and groups. In Databricks the proxy forwards both the user and a scoped token."""

from __future__ import annotations

from ..config import Settings


class ForwardedIdentity:
    """Reads the headers Databricks Apps forwards. Never stores the token."""

    USER_HEADER = "x-forwarded-user"
    EMAIL_HEADER = "x-forwarded-email"
    TOKEN_HEADER = "x-forwarded-access-token"

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg

    def user_id(self, headers: dict[str, str]) -> str:
        h = {k.lower(): v for k, v in headers.items()}
        user = h.get(self.USER_HEADER) or h.get(self.EMAIL_HEADER)
        if user:
            return user
        if self._cfg.require_forwarded_user:
            raise PermissionError("no forwarded user: this app must run behind the Databricks proxy")
        return self._cfg.dev_user

    def home_name(self, headers: dict[str, str], user_id: str) -> str:
        """The name of the user's workspace home folder (/Users/<this>).

        Behind the Databricks proxy `x-forwarded-user` is "<numeric id>@<app id>", which is not a
        folder anyone has; the workspace home is named by the e-mail address.
        """
        h = {k.lower(): v for k, v in headers.items()}
        return h.get(self.EMAIL_HEADER) or user_id

    def token(self, headers: dict[str, str]) -> str | None:
        h = {k.lower(): v for k, v in headers.items()}
        return h.get(self.TOKEN_HEADER)


class NullGroups:
    """No SCIM, so no groups. Safe default: a model granted only to a group appears to nobody.

    The port exists so the app runs unchanged without an identity provider, and so that adding SCIM
    is an adapter rather than a change to the policy module (06 §Authorisation).
    """

    def groups_for(self, user_id: str) -> frozenset[str]:
        return frozenset()


class StaticGroups:
    """A fixed membership map, for tests and for a deployment that cannot reach SCIM."""

    def __init__(self, memberships: dict[str, set[str] | list[str]] | None = None) -> None:
        self._by_user = {k: frozenset(v) for k, v in (memberships or {}).items()}

    def groups_for(self, user_id: str) -> frozenset[str]:
        return self._by_user.get(user_id, frozenset())


__all__ = ["ForwardedIdentity", "NullGroups", "StaticGroups"]
