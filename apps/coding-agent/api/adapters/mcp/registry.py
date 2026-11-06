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
    def __init__(self, server: Path | None = None, python: str = "python3") -> None:
        self._server = server or TOOL_SERVER
        self._python = python
        self._procs: dict[str, tuple[asyncio.subprocess.Process, str]] = {}
        self._stderr: str = ""
        self._logs: dict[str, str] = {}

    async def start(self, session_id: str, folder: str, schema: str | None) -> str:
        port = free_port()
        env = {
            **os.environ,
            "NBMCP_TRANSPORT": "http",
            "NBMCP_PORT": str(port),
            "NBMCP_HOST": "127.0.0.1",
            "NBMCP_PROFILE": "core",
            "NBMCP_ALLOW_WRITES": "1",
            "NBMCP_WRITE_SCHEMAS": schema or "",
            "NBMCP_WRITE_PATHS": folder.rstrip("/") + "/",
            "NBMCP_WRITE_JOB_PREFIX": f"agent_{session_id[:8]}_",
            "NBMCP_WRITE_INSTANCE_PREFIX": f"agent-{session_id[:8]}-",
            "NBMCP_SKILLS_DIR": str(self._server.parent / "skills"),
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


class NullToolRegistry:
    """Demo mode: no tool server. The advertised count is 0 and the UI says writes are off."""

    async def start(self, session_id: str, folder: str, schema: str | None) -> str:
        return ""

    async def health(self, url: str) -> int:
        return 0

    async def stop(self, session_id: str) -> None:
        return None
