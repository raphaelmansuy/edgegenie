import json
from dataclasses import replace
from unittest.mock import AsyncMock
import pytest
from api.domain.asset import Actor, AssetRef, WorkError, digest
from api.domain.asset_registry import AssetRegistry, Registration
from api.domain.scope import Scope
from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
from api.adapters.fake.workspace import DemoWorkspace
from api.adapters.databricks.handlers.workspace import WorkspaceHandler
from api.adapters.databricks.handlers.job import JobHandler
from api.adapters.databricks.handlers.pipeline import PipelineHandler
from api.services.changes import ChangeService
from api.services.work_events import WorkEvents
from api.domain.question import validate_schema, validate_content
from api.domain.policy.sql import mutation_parameters
from api.domain.sqlquery import SqlError


@pytest.fixture
async def rig():
    store = MemoryAgentLedgers()
    ws = DemoWorkspace(store)
    await ws.seed("/scratch")
    who = Actor(
        "session",
        "opaque-owner",
        "turn",
        Scope.for_session("session", "/scratch", "main.agent"),
        username="actual@example.test",
    )
    yield store, ws, who
    await store.close()


async def test_no_jobs_scope_writes_only_a_reviewed_bundle_file(rig):
    store, ws, who = rig
    who = replace(who, delegated=True, scopes=("sql", "workspace.workspace"))
    http = AsyncMock()
    http.get.side_effect = AssertionError("Native API must not be called")
    job = JobHandler(http, ws)
    files = WorkspaceHandler(ws, "file")
    registry = AssetRegistry(
        [
            Registration("job", "Jobs", "jobs", job, ""),
            Registration("file", "Files", "workspace.workspace", files, ""),
        ]
    )
    events = WorkEvents(store, AsyncMock())
    changes = ChangeService(registry, store, events, lambda sid, tid: who, lambda sid: "review")
    spec = {
        "name": "nightly_demo",
        "tasks": [{"task_key": "verify", "notebook_task": {"notebook_path": "/scratch/revenue"}}],
    }
    proposed = await changes.propose(
        "session",
        "turn",
        "inv",
        AssetRef("job", "/scratch/nightly/databricks.yml"),
        "",
        [],
        json.dumps(spec),
    )
    assert proposed["asset"]["kind"] == "file" and proposed["state"] == "awaiting_review"
    assert "not deployed" in proposed["reason"]
    with pytest.raises(LookupError):
        await ws.status("/scratch/nightly/databricks.yml", None)
    applied = await changes.decide("session", proposed["id"], "apply", "approved", "opaque-owner")
    text = (await ws.export_content("/scratch/nightly/databricks.yml", None, "SOURCE")).decode()
    bundle = json.loads(text)
    assert bundle["resources"]["jobs"]["nightly_demo"] == spec
    assert (
        applied["state"] == "applied"
        and (await store.page("resource"))["items"][0]["asset"]["kind"] == "file"
    )
    http.get.assert_not_called()


async def test_job_run_uses_username_and_argument_bound_idempotency(rig):
    store, ws, who = rig
    http = AsyncMock()
    job = JobHandler(http, ws)
    http.get.return_value = {
        "job_id": 1,
        "run_as_user_name": who.run_as,
        "settings": {"name": who.scope.job_prefix + "nightly"},
    }
    http.post.return_value = {"run_id": 99}
    result = await job.submit(AssetRef("job", "1"), {"parameters": {"day": "today"}}, who, "operation-key")
    assert result["nativeId"] == "99"
    body = http.post.call_args.args[2]
    assert body["idempotency_token"] == "operation-key" and body["job_parameters"] == {"day": "today"}
    http.get.return_value["run_as_user_name"] = "app-service-principal"
    with pytest.raises(PermissionError):
        await job.submit(AssetRef("job", "1"), {}, who, "other")
    assert http.post.await_count == 1


async def test_job_repair_refuses_successful_tasks(rig):
    store, ws, who = rig
    http = AsyncMock()
    job = JobHandler(http, ws)
    http.get.side_effect = [
        {
            "job_id": 1,
            "run_as_user_name": who.run_as,
            "settings": {"name": who.scope.job_prefix + "nightly"},
        },
        {"job_id": 1, "tasks": [{"task_key": "succeeded", "state": {"result_state": "SUCCESS"}}]},
    ]
    with pytest.raises(WorkError, match="only tasks observed as failed"):
        await job.submit(
            AssetRef("job", "1"),
            {"action": "repair", "run_id": 9, "rerun_tasks": ["succeeded"]},
            who,
            "key",
        )
    http.post.assert_not_awaited()


