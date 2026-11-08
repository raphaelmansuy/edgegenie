"""Contract tests: the fake and the real runtime must behave identically, and the mapper
must normalise ACP v1 and v2 into the same events."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from api.adapters.acp.mapper import (
    from_permission,
    from_update,
    model_options,
    turn_end_from_prompt_response,
    turn_end_from_state,
)
from api.adapters.acp.runtime import AcpAgentRuntime
from api.adapters.fake.agent import load_scenario
from api.adapters.memory.store import MemoryEventStore
from api.config import Settings
from api.domain.session import SessionStatus, TurnStatus
from api.ports import AgentCrashed, SessionSpec
from api.services.catalogue import SettingsModelCatalog
from api.services.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- mapper units
def test_thought_and_message_chunks_become_domain_events():
    [t] = from_update(
        "s", "t", {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "thinking"}}
    )
    assert t.type == "thought.delta" and t.payload["text"] == "thinking"
    [m] = from_update(
        "s", "t", {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hi"}}
    )
    assert m.type == "message.delta"


def test_tool_call_and_update_become_started_then_updated():
    [started] = from_update(
        "s",
        "t",
        {
            "sessionUpdate": "tool_call",
            "toolCallId": "c1",
            "title": "dbx_run_sql",
            "kind": "other",
            "rawInput": {},
        },
    )
    assert started.type == "tool_call.started" and started.payload["name"] == "dbx_run_sql"
    [done] = from_update(
        "s",
        "t",
        {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "c1",
            "status": "completed",
            "content": {"type": "text", "text": "3 rows"},
        },
    )
    assert done.payload["status"] == "completed" and done.payload["summary"] == "3 rows"


def test_tool_error_text_is_preserved():
    [ev] = from_update(
        "s",
        "t",
        {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "c9",
            "status": "error",
            "rawInput": {"error": "PERMISSION_DENIED: USE SCHEMA"},
        },
    )
    assert "PERMISSION_DENIED" in ev.payload["error"]


def test_unknown_update_is_ignored_not_fatal():
    assert from_update("s", "t", {"sessionUpdate": "brand_new_thing"}) == []


def test_permission_maps_all_four_option_kinds():
    ev = from_permission(
        "s",
        "t",
        {
            "title": "Write a table",
            "description": "the task needs a shared table",
            "subject": {"path": "workspace.default.t", "toolCallId": "c1"},
            "options": [
                {"optionId": "o1", "kind": "allow_once", "name": "Allow once"},
                {"optionId": "o2", "kind": "allow_always", "name": "Allow always"},
                {"optionId": "o3", "kind": "reject_once", "name": "Deny"},
                {"optionId": "o4", "kind": "reject_always", "name": "Never"},
            ],
        },
        "ap_1",
    )
    assert ev.type == "approval.requested"
    assert [o["kind"] for o in ev.payload["options"]] == [
        "allow_once",
        "allow_always",
        "reject_once",
        "reject_always",
    ]
    assert ev.payload["target"] == "workspace.default.t"


def test_v1_end_comes_from_the_prompt_response():
    end = turn_end_from_prompt_response({"stopReason": "end_turn", "usage": {"totalTokens": 11}})
    assert end.stop_reason == "end_turn" and end.usage["totalTokens"] == 11


def test_v2_end_comes_from_an_idle_state_update():
    assert turn_end_from_state({"sessionUpdate": "state_update", "state": "running"}) is None
    end = turn_end_from_state(
        {
            "sessionUpdate": "state_update",
            "state": "idle",
            "stopReason": "cancelled",
            "usage": {"totalTokens": 5},
        }
    )
    assert end and end.stop_reason == "cancelled"


def test_model_options_are_read_from_config_options():
    models, current = model_options(
        {
            "configOptions": [
                {
                    "id": "model",
                    "category": "model",
                    "currentValue": "a",
                    "options": [{"value": "a"}, {"value": "b"}],
                }
            ]
        }
    )
    assert models == ["a", "b"] and current == "a"


def test_stderr_tail_prefers_the_cause_over_a_truncated_object(tmp_path):
    """opencode logs a pretty-printed JSON object; the useful sentence is one field inside it."""
    from api.adapters.acp.runtime import AcpAgentRuntime
    import collections
    rt = AcpAgentRuntime(command="true")
    rt._stderr["s"] = collections.deque([
        "  code: -32603,", '  message: "Internal error: Bad Request: BAD_REQUEST: Sorry, cannot run '
        'or query foundation model endpoints because you have hit your free daily limit.",',
        "  data: {", '    errorName: "APIError",', "  }", "}",
        "timestamp=2026 level=ERROR run=ab message=process error=\"Bad Request\"",
    ], maxlen=50)
    tail = rt.stderr_tail("s")
    assert "free daily limit" in tail
    assert "errorName" not in tail


def test_no_model_selector_yields_empty():
    assert model_options({}) == ([], "")


# ---------------------------------------------------------------- real stdio runtime vs the fake agent
@pytest.fixture
def fake_cmd(tmp_path: Path, monkeypatch) -> str:
    """Run the fake ACP agent as a real child process, exactly like opencode acp."""
    return f"{sys.executable} -m api.adapters.fake.agent fixed:notebook"


async def _spec(tmp_path: Path) -> SessionSpec:
    return SessionSpec(session_id="s1", cwd=str(tmp_path), model="fake/model-a", mcp_url="")


async def test_real_runtime_speaks_to_the_fake_agent(fake_cmd, tmp_path):
    rt = AcpAgentRuntime(command=fake_cmd)
    env = {"PYTHONPATH": str(ROOT)}
    h = await rt.start(SessionSpec("s1", str(tmp_path), "fake/model-a", "", env=env))
    assert h.capabilities.agent == "FakeAgent"
    assert h.models == ["fake/model-a", "fake/model-b"]
    rt.set_turn("s1", "t1")
    await rt.prompt_in_background(h, "build the notebook")
    events, end = [], None
    async for item in rt.events(h):
        if isinstance(item, tuple):
            end = item
            break
        events.append(item)
    await rt.close(h)
    types = [e.type for e in events]
    assert "tool_call.started" in types and "tool_call.updated" in types and "message.delta" in types
    assert end[0] == "end" and end[1].stop_reason == "end_turn"


async def test_no_event_is_lost_when_the_end_signal_arrives_first(fake_cmd, tmp_path):
    """Regression: the reasoning chunk was dropped because a parked read was cancelled, and the
    tool/text updates that arrived before the prompt response were never drained."""
    rt = AcpAgentRuntime(command=fake_cmd)
    h = await rt.start(SessionSpec("s1", str(tmp_path), "fake/model-a", "", env={"PYTHONPATH": str(ROOT)}))
    rt.set_turn("s1", "t1")
    await rt.prompt_in_background(h, "go")
    seen: list[str] = []
    async for item in rt.events(h):
        if isinstance(item, tuple):
            break
        seen.append(item.type)
    await rt.close(h)
    assert "thought.delta" in seen, f"the reasoning trace was lost: {seen}"
    # Reasoning precedes the answer. "first of all" was over-specified: the tool-start update and
    # the thought are two notifications, and which one is read first is up to the event loop.
    assert seen.index("thought.delta") < seen.index("message.delta")
    assert "tool_call.started" in seen and "message.delta" in seen


async def test_model_switch_uses_the_bare_string_shape(fake_cmd, tmp_path):
    """Verified defect RB-10: the documented union is rejected; the primitive must work."""
    rt = AcpAgentRuntime(command=fake_cmd)
    h = await rt.start(SessionSpec("s1", str(tmp_path), "fake/model-a", "", env={"PYTHONPATH": str(ROOT)}))
    await rt.set_model(h, "fake/model-b")
    await rt.close(h)


async def test_a_chatty_agent_on_stderr_does_not_deadlock(tmp_path):
    """Regression: stderr was piped and never read, so an agent that logs filled the pipe buffer
    and blocked forever. A real opencode session hung with no error at all."""
    import textwrap
    chatty = tmp_path / "chatty.py"
    chatty.write_text(textwrap.dedent("""
        import json, sys
        for _ in range(4000):
            sys.stderr.write("noise " * 40 + "\\n")
        sys.stderr.flush()
        for line in sys.stdin:
            msg = json.loads(line)
            if msg.get("method") == "initialize":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {
                    "protocolVersion": 1, "agentInfo": {"name": "Chatty", "version": "1"},
                    "agentCapabilities": {}}}), flush=True)
            elif msg.get("method") == "session/new":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                  "result": {"sessionId": "s"}}), flush=True)
    """))
    rt = AcpAgentRuntime(command=f"{sys.executable} {chatty}")
    h = await asyncio.wait_for(rt.start(SessionSpec("s1", str(tmp_path), "m", "")), timeout=20)
    assert h.capabilities.agent == "Chatty"
    await rt.close(h)


async def test_a_turn_with_no_events_fails_instead_of_hanging(tmp_path):
    """Regression: when the model endpoint returns 403, opencode logs to stderr and never ends the
    ACP turn, so the UI showed "working" forever. The adapter now has an idle guard."""
    import textwrap
    mute = tmp_path / "mute.py"
    mute.write_text(textwrap.dedent("""
        import json, sys, time
        for line in sys.stdin:
            msg = json.loads(line)
            if msg.get("method") == "initialize":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {
                    "protocolVersion": 1, "agentInfo": {"name": "Mute", "version": "1"},
                    "agentCapabilities": {}}}), flush=True)
            elif msg.get("method") == "session/new":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                  "result": {"sessionId": "s"}}), flush=True)
            elif msg.get("method") == "session/prompt":
                sys.stderr.write("Error: free daily limit\\n"); sys.stderr.flush()
                time.sleep(30)          # never answers
    """))
    import api.adapters.acp.runtime as rt_mod
    old = rt_mod.IDLE_TURN_TIMEOUT
    rt_mod.IDLE_TURN_TIMEOUT = 1.0
    try:
        rt = AcpAgentRuntime(command=f"{sys.executable} {mute}")
        h = await rt.start(SessionSpec("s1", str(tmp_path), "m", ""))
        rt.set_turn("s1", "t1")
        await rt.prompt_in_background(h, "hello")
        end = None
        async for item in rt.events(h):
            if isinstance(item, tuple):
                end = item
                break
        assert end and end[0] == "error"
        assert "the model or agent failed" in end[1]
        assert "free daily limit" in end[1], "the agent's stderr must reach the error"
        await rt.close(h)
    finally:
        rt_mod.IDLE_TURN_TIMEOUT = old


async def test_the_end_signal_is_not_swallowed_by_a_cancelled_waiter(tmp_path):
    """Regression: the `ends.get()` waiter was recreated every iteration, so a cancelled one could
    consume the end signal and the turn never finished. A real prompt answered but stayed 'running'."""
    import textwrap
    slow = tmp_path / "slow_end.py"
    slow.write_text(textwrap.dedent("""
        import json, sys
        for line in sys.stdin:
            msg = json.loads(line)
            m = msg.get("method")
            if m == "initialize":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {
                    "protocolVersion": 1, "agentInfo": {"name": "Slow", "version": "1"},
                    "agentCapabilities": {}}}), flush=True)
            elif m == "session/new":
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                  "result": {"sessionId": "s"}}), flush=True)
            elif m == "session/prompt":
                for i in range(6):          # updates first, then the response: the order that broke it
                    print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {
                        "sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk",
                                                     "content": {"type": "text", "text": f"p{i}"}}}}),
                          flush=True)
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                  "result": {"stopReason": "end_turn", "usage": {"totalTokens": 7}}}),
                      flush=True)
    """))
    rt = AcpAgentRuntime(command=f"{sys.executable} {slow}")
    h = await rt.start(SessionSpec("s1", str(tmp_path), "m", ""))
    rt.set_turn("s1", "t1")
    await rt.prompt_in_background(h, "go")

    async def drain():
        types, end = [], None
        async for item in rt.events(h):
            if isinstance(item, tuple):
                end = item
                break
            types.append(item.type)
        return types, end

    types, end = await asyncio.wait_for(drain(), timeout=15)
    await rt.close(h)
    assert end is not None, "the turn never ended: the end signal was lost"
    assert end[0] == "end" and end[1].stop_reason == "end_turn"
    assert types.count("message.delta") == 6, f"updates were lost: {types}"


async def test_agent_that_cannot_start_raises_a_typed_error(tmp_path):
    rt = AcpAgentRuntime(command="/nonexistent/agent")
    with pytest.raises(AgentCrashed):
        await rt.start(await _spec(tmp_path))


# ---------------------------------------------------------------- orchestrator end to end (fake agent)
async def _orchestrator(tmp_path: Path, scenario: str = "notebook", delay: float = 0.0) -> Orchestrator:
    """scenario is pinned with `fixed:` so a test never depends on prompt-based selection."""
    from api.adapters.mcp.registry import NullToolRegistry

    rt = AcpAgentRuntime(command=f"{sys.executable} -m api.adapters.fake.agent fixed:{scenario} {delay}")
    cfg = Settings(allowed_models=["fake/model-a", "fake/model-b"], default_model="fake/model-a")
    models = SettingsModelCatalog(cfg)
    rt._extra_env = {"PYTHONPATH": str(ROOT)}  # noqa: SLF001
    return Orchestrator(rt, NullToolRegistry(), MemoryEventStore(), models, demo=True)


async def _wait(live, *, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if live.task and live.task.done():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("turn did not finish")


async def test_events_are_stored_under_our_session_id_not_the_agents(tmp_path):
    """Regression: events were attributed to the agent's session id, so the UI stream was empty."""
    orch = await _orchestrator(tmp_path)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    await orch.submit(s.id, "Build a notebook with trips by hour, run it, and exit with the hour count.")
    await _wait(live)
    rows = await orch._store.since(s.id, 0)  # noqa: SLF001
    types = [r["type"] for r in rows]
    assert "tool_call.started" in types and "message.delta" in types
    assert all(r["sessionId"] == s.id for r in rows)


