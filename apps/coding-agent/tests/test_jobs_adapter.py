"""The jobs and pipelines adapters: the wire, the state words, and the guards a page depends on.

Every test here is about a fact a screenshot cannot prove: which path was called, whether a call was
skipped, and whether a denial stayed inside its block. The `Fake` seam replaces `DbxHttp` so the path and
the query are asserted directly — the pattern 013's `test_lakebase_tools.py` established, because the
defects in that spec were vocabulary defects, not logic defects.
"""
from __future__ import annotations

import asyncio

import pytest

from api.adapters.databricks.jobs import JobsBrowser
from api.adapters.databricks.pipelines import PipelinesBrowser
from api.domain import jobs as vocab

TERMINATED_FAILED = {"state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED",
                               "state_message": "task gold failed"}}
TERMINATED_OK = {"state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"}}
RUNNING = {"state": {"life_cycle_state": "RUNNING"}}


class Fake:
    """A `DbxHttp` that records and answers. `answers` maps a path fragment to a payload or an exception."""

    def __init__(self, answers: dict | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.answers = answers or {}

    async def get(self, path, token, params=None):
        self.calls.append(("GET", path, params))
        # The LONGEST matching pattern wins, not the first in insertion order: `runs/get` is a prefix of
        # `runs/get-output`, so insertion order made one answer another's call — the same class of bug as
        # a route that shadows a sibling.
        for pattern in sorted(self.answers, key=len, reverse=True):
            if pattern in path:
                payload = self.answers[pattern]
                if isinstance(payload, BaseException):
                    raise payload
                return payload
        return {}

    def paths(self) -> list[str]:
        return [c[1] for c in self.calls]

    def params_for(self, fragment: str) -> dict:
        for method, path, params in self.calls:
            if fragment in path:
                return params or {}
        raise AssertionError(f"no call to {fragment}: {self.paths()}")


def browser(fake: Fake) -> JobsBrowser:
    return JobsBrowser("https://example.invalid", lambda: "token", http=fake)


def pipes(fake: Fake) -> PipelinesBrowser:
    return PipelinesBrowser("https://example.invalid", lambda: "token", http=fake)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------------------------
# the wire
# ---------------------------------------------------------------------------------------------
def test_every_job_read_uses_api_2_2():
    """The same rule as the tool server's: a page and a tool describe ONE object, and 2.1 and 2.2 differ
    in a default that matters ([TOOL-2])."""
    fake = Fake({"jobs/get": {"settings": {"name": "j", "tasks": []}}, "runs/list": {"runs": []}})
    run(browser(fake).job(1, "t"))
    job_calls = [p for p in fake.paths() if "/jobs/" in p]
    assert job_calls
    assert not [p for p in job_calls if "/2.1/" in p], job_calls


def test_the_list_asks_for_one_page_and_no_tasks():
    fake = Fake({"jobs/list": {"jobs": []}})
    run(browser(fake).jobs("t"))
    params = fake.params_for("/jobs/list")
    assert params["expand_tasks"] == "false"
    assert 1 <= params["limit"] <= 100


def test_the_rail_list_makes_one_call_and_reads_no_runs():
    """[RB-7] The rail renders on every page load; one call per job before it paints is unusable."""
    fake = Fake({"jobs/list": {"jobs": [{"job_id": i, "settings": {"name": f"j{i}"}}
                                        for i in range(25)]}})
    rows = run(browser(fake).jobs("t"))
    assert len(rows) == 25
    assert fake.paths() == ["/api/2.2/jobs/list"], fake.paths()


def test_a_job_page_reads_three_calls_and_no_output_when_nothing_failed():
    fake = Fake({
        "jobs/get": {"settings": {"name": "j", "tasks": [
            {"task_key": "a", "notebook_task": {"notebook_path": "/x"}}]}},
        "runs/list": {"runs": [{"run_id": 5, "state": {"life_cycle_state": "TERMINATED",
                                                       "result_state": "SUCCESS"}}]},
        "runs/get": TERMINATED_OK,
    })
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["job"]["name"] == "j"
    assert blocks["runs"]
    assert blocks["latestRun"]["word"] == "succeeded"
    assert not any("get-output" in p for p in fake.paths())


# ---------------------------------------------------------------------------------------------
# [RB-6]: get-output only for a terminal run
# ---------------------------------------------------------------------------------------------
def test_no_output_call_for_a_running_run():
    """[RB-6] `get-output` is documented as valid for a finished run; asking during one is a `400` on
    every poll of the page's most-read state."""
    fake = Fake({
        "jobs/get": {"settings": {"name": "j", "tasks": []}},
        "runs/list": {"runs": [{"run_id": 5, "state": {"life_cycle_state": "RUNNING"}}]},
        "runs/get": {"state": {"life_cycle_state": "RUNNING"},
                     "tasks": [{"task_key": "gold", "run_id": 6,
                                "state": {"life_cycle_state": "RUNNING"}}]},
    })
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["latestRun"]["word"] == "running"
    assert not any("get-output" in p for p in fake.paths()), fake.paths()


def test_a_failed_terminal_run_does_read_its_output():
    fake = Fake({
        "jobs/get": {"settings": {"name": "j", "tasks": []}},
        "runs/list": {"runs": [{"run_id": 5, "state": {"life_cycle_state": "TERMINATED",
                                                       "result_state": "FAILED"}}]},
        "runs/get": {"state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
                     "tasks": [{"task_key": "gold", "run_id": 6,
                                "state": {"life_cycle_state": "TERMINATED",
                                          "result_state": "FAILED"}}]},
        "get-output": {"error": "AnalysisException: no such column"},
    })
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["latestRun"]["output"]["error"].startswith("AnalysisException")


# ---------------------------------------------------------------------------------------------
# the words ([UI-8], [PIPE-5])
# ---------------------------------------------------------------------------------------------
def test_a_failed_run_reads_failed_not_terminated():
    fake = Fake({"jobs/get": {"settings": {"name": "j", "tasks": []}},
                 "runs/list": {"runs": [{"run_id": 5, "state": TERMINATED_FAILED["state"]}]},
                 "runs/get": TERMINATED_FAILED, "get-output": {}})
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["latestRun"]["word"] == "failed"
    assert blocks["latestRun"]["tone"] == "bad"


def test_a_pipeline_reads_its_last_update_not_its_state():
    """THE row: a pipeline in `IDLE` whose last update FAILED is `failed`, not `idle` ([F5], [PIPE-5])."""
    fake = Fake({
        "/updates": {"updates": [{"update_id": "u1", "state": "FAILED"}]},
        "/events": {"events": []},
    })
    blocks = run(pipes(fake).pipeline("f0e1c4a2-0000-11ee-be56-0242ac120002", "t"))
    assert blocks["word"] == "failed"


def test_a_pipeline_that_never_updated_is_idle_and_says_null():
    fake = Fake({"/updates": {"updates": []}, "/events": {"events": []}})
    blocks = run(pipes(fake).pipeline("f0e1c4a2-0000-11ee-be56-0242ac120002", "t"))
    assert blocks["lastUpdate"] is None
    assert blocks["word"] in ("idle", "unknown")


# ---------------------------------------------------------------------------------------------
# isolation ([UI-3], [E-1])
# ---------------------------------------------------------------------------------------------
def test_a_denied_run_read_does_not_blank_the_job_block():
    """One block's refusal must not take its siblings — 013's `page_blocks` decision, and the reason
    `Block` exists in the DOM."""
    fake = Fake({
        "jobs/get": {"settings": {"name": "daily_revenue", "tasks": []}},
        "runs/list": PermissionError("PERMISSION_DENIED: CAN_MANAGE_RUN"),
    })
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["job"]["name"] == "daily_revenue"
    assert "PERMISSION_DENIED" in blocks["runs"]["error"]


def test_a_malformed_id_is_refused_before_any_call():
    fake = Fake()
    with pytest.raises(vocab.JobError):
        run(browser(fake).job("daily_revenue", "t"))
    assert fake.calls == []


def test_a_read_names_the_identity_that_read_it():
    """[RB-1], [E-14]: the page must be able to say it shows what the APP can see, rather than implying
    the stronger claim about the viewer."""
    fake = Fake({"jobs/get": {"settings": {"name": "j", "tasks": []}}, "runs/list": {"runs": []}})
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["identity"] == "the app's service principal"


# ---------------------------------------------------------------------------------------------
# the cache (the database lens's argument)
# ---------------------------------------------------------------------------------------------
def test_the_cache_is_keyed_by_token():
    """[E-28]'s class: one identity's result must never answer another's request."""
    fake = Fake({"jobs/get": {"settings": {"name": "j", "tasks": []}}, "runs/list": {"runs": []}})
    b = browser(fake)
    run(b.job(1, "token-a"))
    before = len(fake.calls)
    run(b.job(1, "token-b"))
    assert len(fake.calls) > before, "a different token was served from another identity's cache"


def test_a_terminal_run_is_cached_and_a_live_one_is_not():
    """A terminal run's timestamps are frozen so it can be kept forever; a live run must be re-read on
    every poll or the page stops moving."""
    done = Fake({
        "jobs/get": {"settings": {"name": "j", "tasks": []}},
        "runs/list": {"runs": [{"run_id": 5, "state": {"life_cycle_state": "TERMINATED",
                                                       "result_state": "SUCCESS"}}]},
        "runs/get": TERMINATED_OK,
    })
    b = browser(done)
    run(b.job(1, "t"))
    calls_after_first = len(done.calls)
    run(b.run(5, "t"))
    assert len(done.calls) == calls_after_first, "a terminal run was re-read; it cannot have changed"

    live = Fake({
        "jobs/get": {"settings": {"name": "j", "tasks": []}},
        "runs/list": {"runs": [{"run_id": 9, "state": {"life_cycle_state": "RUNNING"}}]},
        "runs/get": RUNNING,
    })
    b2 = browser(live)
    run(b2.job(1, "t"))
    one = len(live.calls)
    run(b2.run(9, "t"))
    assert len(live.calls) > one, "a live run was served from cache; the page would freeze"


# ---------------------------------------------------------------------------------------------
# what a run page shows ([RUN-1], [RUN-5])
# ---------------------------------------------------------------------------------------------
def test_a_task_that_has_not_started_is_not_called_running():
    fake = Fake({"runs/get": {"state": {"life_cycle_state": "RUNNING"},
                              "tasks": [{"task_key": "audit", "run_id": 7, "state": {}}]}})
    row = run(browser(fake).run(5, "t"))
    assert row["tasks"][0]["word"] == "not started"


def test_every_task_carries_its_own_word():
    fake = Fake({"runs/get": {
        "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
        "tasks": [
            {"task_key": "silver", "run_id": 1,
             "state": {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
             "start_time": 1000, "end_time": 1038},
            {"task_key": "gold", "run_id": 2,
             "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
             "start_time": 1038, "end_time": 1102},
            {"task_key": "audit", "run_id": 3, "state": {"life_cycle_state": "SKIPPED"}},
        ]}})
    row = run(browser(fake).run(5, "t"))
    words = {t["taskKey"]: t["word"] for t in row["tasks"]}
    assert words == {"silver": "succeeded", "gold": "failed", "audit": "skipped"}


def test_a_duration_is_a_dash_when_the_start_is_missing():
    fake = Fake({"runs/get": {"state": {"life_cycle_state": "RUNNING"},
                              "tasks": [{"task_key": "a", "run_id": 1, "state": {}}]}})
    row = run(browser(fake).run(5, "t"))
    assert row["tasks"][0]["duration"] == "—"


# ---------------------------------------------------------------------------------------------
# the graph, read back from the platform's shape
# ---------------------------------------------------------------------------------------------
def test_the_platform_task_shape_is_flattened_for_the_graph():
    """The platform nests a task's target; `job_graph` wants it flat. One function does that, which is why
    the page and the validator can share one algorithm ([RB-5])."""
    fake = Fake({"jobs/get": {"settings": {
        "name": "j",
        "tasks": [
            {"task_key": "silver", "notebook_task": {"notebook_path": "/x/silver"}},
            {"task_key": "gold", "notebook_task": {"notebook_path": "/x/gold"},
             "depends_on": [{"task_key": "silver"}]},
        ]}}, "runs/list": {"runs": []}})
    blocks = run(browser(fake).job(1, "t"))
    assert blocks["levels"] == [["silver"], ["gold"]]
    assert blocks["summary"] == "2 tasks in 2 levels"
    assert blocks["graphProblem"] is None
    assert blocks["job"]["tasks"][1]["depends_on"] == ["silver"]