async def test_pipeline_uses_platform_conditional_write(rig):
    store, ws, who = rig
    http = AsyncMock()
    pipeline = PipelineHandler(http, ws)
    spec = {"name": who.scope.job_prefix + "pipeline", "libraries": []}
    http.get.return_value = {"spec": spec, "last_modified": 7, "run_as_user_name": who.run_as}
    current = await pipeline.read(AssetRef("pipeline", "id"), who)
    after = {**current.metadata, "continuous": False}
    plan = await pipeline.plan(current.ref, current.revision, [], who, content=json.dumps(after))
    await pipeline.apply(plan, who)
    body = http.request.call_args.kwargs["body"]
    assert body["expected_last_modified"] == 7 and body["run_as"] == {"user_name": who.run_as}
    assert "_last_modified" not in body
    assert pipeline.requires_review({"full_refresh": True})


@pytest.mark.parametrize("field", ["password", "api_key", "access_token", "private_key"])
def test_questions_never_collect_credentials(field):
    with pytest.raises(ValueError):
        validate_schema({"type": "object", "properties": {field: {"type": "string"}}})


def test_question_answer_is_typed_and_bound_to_the_schema():
    schema = {
        "type": "object",
        "properties": {
            "strategy": {"type": "string", "enum": ["small", "large"]},
            "count": {"type": "integer", "minimum": 1},
        },
        "required": ["strategy"],
    }
    assert validate_content(schema, {"strategy": "small", "count": 2})["count"] == 2
    for body in [
        {"strategy": "other"},
        {"strategy": "small", "count": True},
        {"strategy": "small", "extra": "injected"},
        {},
    ]:
        with pytest.raises(ValueError):
            validate_content(schema, body)


def test_mutating_sql_uses_shared_fence_and_shared_parameter_bindings():
    assert (
        mutation_parameters("SELECT :value", [{"name": "value", "type": "INT", "value": "42"}], schema="")[
            0
        ]["value"]
        == "42"
    )
    assert (
        mutation_parameters(
            "INSERT INTO main.agent.t VALUES (:value)",
            [{"name": "value", "type": "INT", "value": "42"}],
            schema="main.agent",
        )[0]["value"]
        == "42"
    )
    for source in [
        "DROP TABLE main.prod.t",
        "INSERT INTO main.agent.t VALUES (1)",
        "EXECUTE IMMEDIATE 'DROP TABLE main.agent.t'",
    ]:
        with pytest.raises(SqlError):
            mutation_parameters(source, [], schema="")


async def test_system_observation_describes_before_one_bounded_query_and_reports_lag(rig):
    from api.adapters.databricks.handlers.observations import SystemObservationHandler

    store, ws, who = rig
    catalog = AsyncMock()
    catalog.table.return_value = {
        "columns": [{"name": n} for n in ("run_id", "result_state", "period_start_time")]
    }
    catalog.run_sql.return_value = (
        {
            "status": {"state": "SUCCEEDED"},
            "manifest": {"schema": {"columns": [{"name": "run_id"}, {"name": "result_state"}]}},
            "result": {"data_array": [["42", "SUCCESS"]]},
        },
        "",
    )
    handler = SystemObservationHandler(catalog, "system.lakeflow.job_run_timeline", "run_id")
    observed = await handler.observe("42", who)
    catalog.table.assert_awaited_once_with("system.lakeflow.job_run_timeline", who.token)
    catalog.run_sql.assert_awaited_once()
    assert "LIMIT 26" in catalog.run_sql.call_args.args[0]
    assert observed["state"] == "succeeded" and observed["result"]["lag"] and observed["result"]["grain"]


async def test_system_observation_permission_error_is_not_an_empty_result(rig):
    from api.adapters.databricks.handlers.observations import SystemObservationHandler

    store, ws, who = rig
    catalog = AsyncMock()
    catalog.table.side_effect = PermissionError("not readable by you")
    handler = SystemObservationHandler(catalog, "system.billing.usage", "record_id")
    with pytest.raises(PermissionError, match="not readable"):
        await handler.find("", who, 25)
    catalog.run_sql.assert_not_awaited()


