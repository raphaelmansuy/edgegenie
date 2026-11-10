"""The state vocabulary and the graph, held to one table across two runtimes.

`web/src/domain/jobs-table.json` holds the cases; `api/domain/jobs.py` and `web/src/domain/jobs.ts` must
both answer them identically. This file asserts the Python half; `domain/jobs.test.ts` asserts the
TypeScript half against the same rows. A word changed on one side alone fails one of them and the message
names the row.

The rows that matter are `IDLE` + `FAILED` (a pipeline whose own state hides its failure) and
`TERMINATED` + `FAILED` (a run whose lifecycle state hides its outcome). Both are the defect 013 recorded
as [RB-12]: the convenient field is not the honest one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.domain import jobs

TABLE = Path(__file__).resolve().parents[1] / "web" / "src" / "domain" / "jobs-table.json"
CASES = json.loads(TABLE.read_text())


# ---------------------------------------------------------------------------------------------
# the words
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("row", CASES["runs"], ids=lambda r: f"{r['lifeCycle']}+{r['result']}")
def test_every_run_row_answers_as_the_fixture_says(row):
    assert jobs.run_word(row["lifeCycle"], row["result"]) == row["word"], row


@pytest.mark.parametrize("row", CASES["runs"], ids=lambda r: f"{r['lifeCycle']}+{r['result']}")
def test_every_run_row_has_the_fixture_tone(row):
    assert jobs.tone(jobs.run_word(row["lifeCycle"], row["result"])) == row["tone"], row


@pytest.mark.parametrize("row", CASES["runs"], ids=lambda r: f"{r['lifeCycle']}+{r['result']}")
def test_every_run_row_agrees_about_active_and_terminal(row):
    assert jobs.is_active(row["lifeCycle"]) is row["active"], row
    assert jobs.is_terminal(row["lifeCycle"]) is row["terminal"], row


@pytest.mark.parametrize("row", CASES["runs"], ids=lambda r: f"{r['lifeCycle']}+{r['result']}")
def test_every_run_row_agrees_about_which_controls_exist(row):
    """The matrix `RUN_ACTIONS` is generated from: Cancel while active, Repair after a failure."""
    assert jobs.can_cancel(row["lifeCycle"]) is row["cancel"], row
    assert jobs.can_repair(row["result"], row["lifeCycle"]) is row["repair"], row


@pytest.mark.parametrize("row", CASES["updates"], ids=lambda r: str(r["state"]))
def test_every_update_row_answers_as_the_fixture_says(row):
    assert jobs.update_word(row["state"]) == row["word"], row
    assert jobs.update_is_active(row["state"]) is row["active"], row


@pytest.mark.parametrize("row", CASES["pipelines"], ids=lambda r: f"{r['state']}+{r['lastUpdate']}")
def test_every_pipeline_row_answers_as_the_fixture_says(row):
    assert jobs.pipeline_word(row["state"], row["lastUpdate"]) == row["word"], row


def test_a_pipeline_whose_update_failed_is_not_idle():
    """The single most important row. `IDLE` is the convenient field; the update is the honest one."""
    assert jobs.pipeline_word("IDLE", "FAILED") == "failed"


def test_a_terminated_run_is_not_a_success():
    assert jobs.run_word("TERMINATED", "FAILED") == "failed"
    assert jobs.run_word("TERMINATED", "SUCCESS") == "succeeded"
    assert jobs.run_word("TERMINATED", None) == "finished", (
        "with no result, `TERMINATED` is a lifecycle fact, not a verdict")


def test_a_running_run_has_no_result_state_and_still_reads_running():
    """[E-10] `result_state` is documented as available only in a terminal state, so a page that reads it
    alone shows nothing for the whole duration of a run — which is the whole time a user is watching."""
    assert jobs.run_word("RUNNING", None) == "running"


def test_an_unknown_word_is_never_a_synonym():
    """A plausible paraphrase of a state nobody has seen is worse than the platform's own word."""
    assert jobs.run_word("TELEPORTING", None) == "teleporting"
    assert jobs.update_word("MEDITATING") == "meditating"
    assert jobs.pipeline_word("FLYING", None) == "flying"


# ---------------------------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------------------------
def test_a_job_id_is_one_number_however_it_is_spelled():
    """[JOB-1] A tab opened from a URL and one opened from a tool result must be the same tab."""
    assert jobs.job_id(812345678901) == 812345678901
    assert jobs.job_id("812345678901") == 812345678901
    assert jobs.job_id(" 812345678901 ") == 812345678901


@pytest.mark.parametrize("bad", [0, -1, "abc", "", "812345678901abc", None, True, 1.5])
def test_a_bad_job_id_is_refused_rather_than_coerced(bad):
    with pytest.raises(jobs.JobError):
        jobs.job_id(bad)


