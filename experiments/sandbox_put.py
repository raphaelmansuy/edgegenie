#!/usr/bin/env python3
"""Upload a local file into the Databricks sandbox via base64 over run_code."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dbx_mcp import rpc  # noqa: E402

ENDPOINT = "/ai-gateway/mcp-services/system.ai.sandbox"


def upload(local: str, remote: str, sandbox_id: str) -> None:
    data = base64.b64encode(Path(local).read_bytes()).decode()
    # Chunk to stay well inside a single tool-call payload.
    chunk = 60000
    parts = [data[i : i + chunk] for i in range(0, len(data), chunk)] or [""]
    for i, part in enumerate(parts):
        mode = ">" if i == 0 else ">>"
        code = f"echo -n '{part}' {mode} /tmp/_up.b64; echo chunk_{i}_ok"
        out = rpc(
            ENDPOINT,
            "tools/call",
            {
                "name": "run_code",
                "arguments": {"sandbox_id": sandbox_id, "language": "sh", "code": code},
            },
        )
        if out.get("result", {}).get("isError"):
            raise SystemExit("upload chunk failed")
    code = f"base64 -d /tmp/_up.b64 > {remote} && chmod +x {remote} && ls -l {remote}"
    out = rpc(
        ENDPOINT,
        "tools/call",
        {
            "name": "run_code",
            "arguments": {"sandbox_id": sandbox_id, "language": "sh", "code": code},
        },
    )
    print("\n".join(i.get("text", "") for i in out.get("result", {}).get("content", [])))


if __name__ == "__main__":
    upload(sys.argv[1], sys.argv[2], sys.argv[3])
