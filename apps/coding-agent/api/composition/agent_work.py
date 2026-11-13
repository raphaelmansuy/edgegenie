"""Composition root for the optional agent-work subsystem. All implementation selection lives here."""

import os
from pathlib import Path
from dataclasses import replace
from ..adapters.mcp.skills import BundledSkills
from ..adapters.durable.agent_ledgers import SqliteAgentLedgers
from ..adapters.durable.agent_postgres import PostgresAgentLedgers
from ..adapters.databricks.handlers.workspace import WorkspaceHandler
from ..adapters.databricks.handlers.notebook import NotebookHandler
from ..adapters.fake.notebook import DemoNotebookHandler
from ..adapters.databricks.handlers.sql import StatementHandler, QueryHandler
from ..adapters.databricks.handlers.table import TableHandler
from ..adapters.databricks.handlers.job import JobHandler
from ..adapters.databricks.handlers.pipeline import PipelineHandler
from ..adapters.databricks.handlers.app import AppHandler
from ..adapters.databricks.app_logs import DatabricksAppLogs
from ..adapters.databricks.handlers.instance import InstanceHandler
from ..adapters.databricks.handlers.run import RunHandler
from ..adapters.databricks.handlers.observations import SystemObservationHandler
from ..adapters.databricks.http import DbxHttp
from ..adapters.fake.workspace import DemoWorkspace
from ..domain.asset_registry import AssetRegistry, Registration
from ..services.work_events import WorkEvents
from ..services.work_sessions import WorkSessions
from ..services.changes import ChangeService
from ..services.operations import OperationService
from ..services.capabilities import CapabilityService
from ..services.toolbox import Toolbox
from ..services.agent_work import AgentWork
from ..services.work_preferences import WorkPreferences


