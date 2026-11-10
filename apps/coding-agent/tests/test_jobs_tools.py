"""The job tools, asserted on what they SEND.

The defects this file exists for are all about the wire, not about the return value:

  * `F1` — the tool spoke Jobs API 2.1 while the platform's 2.2 changes a default (queueing).
  * `F2` — `run-now` carried no idempotency token, so a retry started a second billable run.
  * `F3` — a malformed graph reached the platform and came back as a `400` the model paraphrased.

So the pattern here is a RECORDING fake: every call the tool makes is captured (method, path, body) and
asserted. A test that only read the return string would pass with the wrong API version, which is exactly
how the first defect survived 25 tool tests.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import httpx
import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"

PREFIXES = {
    "NBMCP_WRITE_PATHS": "/Users/me/agent_scratch/",
    "NBMCP_WRITE_SCHEMAS": "main.agent_scratch",
    "NBMCP_WRITE_JOB_PREFIX": "job-prefix-",
    "NBMCP_WRITE_INSTANCE_PREFIX": "inst-prefix-",
    "NBMCP_WRITE_APP_PREFIX": "app-prefix-",
    "NBMCP_WRITE_PIPELINE_PREFIX": "",
    "NBMCP_RUN_SESSION": "session-abc12345",
}


def load(monkeypatch, **overrides):
    env = {**PREFIXES, **overrides}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_TOKEN", "t")
    monkeypatch.setenv("NBMCP_ALLOW_WRITES", "1")
    spec = importlib.util.spec_from_file_location(f"nbmcp_jobs_{os.urandom(4).hex()}", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wire:
    """Every call the tool makes, and a scripted answer per path-substring."""

    def __init__(self, answers: dict | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.answers = answers or {}

    def install(self, module):
        """Replace `_get`/`_post` so the tool still builds its own paths and bodies.

        The recording happens HERE and not in `_answer`, because recording in both places counted every
        call twice — which made `len(calls) == 1` fail for a tool that made one call, and made a list
        comprehension over bodies subscript a `None`.
        """
        def _answer(path: str):
            for pattern, payload in self.answers.items():
                if pattern in path:
                    if isinstance(payload, Exception):
                        raise payload
                    return payload
            return {}

        def fake_get(path, params=None):
            self.calls.append(("GET", path, params))
            return _answer(path)

        def fake_post(path, body=None):
            self.calls.append(("POST", path, body))
            return _answer(path)

        module._get = fake_get
        module._post = fake_post
        module._put = fake_post
        module._retry = lambda fn, **_kw: fn()
        return self

    def paths(self) -> list[str]:
        return [c[1] for c in self.calls]

    def calls_to(self, fragment: str) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if fragment in c[1]]

    def body_for(self, fragment: str) -> dict:
        for method, path, body in self.calls:
            if fragment in path and body is not None:
                return body
        raise AssertionError(f"no call to {fragment}; calls were {self.paths()}")


TASKS = [
    {"task_key": "silver", "notebook_path": "/Users/me/agent_scratch/silver"},
    {"task_key": "gold", "notebook_path": "/Users/me/agent_scratch/gold", "depends_on": ["silver"]},
]


# ---------------------------------------------------------------------------------------------
# F1: the API version
# ---------------------------------------------------------------------------------------------
def test_every_job_call_uses_api_2_2(monkeypatch):
    """The defect: 2.1 accepted, and queueing is off there while it is on in 2.2. Two objects, one name."""
    m = load(monkeypatch)
    wire = Wire({
        "jobs/get": {"settings": {"name": "job-prefix-daily", "tasks": TASKS}},
        "runs/list": {"runs": []},
        "jobs/create": {"job_id": 1},
        "run-now": {"run_id": 2},
        "runs/get": {"state": {"life_cycle_state": "RUNNING"}},
    }).install(m)

    m.dbx_create_job("job-prefix-daily", tasks=TASKS, cron="0 0 6 * * ?")
    m.dbx_run_job(1, wait_seconds=0)
    m.dbx_job_run_status(2)
    m.dbx_list_jobs(include_runs=False)
    m.dbx_job_failure_context(1)

    job_calls = [p for p in wire.paths() if "/jobs/" in p or "/runs/" in p]
    assert job_calls, wire.paths()
    old = [p for p in job_calls if "/2.1/" in p]
    assert not old, f"these job calls still speak 2.1: {old}"


def test_create_body_states_the_queue_setting(monkeypatch):
    """2.2 queues by default; saying so explicitly means the behaviour does not depend on a default that
    could change again (spec 014 [TOOL-2])."""
    m = load(monkeypatch)
    wire = Wire({"jobs/create": {"job_id": 42}}).install(m)
    m.dbx_create_job("job-prefix-daily", tasks=TASKS)
    body = wire.body_for("/jobs/create")
    assert body["queue"] == {"enabled": True}
    assert body["performance_target"] in ("STANDARD", "PERFORMANCE_OPTIMIZED", "COST_OPTIMIZED")


# ---------------------------------------------------------------------------------------------
# F3 / [TOOL-3]: the graph, refused before any call
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tasks,expected", [
    ([], "at least one task"),
    ([{"task_key": "a", "notebook_path": "/Users/me/agent_scratch/a"},
      {"task_key": "a", "notebook_path": "/Users/me/agent_scratch/b"}], "used twice"),
    ([{"task_key": "a", "notebook_path": "/Users/me/agent_scratch/a", "depends_on": ["nope"]}],
     "not a task"),
    ([{"task_key": "a", "notebook_path": "/Users/me/agent_scratch/a", "pipeline_id": "p"}],
     "exactly one"),
    ([{"task_key": "a", "notebook_path": "/Users/me/agent_scratch/a"},
      {"task_key": "b", "notebook_path": "/Users/me/agent_scratch/b", "depends_on": ["a"]},
      {"task_key": "a", "notebook_path": "/Users/me/agent_scratch/c", "depends_on": ["b"]}], "used twice"),
])
def test_a_malformed_graph_makes_zero_http_calls(monkeypatch, tasks, expected):
    """The rule that makes the refusal worth having: nothing was created, and the tool says so."""
    m = load(monkeypatch)
    wire = Wire().install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=tasks))
    assert wire.calls == [], f"the platform was called for a graph it would refuse: {wire.paths()}"
    assert expected in out["error"]
    assert out["nothing_was_created"] is True


def test_a_cycle_is_refused_with_the_cycle_named(monkeypatch):
    m = load(monkeypatch)
    wire = Wire().install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=[
        {"task_key": "a", "notebook_path": "/Users/me/agent_scratch/a", "depends_on": ["b"]},
        {"task_key": "b", "notebook_path": "/Users/me/agent_scratch/b", "depends_on": ["a"]},
    ]))
    assert "cycle" in out["error"]
    assert "a" in out["error"] and "b" in out["error"]
    assert wire.calls == []


def test_a_json_string_is_validated_like_a_list(monkeypatch):
    """A model that formats its arguments as JSON text must not get a way around the validator."""
    m = load(monkeypatch)
    wire = Wire({"jobs/create": {"job_id": 7}}).install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks_json=json.dumps(TASKS)))
    assert out["job_id"] == 7
    assert wire.calls

    wire2 = Wire().install(m)
    bad = json.loads(m.dbx_create_job("job-prefix-daily",
                                      tasks_json='[{"task_key":"a","notebook_path":"/Users/me/agent_scratch/a"},'
                                                 '{"task_key":"a","notebook_path":"/Users/me/agent_scratch/b"}]'))
    assert "used twice" in bad["error"]
    assert wire2.calls == []


def test_an_unparseable_tasks_json_says_what_to_pass_instead(monkeypatch):
    m = load(monkeypatch)
    Wire().install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks_json="{oops"))
    assert "not valid JSON" in out["error"]
    assert "native list" in out["error"]


# ---------------------------------------------------------------------------------------------
# the create itself
# ---------------------------------------------------------------------------------------------
def test_a_scheduled_job_is_created_paused(monkeypatch):
    """[JOB-4] An agent must not start a recurring cost. The pause is in the body AND in the answer, as a
    field a page can parse — it used to be the string 'created PAUSED'."""
    m = load(monkeypatch)
    wire = Wire({"jobs/create": {"job_id": 5}}).install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=TASKS, cron="0 0 6 * * ?"))
    assert wire.body_for("/jobs/create")["schedule"]["pause_status"] == "PAUSED"
    assert out["schedule"] == {"cron": "0 0 6 * * ?", "timezone": "UTC", "pauseStatus": "PAUSED"}
    assert "PAUSED" in out["next"] or "paused" in out["next"]


def test_an_unscheduled_job_has_no_schedule_field(monkeypatch):
    m = load(monkeypatch)
    wire = Wire({"jobs/create": {"job_id": 6}}).install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=TASKS))
    assert "schedule" not in wire.body_for("/jobs/create")
    assert out["schedule"] is None


def test_the_result_carries_the_levels_the_page_will_draw(monkeypatch):
    """The tool and the page use one algorithm ([RB-5]); this asserts the tool reports the same shape the
    page renders, so a screenshot disagreement is impossible."""
    m = load(monkeypatch)
    Wire({"jobs/create": {"job_id": 9}}).install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=TASKS))
    assert out["levels"] == [["silver"], ["gold"]]
    assert out["summary"] == "2 tasks in 2 levels"


def test_a_task_outside_the_write_fence_is_refused(monkeypatch):
    m = load(monkeypatch)
    wire = Wire().install(m)
    with pytest.raises(PermissionError):
        m.dbx_create_job("job-prefix-daily", tasks=[
            {"task_key": "a", "notebook_path": "/Shared/someone_else/x"}])
    assert wire.calls == []


def test_a_job_name_outside_the_prefix_is_refused(monkeypatch):
    m = load(monkeypatch)
    Wire().install(m)
    with pytest.raises(PermissionError, match="job-prefix-"):
        m.dbx_create_job("daily_revenue", tasks=TASKS)


def test_a_platform_400_says_nothing_was_created(monkeypatch):
    """[E-3] Without this sentence a model reads an exception and writes 'the job failed', which asserts
    an object that does not exist."""
    m = load(monkeypatch)
    request = httpx.Request("POST", "https://example.invalid/api/2.2/jobs/create")
    error = httpx.HTTPStatusError(
        "bad request", request=request,
        response=httpx.Response(400, text="INVALID_PARAMETER_VALUE: invalid cron",
                                request=request))
    Wire({"jobs/create": error}).install(m)
    out = json.loads(m.dbx_create_job("job-prefix-daily", tasks=TASKS, cron="nonsense"))
    assert out["created"] is False
    assert out["nothing_was_created"] is True
    assert "invalid cron" in out["platform_error"]


def test_task_types_are_built_from_one_table(monkeypatch):
    """A pipeline task and a notebook task in one job: the shape of each comes from the same map, so a
    new type is a row rather than a second branch."""
    m = load(monkeypatch)
    wire = Wire({"jobs/create": {"job_id": 11}}).install(m)
    m.dbx_create_job("job-prefix-daily", tasks=[
        {"task_key": "load", "notebook_path": "/Users/me/agent_scratch/load"},
        {"task_key": "rollup", "pipeline_id": "f0e1c4a2-0000", "depends_on": ["load"]},
    ])
    tasks = wire.body_for("/jobs/create")["tasks"]
    assert tasks[0]["notebook_task"] == {"notebook_path": "/Users/me/agent_scratch/load"}
    assert tasks[1]["pipeline_task"] == {"pipeline_id": "f0e1c4a2-0000"}
    assert tasks[1]["depends_on"] == [{"task_key": "load"}]


# ---------------------------------------------------------------------------------------------
# F2 / [TOOL-5]: idempotency
# ---------------------------------------------------------------------------------------------
def test_run_sends_an_idempotency_token(monkeypatch):
    m = load(monkeypatch)
    wire = Wire({"jobs/get": {"settings": {"name": "job-prefix-daily"}},
                 "runs/list": {"runs": []},
                 "run-now": {"run_id": 100}}).install(m)
    m.dbx_run_job(1, wait_seconds=0)
    body = wire.body_for("/run-now")
    assert body.get("idempotency_token"), body
    assert len(body["idempotency_token"]) >= 20


def test_two_identical_runs_send_one_token(monkeypatch):
    m = load(monkeypatch)
    wire = Wire({"jobs/get": {"settings": {"name": "job-prefix-daily"}},
                 "runs/list": {"runs": []},
                 "run-now": {"run_id": 100}}).install(m)
    m.dbx_run_job(1, wait_seconds=0)
    m.dbx_run_job(1, wait_seconds=0)
    tokens = [body["idempotency_token"] for method, path, body in wire.calls_to("/run-now")]
    assert len(tokens) == 2 and tokens[0] == tokens[1], tokens


def test_a_different_purpose_sends_a_different_token(monkeypatch):
    """A deliberate re-run after a fix must be a NEW run; the token must not stand in its way."""
    m = load(monkeypatch)
    wire = Wire({"jobs/get": {"settings": {"name": "job-prefix-daily"}},
                 "runs/list": {"runs": []},
                 "run-now": {"run_id": 100}}).install(m)
    m.dbx_run_job(1, wait_seconds=0, purpose="first-run")
    m.dbx_run_job(1, wait_seconds=0, purpose="retry-after-fix")
    tokens = [body["idempotency_token"] for method, path, body in wire.calls_to("/run-now")]
    assert tokens[0] != tokens[1]


def test_a_different_session_sends_a_different_token(monkeypatch):
    """Two conversations are independent: 'run it again' in a new one must produce a new run."""
    m = load(monkeypatch, NBMCP_RUN_SESSION="session-one")
    first = m._idempotency_token(1, "run")
    m2 = load(monkeypatch, NBMCP_RUN_SESSION="session-two")
    assert first != m2._idempotency_token(1, "run")


def test_reused_is_true_when_the_run_id_did_not_change(monkeypatch):
    """The platform does not say whether the token matched; it answers with a run id either way. So the
    tool reads the newest run first and compares — one extra GET to be able to tell the truth."""
    m = load(monkeypatch)
    Wire({"jobs/get": {"settings": {"name": "job-prefix-daily"}},
          "runs/list": {"runs": [{"run_id": 100}]},
          "run-now": {"run_id": 100}}).install(m)
    out = json.loads(m.dbx_run_job(1, wait_seconds=0))
    assert out["reused"] is True
    assert out["run_id"] == 100


def test_reused_is_false_when_a_new_run_started(monkeypatch):
    m = load(monkeypatch)
    Wire({"jobs/get": {"settings": {"name": "job-prefix-daily"}},
          "runs/list": {"runs": [{"run_id": 100}]},
          "run-now": {"run_id": 101}}).install(m)
    out = json.loads(m.dbx_run_job(1, wait_seconds=0))
    assert out["reused"] is False


def test_run_re_reads_the_job_and_refuses_a_foreign_name(monkeypatch):
    """[TOOL-4] The fence is re-applied to the object the PLATFORM returned, not to the id in the
    arguments — an id is not a promise about whose job it is."""
    m = load(monkeypatch)
    wire = Wire({"jobs/get": {"settings": {"name": "someone_elses_job"}}}).install(m)
    with pytest.raises(PermissionError, match="job-prefix-"):
        m.dbx_run_job(999, wait_seconds=0)
    assert not any("run-now" in p for p in wire.paths()), "the platform was asked to run it anyway"


def test_reading_a_foreign_job_is_not_refused(monkeypatch):
    """Inspecting a job you may not run is not a write. `dbx_lakebase_branch` already draws this line."""
    m = load(monkeypatch)
    Wire({"jobs/get": {"settings": {"name": "someone_elses_job", "tasks": []}},
          "runs/list": {"runs": []}}).install(m)
    out = json.loads(m.dbx_job_failure_context(999))
    assert out["name"] == "someone_elses_job"


# ---------------------------------------------------------------------------------------------
# F6 / [TOOL-9]: what the list carries
# ---------------------------------------------------------------------------------------------
def test_list_includes_the_latest_run_state(monkeypatch):
    m = load(monkeypatch)
    Wire({
        "jobs/list": {"jobs": [{"job_id": 1, "settings": {"name": "job-prefix-a"}}]},
        "runs/list": {"runs": [{"run_id": 9,
                                "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
                                "start_time": 1000, "end_time": 2000}]},
    }).install(m)
    rows = json.loads(m.dbx_list_jobs())
    row = rows["jobs"][0] if isinstance(rows, dict) else rows[0]
    assert row["lastRun"]["result"] == "FAILED"


def test_list_reports_a_job_with_no_runs_as_null_not_missing(monkeypatch):
    m = load(monkeypatch)
    Wire({"jobs/list": {"jobs": [{"job_id": 1, "settings": {"name": "job-prefix-a"}}]},
          "runs/list": {"runs": []}}).install(m)
    rows = json.loads(m.dbx_list_jobs())
    row = rows["jobs"][0] if isinstance(rows, dict) else rows[0]
    assert row["lastRun"] is None


def test_a_run_we_could_not_read_is_named_not_silently_empty(monkeypatch):
    """[E-9] 'No runs' and 'not read' are different facts, and the list must not merge them."""
    m = load(monkeypatch)

    def boom(path, params=None):
        if "runs/list" in path:
            raise RuntimeError("the workspace did not answer")
        return {"jobs": [{"job_id": 1, "settings": {"name": "job-prefix-a"}}]}

    m._get = boom
    out = json.loads(m.dbx_list_jobs())
    assert out["runsUnread"] == [1]
    assert out["jobs"][0]["lastRun"] is None


def test_list_without_runs_makes_one_call(monkeypatch):
    """`include_runs=False` is the rail's path: one call, no fan-out ([RB-7])."""
    m = load(monkeypatch)
    wire = Wire({"jobs/list": {"jobs": [{"job_id": 1, "settings": {"name": "job-prefix-a"}}]}}).install(m)
    m.dbx_list_jobs(include_runs=False)
    assert len(wire.calls) == 1, wire.paths()


