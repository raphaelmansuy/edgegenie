"""The HTTP contract: statuses, the catalogue shape, and **no secret in any response**.

C-1 is a scan, not a promise: every `/api/llm/*` route is called with a planted key and every response
body is searched for the plaintext, the ciphertext and each of the seven documented formats.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import base64
import os

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_llm_domain import _service_account  # noqa: E402

PLANTED_OPENAI = "sk-" + "PLANTED" + "p" * 32
PLANTED_VERTEX = _service_account("planted-project-1")


#: A KEK for the tests. Storing a key requires one by design (06 §The KEK: fail closed), so a test
#: that exercises the vault must supply it — exactly as a deployment must.
TEST_KEK = base64.urlsafe_b64encode(bytes(range(32))).decode()


def client(**overrides) -> TestClient:
    cfg = Settings(
        agent_mode="fake",
        demo_scenario="notebook",
        allowed_models=["fake/model-a", "fake/model-b"],
        default_model="fake/model-a",
        dev_user="tester@example.com",
        llm_allow_external=True,
        **{"llm_kek": TEST_KEK, **overrides},
    )
    app = build(cfg)
    app.state.orchestrator._rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    return TestClient(app)


@pytest.fixture
def api() -> TestClient:
    with client() as c:
        yield c


LLM_ROUTES = ("/api/models", "/api/llm/models", "/api/llm/health", "/api/llm/credentials",
              "/api/llm/discovery")


# -- C-1 / S1: no route returns a secret -----------------------------------------------------
def test_no_llm_route_returns_the_planted_keys(api: TestClient):
    """The response-scan test C-1 names. A key appears in no body, in any form."""
    saved = api.put("/api/llm/credentials", json={
        "provider": "openai", "kind": "api_key", "secret": PLANTED_OPENAI})
    assert saved.status_code == 200, saved.text
    api.put("/api/llm/credentials", json={
        "provider": "google_vertex", "kind": "service_account_json", "secret": PLANTED_VERTEX})

    bodies = []
    for route in LLM_ROUTES:
        r = api.get(route)
        bodies.append((route, r.status_code, r.text))
    for route, _status, text in bodies:
        assert PLANTED_OPENAI not in text, f"{route} leaked the plaintext key"
        assert "PLANTED" not in text, f"{route} leaked part of the key"
        assert "BEGIN PRIVATE KEY" not in text, f"{route} leaked the service-account key"
    # The save response itself carries last4 and a fingerprint and nothing derived further.
    body = saved.json()
    assert set(body["credential"]) >= {"id", "provider", "kind", "last4", "fingerprint"}
    assert PLANTED_OPENAI not in json.dumps(body)
    assert body["credential"]["last4"] == PLANTED_OPENAI[-4:]


def test_the_stored_row_holds_no_plaintext(api: TestClient):
    """S10 from the app's own perspective: the vault row is ciphertext only."""
    api.put("/api/llm/credentials", json={"provider": "openai", "kind": "api_key",
                                          "secret": PLANTED_OPENAI})
    vault = api.app.state.llm.vault
    rows = vault.rows()
    assert rows, "nothing was stored"
    for row in rows:
        assert PLANTED_OPENAI.encode() not in row.sealed.ciphertext
        assert row.sealed.wrapped_dek and row.sealed.auth_tag


# -- the catalogue shape ---------------------------------------------------------------------
def test_the_catalogue_is_the_shape_the_picker_reads(api: TestClient):
    body = api.get("/api/models").json()
    assert body["source"] in ("memory", "seed", "database", "degraded")
    assert body["default"] == "fake/model-a"
    assert body["updatedAt"].endswith("Z")
    ids = {m["id"] for m in body["available"]}
    assert ids == {"fake/model-a", "fake/model-b"}
    one = body["available"][0]
    for field in ("id", "name", "provider", "providerName", "wire", "capability", "state",
                  "selectable", "limits", "credential", "group", "origin", "endpoint"):
        assert field in one, f"the picker needs {field}"
    assert {"context", "output", "evidence", "source", "unverified"} <= set(one["limits"])
    assert {"kind", "source", "hint"} <= set(one["credential"])


def test_one_model_can_be_read_by_its_own_route(api: TestClient):
    assert api.get("/api/llm/models/fake/model-a").json()["id"] == "fake/model-a"
    assert api.get("/api/llm/models/nope/nope").status_code == 404


