#!/usr/bin/env python3
"""Create (or reuse) a Databricks sandbox and install the exam toolchain in it.

    python bootstrap_sandbox.py [--sandbox=ID] [--copilot]

Prints the sandbox id and stores it in exams/.sandbox_id. Installs: opencode,
(optionally) GitHub Copilot CLI, the nbmcp server deps, the Gemini signature
shim, and the PAT as a file readable only by the sandbox user.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE))
from dbx_mcp import rpc  # noqa: E402
from sandbox_put import upload  # noqa: E402
from sandbox_run import run  # noqa: E402

from lib import TOKEN  # noqa: E402
import variants  # noqa: E402

EP = "/ai-gateway/mcp-services/system.ai.sandbox"
ID_FILE = HERE / ".sandbox_id"

INSTALL = r"""
set -u
mkdir -p ~/.npm-global ~/proj ~/exam
npm config set prefix ~/.npm-global >/dev/null 2>&1
export PATH="$HOME/.npm-global/bin:$PATH"
command -v opencode >/dev/null || npm install -g opencode-ai 2>&1 | tail -2
[ -x ~/pyenv/bin/python ] || uv venv --system-site-packages ~/pyenv -q
uv pip install -q --python ~/pyenv/bin/python psycopg2-binary requests "mcp<2" httpx 2>&1 | tail -2
echo "opencode: $(opencode --version 2>&1 | tail -1)"
~/pyenv/bin/python -c "import mcp,httpx,psycopg2;print('py deps ok')"
"""

COPILOT = r"""
export PATH="$HOME/.npm-global/bin:$PATH"
command -v copilot >/dev/null || npm install -g @github/copilot 2>&1 | tail -2
echo "copilot: $(copilot --version 2>&1 | head -1)"
"""


def sandbox_id() -> str:
    for a in sys.argv[1:]:
        if a.startswith("--sandbox="):
            return a.split("=", 1)[1]
    if ID_FILE.exists():
        return ID_FILE.read_text().strip()
    out = rpc(EP, "tools/call", {"name": "create_sandbox", "arguments": {}})
    text = out["result"]["content"][0]["text"]
    import json
    return json.loads(text)["sandbox_id"]


def main() -> None:
    sid = sandbox_id()
    ID_FILE.write_text(sid)
    print("sandbox:", sid)
    print(run(INSTALL, sid, 600))
    if "--copilot" in sys.argv:
        print(run(COPILOT, sid, 600))
    tok = HERE / ".tok"
    tok.write_text(TOKEN)
    upload(str(tok), "/tmp/dbx_token.txt", sid)
    tok.unlink()
    for local, remote in [
        (HERE.parent / "mcp" / "databricks_notebook_mcp.py", "/tmp/databricks_notebook_mcp.py"),
        (HERE.parent / "mcp" / "legacy" / "nbmcp_v1.py", "/tmp/nbmcp_v1.py"),
        (HERE.parent / "mcp" / "legacy" / "nbmcp_v2.py", "/tmp/nbmcp_v2.py"),
        (HERE.parent / "mcp" / "legacy" / "nbmcp_v3.py", "/tmp/nbmcp_v3.py"),
        (HERE.parent / "experiments" / "gemini_sig_shim.py", "/tmp/gemini_sig_shim.py"),
        (HERE.parent / "AGENTS.md", "/tmp/AGENTS.md"),
    ]:
        upload(str(local), remote, sid)
    skills = HERE.parent / "mcp" / "skills"
    run("mkdir -p /tmp/skills", sid, 30)
    for f in sorted(skills.glob("*.md")):
        upload(str(f), f"/tmp/skills/{f.name}", sid)
    # official Databricks agent skills (34), cached once; copied into each run's .claude/skills
    print(run("export DATABRICKS_HOST=%s DATABRICKS_TOKEN=$(cat /tmp/dbx_token.txt) HOME=/tmp/h_skills; "
              "unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE; mkdir -p $HOME; rm -rf /tmp/dbx_skills_all; "
              "databricks aitools install --path /tmp/dbx_skills_all --scope global 2>&1 | tail -2" % variants.HOST, sid, 120))
    print(run("chmod 600 /tmp/dbx_token.txt; ls /tmp/skills; ls /tmp/dbx_skills_all | wc -l", sid, 60))


if __name__ == "__main__":
    main()
