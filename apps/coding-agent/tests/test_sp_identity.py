"""Which identity the infrastructure routes use, and why it is not the user's.

`[RB-10]` is the strongest constraint in this spec, and the deployed app proved it the hard way:
`postgres` is "always bound to the SP, not OBO" (Databricks' platform guide), so declaring the scope
makes it *effective on the app* and changes nothing in the forwarded user token. Every Lakebase call
then 403s, and the app offered a "Sign in again" button that could never work.

So these routes authenticate as the app's service principal. This file holds that decision: it fails
if someone switches them back to `_user_token`, which is the natural-looking mistake.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from api.adapters.databricks.sp_token import ServicePrincipalToken, provider
from api.config import Settings
from api.main import build

APP = Path(__file__).resolve().parents[1]


def jwt(claims: dict) -> str:
    """A token-shaped string whose payload is readable, so `token_scopes` can decode it."""
    def enc(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


# -- the token source --------------------------------------------------------------------------
class FakeAuth:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def authenticate(self):
        self.calls += 1
        return {"Authorization": f"Bearer {self.token}"}


class FakeClient:
    def __init__(self, token: str) -> None:
        self.config = FakeAuth(token)


def test_a_token_is_minted_once_and_reused():
    """An hour-long token called per request would be one workspace round trip per page load."""
    client = FakeClient("tok-1")
    source = ServicePrincipalToken(client=client)
    assert source.get() == "tok-1"
    assert source.get() == "tok-1"
    assert client.config.calls == 1, "the token was re-minted for a second call"


def test_a_token_is_refreshed_before_it_expires():
    clock = [0.0]
    client = FakeClient("tok-1")
    source = ServicePrincipalToken(client=client, clock=lambda: clock[0])
    source.get()
    clock[0] = 46 * 60                       # past REFRESH_EARLY_SECONDS
    client.config.token = "tok-2"
    assert source.get() == "tok-2"


def test_no_identity_is_refused_rather_than_borrowed_from_the_sdk_chain(monkeypatch):
    """Outside a Databricks App there is no client id, and `get()` must say so.

    It used to call `WorkspaceClient()` anyway, whose default auth chain tries a PAT before
    oauth-m2m — so a container that happened to define DATABRICKS_TOKEN would authenticate as a
    person while the panes claimed to show the app's objects. A refusal is the honest answer."""
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_SECRET", raising=False)
    source = ServicePrincipalToken()
    assert source.available() is False
    with pytest.raises(RuntimeError, match="no service principal"):
        source.get()


def test_the_service_principal_is_named_not_inferred(monkeypatch):
    """With both credentials present the client is built for oauth-m2m specifically.

    The constructor is intercepted rather than called: a real `WorkspaceClient` reaches the network,
    and this test is about which arguments we pass, not about the SDK working.
    """
    import databricks.sdk

    captured: dict = {}

    class Spy:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.config = type("C", (), {"authenticate": lambda self: {"Authorization": "Bearer x"}})()

    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", Spy)
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "abc-123")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "shh")
    monkeypatch.setenv("DATABRICKS_HOST", "https://h.cloud.databricks.com")

    source = ServicePrincipalToken()
    assert source.available() is True
    assert source.get() == "x"
    assert captured["auth_type"] == "oauth-m2m", "the identity must be NAMED, not inferred"
    assert captured["client_id"] == "abc-123"
    assert captured["client_secret"] == "shh"


def test_the_provider_returns_none_instead_of_raising():
    """`DbxHttp` expects a string or None; an exception there would surface as a broken pane."""
    class Broken:
        def get(self):
            raise RuntimeError("no identity")

    assert provider(Broken())() is None


# -- the routes -----------------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    app = build(Settings(agent_mode="fake", allowed_models=["fake/model-a"], default_model="fake/model-a"))
    return TestClient(app)


def test_the_infra_routes_use_the_service_principal_not_the_user(client):
    """[RB-10] The decision, asserted where it is made.

    A user token is present and readable; the SP token is different and readable. If the route used
    the user's, the adapters would receive the user's claims — which is the deployed defect."""
    sp_claims = {"scope": "postgres apps sql", "sub": "service-principal"}
    user_claims = {"scope": "sql files", "sub": "raphael@example.com"}

    seen: list[str | None] = []

    class Recorder:
        available = staticmethod(lambda: True)
        get = staticmethod(lambda: jwt(sp_claims))

    client.app.state.sp_token = Recorder()

    browser = client.app.state.lakebase
    original = browser._http.get

    async def record(path, token, params=None):
        seen.append(token)
        raise LookupError("not found")          # the call's outcome is irrelevant here

    browser._http.get = record
    try:
        client.get("/api/lakebase/projects",
                   headers={"x-forwarded-access-token": jwt(user_claims)})
    finally:
        browser._http.get = original

    assert seen, "the route did not call the adapter at all"
    assert seen[0] == jwt(sp_claims), "the route used a token other than the service principal's"
    assert seen[0] != jwt(user_claims)


def test_the_apps_route_also_uses_the_service_principal(client):
    seen: list[str | None] = []

    class Recorder:
        available = staticmethod(lambda: True)
        get = staticmethod(lambda: "sp-token")

    client.app.state.sp_token = Recorder()
    browser = client.app.state.apps
    original = browser._http.get

    async def record(path, token, params=None):
        seen.append(token)
        raise LookupError("not found")

    browser._http.get = record
    try:
        client.get("/api/apps", headers={"x-forwarded-access-token": "user-token"})
    finally:
        browser._http.get = original
    assert seen and seen[0] == "sp-token"


def test_the_fallback_is_the_configured_token_when_there_is_no_service_principal(client, monkeypatch):
    """Local development has no injected SP, so the developer's own token is the identity — the same
    one the agent's tool server uses there. The route must still work rather than crash."""
    class Absent:
        available = staticmethod(lambda: False)

    client.app.state.sp_token = Absent()
    seen: list[str | None] = []
    browser = client.app.state.lakebase
    original = browser._http.get

    async def record(path, token, params=None):
        seen.append(token)
        raise LookupError("not found")

    browser._http.get = record
    try:
        client.get("/api/lakebase/projects", headers={"x-forwarded-access-token": "user-token"})
    finally:
        browser._http.get = original
    assert seen and seen[0] == "user-token"


# -- the claim that was wrong ---------------------------------------------------------------------
def test_the_platform_documentation_still_says_postgres_cannot_run_obo():
    """This test exists to make the reasoning auditable.

    The whole design rests on one platform rule. It is quoted in `sp_token.py`, in the router and in
    the spec, so if it ever changes, the quotation is the thing to check — and a reader can find it
    without re-deriving it. It asserts the text we relied on, in the module that relies on it.
    """
    text = (APP / "api" / "adapters" / "databricks" / "sp_token.py").read_text()
    assert "always bound to the SP, not OBO" in text
    assert "cannot run OBO" in text
