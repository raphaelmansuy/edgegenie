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

def test_every_builtin_tool_that_touches_the_machine_is_denied():
    """The list is the specification. A tool that reads, writes, globs, greps or shells is denied."""
    dangerous = {"bash", "edit", "read", "glob", "grep", "list", "external_directory"}
    missing = dangerous - set(agent_config.DENIED_BUILTINS)
    assert not missing, f"these built-ins reach the container and are not denied: {sorted(missing)}"


def test_the_config_file_actually_carries_the_denials(tmp_path):
    """The list is a constant; this asserts the file the agent reads is built from it."""
    cfg = agent_config.AgentConfig.from_resolved(_resolved(), host="https://example.invalid")
    path = cfg.write(tmp_path, session_rules="")
    written = json.loads(path.read_text())
    permissions = written["permission"]
    for tool in agent_config.DENIED_BUILTINS:
        assert permissions.get(tool) == "deny", f"{tool} is not denied in opencode.json"
    # Planning stays on: it drives the checklist the user sees, and it touches nothing.
    assert "todowrite" not in permissions or permissions["todowrite"] != "deny"


def test_network_fetch_tools_are_denied():
    """An egress tool is G-6's gap made reachable from a prompt: `webfetch` can POST a token out."""
    for tool in ("webfetch", "websearch"):
        assert tool in agent_config.DENIED_BUILTINS, f"{tool} would let a prompt reach the internet"


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
    orch = (APP / "api" / "services" / "orchestrator.py").read_text(encoding="utf-8")
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
