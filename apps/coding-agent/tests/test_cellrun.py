"""Cell execution: what a run means, and what the user is told.

The cases that matter are the ugly ones — a refusal, a cancellation, a query still running after the
wait, an engine error with its own words. A happy-path-only test would let all of those ship as
"something went wrong".
"""

from __future__ import annotations

import pytest

from api.domain.cellrun import (
    Clock, RunResult, RunState, is_runnable, refused, result_from_statement, without_skip,
)


def payload(state: str, *, columns=("a", "b"), rows=(("1", "2"),), total=None, error="", statement="select 1"):
    out = {"statement": statement, "status": {"state": state}}
    if columns:
        out["manifest"] = {"schema": {"columns": [{"name": c} for c in columns]},
                           "total_row_count": total if total is not None else len(rows)}
        out["result"] = {"data_array": [list(r) for r in rows]}
    if error:
        out["status"]["error"] = {"message": error}
    return out


# ---------------------------------------------------------------- what may run

def test_sql_is_runnable_and_python_is_not_but_says_why():
    ok, _ = is_runnable("sql", "select 1")
    assert ok
    ok, why = is_runnable("python", "print(1)")
    assert not ok
    assert "cluster" in why and "SQL" in why          # names what WOULD work


def test_sql_magic_runs_and_other_magics_do_not():
    assert is_runnable("python", "%sql select 1")[0]
    ok, why = is_runnable("python", "%scala sc.parallelize(1)")
    assert not ok and "%scala" in why


def test_skip_is_a_directive_and_the_statement_that_follows_can_still_run():
    assert without_skip("%skip\nselect 1") == (True, "select 1")
    assert is_runnable("sql", "%skip\nselect 1")[0]
    ok, why = is_runnable("sql", "%skip")
    assert not ok and "%skip" in why


def test_an_empty_cell_is_refused_rather_than_sent():
    ok, why = is_runnable("sql", "   \n ")
    assert not ok and "empty" in why


def test_a_refusal_is_a_state_with_a_reason_not_an_error():
    r = refused("no SQL warehouse is available to run this query")
    d = r.to_dict()
    assert d["state"] == "refused"
    assert "no SQL warehouse" in d["error"]
    assert "columns" not in d


# ---------------------------------------------------------------- decoding a response

def test_a_successful_select_carries_columns_rows_and_timing():
    r = result_from_statement(payload("SUCCEEDED", total=2), waited=1.234)
    assert r.state is RunState.SUCCEEDED
    assert r.columns == ["a", "b"] and r.rows == [["1", "2"]]
    assert r.total_rows == 2
    d = r.to_dict()
    assert d["seconds"] == 1.23
    assert d["statement"] == "select 1"


def test_nulls_become_empty_cells_rather_than_the_word_none():
    p = payload("SUCCEEDED")
    p["result"]["data_array"] = [[None, "x"]]
    r = result_from_statement(p, waited=0.1)
    assert r.rows == [["", "x"]]


def test_a_truncated_result_says_so():
    r = result_from_statement(payload("SUCCEEDED", rows=(("1", "2"),), total=500), waited=0.2)
    assert r.truncated and r.total_rows == 500


def test_a_query_still_running_is_reported_as_running_with_advice_not_as_a_failure():
    r = result_from_statement(payload("RUNNING"), waited=50.0)
    assert r.state is RunState.RUNNING
    assert "still running" in r.error and "job" in r.error      # names the next step
    assert r.state is not RunState.FAILED


def test_a_cancellation_is_its_own_state():
    r = result_from_statement(payload("CANCELED"), waited=2.0)
    assert r.state is RunState.CANCELLED
    assert "cancelled" in r.error


def test_an_engine_error_keeps_the_engines_own_words():
    r = result_from_statement(
        payload("FAILED", error="[TABLE_OR_VIEW_NOT_FOUND] The table `main.s.nope` cannot be found."),
        waited=0.3)
    assert r.state is RunState.FAILED
    assert "TABLE_OR_VIEW_NOT_FOUND" in r.error       # verbatim: the user can act on this
    assert "something went wrong" not in r.error.lower()


def test_an_empty_result_set_is_a_success_with_no_rows():
    r = result_from_statement(payload("SUCCEEDED", columns=("a",), rows=()), waited=0.1)
    assert r.state is RunState.SUCCEEDED
    assert r.rows == [] and r.columns == ["a"]


def test_a_missing_state_does_not_crash_and_still_says_something():
    """An unknown state is NOT a failure ([R-29], `[F-15]`).

    The warehouse never said it failed, so reporting `FAILED` is a claim this app cannot support — and
    it used to say exactly that, with `"the warehouse reported "` and nothing after it. `UNRESOLVED` is
    the honest outcome, and the sentence names the state so a reader can look it up.
    """
    p = {"statement": "select 1", "status": {}}
    r = result_from_statement(p, waited=0.1)
    assert r.state is RunState.UNRESOLVED
    assert r.error
    assert "no state" in r.error


def test_a_queued_statement_is_waiting_not_failed():
    """`QUEUED` is a legitimate Statements-API state meaning *not yet*.

    A large query on a shared endpoint spends real time queued. It fell through to the failure branch,
    so the user saw a red failure whose reason was "the warehouse reported QUEUED" — the name of a
    state that means the opposite ([F-15], `[R-29]`).
    """
    r = result_from_statement({"statement": "select 1", "status": {"state": "QUEUED"}}, waited=3.0)
    assert r.state is RunState.RUNNING
    assert "still running" in r.error


def test_an_unknown_future_state_names_itself_and_is_not_a_failure():
    r = result_from_statement({"statement": "select 1", "status": {"state": "SOMETHING_NEW"}},
                              waited=1.0)
    assert r.state is RunState.UNRESOLVED
    assert "SOMETHING_NEW" in r.error
    assert "may have run" in r.error


# ---------------------------------------------------------------- timing

def test_the_clock_is_injectable_so_a_duration_is_testable():
    ticks = iter([10.0, 12.5])
    clock = Clock(now=lambda: next(ticks))
    at = clock.start()
    assert clock.since(at) == 2.5


def test_a_run_serialises_without_optional_noise():
    r = RunResult(state=RunState.SUCCEEDED, seconds=0.5, columns=["a"], rows=[["1"]], total_rows=1)
    d = r.to_dict()
    assert d == {"state": "succeeded", "seconds": 0.5, "columns": ["a"], "rows": [["1"]],
                 "truncated": False, "totalRows": 1}
