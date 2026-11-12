"""SQL cell runs: started, polled to the end, cancelled, several statements in one cell.

The warehouse is a fake with the same four verbs as `CatalogBrowser`. What is tested is what a user sees:
a long query is not cut at 50 seconds, a failure in statement 2 names statement 2, Stop cancels the
statement the warehouse is running, and another user's handle is "not found".
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build
from api.services.sql_run_service import SqlRuns

OWNER = "a@example.com"


def done(columns=("n",), rows=(("1",),), types=("INT",), **extra):
    return {"statement_id": "st-1", "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": c, "type_name": t} for c, t in zip(columns, types)]},
                         "total_row_count": len(rows)},
            "result": {"data_array": [list(r) for r in rows]}, **extra}


def live(state="RUNNING"):
    return {"statement_id": "st-1", "status": {"state": state}}


class FakeWarehouse:
    """`script` is a list per statement of the responses: the first answers the submit, the rest the polls."""

    def __init__(self, *script, warehouse="default"):
        self.script = [list(s) for s in script]
        self.warehouse = {"id": "w1", "name": "Shared Endpoint"} if warehouse == "default" else warehouse
        self.submitted: list[str] = []
        self.parameters: list = []
        self.cancelled: list[str] = []
        self._n = -1

    async def pick_warehouse(self, token):
        if self.warehouse is None:
            raise LookupError("no SQL warehouse is available to run this query")
        return self.warehouse

    async def submit_statement(self, warehouse_id, statement, token, *, limit, parameters=None):
        assert warehouse_id == "w1" and limit == 1000
        self.submitted.append(statement)
        self.parameters.append(parameters)
        self._n += 1
        return dict(self.script[self._n].pop(0))

    async def statement(self, statement_id, token):
        queue = self.script[self._n]
        return dict(queue.pop(0) if len(queue) > 1 else queue[0])

    async def cancel_statement(self, statement_id, token):
        self.cancelled.append(statement_id)


class Ticker:
    """A clock the test moves, so a ten-minute limit does not take ten minutes."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def runs_for(api, ticker=None, **kw):
    return SqlRuns(api, clock=ticker or Ticker(), wall=lambda: "2026-11-12T00:00:00+00:00",
                   poll_seconds=0, **kw)


async def finish(runs, handle, owner=OWNER):
    for _ in range(500):
        got = await runs.poll(owner, handle)
        if got["state"] == "done":
            return got
        await asyncio.sleep(0)
    raise AssertionError("the run never finished")


def test_a_query_is_started_polled_and_returns_rows_types_when_and_who():
    api = FakeWarehouse([live(), live(), done(rows=(("1",), ("2",)))])

    async def go():
        runs = runs_for(api)
        h = (await runs.start(OWNER, "tok", "sql", "select n from t"))["handle"]
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert got["state"] == "succeeded" and got["rows"] == [["1"], ["2"]]
    assert got["types"] == ["int"]
    assert got["warehouse"] == "Shared Endpoint" and got["ranBy"] == OWNER
    assert got["finishedAt"] == "2026-11-12T00:00:00+00:00"
    assert api.submitted == ["select n from t"]


def test_a_percent_sql_marker_does_not_reach_the_warehouse():
    api = FakeWarehouse([done()])

    async def go():
        runs = runs_for(api)
        await finish(runs, (await runs.start(OWNER, "t", "python", "%sql\nselect 1"))["handle"])

    asyncio.run(go())
    assert api.submitted == ["select 1"]


def test_several_statements_run_in_order_and_the_last_result_is_the_cells():
    api = FakeWarehouse([done(columns=(), rows=(), types=())], [done(rows=(("7",),))])

    async def go():
        runs = runs_for(api)
        h = (await runs.start(OWNER, "t", "sql", "create table t(n int); select 7"))["handle"]
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert api.submitted == ["create table t(n int)", "select 7"]
    assert got["rows"] == [["7"]]


def test_a_failure_stops_the_rest_and_names_the_statement():
    err = {"statement_id": "st-2",
           "status": {"state": "FAILED", "error": {"message": "[TABLE_OR_VIEW_NOT_FOUND] nope"}}}
    api = FakeWarehouse([done()], [err], [done()])

    async def go():
        runs = runs_for(api)
        h = (await runs.start(OWNER, "t", "sql", "select 1; select * from nope; select 3"))["handle"]
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert got["state"] == "failed"
    assert got["error"].startswith("statement 2 of 3:") and "TABLE_OR_VIEW_NOT_FOUND" in got["error"]
    assert len(api.submitted) == 2                      # the third never ran


def test_a_query_is_not_cut_at_fifty_seconds():
    ticker = Ticker()
    api = FakeWarehouse([live(), live(), live(), live(), done()])
    orig = api.statement

    async def slow(statement_id, token):
        ticker.t += 30                                  # each poll is thirty seconds later
        return await orig(statement_id, token)

    api.statement = slow

    async def go():
        runs = runs_for(api, ticker)
        h = (await runs.start(OWNER, "t", "sql", "select 1"))["handle"]
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert got["state"] == "succeeded" and not api.cancelled
    assert got["seconds"] >= 120


