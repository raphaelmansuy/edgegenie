"""The pipeline tools: the wire, the ledger fence, and the state that is easy to get wrong.

Two findings drive this file:

  * `F4` — there was ONE pipeline tool and it was a read, so "build me a pipeline" produced a job.
  * `F5` — the tool read the PIPELINE's `state`, which is `IDLE` both when a pipeline has never run and
    when its last update FAILED. The status tool therefore has to reach an update, not just the object.

The third subject is the fence. A pipeline id is a platform UUID with no session prefix, so a prefix rule
cannot exist; the rule is "did this conversation create it?". `[TOOL-6]` and `[RB-3]`.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"

PREFIXES = {
    "NBMCP_WRITE_PATHS": "/Users/me/agent_scratch/",
    "NBMCP_WRITE_SCHEMAS": "main.agent_scratch",
    "NBMCP_WRITE_JOB_PREFIX": "job-prefix-",
    "NBMCP_WRITE_INSTANCE_PREFIX": "inst-prefix-",
    "NBMCP_WRITE_APP_PREFIX": "app-prefix-",
    "NBMCP_WRITE_PIPELINE_PREFIX": "",
    "NBMCP_RUN_SESSION": "session-pipe",
}

PIPE = "f0e1c4a2-0000-11ee-be56-0242ac120002"
NOTEBOOKS = ["/Users/me/agent_scratch/sales/bronze", "/Users/me/agent_scratch/sales/silver"]


def load(monkeypatch, ledger: Path | None = None, **overrides):
    env = {**PREFIXES, **overrides}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if ledger is not None:
        monkeypatch.setenv("NBMCP_SESSION_LEDGER", str(ledger))
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_TOKEN", "t")
    monkeypatch.setenv("NBMCP_ALLOW_WRITES", "1")
    spec = importlib.util.spec_from_file_location(f"nbmcp_pipe_{os.urandom(4).hex()}", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wire:
    def __init__(self, answers: dict | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.answers = answers or {}

    def install(self, module):
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

        def fake_write(path, body=None):
            self.calls.append(("WRITE", path, body))
            return _answer(path)

        module._get = fake_get
        module._post = fake_write
        module._put = fake_write
        module._retry = lambda fn, **_kw: fn()
        return self

    def paths(self) -> list[str]:
        return [c[1] for c in self.calls]

    def body_for(self, fragment: str) -> dict:
        for method, path, body in self.calls:
            if fragment in path and body is not None:
                return body
        raise AssertionError(f"no body for {fragment}; calls were {self.paths()}")


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "ledger.jsonl"


# ---------------------------------------------------------------------------------------------
# F4: a pipeline can be created
# ---------------------------------------------------------------------------------------------
def test_create_sends_the_serverless_body(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    wire = Wire({"/pipelines": {"pipeline_id": PIPE, "state": "IDLE"}}).install(m)
    out = json.loads(m.dbx_create_pipeline("sales_medallion", notebooks=NOTEBOOKS,
                                           catalog="main", schema="sales"))
    body = wire.body_for("/pipelines")
    assert body["serverless"] is True
    assert body["edition"] == "ADVANCED"
    assert "clusters" not in body
    assert body["catalog"] == "main" and body["schema"] == "sales"
    assert out["created"] is True and out["pipeline_id"] == PIPE
    assert "dbx_start_pipeline" in out["next"]


def test_create_records_the_id_in_the_ledger(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    Wire({"/pipelines": {"pipeline_id": PIPE, "state": "IDLE"}}).install(m)
    m.dbx_create_pipeline("sales_medallion", notebooks=NOTEBOOKS, catalog="main", schema="sales")
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert rows == [{"kind": "pipeline", "id": PIPE, "name": "sales_medallion",
                     "created": rows[0]["created"]}]


def test_create_without_a_catalog_is_refused_locally_with_no_call(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    wire = Wire().install(m)
    out = json.loads(m.dbx_create_pipeline("sales_medallion", notebooks=NOTEBOOKS, catalog=""))
    assert wire.calls == []
    assert "Unity Catalog" in out["error"]
    assert out["nothing_was_created"] is True


def test_create_outside_the_write_fence_is_refused(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    wire = Wire().install(m)
    with pytest.raises(PermissionError):
        m.dbx_create_pipeline("x", notebooks=["/Shared/someone/x"], catalog="main", schema="s")
    assert wire.calls == []


def test_a_serverless_refusal_names_the_three_workspace_properties(monkeypatch, ledger):
    """[RB-8]: a `400` saying "serverless is not enabled" does not say which of three settings to change."""
    import httpx
    m = load(monkeypatch, ledger)
    request = httpx.Request("POST", "https://example.invalid/api/2.0/pipelines")
    refusal = httpx.HTTPStatusError(
        "bad", request=request,
        response=httpx.Response(400, text="Serverless is not enabled for this workspace",
                                request=request))
    Wire({"/pipelines": refusal}).install(m)
    out = json.loads(m.dbx_create_pipeline("x", notebooks=NOTEBOOKS, catalog="main", schema="s"))
    assert out["created"] is False
    assert "ADVANCED" in out["hint"] and "Unity Catalog" in out["hint"]


# ---------------------------------------------------------------------------------------------
# the ledger fence ([TOOL-6], [RB-3], [E-16])
# ---------------------------------------------------------------------------------------------
def test_a_pipeline_not_in_the_ledger_is_refused(monkeypatch, ledger):
    """The sentence matters: it must not read as a permission an admin could grant."""
    m = load(monkeypatch, ledger)
    Wire({}).install(m)
    with pytest.raises(PermissionError) as caught:
        m.dbx_start_pipeline(PIPE)
    message = str(caught.value)
    assert "this conversation" in message
    assert "Databricks" in message


def test_a_pipeline_in_the_ledger_is_accepted(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "sales"}) + "\n")
    wire = Wire({"/updates": {"update_id": "u1"}}).install(m)
    out = json.loads(m.dbx_start_pipeline(PIPE))
    assert out["started"] is True
    assert any("/updates" in p for p in wire.paths())


def test_the_ledger_survives_a_tool_server_restart(monkeypatch, ledger):
    """010's durable sessions make a tool-server restart routine. A ledger in process memory would forget
    which pipelines the conversation may stop — and the refusal would look like a permission problem."""
    first = load(monkeypatch, ledger)
    Wire({"/pipelines": {"pipeline_id": PIPE, "state": "IDLE"}}).install(first)
    first.dbx_create_pipeline("sales_medallion", notebooks=NOTEBOOKS, catalog="main", schema="sales")

    restarted = load(monkeypatch, ledger)      # a fresh module: no memory at all
    Wire({"/updates": {"update_id": "u1"}}).install(restarted)
    out = json.loads(restarted.dbx_start_pipeline(PIPE))
    assert out["started"] is True


def test_a_corrupt_ledger_does_not_refuse_work(monkeypatch, ledger):
    """A fence that fails closed on a corrupt file refuses work the user can see they did."""
    m = load(monkeypatch, ledger)
    ledger.write_text("{not json\n")
    assert m._ledger_read() == []


def test_a_pipeline_prefix_fences_when_one_is_configured(monkeypatch, ledger):
    """The ledger is the fallback; a real prefix, where a workspace can have one, outranks it."""
    m = load(monkeypatch, ledger, NBMCP_WRITE_PIPELINE_PREFIX="pipe-prefix-")
    Wire({"/updates": {"update_id": "u"}}).install(m)
    out = json.loads(m.dbx_start_pipeline("pipe-prefix-x"))
    assert out["started"] is True
    with pytest.raises(PermissionError):
        m.dbx_start_pipeline(PIPE)


# ---------------------------------------------------------------------------------------------
# F5 / [PIPE-5]: the status carries the UPDATE
# ---------------------------------------------------------------------------------------------
def test_status_carries_the_last_update_and_not_only_the_pipeline_state(monkeypatch, ledger):
    """THE finding: a pipeline with a FAILED last update reports `IDLE`, so the pipeline's state cannot
    answer 'did the last run work?'."""
    m = load(monkeypatch, ledger)
    Wire({
        f"/pipelines/{PIPE}/updates/": {"update": {"state": "FAILED"}},
        f"/pipelines/{PIPE}/updates": {"updates": [{"update_id": "u1", "state": "FAILED"}]},
        f"/pipelines/{PIPE}/events": {"events": [{"level": "ERROR", "message": "expectation failed"}]},
        f"/pipelines/{PIPE}": {"state": "IDLE", "spec": {"name": "sales", "serverless": True}},
    }).install(m)
    out = json.loads(m.dbx_pipeline_status(PIPE))
    assert out["state"] == "IDLE"
    assert out["lastUpdate"]["state"] == "FAILED"
    assert out["failureDetail"] == "expectation failed"


def test_a_pipeline_that_never_updated_reports_null_and_says_so(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    Wire({
        f"/pipelines/{PIPE}/updates": {"updates": []},
        f"/pipelines/{PIPE}/events": {"events": []},
        f"/pipelines/{PIPE}": {"state": "IDLE", "spec": {"name": "sales"}},
    }).install(m)
    out = json.loads(m.dbx_pipeline_status(PIPE))
    assert out["lastUpdate"] is None


def test_events_put_errors_first(monkeypatch, ledger):
    """A model reading 200 INFO lines spends its context on nothing ([06 §7], [PIPE-6])."""
    m = load(monkeypatch, ledger)
    Wire({
        f"/pipelines/{PIPE}/updates": {"updates": []},
        f"/pipelines/{PIPE}/events": {"events": [
            {"level": "INFO", "message": "started"},
            {"level": "ERROR", "message": "bad"},
        ]},
        f"/pipelines/{PIPE}": {"state": "IDLE", "spec": {}},
    }).install(m)
    out = json.loads(m.dbx_pipeline_status(PIPE))
    assert out["events"][0]["level"] == "ERROR"


def test_a_failed_update_with_no_error_event_says_that_rather_than_inventing_one(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    Wire({
        f"/pipelines/{PIPE}/updates": {"updates": [{"update_id": "u1", "state": "FAILED"}]},
        f"/pipelines/{PIPE}/events": {"events": []},
        f"/pipelines/{PIPE}": {"state": "IDLE", "spec": {}},
    }).install(m)
    out = json.loads(m.dbx_pipeline_status(PIPE))
    assert "no ERROR event" in out["failureDetail"]


# ---------------------------------------------------------------------------------------------
# starting, stopping, editing
# ---------------------------------------------------------------------------------------------
def test_start_sends_full_refresh_explicitly(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    wire = Wire({"/updates": {"update_id": "u1"}}).install(m)
    m.dbx_start_pipeline(PIPE)
    assert wire.body_for("/updates")["full_refresh"] is False


def test_validate_only_is_a_real_mode(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    wire = Wire({"/updates": {"update_id": "u1"}}).install(m)
    out = json.loads(m.dbx_start_pipeline(PIPE, validate_only=True))
    assert wire.body_for("/updates")["validate_only"] is True
    assert out["mode"] == "validated only"


def test_a_busy_pipeline_names_the_active_update(monkeypatch, ledger):
    """[E-7]: the platform refuses, and the refusal must point at the update to watch instead of inviting a
    retry."""
    import httpx
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    request = httpx.Request("POST", f"https://example.invalid/api/2.0/pipelines/{PIPE}/updates")
    busy = httpx.HTTPStatusError("busy", request=request,
                                 response=httpx.Response(400, text="update already active",
                                                         request=request))
    Wire({"/updates": busy}).install(m)
    m._active_update = lambda _id: "u-active"
    out = json.loads(m.dbx_start_pipeline(PIPE))
    assert out["started"] is False
    assert out["activeUpdate"] == "u-active"
    assert "watch it" in out["hint"]


def test_stop_with_nothing_active_is_refused_with_the_reason(monkeypatch, ledger):
    """[PIPE-4]: a Stop that always succeeds teaches a user the button did something."""
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    Wire({"/updates": {"updates": []}}).install(m)
    out = json.loads(m.dbx_stop_pipeline(PIPE))
    assert out["stopped"] is False
    assert "no update is active" in out["reason"]


def test_stop_says_cancellation_is_asynchronous(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    Wire({"/updates": {"updates": [{"update_id": "u1", "state": "RUNNING"}]}}).install(m)
    out = json.loads(m.dbx_stop_pipeline(PIPE))
    assert out["stopped"] is True
    assert "asynchronous" in out["note"]


def test_an_edit_names_the_libraries_it_removes(monkeypatch, ledger):
    """[E-18] A dropped library's tables stop being maintained."""
    m = load(monkeypatch, ledger)
    ledger.write_text(json.dumps({"kind": "pipeline", "id": PIPE, "name": "s"}) + "\n")
    Wire({
        f"/pipelines/{PIPE}": {"spec": {
            "name": "s", "catalog": "main", "schema": "sales", "serverless": True,
            "libraries": [{"notebook": {"path": "/Users/me/agent_scratch/sales/bronze"}},
                          {"notebook": {"path": "/Users/me/agent_scratch/sales/silver"}}],
        }},
    }).install(m)
    out = json.loads(m.dbx_pipeline_edit(PIPE, notebooks=["/Users/me/agent_scratch/sales/bronze"]))
    assert out["updated"] is True
    assert out["removed"] == ["/Users/me/agent_scratch/sales/silver"]
    assert "no longer be maintained" in out["warning"]


