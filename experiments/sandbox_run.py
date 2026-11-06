#!/usr/bin/env python3
"""Run a local shell script inside a Databricks sandbox.

    python sandbox_run.py <local-script.sh> [--sandbox ID] [--timeout 300]

The script is shipped base64-encoded so quoting never has to survive the
JSON-RPC boundary.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dbx_mcp import rpc  # noqa: E402

ENDPOINT = "/ai-gateway/mcp-services/system.ai.sandbox"


def run(script: str, sandbox_id: str, timeout: int = 300) -> str:
    payload = base64.b64encode(script.encode()).decode()
    code = (
        f"echo '{payload}' | base64 -d > /tmp/_step.sh; "
        f"bash /tmp/_step.sh"
    )
    out = rpc(
        ENDPOINT,
        "tools/call",
        {
            "name": "run_code",
            "arguments": {
                "sandbox_id": sandbox_id,
                "language": "sh",
                "timeout_seconds": timeout,
                "code": code,
            },
        },
    )
    result = out.get("result", {})
    text = "\n".join(i.get("text", "") for i in result.get("content", []))
    if result.get("isError"):
        return "TOOL ERROR: " + text
    return text


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {
        a.split("=")[0][2:]: a.split("=", 1)[1]
        for a in sys.argv[1:]
        if a.startswith("--") and "=" in a
    }
    script = Path(args[0]).read_text()
    sandbox = opts.get("sandbox", "mas-sbx-d14169ed1e854dada255e7c0")
    timeout = int(opts.get("timeout", "300"))
    print(run(script, sandbox, timeout))


if __name__ == "__main__":
    main()