def test_past_the_limit_the_statement_is_cancelled_and_the_result_says_to_use_a_job():
    ticker = Ticker()
    api = FakeWarehouse([live(), live()])
    orig = api.statement

    async def slow(statement_id, token):
        ticker.t += 400
        return await orig(statement_id, token)

    api.statement = slow

    async def go():
        runs = runs_for(api, ticker, limit_seconds=600)
        h = (await runs.start(OWNER, "t", "sql", "select 1"))["handle"]
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert got["state"] == "running" and "job" in got["error"] and "10-minute" in got["error"]
    assert api.cancelled == ["st-1"]


def test_stop_cancels_the_statement_the_warehouse_is_running():
    api = FakeWarehouse([live(), live()])

    async def go():
        runs = runs_for(api)
        h = (await runs.start(OWNER, "t", "sql", "select 1"))["handle"]
        for _ in range(5):                              # let the driver submit and begin polling
            await asyncio.sleep(0)
        await runs.cancel(OWNER, h, "t")
        return await finish(runs, h)

    got = asyncio.run(go())["result"]
    assert got["state"] == "cancelled" and api.cancelled == ["st-1"]


def test_a_running_poll_says_which_statement_and_where():
    api = FakeWarehouse([live()], [done()])

    async def go():
        runs = runs_for(api)
        h = (await runs.start(OWNER, "t", "sql", "select 1; select 2"))["handle"]
        return await runs.poll(OWNER, h)

    got = asyncio.run(go())
    assert got["state"] == "running" and "Shared Endpoint" in got["stage"]


def test_refusals_and_a_missing_warehouse_are_answered_at_once():
    async def go():
        runs = runs_for(FakeWarehouse([done()]))
        scala = await runs.start(OWNER, "t", "scala", "println(1)")
        empty = await runs.start(OWNER, "t", "sql", "-- only a comment")
        none = await runs_for(FakeWarehouse([done()], warehouse=None)).start(OWNER, "t", "sql", "select 1")
        return scala, empty, none

    scala, empty, none = asyncio.run(go())
    assert scala["result"]["state"] == "refused"
    assert empty["result"]["state"] == "refused" and "no SQL statement" in empty["result"]["error"]
    assert none["result"]["state"] == "refused" and "no SQL warehouse" in none["result"]["error"]


def test_someone_elses_handle_is_not_found():
    async def go():
        runs = runs_for(FakeWarehouse([live()]))
        h = (await runs.start(OWNER, "t", "sql", "select 1"))["handle"]
        with pytest.raises(LookupError):
            await runs.poll("intruder@example.com", h)
        with pytest.raises(LookupError):
            await runs.cancel("intruder@example.com", h)

    asyncio.run(go())


def test_the_routes_start_poll_and_refuse():
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user=OWNER, llm_demo_seed=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a")
    with TestClient(build(cfg)) as c:
        c.app.state.sqlruns = SqlRuns(FakeWarehouse([done()]), poll_seconds=0)
        refused = c.post("/api/notebook/sql-runs", json={"language": "scala", "source": "x"}).json()
        assert refused["result"]["state"] == "refused"
        started = c.post("/api/notebook/sql-runs", json={"language": "sql", "source": "select 1"}).json()
        got: dict = {}
        for _ in range(100):
            got = c.get(f"/api/notebook/sql-runs/{started['handle']}").json()
            if got["state"] == "done":
                break
            time.sleep(0.02)
        assert got["state"] == "done" and got["result"]["rows"] == [["1"]]
        assert c.get("/api/notebook/sql-runs/unknown").status_code == 404
        assert c.delete("/api/notebook/sql-runs/unknown").status_code == 404


# -- named parameters: widget values bound to :name ------------------------------------------------------

def test_only_the_parameters_a_statement_uses_are_sent_to_the_warehouse():
    api = FakeWarehouse([done()], [done()])

    async def go():
        runs = runs_for(api)
        started = await runs.start(OWNER, None, "sql", "select :city; select :year, :city",
                                   {"city": "Oslo", "year": "2026", "unused": "x"})
        await finish(runs, started["handle"])

    asyncio.run(go())
    assert api.parameters == [[{"name": "city", "value": "Oslo"}],
                              [{"name": "year", "value": "2026"}, {"name": "city", "value": "Oslo"}]]


def test_a_statement_with_no_parameters_sends_none_even_when_values_exist():
    api = FakeWarehouse([done()])

    async def go():
        runs = runs_for(api)
        started = await runs.start(OWNER, None, "sql", "select 1", {"city": "Oslo"})
        await finish(runs, started["handle"])

    asyncio.run(go())
    assert api.parameters == [None]


def test_a_marker_with_no_value_is_left_for_the_warehouse_to_report():
    api = FakeWarehouse([done()])

    async def go():
        runs = runs_for(api)
        started = await runs.start(OWNER, None, "sql", "select :missing", {"other": "x"})
        await finish(runs, started["handle"])

    asyncio.run(go())
    assert api.parameters == [None]
    assert api.submitted == ["select :missing"]


def test_the_route_refuses_a_parameter_name_that_cannot_be_a_marker_and_a_huge_value():
    cfg = Settings(agent_mode="fake", demo_scenario="notebook", dev_user=OWNER, llm_demo_seed=True,
                   allowed_models=["fake/model-a"], default_model="fake/model-a")
    with TestClient(build(cfg)) as c:
        bad = c.post("/api/notebook/sql-runs", json={"source": "select 1", "params": {"a b": "x"}})
        assert bad.status_code == 422 and "not a SQL parameter name" in bad.text
        big = c.post("/api/notebook/sql-runs", json={"source": "select 1", "params": {"a": "x" * 2001}})
        assert big.status_code == 422 and "longer than 2,000" in big.text
