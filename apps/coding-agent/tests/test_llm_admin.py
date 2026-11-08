"""The configuration routes: who may write, what is validated, and that a write is kept.

Demo mode runs the same routes over a memory store, which is why these tests need no database. The
Postgres statements behind the same operations are exercised in `test_llm_lakebase.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.domain.llm import Capability, InvalidModel, ProviderKind, custom_model
from api.main import build

ADMIN = "tester@example.com"


def client(admins: str = ADMIN) -> TestClient:
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user=ADMIN,
                   allowed_models=["fake/model-a", "fake/model-b"], default_model="fake/model-a",
                   llm_allow_external=True, llm_demo_seed=True, llm_admins=admins)
    return TestClient(build(cfg))


@pytest.fixture
def api():
    with client() as c:
        yield c


NEW = {"provider": "google_vertex", "model": "google/gemini-9-test", "name": "gemini-9-test",
       "context": 200_000, "output": 16_000}


def test_the_screen_lists_providers_models_and_who_may_edit(api):
    cfg = api.get("/api/llm/config").json()
    assert cfg["canConfigure"] is True and cfg["canSave"] is True
    kinds = {p["kind"] for p in cfg["providers"]}
    assert {"openai", "anthropic", "google_vertex"} <= kinds
    assert all("key" not in p or isinstance(p["hasKey"], bool) for p in cfg["providers"])
    assert any(m["provider"] == "google_vertex" for m in cfg["models"])


def test_a_user_who_is_not_listed_can_read_but_not_write():
    with client(admins="someone-else@example.com") as c:
        assert c.get("/api/llm/config").json()["canConfigure"] is False
        r = c.post("/api/llm/config/models", json=NEW)
        assert r.status_code == 403 and "administrator" in r.text


def test_behind_the_proxy_an_administrator_is_recognised_by_e_mail():
    """The proxy's user id is `<number>@<app>`; the list holds e-mails, so the e-mail header must count."""
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", llm_demo_seed=True, llm_allow_external=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a",
                   llm_admins="boss@example.com", require_forwarded_user=True)
    with TestClient(build(cfg)) as c:
        theirs = {"x-forwarded-user": "123@456", "x-forwarded-email": "boss@example.com"}
        other = {"x-forwarded-user": "789@456", "x-forwarded-email": "intern@example.com"}
        assert c.get("/api/llm/config", headers=theirs).json()["canConfigure"] is True
        assert c.get("/api/llm/config", headers=other).json()["canConfigure"] is False
        assert c.post("/api/llm/config/models", json=NEW, headers=theirs).status_code == 201
        assert c.post("/api/llm/config/models", json=NEW, headers=other).status_code == 403
        row = next(m for m in c.get("/api/llm/config", headers=theirs).json()["models"]
                   if m["id"].endswith("gemini-9-test"))
        assert "stated by boss@example.com" in row["limits"]["source"]


def test_behind_the_proxy_the_email_header_identifies_the_administrator():
    """`user_id` is `<numeric>@<app>` there; the owner is listed by e-mail, which arrives in a header."""
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user="42@app",
                   llm_allow_external=True, llm_demo_seed=True, llm_admins="owner@example.com")
    with TestClient(build(cfg)) as c:
        assert c.get("/api/llm/config").json()["canConfigure"] is False
        mine = c.get("/api/llm/config", headers={"x-forwarded-email": "Owner@Example.com"})
        assert mine.json()["canConfigure"] is True
        other = c.get("/api/llm/config", headers={"x-forwarded-email": "intruder@example.com"})
        assert other.json()["canConfigure"] is False


def test_with_no_administrators_nobody_may_write():
    with client(admins="") as c:
        assert c.post("/api/llm/config/models", json=NEW).status_code == 403


def test_an_added_model_appears_in_the_catalogue_and_can_be_made_the_default(api):
    r = api.post("/api/llm/config/models", json={**NEW, "makeDefault": True})
    assert r.status_code == 201, r.text
    cfg = api.get("/api/llm/config").json()
    row = next(m for m in cfg["models"] if m["id"] == "google_vertex/google/gemini-9-test")
    assert row["limits"]["context"] == 200_000 and row["limits"]["evidence"] == "documented"
    assert "stated by tester@example.com" in row["limits"]["source"]
    assert cfg["default"] == "google_vertex/google/gemini-9-test"
    ids = [m["id"] for m in api.get("/api/llm/models").json()["available"]]
    assert "google_vertex/google/gemini-9-test" in ids


