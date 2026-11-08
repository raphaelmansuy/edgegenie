"""Lakebase connection rules (offline) and the Postgres store's administration (opt-in, live).

The live class runs only when `LAKEBASE_TEST_ENDPOINT` names a Lakebase endpoint the caller can reach
(`projects/<p>/branches/<b>/endpoints/<e>`); it uses its own schema name so it never touches the app's.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from api.adapters.llm.store import lakebase
from api.services.model_registry import has_database
from api.config import Settings


class FakePostgres:
    def __init__(self) -> None:
        self.calls = 0

    def generate_database_credential(self, endpoint: str):
        self.calls += 1
        return SimpleNamespace(token=f"tok-{self.calls}")


def _source(clock):
    pg = FakePostgres()
    return lakebase.TokenSource("projects/p/branches/b/endpoints/e",
                                client=SimpleNamespace(postgres=pg), clock=clock), pg


def test_the_token_is_cached_until_it_is_close_to_expiry():
    now = [0.0]
    source, pg = _source(lambda: now[0])
    assert source.get() == "tok-1"
    now[0] = lakebase.TOKEN_REFRESH_SECONDS - 1
    assert source.get() == "tok-1" and pg.calls == 1
    now[0] = lakebase.TOKEN_REFRESH_SECONDS + 1
    assert source.get() == "tok-2" and pg.calls == 2


def test_connections_are_recycled_before_their_token_expires():
    assert lakebase.CONNECTION_MAX_LIFETIME < lakebase.TOKEN_REFRESH_SECONDS


def test_the_connection_string_carries_no_password():
    target = lakebase.LakebaseTarget("h.example", "db", "role", "ep")
    assert "password" not in target.conninfo and "sslmode=require" in target.conninfo


def test_the_target_defaults_to_the_apps_service_principal(monkeypatch):
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-123")
    endpoint = SimpleNamespace(status=SimpleNamespace(hosts=SimpleNamespace(host="h.example")))
    client = SimpleNamespace(postgres=SimpleNamespace(get_endpoint=lambda name: endpoint))
    target = lakebase.resolve_target("projects/p/branches/b/endpoints/e", "db", client=client)
    assert (target.host, target.user) == ("h.example", "sp-123")


def test_an_endpoint_without_a_host_is_an_error_not_an_empty_dsn():
    client = SimpleNamespace(postgres=SimpleNamespace(
        get_endpoint=lambda name: SimpleNamespace(status=SimpleNamespace(hosts=None))))
    with pytest.raises(RuntimeError, match="no host"):
        lakebase.resolve_target("projects/p/branches/b/endpoints/e", "db", client=client)


def test_either_a_dsn_or_an_endpoint_counts_as_a_configured_database():
    assert not has_database(Settings())
    assert has_database(Settings(llm_pg_endpoint="projects/p/branches/b/endpoints/e"))
    assert has_database(Settings(llm_database_url="postgresql://x"))


LIVE = os.environ.get("LAKEBASE_TEST_ENDPOINT", "")


@pytest.mark.skipif(not LIVE, reason="set LAKEBASE_TEST_ENDPOINT to run against a real Lakebase")
async def test_the_postgres_store_keeps_administrators_choices():
    from api.domain.llm import ProviderKind, custom_model
    from api.services.model_registry import connect_database

    store = await connect_database(Settings(llm_pg_endpoint=LIVE,
                                            llm_pg_user=os.environ.get("LAKEBASE_TEST_USER", "")))
    try:
        spec = custom_model(ProviderKind.OPENAI, "gpt-live-test", context=128_000, output=8_000, added_by="test")
        await store.upsert_model(spec)
        assert any(m.id.value == spec.id.value for m in await store.models(""))
        await store.set_model_enabled(spec.id.value, False)
        assert all(m.id.value != spec.id.value for m in await store.models(""))
        assert any(m.id.value == spec.id.value for m in await store.all_models())
        await store.set_setting("probe", "x", "test")
        assert await store.get_setting("probe") == "x"
        assert await store.delete_model(spec.id.value)
    finally:
        await store.close()
