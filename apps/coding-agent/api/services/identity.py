"""Identity and model policy. In Databricks the proxy forwards both the user and a scoped token."""

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


class StaticModelCatalog:
    """Allow-list per user. A catalogue entry must also be served by the workspace (RB-11)."""

    def __init__(self, cfg: Settings, extra_allowed: dict[str, list[str]] | None = None) -> None:
        self._cfg = cfg
        self._extra = extra_allowed or {}

    def allowed(self, user_id: str) -> list[dict]:
        ids = list(self._cfg.allowed_models) + self._extra.get(user_id, [])
        return [
            {"id": m, "name": m.split("/")[-1], "default": m == self._cfg.default_model}
            for m in dict.fromkeys(ids)
        ]

    def check(self, user_id: str, model: str) -> None:
        if model not in {m["id"] for m in self.allowed(user_id)}:
            raise ValueError(f"model {model} is not allowed for this user")
