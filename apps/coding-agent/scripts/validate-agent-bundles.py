"""Validate actual as-code handler output with the installed Databricks CLI; never deploy."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.adapters.databricks.handlers.job import JobHandler
from api.adapters.databricks.handlers.pipeline import PipelineHandler
from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
from api.adapters.fake.workspace import DemoWorkspace
from api.domain.asset import Actor, AssetRef
from api.domain.scope import Scope


async def main():
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config

    profile = os.environ.get("EXAM_DATABRICKS_PROFILE", "opengenie-dev")
    cfg = Config(profile=profile)
    assert cfg.host.rstrip("/") == "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
    me = WorkspaceClient(config=cfg).current_user.me()
    assert me.user_name == "raphael.mansuy@gmail.com"
    store = MemoryAgentLedgers()
    ws = DemoWorkspace(store)
    scope = Scope.for_session("bundlecheck", "/Users/" + me.user_name + "/agent_scratch", None)
    who = Actor(
        "bundlecheck",
        str(me.id),
        "t",
        scope,
        workspace=cfg.host,
        username=me.user_name,
        delegated=True,
        scopes=("workspace.workspace", "sql"),
    )
    http = AsyncMock()
    http.get.side_effect = AssertionError("As-code must not call native API")
    cases = [
        (
            "job",
            JobHandler(http, ws),
            {
                "name": "agent_bundle_job",
                "tasks": [
                    {"task_key": "verify", "notebook_task": {"notebook_path": scope.folder + "/source"}}
                ],
            },
        ),
        (
            "pipeline",
            PipelineHandler(http, ws),
            {
                "name": "agent_bundle_pipeline",
                "serverless": True,
                "libraries": [{"notebook": {"path": scope.folder + "/source"}}],
            },
        ),
    ]
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="agent014-bundles-") as root:
            for kind, handler, spec in cases:
                plan = await handler.plan(
                    AssetRef(kind, scope.folder + "/" + kind + "/databricks.yml"),
                    "",
                    [],
                    who,
                    content=json.dumps(spec),
                )
                folder = Path(root) / kind
                folder.mkdir()
                (folder / "databricks.yml").write_text(plan.after)
                command = subprocess.run(
                    ["databricks", "bundle", "validate", "--profile", profile, "--output", "json"],
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if command.returncode:
                    raise RuntimeError(kind + " bundle did not validate: " + command.stderr[:500])
                document = json.loads(command.stdout)
                assert kind + "s" in document["resources"]
                results.append(
                    {
                        "kind": kind,
                        "validated": True,
                        "definedNotDeployed": True,
                        "definitionAsset": plan.ref.to_dict(),
                        "warningCount": command.stderr.count("Warning:"),
                    }
                )
        output = {
            "pass": True,
            "identity": me.user_name,
            "workspace": cfg.host,
            "cases": results,
            "noDeployment": True,
            "nativeApiCallsByHandler": len(http.mock_calls),
        }
        destination = (
            Path(__file__).resolve().parents[3]
            / "specs/014-improve-agent/e2e/as-code-bundle-validation.json"
        )
        destination.write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output))
    finally:
        await store.close()


asyncio.run(main())
