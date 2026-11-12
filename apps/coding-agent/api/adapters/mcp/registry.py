"""Tool server lifecycle: one process per session, scoped by folder and schema.

In demo/test mode there is no tool server and the fake agent needs none. In real mode this
starts `mcp/databricks_notebook_mcp.py` with the session's scope and returns its URL.
"""

from __future__ import annotations

import asyncio
import os
import socket
import tempfile
from pathlib import Path

# Look in the app's own tree first (a deployment ships only its source folder), then in the
# repository (local development). The app folder carries a copy at tools/ for exactly this reason.
def _find_server() -> Path:
    """Locate the tool server. Walk up from this file: a deployment ships only the app folder, and
    a relative path here once pointed at api/tools/, which does not exist."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        for candidate in (parent / "tools" / "databricks_notebook_mcp.py",
                          parent / "mcp" / "databricks_notebook_mcp.py"):
            if candidate.exists():
                return candidate
    return here.parents[3] / "tools" / "databricks_notebook_mcp.py"


TOOL_SERVER = _find_server()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SubprocessToolRegistry:
    def __init__(self, server: Path | None = None, python: str = "python3", bridge=None,
                 *, user_skills: str = "", workspace_skills: str = "", hooks_file: str = "",
                 hooks_allow_run: bool = False) -> None:
        #: The workspace's declarative rules ([R-13]). A PATH, not the rules: the tool server parses them,
        #: so the policy lives with the process that enforces it.
        self._hooks_file = hooks_file
        self._hooks_allow_run = hooks_allow_run
        #: Directories for user and workspace skills ([R-18]). Empty means "not configured", which is the
        #: normal case: a laptop has no workspace, and the built-in four are enough there.
        self._user_skills = user_skills
        self._workspace_skills = workspace_skills
        self._server = server or TOOL_SERVER
        #: How a tool asks the app to run a notebook (services/run_bridge.py); None = it cannot.
        self._bridge = bridge
        self._python = python
        self._procs: dict[str, tuple[asyncio.subprocess.Process, str]] = {}
        self._stderr: str = ""
        self._logs: dict[str, str] = {}

    async def start(self, session_id: str, folder: str, schema: str | None,
                    token_file: str | None = None, sp_token_file: str | None = None,
                    ledger_dir: str | None = None, write_mode: str = "fenced") -> str:
        port = free_port()
        # The session ledger: what THIS conversation created. A pipeline id is a platform UUID with no
        # session prefix, so the fence for it cannot be a prefix; it is "in this ledger" (spec 014
        # [TOOL-6]). The file is owned by the app, not by the tool server, because the tool server is a
        # subprocess and 010's durable sessions make a restart routine ([RB-3], [E-16]).
        ledger = os.path.join(ledger_dir, f"{session_id}.jsonl") if ledger_dir else ""
        # The write scope comes from `fence_rules`, not from string arithmetic in this method. The old
        # `folder.rstrip("/") + "/"` turned both "" and "/" into "/", which is a wildcard every path
        # matches — so a session with no folder could write anywhere ([F-1], [R-1]).
        from ...domain.fence_rules import writable_folder, writable_schema

        env = {
            **os.environ,
            "NBMCP_TRANSPORT": "http",
            "NBMCP_PORT": str(port),
            "NBMCP_HOST": "127.0.0.1",
            "NBMCP_PROFILE": "core",
            "NBMCP_ALLOW_WRITES": "1",
            # What this session may change ([R-9]). `read-only` refuses every mutation in the tool
            # server; `ask` returns a needs-human result the app turns into an approval. The mode is a
            # decision the user made, so it travels with the session rather than being a constant here.
            "NBMCP_WRITE_MODE": write_mode,
            "NBMCP_WRITE_SCHEMAS": writable_schema(schema),
            "NBMCP_WRITE_PATHS": writable_folder(folder),
            "NBMCP_WRITE_JOB_PREFIX": f"agent_{session_id[:8]}_",
            "NBMCP_WRITE_INSTANCE_PREFIX": f"agent-{session_id[:8]}-",
            # The app prefix is passed separately even though it currently equals the instance one:
            # a fence that works only because two strings happen to match is not a fence
            # (spec 013 [F3], [AP-2], [E-6]).
            "NBMCP_WRITE_APP_PREFIX": f"agent-{session_id[:8]}-",
            # No pipeline prefix: a pipeline id is a UUID, so the ledger is the fence ([TOOL-6]).
            "NBMCP_WRITE_PIPELINE_PREFIX": "",
            **({"NBMCP_SESSION_LEDGER": ledger} if ledger else {}),
            "NBMCP_SKILLS_DIR": str(self._server.parent / "skills"),
            # User and workspace skills ([R-18]). The same conventions Genie Code reads, so a skill
            # written for one is a skill for the other. Empty when the caller does not know the home.
            **({"NBMCP_SKILLS_USER_DIR": self._user_skills} if self._user_skills else {}),
            **({"NBMCP_SKILLS_WORKSPACE_DIR": self._workspace_skills} if self._workspace_skills else {}),
            # Where the server reads the user's current token; never the agent's working folder.
            **({"NBMCP_TOKEN_FILE": token_file} if token_file else {}),
            # The app's own identity, for the one API a user token can never call ([RB-10]).
            **({"NBMCP_SP_TOKEN_FILE": sp_token_file} if sp_token_file else {}),
            **(self._bridge.env_for(session_id) if self._bridge else {}),
            # A platform team's rules ([R-13]). `NBMCP_HOOKS_ALLOW_RUN` is an administrator's switch: a
            # `then: run` rule executes a program inside this process, which holds the user's token.
            **({"NBMCP_HOOKS_FILE": self._hooks_file} if self._hooks_file else {}),
            "NBMCP_HOOKS_ALLOW_RUN": "1" if self._hooks_allow_run else "0",
        }
        # stderr goes to a file, not a pipe nobody reads and not /dev/null: when the server cannot
        # start, its own message is the only useful diagnostic, and a full pipe would block it.
        log = tempfile.NamedTemporaryFile(prefix=f"toolserver-{session_id[:8]}-", suffix=".log", delete=False)
        self._logs[session_id] = log.name
        proc = await asyncio.create_subprocess_exec(
            self._python,
            str(self._server),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=log,
        )
        log.close()
        url = f"http://127.0.0.1:{port}/mcp"
        self._procs[session_id] = (proc, url)
        for _ in range(60):
            if proc.returncode is not None:
                break
            if await self.health(url) > 0:
                return url
            await asyncio.sleep(0.25)
        stderr_tail = self._read_log(session_id)
        await self.stop(session_id)
        raise RuntimeError(
            f"the tool server did not start (server={self._server}, exists={self._server.exists()}). "
            f"Last output: {stderr_tail.strip()[:300] or '(none)'}")

    def _read_log(self, session_id: str) -> str:
        try:
            return Path(self._logs.get(session_id, "")).read_text(errors="replace")[-600:]
        except OSError:
            return ""

    async def health(self, url: str) -> int:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    url.split("//")[1].split(":")[0], int(url.split(":")[2].split("/")[0])
                ),
                2,
            )
        except (TimeoutError, OSError, IndexError):
            return 0
        writer.close()
        return 200

    async def stop(self, session_id: str) -> None:
        proc, _ = self._procs.pop(session_id, (None, ""))
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()


def read_ledger(ledger_dir: str | None = None) -> list[dict]:
    """Every object any session created, newest last, read from the ledger files.

    The ledger is one JSONL file per session (spec 014 [RB-3]); this reads them all so a page can ask "did
    this conversation make this pipeline?" by checking the session prefix in its own client. A missing
    directory is an empty ledger: a fence that fails closed on a missing file refuses work the user can
    see they did.
    """
    import json
    from pathlib import Path

    root = Path(ledger_dir or os.environ.get("APP_SESSION_LEDGER_DIR")
                or os.path.join(tempfile.gettempdir(), "agent-ledgers"))
    rows: list[dict] = []
    try:
        for path in sorted(root.glob("*.jsonl")):
            session = path.stem
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append({**row, "session": session})
    except OSError:
        return []
    return rows


class NullToolRegistry:
    """Demo mode: no tool server. The advertised count is 0 and the UI says writes are off."""

    async def start(self, session_id: str, folder: str, schema: str | None,
                    token_file: str | None = None, sp_token_file: str | None = None,
                    ledger_dir: str | None = None, write_mode: str = "fenced") -> str:
        return ""

    async def health(self, url: str) -> int:
        return 0

    async def stop(self, session_id: str) -> None:
        return None