async def test_a_turn_completes_with_verified_evidence(tmp_path):
    orch = await _orchestrator(tmp_path)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    assert s.status is SessionStatus.READY
    live = orch.get(s.id)
    await orch.submit(s.id, "Build a notebook with trips by hour, run it, and exit with the hour count.")
    await _wait(live)
    turn = live.state.turns[0]
    assert turn.status is TurnStatus.COMPLETED, turn.error
    rows = [r for r in await orch._store.since(s.id, 0) if r["type"] == "evidence.proposed"]  # noqa: SLF001
    assert rows and rows[0]["rows"][0]["verified"] is True


async def test_blocked_turn_is_reported_not_dressed_up(tmp_path):
    orch = await _orchestrator(tmp_path, "blocked")
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    await orch.submit(s.id, "Read samples.nyctaxi.trips and count the rows.")
    await _wait(live)
    assert live.state.turns[0].status is TurnStatus.BLOCKED


async def test_cancel_marks_the_turn_cancelled_and_keeps_the_partial(tmp_path):
    orch = await _orchestrator(tmp_path, "slow", delay=0.05)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    await orch.submit(s.id, "Do a lot of work.")
    await asyncio.sleep(0.35)
    await orch.cancel(s.id)
    await _wait(live)
    assert live.state.turns[0].status is TurnStatus.CANCELLED