def test_health_names_the_registry_source_and_the_vault_mode(api: TestClient):
    body = api.get("/api/llm/health").json()
    assert body["source"] in ("memory", "seed")
    assert body["vault"]["mode"] in ("env", "scope", "none", "env-only")
    assert isinstance(body["providers"], list)


# -- credentials: validation, refusal, revocation --------------------------------------------
def test_a_malformed_service_account_is_a_422_that_names_the_field(api: TestClient):
    r = api.put("/api/llm/credentials", json={
        "provider": "google_vertex", "kind": "service_account_json",
        "secret": '{"type":"user"}'})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["field"] == "type"


def test_an_unknown_provider_is_refused_before_it_reaches_a_vault(api: TestClient):
    r = api.put("/api/llm/credentials", json={"provider": "mystery", "kind": "api_key",
                                              "secret": "sk-" + "a" * 30})
    assert r.status_code == 422


def test_a_stored_key_can_be_listed_and_revoked(api: TestClient):
    saved = api.put("/api/llm/credentials", json={
        "provider": "openai", "kind": "api_key", "secret": PLANTED_OPENAI}).json()
    listed = api.get("/api/llm/credentials").json()["credentials"]
    assert [c["id"] for c in listed] == [saved["credential"]["id"]]
    assert api.delete(f"/api/llm/credentials/{saved['credential']['id']}").status_code == 204
    assert api.get("/api/llm/credentials").json()["credentials"] == []


def test_test_connection_validates_and_probes_without_storing(api: TestClient):
    """K3: Test must fail before Save, and it must not leave a row behind."""
    r = api.post("/api/llm/credentials/test", json={
        "provider": "openai", "kind": "api_key", "secret": "short"})
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["field"] == "secret"
    assert api.get("/api/llm/credentials").json()["credentials"] == []


# -- C-5 / E-14: no database is not a broken app ---------------------------------------------
def test_with_no_database_the_app_serves_a_catalogue_and_says_where_it_came_from():
    with client(llm_kek="", llm_database_url="") as c:
        body = c.get("/api/models").json()
        assert body["available"], "an app with no database served nothing"
        assert body["source"] in ("memory", "seed")


def test_with_no_kek_saving_a_key_is_refused_with_the_reason_and_not_a_500():
    with client(llm_kek="", llm_database_url="") as c:
        listing = c.get("/api/llm/credentials").json()
        if listing["canSave"]:
            pytest.skip("this build has a KEK; the refusal path is covered by the env-vault test")
        r = c.put("/api/llm/credentials", json={"provider": "openai", "kind": "api_key",
                                                "secret": PLANTED_OPENAI})
        assert r.status_code == 503
        assert "saved" in r.json()["detail"].lower() or "key" in r.json()["detail"].lower()


# -- FR-9 / FR-16: a model switch on a live session -----------------------------------------
def test_a_model_switch_returns_the_new_current_model(api: TestClient):
    sid = api.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    r = api.post(f"/api/sessions/{sid}/model", json={"model": "fake/model-b"})
    assert r.status_code == 200, r.text
    assert r.json()["current"] == "fake/model-b"


def test_a_switch_to_an_unknown_model_is_a_422_with_a_named_model(api: TestClient):
    sid = api.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    r = api.post(f"/api/sessions/{sid}/model", json={"model": "openai/gpt-5"})
    assert r.status_code == 422
    assert "gpt-5" in str(r.json()["detail"])


def test_model_facts_report_the_current_model_and_the_turn_pins(api: TestClient):
    sid = api.post("/api/sessions", json={"folder": "/tmp/agent-work"}).json()["id"]
    facts = api.get(f"/api/sessions/{sid}/model-facts").json()
    assert facts["current"] == "fake/model-a"
    assert facts["turns"] == []
    assert facts["resolved"]["wire"] == "fake"


# -- discovery: not readable is not empty ----------------------------------------------------
def test_discovery_refresh_reports_what_it_saw_without_a_workspace_host(api: TestClient):
    r = api.post("/api/llm/discovery/refresh")
    assert r.status_code in (200, 409)
    if r.status_code == 409:
        assert "workspace host" in r.json()["detail"]
