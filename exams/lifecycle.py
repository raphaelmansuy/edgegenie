"""Bounded native lifecycle helpers shared by the spec 014 qualification missions."""

import time
import sys
from pathlib import Path
from lib import api, export_nb, import_nb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/coding-agent"))
from api.domain.policy.paths import normalize


def wait_for(read, terminal, timeout=720):
    deadline = time.monotonic() + timeout
    while True:
        row = read()
        if terminal(row):
            return row
        if time.monotonic() >= deadline:
            raise TimeoutError("Native fixture did not settle; it was not resubmitted")
        time.sleep(3)


def job_run(run_id):
    return api(
        "GET",
        "/api/2.1/jobs/runs/get",
        params={"run_id": run_id, "include_history": True},
    )


def wait_job(run_id):
    return wait_for(
        lambda: job_run(run_id),
        lambda r: (
            r["state"]["life_cycle_state"]
            in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
        ),
    )


def replace_fixture(path, before, after):
    if export_nb(path) != before:
        raise RuntimeError("The isolated fixture changed; refusing to overwrite it")
    import_nb(path, after)


def queries():
    token = ""
    for _ in range(100):
        page = api(
            "GET",
            "/api/2.0/sql/queries",
            params={"page_size": 100, **({"page_token": token} if token else {})},
        )
        yield from page.get("results", [])
        token = page.get("next_page_token", "")
        if not token:
            return
    raise RuntimeError(
        "Query enumeration exceeded the qualification cap; results are incomplete"
    )


def delete_owned_query(query_id, parent):
    row = api("GET", "/api/2.0/sql/queries/" + query_id, ok_404=True)
    if row is None or row.get("lifecycle_state") == "TRASHED":
        return
    from lib import USER

    if row.get("owner_user_name") != USER or normalize(
        row.get("parent_path", "")
    ) != normalize(parent):
        raise RuntimeError("Query cleanup refused: owner or isolated parent changed")
    api("DELETE", "/api/2.0/sql/queries/" + query_id)


def reference_cleanup(ctx, source):
    """Run the real change/resource services against the isolated native workspace fixture."""
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/coding-agent"))
    from lib import HOST, TOKEN, USER
    from api.adapters.databricks.http import DbxHttp
    from api.adapters.databricks.workspace import WorkspaceBrowser
    from api.adapters.databricks.handlers.workspace import WorkspaceHandler
    from api.adapters.durable.agent_ledgers import MemoryAgentLedgers
    from api.domain.asset import Actor, AssetRef
    from api.domain.asset_registry import AssetRegistry, Registration
    from api.domain.scope import Scope
    from api.services.changes import ChangeService
    from api.services.agent_work import AgentWork
    from api.services.work_events import WorkEvents

    async def run():
        store = MemoryAgentLedgers()
        http = DbxHttp(HOST, lambda: None)
        ws = WorkspaceBrowser(HOST, lambda: None, http)
        registry = AssetRegistry(
            [
                Registration(
                    "notebook", "Notebooks", "", WorkspaceHandler(ws, "notebook"), ""
                )
            ]
        )
        who = Actor(
            ctx.run_id,
            USER,
            "reference",
            Scope.for_session(ctx.run_id, ctx.home, None),
            token=TOKEN,
            username=USER,
        )
        actor = lambda sid, tid: who

        async def emit(event):
            pass

        events = WorkEvents(store, emit)
        changes = ChangeService(registry, store, events, actor, lambda sid: "review")
        work = AgentWork(
            None, None, changes, None, None, registry, store, events, actor
        )
        try:
            proposal = await changes.propose(
                ctx.run_id,
                "reference",
                "",
                AssetRef("notebook", ctx.home + "/temporary"),
                "",
                [],
                content=source,
            )
            applied = await changes.decide(
                ctx.run_id, proposal["id"], "apply", "reference-reviewed-create", USER
            )
            if applied["state"] != "applied":
                raise RuntimeError("Reference create did not apply")
            resources = (await store.page("resource", session_id=ctx.run_id))["items"]
            if len(resources) != 1:
                raise RuntimeError("Reference create did not record one resource")
            rid = resources[0]["id"]
            await work.propose_cleanup(ctx.run_id, rid)
            await work.cleanup(ctx.run_id, rid, True)
            ctx.extra["resourceReceipt"] = (
                await store.page("resource", session_id=ctx.run_id)
            )["items"]
        finally:
            await http.close()
            await store.close()

    asyncio.run(run())