async def test_new_conflict_is_not_recorded_as_an_owner_rejection(rig):
    from api.services.agent_work import AgentWork

    store, ws, who = rig
    toolbox = AsyncMock()
    toolbox.proposal.return_value = {
        "id": "change",
        "state": "conflicted",
        "reason": "Read the base revision first.",
    }
    events = WorkEvents(store, AsyncMock())
    work = AgentWork(None, toolbox, None, None, None, None, store, events, lambda sid, tid: who)
    request = {
        "action": "db_dbx_edit",
        "input": {"kind": "notebook", "id": "/scratch/revenue", "ops": []},
        "approvalId": "approval",
    }
    with pytest.raises(WorkError):
        await work.native_proposal("session", "turn", request)
    assert "_recordedOutcome" not in request and "changeId" not in request


def test_edit_schema_teaches_required_base_and_exact_operation_fields():
    from api.services.toolbox import Toolbox
    from jsonschema import validate, ValidationError
    from types import SimpleNamespace

    caps = SimpleNamespace(
        rows=lambda sid: [{"kind": "notebook", "read": True, "change": True, "run": False}]
    )
    modes = SimpleNamespace(mode=lambda sid: "review")
    toolbox = Toolbox(None, None, None, None, None, modes, caps, None)
    schemas = {r["name"]: r["inputSchema"] for r in toolbox.catalogue("s")}
    good = {
        "kind": "notebook",
        "id": "/scratch/n",
        "base": "revision",
        "ops": [{"op": "replace_cell", "index": 37, "sha": "a" * 64, "source": "print(42)\n"}],
    }
    validate(good, schemas["dbx_edit"])
    for bad in (
        {k: v for k, v in good.items() if k != "base"},
        {
            **good,
            "ops": [{"op": "replace_cell", "cell_index": 37, "sha": "a" * 64, "source": "print(42)\n"}],
        },
    ):
        with pytest.raises(ValidationError):
            validate(bad, schemas["dbx_edit"])
    assert schemas["dbx_capabilities"]["properties"] == {}


async def test_query_cleanup_rechecks_owner_parent_and_revision(rig):
    from api.adapters.databricks.handlers.sql import QueryHandler
    store, ws, who = rig
    service = AsyncMock()
    source = {'text':'SELECT 42', 'modifiedAt':'rev-1', 'parent':'/scratch', 'name':'result', 'owner':who.run_as}
    service.source.return_value = source
    handler = QueryHandler(service)
    ref = AssetRef('query', '00000000-0000-4000-8000-000000000001')
    with pytest.raises(WorkError):
        await handler.remove(ref, 'stale', who)
    service.provider.delete.assert_not_awaited()
    for changed in ({'parent':'/outside'}, {'owner':'other@example.test'}):
        service.source.return_value = {**source, **changed}
        with pytest.raises(WorkError, match='moved outside'):
            await handler.remove(ref, 'rev-1', who)
    service.source.return_value = source
    await handler.remove(ref, 'rev-1', who)
    service.provider.delete.assert_awaited_once()


async def test_repair_has_its_own_native_identity_and_ignores_the_original_terminal_failure(rig):
    store, ws, who = rig
    http = AsyncMock()
    job = JobHandler(http, ws)
    http.get.side_effect = [
        {'job_id': 1, 'run_as_user_name': who.run_as, 'settings': {'name': who.scope.job_prefix + 'repair'}},
        {'job_id': 1, 'tasks': [{'task_key': 'bad', 'state': {'result_state': 'FAILED'}}]},
    ]
    http.post.return_value = {'repair_id': 12}
    submitted = await job.submit(AssetRef('job', '1'), {'action': 'repair', 'run_id': 9, 'rerun_tasks': ['bad']}, who, 'key')
    assert submitted['nativeId'] == '9:repair:12' and submitted['repairId'] == 12
    http.get.side_effect = None
    original = {'state': {'life_cycle_state': 'TERMINATED', 'result_state': 'FAILED'}, 'tasks': []}
    http.get.return_value = original
    assert (await job.observe(submitted['nativeId'], who))['state'] == 'running'
    http.get.return_value = {**original, 'repair_history': [{'id': 11, 'type': 'REPAIR', 'state': {'life_cycle_state': 'TERMINATED', 'result_state': 'FAILED'}}, {'id': 12, 'type': 'REPAIR', 'state': {'life_cycle_state': 'RUNNING'}}]}
    assert (await job.observe(submitted['nativeId'], who))['state'] == 'running'
    http.get.return_value['repair_history'][-1]['state'] = {'life_cycle_state': 'TERMINATED', 'result_state': 'SUCCESS'}
    settled = await job.observe(submitted['nativeId'], who)
    assert settled['state'] == 'succeeded' and settled['result']['repairId'] == '12'
    await job.cancel(submitted['nativeId'], who)
    assert http.post.call_args.args[2] == {'run_id': 9}