# ---------------------------------------------------------------------------------------------
# [E-17]: a name is not an id
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["sales_medallion", "my pipeline", ""])
def test_a_pipeline_name_is_refused_as_an_id_with_the_alternative(monkeypatch, ledger, bad):
    m = load(monkeypatch, ledger)
    Wire({}).install(m)
    with pytest.raises(ValueError) as caught:
        m._pipeline_id(bad)
    assert "dbx_list_pipelines" in str(caught.value) or "not a pipeline id" in str(caught.value)


def test_a_uuid_is_accepted(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    assert m._pipeline_id(PIPE) == PIPE


# ---------------------------------------------------------------------------------------------
# [TOOL-8]: the list
# ---------------------------------------------------------------------------------------------
def test_list_carries_the_last_update_state_and_null_when_absent(monkeypatch, ledger):
    m = load(monkeypatch, ledger)
    Wire({"/pipelines": {"statuses": [
        {"pipeline_id": "a", "name": "ran", "state": "IDLE",
         "latest_updates": [{"update_id": "u1", "state": "COMPLETED"}]},
        {"pipeline_id": "b", "name": "never", "state": "IDLE"},
    ]}}).install(m)
    rows = json.loads(m.dbx_list_pipelines())
    assert rows[0]["lastUpdate"]["state"] == "COMPLETED"
    assert rows[1]["lastUpdate"] is None
