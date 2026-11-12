"""Cell execution: what a run means, and what the user is told.

The cases that matter are the ugly ones — a refusal, a cancellation, a query still running after the
wait, an engine error with its own words. A happy-path-only test would let all of those ship as
"something went wrong".
"""

from __future__ import annotations

import pytest

from api.domain.cellrun import (
    Clock, MAX_ERROR_CHARS, RunResult, RunState, is_runnable, refused, result_from_statement,
    split_statements, sql_statement, without_skip,
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


def test_nulls_stay_null_and_an_empty_string_stays_empty():
    """NULL and '' are different values; Databricks draws the first as an italic `null`. Turning both
    into "" made them indistinguishable, and "None" would be a string that was never in the data."""
    p = payload("SUCCEEDED")
    p["result"]["data_array"] = [[None, "x"], ["", "y"]]
    r = result_from_statement(p, waited=0.1)
    assert r.rows == [[None, "x"], ["", "y"]]


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


# ---------------------------------------------------------------- what is sent to the warehouse

def test_a_sql_magic_line_is_not_sent_to_the_warehouse():
    """`%sql` marks the cell, it is not SQL: sent as-is the engine fails with a syntax error at `%sql`."""
    assert sql_statement("%sql\nselect 1") == "select 1"
    assert sql_statement("%sql select 1") == "select 1"
    assert sql_statement("%SQL\n  select 1  ") == "select 1"
    assert sql_statement("select 1") == "select 1"
    assert sql_statement("%skip\n%sql\nselect 1") == "select 1"


def test_a_cell_with_several_statements_is_split_at_top_level_semicolons():
    assert split_statements("select 1; select 2;") == ["select 1", "select 2"]
    assert split_statements("create table t(a int);\ninsert into t values (1);\nselect * from t") == [
        "create table t(a int)", "insert into t values (1)", "select * from t"]


def test_a_semicolon_in_a_string_a_name_or_a_comment_is_not_a_separator():
    assert split_statements("select 'a;b'; select 2") == ["select 'a;b'", "select 2"]
    assert split_statements('select "a;b" as x') == ['select "a;b" as x']
    assert split_statements("select `a;b` from t; select 2") == ["select `a;b` from t", "select 2"]
    assert split_statements("select 1 -- not; a split\n; select 2") == ["select 1 -- not; a split", "select 2"]
    assert split_statements("select /* a; b */ 1; select 2") == ["select /* a; b */ 1", "select 2"]
    assert split_statements(r"select 'it\'s; fine'; select 2") == [r"select 'it\'s; fine'", "select 2"]


def test_pieces_with_only_comments_or_blanks_are_dropped():
    assert split_statements("-- nothing\n;;  ;\n/* x */") == []
    assert split_statements("") == []


def test_a_sql_script_is_one_statement_because_its_body_has_its_own_semicolons():
    script = "BEGIN\n  DECLARE x INT; SET x = 1; SELECT x;\nEND"
    assert split_statements(script) == [script]


# ---------------------------------------------------------------- what is shown

def test_a_statement_with_no_result_set_says_ok():
    r = result_from_statement({"statement": "create table t(a int)", "status": {"state": "SUCCEEDED"}}, waited=0.4)
    assert r.state is RunState.SUCCEEDED and r.output == "OK"
    assert r.to_dict()["output"] == "OK"


def test_a_select_does_not_say_ok():
    assert result_from_statement(payload("SUCCEEDED"), waited=0.1).output == ""


def test_column_types_travel_with_the_result():
    p = payload("SUCCEEDED")
    p["manifest"]["schema"]["columns"] = [{"name": "a", "type_name": "INT"}, {"name": "b", "type_name": "STRING"}]
    r = result_from_statement(p, waited=0.1)
    assert r.types == ["int", "string"]
    assert r.to_dict()["types"] == ["int", "string"]


def test_no_types_reported_means_no_types_key():
    assert "types" not in result_from_statement(payload("SUCCEEDED"), waited=0.1).to_dict()


def test_the_engines_truncated_flag_is_honoured_even_without_a_total():
    p = payload("SUCCEEDED", total=1)
    p["manifest"]["truncated"] = True
    assert result_from_statement(p, waited=0.1).truncated


def test_a_long_engine_error_keeps_its_pointers():
    msg = "[PARSE_SYNTAX_ERROR] Syntax error at or near 'x'. SQLSTATE: 42601\n" + "line 3, pos 14 " * 100
    r = result_from_statement(payload("FAILED", error=msg), waited=0.1)
    assert len(r.error) > 400 and len(r.error) <= MAX_ERROR_CHARS
    assert "\n" in r.error and "line 3, pos 14" in r.error


def test_finished_at_and_who_ran_it_are_in_the_dict_only_when_known():
    r = RunResult(state=RunState.SUCCEEDED, seconds=1, finished_at="2026-11-12T00:00:00+00:00", ran_by="a@x")
    d = r.to_dict()
    assert d["finishedAt"] == "2026-11-12T00:00:00+00:00" and d["ranBy"] == "a@x"
    assert "finishedAt" not in RunResult(state=RunState.SUCCEEDED).to_dict()


# -- nested values: the type text travels with the result, only when it is needed ----------------------

def _typed(cols):
    return {"status": {"state": "SUCCEEDED"}, "statement": "select 1",
            "manifest": {"schema": {"columns": [{"name": n, "type_name": t, "type_text": tt} for n, t, tt in cols]}},
            "result": {"data_array": [["[\"1\",\"2\"]", "x"]], "row_count": 1}}


def test_a_nested_column_sends_its_full_type_text():
    r = result_from_statement(_typed([("a", "ARRAY", "ARRAY<INT>"), ("s", "STRING", "STRING")]), waited=0.1)
    assert r.types == ["array", "string"]
    assert r.to_dict()["typeTexts"] == ["ARRAY<INT>", "STRING"]


def test_a_result_with_no_nested_column_does_not_carry_type_texts():
    r = result_from_statement(_typed([("a", "INT", "INT"), ("s", "STRING", "STRING")]), waited=0.1)
    assert "typeTexts" not in r.to_dict()


# -- :name markers -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sql,names", [
    ("select :a, :b, :a", ["a", "b"]),
    ("select a::int, raw:field from t", []),                      # a cast and a JSON path are not parameters
    ("select ':no', \":no\", `:no`, 'it''s :no', :yes", ["yes"]),   # strings and quoted names
    ("-- :no\nselect :yes /* :no */, :yes2", ["yes", "yes2"]),       # comments
    ("select 'a\\' :no', :ok", ["ok"]),                              # an escaped quote does not end the string
    ("where d = :start_date and e = :_x1", ["start_date", "_x1"]),
    ("select 1:2, :1", []),                                        # not names
    ("select :", []),
    ("select 'open :no", []),                                      # an unterminated string swallows the rest
])
def test_sql_parameters(sql, names):
    from api.domain.cellrun import sql_params
    assert sql_params(sql) == names
