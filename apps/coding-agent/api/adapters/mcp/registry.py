"""Tool server lifecycle: one process per session, scoped by folder and schema.

In demo/test mode there is no tool server and the fake agent needs none. In real mode this
starts `mcp/databricks_notebook_mcp.py` with the session's scope and returns its URL.
"""

from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

TOOL_SERVER = Path(__file__).resolve().parents[4].parent / "mcp" / "databricks_notebook_mcp.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SubprocessToolRegistry:
    def __init__(self, server: Path | None = None, python: str = "python3") -> None:
        self._server = server or TOOL_SERVER
        self._python = python
        self._procs: dict[str, tuple[asyncio.subprocess.Process, str]] = {}

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
        }
        proc = await asyncio.create_subprocess_exec(
            self._python,
            str(self._server),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}/mcp"
        self._procs[session_id] = (proc, url)
        for _ in range(20):
            if await self.health(url) > 0:
                return url
            await asyncio.sleep(0.25)
        await self.stop(session_id)
        raise RuntimeError("the tool server did not start (see INFRA in the runbook)")

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