# ---------------------------------------------------------------------------------------------
# the model-only tool
# ---------------------------------------------------------------------------------------------
def test_failure_context_carries_the_error_and_the_real_columns(monkeypatch):
    """Lens 7: a model given a status code writes a story; a model given an error and the real columns
    writes a fix. Three calls, one answer."""
    m = load(monkeypatch)
    Wire({
        "jobs/get": {"settings": {"name": "job-prefix-daily",
                                  "tasks": [{"task_key": "gold",
                                             "notebook_task": {"notebook_path": "/Users/me/agent_scratch/gold"}}]}},
        "runs/list": {"runs": [
            {"run_id": 5, "state": {"result_state": "FAILED"}, "start_time": 1000},
            {"run_id": 4, "state": {"result_state": "SUCCESS"}, "start_time": 500, "end_time": 600},
        ]},
        "runs/get-output": {"error": "AnalysisException: cannot resolve 'fare_amount'"},
        "runs/get": {"state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"},
                     "tasks": [{"task_key": "gold", "run_id": 6,
                                "state": {"life_cycle_state": "TERMINATED", "result_state": "FAILED"}}]},
        "workspace/export": {"content": ""},
        "unity-catalog/tables/main.silver.trips": {"columns": [{"name": "total"}, {"name": "trip_id"}]},
    }).install(m)
    out = json.loads(m.dbx_job_failure_context(1))
    assert out["failed"] is True
    assert out["run_id"] == 5
    assert out["failingTask"]["task_key"] == "gold"
    assert "fare_amount" in out["failingTask"]["error"]
    assert out["lastSuccess"]["run_id"] == 4
    assert "dbx_run_job" in out["next"] and "retry-after-fix" in out["next"]


def test_failure_context_on_a_healthy_job_says_so_without_inventing_a_cause(monkeypatch):
    m = load(monkeypatch)
    Wire({
        "jobs/get": {"settings": {"name": "job-prefix-daily", "tasks": []}},
        "runs/list": {"runs": [{"run_id": 5, "state": {"result_state": "SUCCESS"}}]},
    }).install(m)
    out = json.loads(m.dbx_job_failure_context(1))
    assert out["failed"] is False
    assert "no failed run" in out["note"]


def test_failure_context_on_a_never_run_job_says_never_run(monkeypatch):
    m = load(monkeypatch)
    Wire({"jobs/get": {"settings": {"name": "job-prefix-daily", "tasks": []}},
          "runs/list": {"runs": []}}).install(m)
    out = json.loads(m.dbx_job_failure_context(1))
    assert out["failed"] is False
    assert "never run" in out["note"]
