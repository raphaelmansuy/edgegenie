"""G-1: the agent's own file and shell tools, and the two layers that keep them off.

The gap, stated precisely: an ACP agent ships tools that operate on the machine it runs on — a shell,
a file reader, a globber. Inside the app that machine is the container, which holds the user's token in
a `0600` file. A shell would read it. So the app has to make sure those tools cannot be reached, and a
claim that it does is worth exactly as much as the test behind it. There were none.

There are **two independent layers**, and this file asserts both, because either one alone is a single
mistake away from being the only one:

  1. **The config.** `opencode.json` sets `permission: {bash: deny, edit: deny, read: deny, …}`. The
     agent is told not to offer them. This is the layer that is easy to see and easy to regress.
  2. **The protocol handshake.** The ACP `initialize` request declares
     `clientCapabilities: {fs: {readTextFile: false, writeTextFile: false}, terminal: false}`. The
     agent is told the *client* cannot serve a file or a terminal, so a tool that asked would be
     asking a client that has none. This layer survives a config the agent ignores.

Layer 2 is the one that matters, because layer 1 is an instruction to a model and the whole design
assumes a model can be talked out of its instructions.
"""
from __future__ import annotations

import json
from pathlib import Path

from api.adapters.acp import agent_config
from api.adapters.acp.runtime import CLIENT_INFO

APP = Path(__file__).resolve().parents[1]


# =============================================================== layer 1: the config file

DANGEROUS = {"bash", "edit", "read", "glob", "grep", "list", "external_directory", "webfetch", "websearch", "future_builtin"}


def test_every_builtin_tool_that_touches_the_machine_is_denied(tmp_path):
    cfg = agent_config.AgentConfig.from_resolved(_resolved(), host="https://example.invalid")
    permissions = json.loads(cfg.write(tmp_path, session_rules="").read_text())["permission"]
    assert permissions["*"] == "deny"
    for tool in DANGEROUS:
        assert permissions.get(tool, permissions["*"]) == "deny"


def test_the_config_file_actually_carries_the_denials(tmp_path):
    cfg = agent_config.AgentConfig.from_resolved(_resolved(), host="https://example.invalid")
    permissions = json.loads(cfg.write(tmp_path, session_rules="").read_text())["permission"]
    assert permissions["*"] == "deny"
    assert permissions["todowrite"] == "allow"


def test_network_fetch_tools_are_denied(tmp_path):
    cfg = agent_config.AgentConfig.from_resolved(_resolved(), host="https://example.invalid")
    permissions = json.loads(cfg.write(tmp_path, session_rules="").read_text())["permission"]
    for tool in ("webfetch", "websearch"):
        assert permissions.get(tool, permissions["*"]) == "deny"


# =============================================================== layer 2: the protocol

def test_the_acp_handshake_declares_no_filesystem_and_no_terminal():
    """The layer that survives a config the agent ignores.

    `initialize` is the first thing the runtime sends. A client that advertises
    `fs.readTextFile: true` is inviting the agent to read a file through the app — which would read
    the container, including the token file. Asserted by reading the source of `start()` rather than
    by driving a subprocess: the value is a literal in the request, and the shape of the request is
    what the agent acts on.
    """
    src = (APP / "api" / "adapters" / "acp" / "runtime.py").read_text(encoding="utf-8")
    start = src.index("clientCapabilities")
    block = src[start:start + 400]          # the whole literal, which is four lines long
    assert '"readTextFile": False' in block, (
        "the runtime advertises readTextFile; an agent could read the container, token file included")
    assert '"writeTextFile": False' in block, (
        "the runtime advertises writeTextFile; an agent could write outside the fence's knowledge")
    assert '"terminal": False' in block, (
        "the runtime advertises a terminal; a shell would bypass the tool server entirely")


def test_the_client_identifies_itself():
    """`clientInfo` is what an agent logs, and what a session's `agentInfo` is paired with."""
    assert CLIENT_INFO.get("name") and CLIENT_INFO.get("version")


# =============================================================== the consequence, as a statement

def test_the_token_file_is_not_in_the_agent_working_directory():
    """Even if a tool ran, it must not find a token in the agent's own cwd.

    The token lives in a `mkdtemp` folder the orchestrator owns and deletes on archive; the agent's cwd
    is a different `mkdtemp`. This asserts the two are produced by separate calls, so "the agent's cwd
    contains the token" cannot become true by a refactor that passes one path to both.
    """
    import inspect
    from api.services.orchestrator import Orchestrator
    orch = inspect.getsource(Orchestrator._provision) + inspect.getsource(Orchestrator._write_token)
    # the token's folder
    assert 'tempfile.mkdtemp(prefix="nbmcp-")' in orch
    # the agent's own folder
    assert 'tempfile.mkdtemp(prefix=f"agent-' in orch
    # and the token path is never derived from the cwd variable
    assert "os.path.join(cwd" not in orch.split("def _write_token")[1].split("def ")[0]


def _resolved():
    """A minimal ResolvedModel for the config writer. No network, no credential."""
    from api.domain.llm import Capability, ModelId, ProviderKind, ResolvedModel, WireProtocol
    from api.domain.llm.limits import Limits

    return ResolvedModel(
        id=ModelId.parse("databricks/databricks-llama-4-maverick"),
        provider=ProviderKind.DATABRICKS, wire=WireProtocol.SERVING,
        endpoint="databricks-llama-4-maverick",
        base_url="", limits=Limits(128_000, 8_000), capability=Capability.TOOLS,
    )