def build_work(cfg, orch, journal, workspace, catalog, sql):
    if cfg.agent_ascode_demo and not cfg.agent_workspace_demo:
        raise ValueError("The as-code fixture requires the deterministic workspace fixture.")

    def actor(sid, tid=""):
        who = orch.actor(sid, tid)
        return replace(who, delegated=True, scopes=()) if cfg.agent_ascode_demo else who

    orch.delegated_by_default = cfg.production
    key = cfg.agent_key or cfg.llm_kek or os.environ.get("LLM_KEK", "")
    store = (
        PostgresAgentLedgers(journal, key)
        if cfg.session_database_url or cfg.session_use_lakebase
        else SqliteAgentLedgers(
            cfg.agent_db_path or (cfg.session_db_path + ".agent" if cfg.session_db_path else ""),
            key,
            cfg.production,
            journal=journal,
        )
    )
    ws = DemoWorkspace(store) if cfg.agent_workspace_demo else workspace
    http = DbxHttp(os.environ.get("DATABRICKS_HOST", ""), lambda: None, max_response_bytes=4 * 1024 * 1024)
    notebook = DemoNotebookHandler(ws, store) if cfg.agent_workspace_demo else NotebookHandler(ws, http)
    table = TableHandler(catalog, sql)
    registry = AssetRegistry(
        [
            Registration(
                "notebook",
                "Notebooks",
                "workspace.workspace",
                notebook,
                "Notebook cells, revisions and reviewed changes.",
            ),
            Registration(
                "file",
                "Files",
                "workspace.workspace",
                WorkspaceHandler(ws, "file"),
                "Workspace source files and reviewed range edits.",
            ),
            Registration(
                "statement",
                "SQL statements",
                "sql",
                StatementHandler(sql, table),
                "SQL execution through the shared query service.",
            ),
            Registration(
                "query",
                "Queries",
                "sql",
                QueryHandler(sql, resources=table),
                "Saved Queries, reviewed copies and SQL execution.",
            ),
            Registration(
                "query-draft",
                "Query drafts",
                "sql",
                QueryHandler(sql, "query-draft", resources=table),
                "Private query drafts.",
            ),
            Registration(
                "table",
                "Tables",
                "catalog.tables:read",
                table,
                "Schema grounding and one bounded catalogue query.",
            ),
        ]
    )
    if cfg.assets and (not cfg.agent_workspace_demo or cfg.agent_ascode_demo):
        registry.register(
            Registration(
                "job",
                "Jobs",
                "jobs",
                JobHandler(
                    http,
                    ws,
                    SystemObservationHandler(catalog, "system.lakeflow.job_run_timeline", "run_id"),
                ),
                "Native Jobs or reviewed bundle definitions.",
            )
        )
        registry.register(
            Registration(
                "pipeline",
                "Pipelines",
                "pipelines",
                PipelineHandler(
                    http,
                    ws,
                    SystemObservationHandler(
                        catalog, "system.lakeflow.pipeline_update_timeline", "update_id"
                    ),
                ),
                "Conditional pipeline changes or reviewed bundle definitions.",
            )
        )
        registry.register(
            Registration(
                "app",
                "Apps",
                "apps",
                AppHandler(http, ws, logs=DatabricksAppLogs()),
                "Reviewed app definitions, deployments and bounded logs as you.",
            )
        )
        registry.register(
            Registration(
                "instance",
                "Instances",
                "postgres",
                InstanceHandler(http, ws),
                "Reviewed Lakebase instance definitions and readiness.",
            )
        )
        registry.register(
            Registration(
                "job_run",
                "Job runs",
                "sql",
                RunHandler(
                    registry.handler("job"),
                    SystemObservationHandler(catalog, "system.lakeflow.job_run_timeline", "run_id"),
                ),
                "Native or lagged system-table job run observations.",
            )
        )
        registry.register(
            Registration(
                "pipeline_update",
                "Pipeline updates",
                "sql",
                RunHandler(
                    registry.handler("pipeline"),
                    SystemObservationHandler(
                        catalog, "system.lakeflow.pipeline_update_timeline", "update_id"
                    ),
                ),
                "Native or lagged system-table pipeline update observations.",
            )
        )
    if cfg.assets and not cfg.agent_workspace_demo:
        for kind, label, table, identifier in (
            ("job_task_run", "Job task results", "system.lakeflow.job_task_run_timeline", "run_id"),
            ("lineage", "Table lineage", "system.access.table_lineage", "target_table_full_name"),
            ("column_lineage", "Column lineage", "system.access.column_lineage", "target_table_full_name"),
            ("compute_usage", "Compute usage", "system.billing.usage", "record_id"),
            ("query_history", "Query history", "system.query.history", "statement_id"),
        ):
            if kind in cfg.asset_kinds:
                registry.register(
                    Registration(
                        kind,
                        label,
                        "sql",
                        SystemObservationHandler(catalog, table, identifier, kind=kind),
                        "Read-only system-table records with explicit grain, refresh time and lag.",
                    )
                )
    for entry in registry.entries():
        if (
            entry.kind in {"job", "pipeline", "app", "instance", "job_run", "pipeline_update"}
            and entry.kind not in cfg.asset_kinds
        ):
            registry.unregister(entry.kind)
    events = WorkEvents(store, orch.record_event)
    capabilities = CapabilityService(registry, store, events, actor, operations=cfg.operations)
    sessions = WorkSessions(
        store,
        events,
        capabilities,
        actor,
        token_ceiling=cfg.agent_token_ceiling,
        money_ceiling=cfg.agent_money_ceiling,
        max_pass_cost=cfg.agent_max_pass_cost,
    )
    changes = ChangeService(
        registry,
        store,
        events,
        actor,
        sessions.mode,
        can_run=lambda sid, kind: capabilities.allows(sid, kind, "run"),
    )
    operations = OperationService(
        registry,
        store,
        events,
        actor,
        orch.wake_operation,
        interval=cfg.agent_poll_seconds,
        on_denial=capabilities.downgrade,
        concurrency=cfg.agent_native_concurrency,
    )
    preferences = WorkPreferences(
        registry.handler("file"), BundledSkills(Path(__file__).resolve().parents[2] / "tools/skills")
    )
    toolbox = Toolbox(
        registry, store, events, changes, operations, sessions, capabilities, actor, skills=preferences
    )
    work = AgentWork(sessions, toolbox, changes, operations, capabilities, registry, store, events, actor)
    work.workspace = ws
    work.evidence_enabled = cfg.evidence_v2
    work.preferences = preferences
    work.close_adapters = [http.close]
    return work
