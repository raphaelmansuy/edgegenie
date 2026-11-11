"""What `Orchestrator.create` leaves behind when it fails.

First principles: creating a session acquires resources in order — a journal row, a private token
folder, a tool-server process, an agent process. A failure at step N must release steps 1..N-1, or
every failed attempt costs a process until the app restarts. `resume()` already stopped its tool server
on failure; `create()` did not, so a user whose first message failed (as in the screenshot where the
journal rejected the write) left a tool server running per click on Send.
"""

from __future__ import annotations

import os

import pytest

from api.adapters.memory.store import MemoryEventStore
from api.config import Settings
from api.domain.session import SessionStatus
from api.main import build


class FlakyStore(MemoryEventStore):
    """The journal, failing the Nth write onwards."""

    def __init__(self, fail_from: int) -> None:
        super().__init__()
        self.writes = 0
        self.fail_from = fail_from

    async def commit(self, event, snapshot):
        self.writes += 1
        if self.writes >= self.fail_from:
            raise RuntimeError("the session journal (Lakebase) is not reachable; try again in a moment")
        return await super().commit(event, snapshot)


class RecordingTools:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []

    async def start(self, session_id, folder, schema, token_file=None, sp_token_file=None,
                    ledger_dir=None, write_mode="fenced") -> str:
        self.started.append(session_id)
        return "http://127.0.0.1:1/mcp"

    async def health(self, url):
        return 1

    async def stop(self, session_id):
        self.stopped.append(session_id)


def _orch(tmp_path, store, tools):
    app = build(Settings(agent_mode="fake", default_model="fake/model-a", allowed_models=["fake/model-a"],
                         dev_user="alice"))
    orch = app.state.orchestrator
    orch._store = store            # noqa: SLF001 - the seam under test is the journal
    orch._tools = tools            # noqa: SLF001
    os.environ["APP_AGENT_CWD"] = str(tmp_path)
    return orch


@pytest.fixture(autouse=True)
def _clean_env():
    before = os.environ.get("APP_AGENT_CWD")
    yield
    if before is None:
        os.environ.pop("APP_AGENT_CWD", None)
    else:
        os.environ["APP_AGENT_CWD"] = before


@pytest.mark.asyncio
async def test_a_journal_that_refuses_the_first_write_leaves_no_ghost_session(tmp_path):
    orch = _orch(tmp_path, FlakyStore(fail_from=1), RecordingTools())
    with pytest.raises(RuntimeError, match="not reachable"):
        await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
    assert orch.sessions_for("alice") == [], "a session that was never journaled must not be listed"


@pytest.mark.asyncio
async def test_a_failed_provision_stops_the_tool_server_it_started(tmp_path):
    """The journal accepts `session.created`, then fails: the tool server and agent just started go."""
    tools = RecordingTools()
    orch = _orch(tmp_path, FlakyStore(fail_from=2), tools)
    try:
        with pytest.raises(RuntimeError, match="not reachable"):
            await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
        assert tools.started and set(tools.started) == set(tools.stopped), (
            f"started {tools.started} but only stopped {tools.stopped}")
        listed = orch.sessions_for("alice")
        assert all(s.status is SessionStatus.FAILED for s in listed)
        for live in orch._live.values():     # noqa: SLF001
            assert live.handle is None, "the agent process of a failed session must be closed"
    finally:
        await orch.shutdown()


@pytest.mark.asyncio
async def test_the_original_failure_is_not_masked_by_a_second_one(tmp_path):
    """Recording `session.degraded` fails too when the journal is down; the caller must still see WHY."""
    class Boom(RecordingTools):
        async def start(self, *a, **k):
            raise ValueError("tool server refused to start")

    orch = _orch(tmp_path, FlakyStore(fail_from=2), Boom())
    with pytest.raises(ValueError, match="tool server refused"):
        await orch.create("alice", "/Users/alice/agent_scratch", "fake/model-a", None)
