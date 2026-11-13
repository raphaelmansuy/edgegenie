"""Spike MCP server for spec 014. Its tools touch nothing: they only return text, sleep, or raise.

Run:  PROBE_PORT=8899 python acp_spike_mcp.py     (needs the `mcp` package; the app's venv has it)
"""
import os
import time

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("probe")


@mcp.tool()
def probe_read(name: str) -> str:
    """Read a probe value. Returns a small JSON object."""
    return '{"name": "%s", "rows": 3}' % name


@mcp.tool()
def probe_write(path: str, content: str) -> str:
    """Pretend to write `content` to `path`. Nothing is written anywhere."""
    return '{"written": "%s", "bytes": %d}' % (path, len(content))


@mcp.tool()
def probe_slow(seconds: int) -> str:
    """Sleep for `seconds`, then return. Shows what the agent emits while a tool runs."""
    time.sleep(int(seconds))
    return '{"slept": %d}' % int(seconds)


@mcp.tool()
def probe_refuse_as_content(path: str) -> str:
    """Refuse a write by returning an error object as ordinary content."""
    return '{"error": "write blocked: %s is outside the allowed paths"}' % path


@mcp.tool()
def probe_refuse_by_raising(path: str) -> str:
    """Refuse a write by raising, so MCP reports isError."""
    raise PermissionError(f"write blocked: {path} is outside the allowed paths")


if __name__ == "__main__":
    mcp.settings.port = int(os.environ.get("PROBE_PORT", "8899"))
    mcp.settings.host = "127.0.0.1"
    mcp.run(transport="streamable-http")
