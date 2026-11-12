"""The HTTP contract of the job, run and pipeline routes — and the shape that is deliberately absent.

Three things are asserted here that a page test cannot:

  * the status mapping (a denial is a 403, a missing job is a 404, a bad id is a 422, never a 500);
  * that a payload names the identity that read it;
  * that there is **no write route** under `/api/jobs` or `/api/pipelines`. That absence is a design
    decision (spec 014 [07 §5]): every action goes through the agent, so the fence has one home. A future
    contributor with a good reason for a direct POST has to delete this test, which is the version of
    that decision that survives them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import build

ROOT = Path(__file__).resolve().parents[1]


class FakeJobs:
    """A browser whose answers a test scripts. The router only calls these four methods."""

    def __init__(self, answer=None, error: BaseException | None = None):
        self.answer = answer if answer is not None else {}
        self.error = error
        self.calls: list[tuple] = []

    async def jobs(self, token, limit=25):
        self.calls.append(("jobs", limit))
        if self.error:
            raise self.error
        return self.answer.get("items", [])

    async def job(self, ref, token):
        self.calls.append(("job", ref))
        if self.error:
            raise self.error
        return self.answer

    async def run(self, ref, token):
        self.calls.append(("run", ref))
        if self.error:
            raise self.error
        return self.answer


class FakePipes:
    def __init__(self, answer=None, error: BaseException | None = None):
        self.answer = answer if answer is not None else {}
        self.error = error
        self.calls: list[tuple] = []

    async def pipelines(self, token, limit=25):
        self.calls.append(("list", limit))
        if self.error:
            raise self.error
        return self.answer.get("items", [])

    async def pipeline(self, ref, token, events=20):
        self.calls.append(("pipeline", ref, events))
        if self.error:
            raise self.error
        return self.answer

    async def events(self, ref, token, limit=20):
        self.calls.append(("events", ref, limit))
        if self.error:
            raise self.error
        return self.answer.get("items", [])


def client(jobs=None, pipes=None) -> TestClient:
    cfg = Settings(
        agent_mode="fake", demo_scenario="notebook",
        agent_command=f"{sys.executable} -m api.adapters.fake.agent notebook 0",
        allowed_models=["fake/model-a"], default_model="fake/model-a",
        dev_user="tester@example.com",
    )
    app = build(cfg)
    app.state.orchestrator._rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    if jobs is not None:
        app.state.jobs = jobs
    if pipes is not None:
        app.state.pipelines = pipes
    return TestClient(app)


# ---------------------------------------------------------------------------------------------
# the reads
# ---------------------------------------------------------------------------------------------
def test_the_jobs_list_names_the_identity_that_read_it():
    """[RB-1], [E-14]. The page must be able to say it shows what the APP can see."""
    body = client(FakeJobs({"items": [{"job_id": 1, "name": "j"}]})).get("/api/jobs").json()
    assert body["items"][0]["name"] == "j"
    assert body["identity"] == "the app's service principal"


def test_a_job_read_returns_its_blocks_verbatim():
    blocks = {"job": {"job_id": 1, "name": "j"}, "runs": [], "latestRun": None,
              "levels": [["a"]], "graphProblem": None, "identity": "the app's service principal"}
    body = client(FakeJobs(blocks)).get("/api/jobs/1").json()
    assert body["job"]["name"] == "j"
    assert body["levels"] == [["a"]]


def test_a_run_read_returns_its_tasks():
    body = client(FakeJobs({"run_id": 5, "tasks": [{"taskKey": "a", "word": "failed"}]})) \
        .get("/api/runs/5").json()
    assert body["tasks"][0]["word"] == "failed"


def test_a_pipeline_read_carries_the_last_update():
    client_ = client(pipes=FakePipes({"word": "failed", "lastUpdate": {"state": "FAILED"}}))
    body = client_.get("/api/pipelines/f0e1c4a2-0000-11ee-be56-0242ac120002").json()
    assert body["word"] == "failed"
    assert body["lastUpdate"]["state"] == "FAILED"


def test_the_pipeline_events_route_is_its_own_read():
    client_ = client(pipes=FakePipes({"items": [{"level": "ERROR", "message": "boom"}]}))
    body = client_.get("/api/pipelines/f0e1c4a2-0000-11ee-be56-0242ac120002/events").json()
    assert body["items"][0]["level"] == "ERROR"


# ---------------------------------------------------------------------------------------------
# the status mapping
# ---------------------------------------------------------------------------------------------
def test_a_denial_is_a_403_and_the_platform_sentence_survives():
    """[E-1]: the sentence is the message. Paraphrasing it sends the user to the wrong person."""
    client_ = client(FakeJobs(error=PermissionError("PERMISSION_DENIED: CAN_MANAGE_RUN")))
    r = client_.get("/api/jobs/1")
    assert r.status_code == 403
    assert "CAN_MANAGE_RUN" in r.json()["detail"]


def test_a_missing_job_is_a_404():
    client_ = client(FakeJobs(error=LookupError("not found: /api/2.2/jobs/get")))
    assert client_.get("/api/jobs/999").status_code == 404


def test_a_malformed_id_is_a_422_from_the_domain_module():
    """The route does no validation of its own: `api.domain.jobs.job_id` raises `JobError`, which
    `_dbx_errors` maps to 422, and the sentence names the alternative ([E-20])."""
    real = __import__("api.adapters.databricks.jobs", fromlist=["JobsBrowser"]).JobsBrowser(
        "https://example.invalid", lambda: "t")
    body = client(real).get("/api/jobs/daily_revenue").json()
    assert "Data tab" in body["detail"]


def test_a_workspace_failure_is_a_502_not_a_500():
    client_ = client(FakeJobs(error=RuntimeError("DATABRICKS_HOST is not set")))
    assert client_.get("/api/jobs/1").status_code == 502


# ---------------------------------------------------------------------------------------------
# the absence
# ---------------------------------------------------------------------------------------------
def test_there_is_no_write_route_for_a_job_or_a_pipeline():
    """[07 §5]: one fence, one process. The browser asks the AGENT to run, resume, cancel, repair, start or
    stop — so this route table has no POST under either prefix, and a future direct write has to delete
    this test on purpose."""
    app = client(FakeJobs(), FakePipes()).app
    writes = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if not any(path.startswith(p) for p in ("/api/jobs", "/api/runs", "/api/pipelines")):
            continue
        if methods - {"GET", "HEAD", "OPTIONS"}:
            writes.append((sorted(methods), path))
    assert not writes, (
        f"these write routes exist; every action must go through the agent so the fence has one home: "
        f"{writes}")


# ---------------------------------------------------------------------------------------------
# the rules the page reads
# ---------------------------------------------------------------------------------------------
def test_run_actions_answers_from_the_domain_module():
    body = client().get("/api/infra/run-actions?life_cycle=TERMINATED&result=FAILED").json()
    assert body == {"word": "failed", "tone": "bad", "active": False, "terminal": True,
                    "cancel": False, "repair": True}


def test_run_actions_says_a_running_run_can_be_cancelled():
    body = client().get("/api/infra/run-actions?life_cycle=RUNNING").json()
    assert body["cancel"] is True and body["active"] is True


# ---------------------------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------------------------
def test_the_ledger_reads_what_the_tool_server_wrote(monkeypatch, tmp_path):
    """[RB-3]: the ledger is a file the app owns, so a resumed session still knows what it made."""
    (tmp_path / "session-1.jsonl").write_text(
        json.dumps({"kind": "pipeline", "id": "p1", "name": "sales"}) + "\n")
    monkeypatch.setenv("APP_SESSION_LEDGER_DIR", str(tmp_path))
    body = client().get("/api/infra/ledger").json()
    assert body["items"] == [{"kind": "pipeline", "id": "p1", "name": "sales", "session": "session-1"}]


def test_an_empty_ledger_is_an_empty_list_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SESSION_LEDGER_DIR", str(tmp_path / "does-not-exist"))
    r = client().get("/api/infra/ledger")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_a_corrupt_ledger_line_is_skipped_not_fatal(monkeypatch, tmp_path):
    (tmp_path / "s.jsonl").write_text("{not json\n" + json.dumps({"kind": "pipeline", "id": "p"}) + "\n")
    monkeypatch.setenv("APP_SESSION_LEDGER_DIR", str(tmp_path))
    body = client().get("/api/infra/ledger").json()
    assert len(body["items"]) == 1
