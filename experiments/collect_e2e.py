#!/usr/bin/env python3
"""Pull E2E transcripts out of the sandbox and write them into docs/e2e/.

The sandbox is the source of truth for what actually happened; this script
copies the ANSI-stripped logs back so the spec can cite them.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dbx_mcp import rpc  # noqa: E402

SBX = "mas-sbx-d14169ed1e854dada255e7c0"
ENDPOINT = "/ai-gateway/mcp-services/system.ai.sandbox"
OUT = Path(__file__).resolve().parents[1] / "docs" / "e2e"

WANTED = {
    "proj/run2.log": "01_opencode_gateway.txt",
    "proj/mcp1.log": "02_opencode_sql_mcp.txt",
    "proj/c1b.log": "03_opencode_custom_mcp.txt",
    "gemtest/g3.log": "04_gemini38_shim.txt",
    "cop/c1.log": "05_copilot_byok.txt",
    "cop/c2.log": "06_copilot_mcp.txt",
    "proj/gem.log": "07_gemini_thought_signature_failure.txt",
    "proj/ab_A.log": "08_custom_mcp_not_chosen.txt",
    "proj/e_case.log": "09_post_tool_stall.txt",
    "proj/repo/d_case.log": "10_local_file_control.txt",
    "proj/s_sqlchain.log": "11_sql_chain.txt",
    "proj/s_paged.log": "12_paged_grep.txt",
    "proj/s_onepage.log": "13_one_page_read.txt",
    "proj/fx.log": "14_fixed_grep_success.txt",
    "proj/rec.log": "15_no_match_hallucination.txt",
    "proj/px.log": "16_stall_tool_chain.txt",
}


def fetch(remote: str) -> str:
    code = (
        f"f=\"$HOME/{remote}\"; "
        f"if [ -f \"$f\" ]; then "
        f"sed -e 's/\\x1b\\[[0-9;]*m//g' -e 's/\\r$//' \"$f\" | base64 -w0; "
        f"else echo NOTFOUND; fi"
    )
    out = rpc(
        ENDPOINT,
        "tools/call",
        {"name": "run_code", "arguments": {"sandbox_id": SBX, "language": "sh", "code": code}},
    )
    text = "".join(i.get("text", "") for i in out.get("result", {}).get("content", [])).strip()
    if text == "NOTFOUND" or not text:
        return ""
    try:
        return base64.b64decode(text).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for remote, local in WANTED.items():
        body = fetch(remote)
        if not body:
            print(f"skip  {remote} (not present)")
            continue
        header = (
            f"# source: sandbox {SBX}\n"
            f"# remote: ~/{remote}\n"
            f"# ANSI stripped, captured {__import__('datetime').datetime.utcnow():%Y-%m-%dT%H:%M:%SZ}\n"
            f"{'-' * 70}\n"
        )
        (OUT / local).write_text(header + body)
        print(f"ok    {local} ({len(body)} chars)")


if __name__ == "__main__":
    main()