async def test_a_second_message_is_queued_not_interleaved(tmp_path):
    orch = await _orchestrator(tmp_path, "slow", delay=0.05)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    first = await orch.submit(s.id, "First long task.")
    second = await orch.submit(s.id, "Second task.")
    assert second.status is TurnStatus.QUEUED and "after turn 1" in second.queued_reason
    await orch.cancel(s.id)
    await _wait(live)
    assert first.id != second.id


async def test_a_queued_turn_runs_after_the_running_one_ends(tmp_path):
    """Regression: a second message stayed 'queued' for ever because nothing started it after the
    first turn reached a terminal state."""
    orch = await _orchestrator(tmp_path, "notebook", delay=0.02)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    await orch.submit(s.id, "First task: build a notebook.")
    second = await orch.submit(s.id, "Second task: build another notebook.")
    assert second.status is TurnStatus.QUEUED

    # Wait for the FIRST turn to finish, then for the second one to leave QUEUED.
    for _ in range(400):
        first_done = live.state.turns[0].status.value in ("completed", "blocked", "failed", "cancelled")
        if first_done and live.state.turns[1].status is not TurnStatus.QUEUED:
            break
        await asyncio.sleep(0.05)
    assert live.state.turns[0].status.value in ("completed", "blocked", "failed", "cancelled")
    assert live.state.turns[1].status is not TurnStatus.QUEUED, (
        f"the queued turn never started: {live.state.turns[1].status}; "
        f"states={[(t.index, t.status.value) for t in live.state.turns]}")


