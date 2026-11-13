"""Lost SQL acknowledgements are lookup-only, exact-input, same-user recovery."""

import time
from uuid import uuid4

import pytest

from api.adapters.databricks.queries import DatabricksQueries
from api.adapters.durable.query_sqlite import SqliteQueryStore
from api.domain.sqlquery import SqlActor
from api.services.sql_service import SqlService


class HistoryHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    async def get(self, path, token, params):
        assert path == "/api/2.0/sql/history/queries"
        assert token == "user-token"
        self.calls.append(params)
        return self.pages[len(self.calls) - 1]


def fixture():
    actor = SqlActor("workspace", "numeric-owner-id", "user-token", "alice@example.test")
    now = time.time()
    intent = {
        "operationKey": "op_abc",
        "text": "/* opengenie-operation:op_abc */\nSELECT 1",
        "warehouseId": "warehouse",
        "createdAt": now,
    }
    row = {
        "query_id": str(uuid4()),
        "query_text": intent["text"],
        "warehouse_id": "warehouse",
        "user_name": actor.run_as,
        "executed_as_user_name": actor.run_as,
        "query_start_time_ms": int(now * 1000),
    }
    return actor, intent, row


async def test_recovery_requires_complete_paged_history_and_preserves_cursor():
    actor, intent, row = fixture()
    http = HistoryHttp([{"res": [], "next_page_token": "next+/="}, {"res": [row]}])
    assert await DatabricksQueries(http).lookup_statement(actor, intent) == row["query_id"]
    assert http.calls[1]["page_token"] == "next+/="
    assert http.calls[0]["filter_by.warehouse_ids"] == "warehouse"


@pytest.mark.parametrize(
    "override",
    [
        {"user_name": "bob"},
        {"executed_as_user_name": "bob"},
        {"warehouse_id": "other"},
        {"query_text": "/* opengenie-operation:op_abc */\nSELECT 2"},
        {"query_start_time_ms": 1},
    ],
)
async def test_mismatched_history_never_recovers(override):
    actor, intent, row = fixture()
    http = HistoryHttp([{"res": [{**row, **override}]}])
    assert await DatabricksQueries(http).lookup_statement(actor, intent) is None


@pytest.mark.parametrize("pages", ["ambiguous", "capped", "broken_cursor"])
async def test_uncertain_history_remains_unknown(pages):
    actor, intent, row = fixture()
    variants = {
        "ambiguous": [{"res": [row, {**row, "query_id": str(uuid4())}]}],
        "capped": [{"res": [row], "next_page_token": str(i)} for i in range(10)],
        "broken_cursor": [{"res": [row], "has_next_page": True}],
    }
    http = HistoryHttp(variants[pages])
    assert await DatabricksQueries(http).lookup_statement(actor, intent) is None
    assert len(http.calls) <= 10


async def test_permission_denial_is_reported_without_fallback():
    class Denied:
        async def get(self, *args):
            raise PermissionError("history denied")

    actor, intent, _ = fixture()
    with pytest.raises(PermissionError, match="history denied"):
        await DatabricksQueries(Denied()).lookup_statement(actor, intent)


async def test_lost_submission_recovers_after_store_reopen_without_second_post(tmp_path):
    actor, intent, history = fixture()

    class Provider:
        demo = True
        dialect = None
        calls = 0
        lookup_calls = 0

        async def warehouses(self, actor):
            return [{"id": "warehouse"}]

        async def submit(self, actor, payload):
            self.calls += 1
            assert payload["statement"] == intent["text"]
            raise TimeoutError("accepted, response lost")

        async def lookup_statement(self, actor, row):
            self.lookup_calls += 1
            assert row["operationKey"] == intent["operationKey"]
            return history["query_id"]

        async def status(self, actor, statement):
            assert statement == history["query_id"]
            return {"status": {"state": "SUCCEEDED"}}

    provider = Provider()
    path = str(tmp_path / "sql.db")
    store = SqliteQueryStore(path)
    service = SqlService(provider, store)
    draft = await service.draft(actor, {"text": intent["text"]})
    body = {"draftId": draft["id"], "version": draft["version"], "warehouseId": "warehouse"}
    attempt = await service.run(actor, body, "op_abc", mutation_scope="catalog.schema")
    assert attempt["state"] == "submission_unknown" and provider.calls == 1
    store.close()
    store = SqliteQueryStore(path)
    service = SqlService(provider, store)
    assert await service.lookup_operation(actor, "op_abc") == attempt["id"]
    assert await service.lookup_operation(SqlActor("workspace", "bob"), "op_abc") is None
    recovered = await service.observe(actor, attempt["id"])
    assert recovered["state"] == "succeeded" and recovered["statementId"] == history["query_id"]
    again = await service.run(actor, body, "op_abc", mutation_scope="catalog.schema")
    assert again["id"] == attempt["id"] and provider.calls == 1 and provider.lookup_calls == 1
    store.close()