@pytest.mark.parametrize("patch,field", [
    ({"model": "bad name with spaces"}, "model"),
    ({"model": "../etc/passwd"}, "model"),
    ({"output": 300_000}, "output"),
    ({"capability": "chat_only"}, "capability"),
    ({"provider": "databricks"}, "provider"),
])
def test_invalid_models_are_refused_with_the_field_named(api, patch, field):
    r = api.post("/api/llm/config/models", json={**NEW, **patch})
    assert r.status_code == 422
    assert r.json()["detail"]["field"] == field


def test_a_model_can_be_switched_off_and_removed(api):
    api.post("/api/llm/config/models", json=NEW)
    mid = "google_vertex/google/gemini-9-test"
    assert api.patch(f"/api/llm/config/models/{mid}", json={"enabled": False}).status_code == 200
    row = next(m for m in api.get("/api/llm/config").json()["models"] if m["id"] == mid)
    assert row["enabled"] is False
    assert api.delete(f"/api/llm/config/models/{mid}").status_code == 204
    assert all(m["id"] != mid for m in api.get("/api/llm/config").json()["models"])


def test_the_default_model_cannot_be_removed_or_switched_off(api):
    api.post("/api/llm/config/models", json={**NEW, "makeDefault": True})
    mid = "google_vertex/google/gemini-9-test"
    assert api.patch(f"/api/llm/config/models/{mid}", json={"enabled": False}).status_code == 409
    assert api.delete(f"/api/llm/config/models/{mid}").status_code == 409


def test_a_databricks_model_cannot_be_edited_here(api):
    r = api.patch("/api/llm/config/models/databricks/databricks-llama-4-maverick", json={"enabled": False})
    assert r.status_code in (404, 409)


def test_the_default_must_be_a_model_that_exists(api):
    assert api.put("/api/llm/config/default", json={"model": "openai/not-a-model"}).status_code == 404


def test_a_provider_address_must_be_https(api):
    r = api.patch("/api/llm/config/providers/openai", json={"baseUrl": "http://insecure.example"})
    assert r.status_code == 422
    ok = api.patch("/api/llm/config/providers/openai", json={"baseUrl": "https://proxy.example/v1"})
    assert ok.status_code == 200
    row = next(p for p in api.get("/api/llm/config").json()["providers"] if p["id"] == "openai")
    assert row["baseUrl"] == "https://proxy.example/v1"


def test_without_a_database_the_routes_refuse_instead_of_pretending_to_save():
    cfg = Settings(agent_mode="stdio", dev_user=ADMIN, llm_admins=ADMIN)
    with TestClient(build(cfg)) as c:
        body = c.get("/api/llm/config").json()
        assert body["canSave"] is False and "database" in body["reason"]
        r = c.post("/api/llm/config/models", json=NEW)
        assert r.status_code == 503 and "database" in r.text


# -- the pure rules -----------------------------------------------------------------------
def test_custom_model_builds_a_spec_with_the_administrators_name_as_evidence():
    spec = custom_model(ProviderKind.OPENAI, "gpt-4.1", context=1_000_000, output=32_000, added_by="a@b.c")
    assert spec.id.value == "openai/gpt-4.1" and spec.endpoint == "gpt-4.1"
    assert spec.limits.source == "stated by a@b.c"
    assert spec.credential_kind.value == "api_key" and spec.wire.value == "openai"


def test_custom_model_refuses_a_databricks_endpoint():
    with pytest.raises(InvalidModel) as err:
        custom_model(ProviderKind.DATABRICKS, "x", context=10, output=5)
    assert err.value.field == "provider"


def test_custom_model_refuses_chat_only():
    with pytest.raises(InvalidModel):
        custom_model(ProviderKind.OPENAI, "gpt", context=10, output=5, capability=Capability.CHAT_ONLY)
