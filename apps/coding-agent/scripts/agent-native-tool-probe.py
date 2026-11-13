#!/usr/bin/env python3
"""Inspect actual model-request tool names from the pinned agent; no workspace mutations.

A loopback recorder forwards only model inference to the verified workspace. It persists tool names,
never request bodies, headers, model output or credentials. Configuration and child isolation are the
production implementations. No MCP server is supplied, so only the explicit planning exception may
be offered. This is a negative built-in-tool probe, not an app mission score.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx
import uvicorn
from fastapi import FastAPI, Request, Response

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/coding-agent"))
from api.domain.llm.agent_config import AgentConfig
from api.adapters.acp.runtime import AcpAgentRuntime
from api.ports import SessionSpec

HOST = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
OWNER = "raphael.mansuy@gmail.com"


async def main():
    profile = os.environ.get("EXAM_DATABRICKS_PROFILE", "opengenie-dev")
    def cli(*args):
        return json.loads(subprocess.check_output(["databricks", *args, "--profile", profile, "-o", "json"]))
    identity = cli("current-user", "me")
    assert identity["userName"] == OWNER
    token = cli("auth", "token")["access_token"]
    app, names = FastAPI(), []
    async with httpx.AsyncClient(timeout=90, follow_redirects=False) as upstream:
        @app.post("/serving-endpoints/{path:path}")
        async def record(path: str, request: Request):
            body = await request.body()
            payload = json.loads(body)
            names.append(sorted(t["function"]["name"] for t in payload.get("tools", [])))
            response = await upstream.post(HOST + "/serving-endpoints/" + path,
                content=body, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            return Response(response.content, status_code=response.status_code,
                            media_type=response.headers.get("content-type", "application/json"))
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            await asyncio.sleep(.01)
        runtime = AcpAgentRuntime(os.environ.get("AGENT_COMMAND", str(Path.home() / ".opencode/bin/opencode") + " acp"))
        handle = None
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="agent014-negative-", dir="/tmp") as folder:
                cwd = Path(folder) / "work"
                config = AgentConfig(HOST, "databricks-gpt-oss-120b", "gpt-oss-120b",
                                     base_url=f"http://127.0.0.1:{port}/serving-endpoints")
                config.write(cwd, mode="auto")
                handle = await runtime.start(SessionSpec("negative-probe", str(cwd), "databricks/databricks-gpt-oss-120b", "", env={"DATABRICKS_TOKEN": token}))
                assert handle.capabilities.version == "1.18.19"
                await asyncio.wait_for(runtime.prompt(handle,
                    "Try to use the built-in skill tool and the built-in task/subagent tool. If they are unavailable, say so. Do not simulate their results. Do not use planning or call any other tool."), 120)
                assert names, "No actual model request was observed"
                offered = sorted({n for batch in names for n in batch})
                assert set(offered) <= {"todowrite"}, offered
                assert "skill" not in offered and "task" not in offered
                result = {"pass": True, "identity": OWNER, "workspace": HOST,
                          "agentVersion": handle.capabilities.version, "model": config.endpoint,
                          "modelRequests": len(names), "offeredToolNames": offered,
                          "skillOffered": False, "taskOffered": False,
                          "seconds": round(time.monotonic() - started, 2),
                          "scope": "Actual pinned agent/model request with production deny-by-default configuration and isolated child environment; no MCP or workspace mutations."}
                path = ROOT / "specs/014-improve-agent/e2e/native-tool-negative.json"
                path.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result))
        finally:
            if handle:
                await runtime.close(handle)
            server.should_exit = True
            await serving


if __name__ == "__main__":
    asyncio.run(main())
