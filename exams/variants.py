"""Agent configurations under test.

A *variant* is the "approach" being evaluated: which tools and which standing
instructions the coding agent gets. The model and the agent CLI are separate
axes (see MODELS / AGENTS). Improving the approach = adding a new variant that
fixes failure modes found in the previous one, then re-running the same exams.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"

# model key -> (provider/model string for the CLI, provider block for opencode)
MODELS = {
    "gpt-oss-120b": {
        "id": "dbx/system.ai.gpt-oss-120b",
        "provider": {
            "dbx": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Databricks AI Gateway",
                "options": {"baseURL": f"{HOST}/ai-gateway/openai/v1", "apiKey": "{env:DATABRICKS_TOKEN}"},
                "models": {"system.ai.gpt-oss-120b": {"name": "gpt-oss-120b",
                                                      "limit": {"context": 128000, "output": 24000}}},
            }
        },
    },
    "gemini-3.8-flash": {
        "id": "vertex/google/gemini-3.8-flash",
        "provider": {
            "vertex": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Vertex Gemini 3.8 Flash (via signature shim)",
                "options": {"baseURL": "http://127.0.0.1:8790/v1", "apiKey": "unused"},
                "models": {"google/gemini-3.8-flash": {"name": "gemini-3.8-flash",
                                                       "limit": {"context": 1000000, "output": 30000}}},
            }
        },
    },
}


def mcp_block(variant: str, nbmcp_port: int) -> dict:
    dbsql = {"type": "remote", "url": f"{HOST}/ai-gateway/mcp-services/system.ai.dbsql", "oauth": False,
             "headers": {"Authorization": "Bearer {env:DATABRICKS_TOKEN}"}}
    nb = {"type": "remote", "url": f"http://127.0.0.1:{nbmcp_port}/mcp", "oauth": False}
    if variant in ("V0", "V5"):
        return {}
    if variant == "V1":
        return {"dbsql": dbsql, "dbxnb": nb}
    # V2+: the improved approach drops the unscoped dbsql server entirely: fewer
    # tools in context and no write path that bypasses the server-side scope.
    return {"dbxnb": nb}


def agents_md(variant: str) -> str:
    if variant == "V0":
        return ""
    if variant == "V1":
        return (HERE.parent / "AGENTS.md").read_text()
    if variant == "V2":
        return (HERE / "agents_v2.md").read_text()
    if variant == "V3":
        return (HERE / "agents_v3.md").read_text()
    if variant == "V5":
        return (HERE / "agents_v5.md").read_text()
    if variant == "V6":
        return (HERE / "agents_v6.md").read_text()
    return (HERE / "agents_v4.md").read_text()


def opencode_config(model: str, variant: str, nbmcp_port: int) -> str:
    m = MODELS[model]
    cfg = {"$schema": "https://opencode.ai/config.json", "model": m["id"], "provider": m["provider"]}
    mcp = mcp_block(variant, nbmcp_port)
    if mcp:
        cfg["mcp"] = mcp
    if variant in ("V3", "V4", "V6"):
        # V3: remove built-in tools that act on the sandbox's local disk. Their
        # presence made the agent try to read/edit *workspace* paths locally.
        cfg["permission"] = {"edit": "deny", "webfetch": "deny", "task": "deny", "todowrite": "deny"}
        if variant not in ("V6",):
            cfg["permission"]["skill"] = "deny"
        cfg["tools"] = {"read": False, "write": False, "glob": False, "grep": False}
    return json.dumps(cfg, indent=2)


VARIANTS = {
    "V0": "bare: coding agent + shell in the Databricks sandbox, PAT in env, no MCP, no rules",
    "V1": "tools+rules: dbsql MCP + nbmcp (scoped writes) + AGENTS.md working agreement",
    "V2": "improved: lean tool profile + run/job/lakebase/file tools + audit supervisor + scope on writes",
    "V3": "V2 + cells-based notebook writer, no local file tools, final-report template, ANSI/serverless rules",
    "V5": "stock Databricks: shell + databricks CLI + official agent skills (databricks aitools), NO custom MCP",
    "V6": "hybrid: V4 (custom MCP, scoped) + databricks CLI + official agent skills",
    "V4": "V3 + native list params (cells/tasks), liberal input handling, on-demand skills (dbx_skill)",
}


def uses_nbmcp(variant: str) -> bool:
    return variant not in ("V0", "V5")


def uses_official_skills(variant: str) -> bool:
    return variant in ("V5", "V6")


def profile(variant: str) -> str:
    return "full" if variant in ("V0", "V1") else "core"


def supervised(variant: str) -> bool:
    return variant not in ("V0", "V1")


def server_file(variant: str) -> str:
    """V0/V1: frozen original server (19 tools). V2: frozen V2 server. V3+: current server."""
    return {"V0": "/tmp/nbmcp_v1.py", "V1": "/tmp/nbmcp_v1.py", "V2": "/tmp/nbmcp_v2.py",
                                                 "V3": "/tmp/nbmcp_v3.py"}.get(
        variant, "/tmp/databricks_notebook_mcp.py")


def copilot_env(model: str) -> str:
    """Shell exports for GitHub Copilot CLI in BYOK mode (no GitHub login needed)."""
    if model.startswith("gemini"):
        base, key, mid, out = "http://127.0.0.1:8790/v1", "unused", "google/gemini-3.8-flash", 30000
    else:
        # via experiments/copilot_field_shim.py: Copilot CLI adds a private "__copilotMessageSource" field
        # that the Databricks gateway rejects with HTTP 400 (see docs/06).
        base, key, mid, out = "http://127.0.0.1:8791/v1", "$DATABRICKS_TOKEN", "system.ai.gpt-oss-120b", 16000
    return (f'export COPILOT_PROVIDER_BASE_URL="{base}"\nexport COPILOT_PROVIDER_API_KEY="{key}"\n'
            f'export COPILOT_MODEL="{mid}"\nexport COPILOT_PROVIDER_WIRE_MODEL="{mid}"\n'
            f'export COPILOT_PROVIDER_MAX_OUTPUT_TOKENS="{out}"\nexport COPILOT_OFFLINE="true"')


def copilot_mcp_json(variant: str, nbmcp_port: int) -> str:
    servers: dict = {}
    if uses_nbmcp(variant):
        if variant == "V1":
            servers["dbsql"] = {"type": "http", "url": f"{HOST}/ai-gateway/mcp-services/system.ai.dbsql",
                                "headers": {"Authorization": "Bearer __DBX_TOKEN__"}, "tools": ["*"]}
        servers["dbxnb"] = {"type": "http", "url": f"http://127.0.0.1:{nbmcp_port}/mcp", "tools": ["*"]}
    return json.dumps({"mcpServers": servers}, indent=2)
