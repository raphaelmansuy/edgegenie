#!/usr/bin/env python3
"""Minimal Databricks MCP client used by the experiments in this repo.

Supports both the workspace MCP endpoints (/api/2.0/mcp/...) and the
Unity Gateway MCP services (/ai-gateway/mcp-services/...).

Usage:
    python dbx_mcp.py list <endpoint>
    python dbx_mcp.py call <endpoint> <tool> '<json-args>'
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def load_env() -> tuple[str, str]:
    host = os.environ.get("DATABRICKS_HOST", "https://dbc-cb61f1e1-bd8e.cloud.databricks.com")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not token and ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith("TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token:
        raise SystemExit("no token found")
    return host.rstrip("/"), token


def rpc(endpoint: str, method: str, params: dict) -> dict:
    host, token = load_env()
    url = f"{host}{endpoint}"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read().decode()
    # Streamable HTTP transport may wrap the payload in SSE frames.
    for line in raw.splitlines():
        if line.startswith("data: "):
            raw = line[6:]
    return json.loads(raw)


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, endpoint = sys.argv[1], sys.argv[2]
    if cmd == "list":
        out = rpc(endpoint, "tools/list", {})
        for tool in out.get("result", {}).get("tools", []):
            print(json.dumps(tool, indent=2))
    elif cmd == "call":
        args = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        out = rpc(endpoint, "tools/call", {"name": sys.argv[3], "arguments": args})
        result = out.get("result", {})
        if result.get("isError"):
            print("ERROR:", json.dumps(result, indent=2)[:4000])
            sys.exit(1)
        for item in result.get("content", []):
            print(item.get("text", item))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