async def test_focused_notebook_read_returns_exact_raw_cell_sha_and_explicit_partial_scope(rig):
    from api.services.toolbox import Toolbox
    from api.domain.edits import cells
    store, ws, who = rig
    handler = WorkspaceHandler(ws, 'notebook')
    registry = AssetRegistry([Registration('notebook', 'Notebooks', '', handler, '')])
    toolbox = Toolbox(registry, store, None, None, None, None, None, lambda sid, tid: who)
    ref = AssetRef('notebook', '/scratch/revenue')
    before = await handler.read(ref, who)
    _, parts, _ = cells(before.content)
    result = await toolbox._execute('session', 'turn', 'dbx_read', {'kind':'notebook', 'id':ref.id, 'cell':37}, 'inv')
    assert result['revision'] == before.revision and result['text'] == parts[37]
    assert result['cellOnly'] and result['cell'] == 37 and result['totalCells'] == 60
    assert result['cells'] == [{'index':37, 'sha':digest(parts[37]), 'source':parts[37], 'truncated':False}]
    assert result['next_offset'] is None and len(json.dumps(result)) < len(before.content)
    with pytest.raises(WorkError, match='does not exist'):
        await toolbox._execute('session', 'turn', 'dbx_read', {'kind':'notebook', 'id':ref.id, 'cell':60}, 'inv')


def test_large_notebook_manifest_is_bounded_without_losing_full_cell_hashes():
    from api.domain.asset import AssetContent
    handler = WorkspaceHandler(None, 'notebook')
    raw = '\n# COMMAND ----------\n'.join('x' * 2500 for _ in range(1000))
    value = AssetContent(AssetRef('notebook', '/scratch/large'), 'rev', raw)
    manifest = handler.cell_index(value)
    assert len(manifest) == 100
    assert sum(len(r['source']) for r in manifest) == 6000
    assert manifest[0]['sha'] != digest(manifest[0]['source'])
    assert all(r['truncated'] for r in manifest)
    assert manifest[-1]['source'] == '' and len(manifest[-1]['sha']) == 64


async def test_catalogue_search_is_one_parameterized_capped_query_as_the_user(rig):
    from api.adapters.databricks.handlers.table import TableHandler

    _, _, who = rig
    catalog = AsyncMock()
    catalog.table.return_value = {"columns": [{"name": n} for n in ("table_catalog", "table_schema", "table_name")]}
    catalog.run_sql.return_value = ({"status": {"state": "SUCCEEDED"}, "result": {"data_array": [["c", "s", "one"], ["c", "s", "two"]]}}, "warehouse")
    hostile = "x\\'; DROP TABLE c.s.private; --%_"
    rows = await TableHandler(catalog).find(hostile, who, 1)
    catalog.table.assert_awaited_once_with("system.information_schema.tables", who.token)
    catalog.run_sql.assert_awaited_once()
    source, token = catalog.run_sql.call_args.args
    assert token == who.token and hostile not in source and "LIMIT 2" in source
    assert catalog.run_sql.call_args.kwargs["parameters"] == [{"name": "needle", "value": hostile.casefold(), "type": "STRING"}]
    assert rows == [{"kind": "table", "id": "c.s.one", "name": "one", "capped": True}]