def test_a_job_name_is_refused_as_an_id_with_the_alternative():
    with pytest.raises(jobs.JobError) as caught:
        jobs.job_id("daily_revenue")
    assert "Data tab" in str(caught.value)


def test_a_pipeline_name_is_refused_as_an_id_with_the_alternative():
    """[E-17] The class 013's [RB-12] recorded: a name answered with a 404 reads as a permission problem."""
    with pytest.raises(jobs.JobError) as caught:
        jobs.pipeline_id("sales_medallion")
    assert "UUID" in str(caught.value)
    assert "dbx_list_pipelines" in str(caught.value)


def test_a_uuid_is_accepted():
    assert jobs.pipeline_id("f0e1c4a2-0000-11ee-be56-0242ac120002") == "f0e1c4a2-0000-11ee-be56-0242ac120002"


# ---------------------------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("start,end,now,expected", [
    (1_000_000, 1_102_000, None, 102),        # finished: end - start
    (1_000_000, None, 1_012_000, 12),         # active: now - start
    (None, None, 1_000_000, None),            # never started: NOT zero
    (None, 1_000_000, None, None),            # no start, an end: unknowable
    (1_000_000, 1_000_000, None, 0),          # genuinely instantaneous
])
def test_duration_is_computed_and_a_missing_start_is_not_zero(start, end, now, expected):
    """[E-12] A zero duration reads as "instant" and a queued task was not instant."""
    assert jobs.duration_seconds(start, end, now) == expected


def test_a_duration_reads_as_a_person_says_it():
    assert jobs.describe_duration(None) == "—"
    assert jobs.describe_duration(38) == "38 s"
    assert jobs.describe_duration(102) == "1 m 42 s"
    assert jobs.describe_duration(3720) == "1 h 02 m"


# ---------------------------------------------------------------------------------------------
# the graph, through the domain module
# ---------------------------------------------------------------------------------------------
def test_the_app_levels_what_the_tool_validated():
    """The guard that matters ([RB-5]): the page draws with the same code the tool validated with, so a
    graph the validator accepted cannot render as cyclic — and a cyclic one cannot render at all."""
    tasks = [
        {"task_key": "silver", "notebook_path": "/x/silver"},
        {"task_key": "gold", "notebook_path": "/x/gold", "depends_on": ["silver"]},
    ]
    assert jobs.task_graph_problem(tasks) is None
    assert jobs.task_levels(tasks) == [["silver"], ["gold"]]


def test_a_cyclic_graph_neither_validates_nor_draws():
    tasks = [
        {"task_key": "a", "notebook_path": "/x/a", "depends_on": ["b"]},
        {"task_key": "b", "notebook_path": "/x/b", "depends_on": ["a"]},
    ]
    assert jobs.task_graph_problem(tasks)
    assert jobs.task_levels(tasks) == []


def test_validate_task_graph_raises_a_job_error_a_route_can_map():
    with pytest.raises(jobs.JobError):
        jobs.validate_task_graph([{"task_key": "a"}])


# ---------------------------------------------------------------------------------------------
# what a tool call names
# ---------------------------------------------------------------------------------------------
def test_a_job_is_read_from_a_create_result_before_its_arguments():
    """A create's identity is something the platform granted; the arguments only asked for a name."""
    result = '{"job_id": 812345678901, "name": "agent_4ff4405d_daily"}'
    assert jobs.job_from_tool("dbx_create_job", '{"name": "agent_4ff4405d_daily"}', result) == 812345678901


def test_a_run_is_read_from_a_run_result():
    assert jobs.run_from_tool("dbx_run_job", '{"job_id": 1}', '{"run_id": 812345679}') == 812345679


def test_a_pipeline_is_read_from_a_create_result():
    result = '{"pipeline_id": "f0e1c4a2-0000-11ee-be56-0242ac120002"}'
    assert jobs.pipeline_from_tool("dbx_create_pipeline", "{}", result) == "f0e1c4a2-0000-11ee-be56-0242ac120002"


def test_a_truncated_result_still_yields_its_first_field():
    """Every tool writes the identity before the payload, and a result is capped, so the id survives a
    truncation even when the JSON does not parse."""
    truncated = '{"job_id": 812345678901, "tasks": [{"task_key": "silver", "notebook_pa'
    assert jobs.job_from_tool("dbx_create_job", None, truncated) == 812345678901


def test_a_tool_that_names_nothing_returns_none():
    assert jobs.job_from_tool("dbx_write_notebook", '{"path": "/x"}', '{"bytes": 12}') is None
    assert jobs.run_from_tool("dbx_list_jobs", None, "[]") is None
