#!/usr/bin/env python3
"""Credential-free MCP facade. Its only authority is one revocable session key on loopback."""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route


async def serve():
    server = Server("opengenie-tools")
    sid, key, url = (os.environ[n] for n in ("TOOL_SESSION", "TOOL_KEY", "TOOL_APP_URL"))
    async with httpx.AsyncClient(base_url=url, timeout=29) as client:

        async def request(name, args):
            response = await client.post(
                "/internal/tools/" + name, json={"session": sid, "key": key, "arguments": args}
            )
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "Tool refused")
                except ValueError:
                    detail = "Tool service unavailable"
                raise RuntimeError(str(detail))
            return response.json()

        @server.list_tools()
        async def listing():
            return [Tool(**row) for row in (await request("catalogue", {}))["tools"]]

        @server.call_tool()
        async def calling(name, arguments):
            result = await request(name, arguments or {})
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True)

        @asynccontextmanager
        async def lifespan(app):
            async with manager.run():
                yield

        app = Starlette(routes=[Route("/mcp", endpoint=StreamableHTTPASGIApp(manager))], lifespan=lifespan)
        await uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=int(os.environ["NBMCP_PORT"]), log_level="warning")
        ).serve()


if __name__ == "__main__":
    import asyncio

    asyncio.run(serve())