async def test_system_record_identifier_is_bound_and_cannot_change_sql(rig):
    from api.adapters.databricks.handlers.observations import SystemObservationHandler

    _, _, who = rig
    catalog = AsyncMock()
    catalog.table.return_value = {"columns": [{"name": "run_id"}]}
    catalog.run_sql.return_value = ({"status": {"state": "SUCCEEDED"}, "result": {"data_array": []}}, "warehouse")
    hostile = "42\\'; SELECT * FROM private; --"
    await SystemObservationHandler(catalog, "system.lakeflow.job_run_timeline", "run_id").rows(who, hostile)
    assert hostile not in catalog.run_sql.call_args.args[0]
    assert catalog.run_sql.call_args.kwargs["parameters"] == [{"name": "record_id", "value": hostile, "type": "STRING"}]


async def test_new_asset_kind_is_attachable_without_another_kind_dispatch_implementation(rig):
    from api.domain.asset import AssetContent
    from api.domain.context import Attachment, ContextError, parse
    from api.services.context import RegistryContextReader, resolve

    _, _, who = rig
    handler = AsyncMock()
    handler.read.return_value = AssetContent(AssetRef("novel_asset", "owned-id"), "native-rev", "actual content")
    registry = AssetRegistry([Registration("novel_asset", "New kind", "test.scope", handler, "")])
    items = parse([{"kind": "novel_asset", "ref": "owned-id"}], asset_kinds=[entry.kind for entry in registry.entries()])
    result = await resolve(items, RegistryContextReader(registry, who))
    assert result[0].text == "actual content" and "native-rev" in result[0].note
    handler.read.assert_awaited_once_with(AssetRef("novel_asset", "owned-id"), who)
    with pytest.raises(ContextError):
        parse([{"kind": "novel_asset", "ref": "owned-id"}])
    with pytest.raises(ContextError):
        parse([{"kind": "novel_asset", "ref": "../outside"}], asset_kinds=["novel_asset"])


async def test_cell_attachment_uses_the_notebook_handler_and_preserves_stale_binding_notice(rig):
    from api.adapters.databricks.handlers.attachments import CellAttachmentReader
    from api.domain.asset import AssetContent
    from api.domain.context import Attachment

    _, _, who = rig
    notebook = AsyncMock()
    notebook.read.return_value = AssetContent(AssetRef("notebook", "/scratch/book"), "r", "# Databricks notebook source\nprint(1)\n\n# COMMAND ----------\n\nprint(2)\n", "PYTHON")
    result = await CellAttachmentReader(notebook).read(Attachment("cell", "/scratch/book#2", "old-sha"), who)
    notebook.read.assert_awaited_once_with(AssetRef("notebook", "/scratch/book"), who)
    assert "print(2)" in result.text and "print(1)" not in result.text
    assert "changed after the user selected it" in result.text and "one cell of 2" in result.note


def test_message_route_resolves_a_registered_kind_with_the_session_owner(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.config import Settings
    from api.domain.asset import AssetContent
    from api.main import build

    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    cfg = Settings(agent_mode="fake", tool_mode="none", allowed_models=["fake/model-a"],
                   default_model="fake/model-a", dev_user="alice", changes=True,
                   journal_v2=True, agent_workspace_demo=True,
                   session_db_path=str(tmp_path / "context.db"))
    with TestClient(build(cfg)) as client:
        sid = client.post("/api/sessions", json={"folder": "/Users/alice/agent_scratch"}).json()["id"]
        handler = AsyncMock()
        handler.read.return_value = AssetContent(AssetRef("novel_asset", "owned-id"), "observed-revision", "owner-only content")
        client.app.state.work.registry.register(Registration("novel_asset", "New kind", "test.scope", handler, ""))
        response = client.post(f"/api/sessions/{sid}/messages", json={"text": "Explain the attached content without tools or changes.", "attachments": [{"kind": "novel_asset", "ref": "owned-id"}]})
        assert response.status_code == 202
        turn = next(t for t in client.app.state.orchestrator.get(sid).state.turns if t.id == response.json()["turnId"])
        assert "owner-only content" in turn.context and "observed-revision" in turn.context
        handler.read.assert_awaited_once()
        assert handler.read.call_args.args[1].user_id == "alice"
        # Resolved private data stays out of the public session response.
        assert all("context" not in t for t in client.get(f"/api/sessions/{sid}").json()["turns"])