async def test_model_switch_is_reflected_in_the_session(tmp_path):
    orch = await _orchestrator(tmp_path)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    await orch.set_model(s.id, "fake/model-b")
    assert orch.get(s.id).state.session.model == "fake/model-b"


async def test_disallowed_model_is_refused(tmp_path):
    orch = await _orchestrator(tmp_path)
    with pytest.raises(ValueError):
        await orch.create("u", str(tmp_path), "openai/gpt-5", None)


async def test_sessions_are_scoped_to_their_owner(tmp_path):
    orch = await _orchestrator(tmp_path)
    s = await orch.create("alice", str(tmp_path), "fake/model-a", None)
    assert [x.id for x in orch.sessions_for("alice")] == [s.id]
    assert orch.sessions_for("bob") == []


async def test_demo_agent_picks_its_behaviour_from_the_prompt(tmp_path):
    """One demo server must be able to show every state, so the scenario follows the request."""
    from api.adapters.fake.agent import ScenarioAgent

    a = ScenarioAgent("notebook")
    a.pick("s1", "Document the tables in my schema.")
    assert [
        u.get("toolCallId")
        for u in a.scenario_for("s1")["turn"]["updates"]
        if u.get("sessionUpdate") == "tool_call"
    ] == ["i1", "i2"]
    a.pick("s2", "Build a notebook with revenue by month.")
    assert "notebook" in a.scenario_for("s2")["turn"]["answer"].lower()


async def test_scenario_fixtures_are_valid_json():
    for name in ("notebook", "blocked", "injection", "slow", "permission"):
        assert load_scenario(name)["turn"]["answer"]


async def test_a_demo_hint_picks_the_scenario_but_is_never_stored(tmp_path):
    """The start cards send `[[scenario:x]]` to choose a behaviour. Stripping it from the STORED prompt
    is right; stripping it from the prompt the reference agent receives made every card play the same
    notebook, so "investigate a number" answered with one. Both halves must hold."""
    orch = await _orchestrator(tmp_path)
    s = await orch.create("u", str(tmp_path), "fake/model-a", None)
    live = orch.get(s.id)
    await orch.submit(s.id, "Investigate why revenue dropped. [[scenario:blocked]]")
    await _wait(live, timeout=20)
    turn = live.state.turns[0]
    assert "scenario:" not in turn.prompt                     # the user's words are clean
    # …and the hint still reached the agent, so the blocked behaviour is the one that played.
    assert turn.status is TurnStatus.BLOCKED
