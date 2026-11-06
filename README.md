# edgegenie

Research workspace: **can a general-purpose coding agent replace Databricks Genie Code?**

Everything here was executed against a live workspace
(`dbc-cb61f1e1-bd8e.cloud.databricks.com`), not simulated.

## Start here

| Document | What it is |
|---|---|
| [`docs/genie-code-replacement-spec.md`](docs/genie-code-replacement-spec.md) | The specification: 5-Why, capability register, gap analysis, reference architecture, cost model, risk |
| [`docs/e2e/`](docs/e2e/) | 16 executed transcripts + MCP conformance results |
| [`AGENTS.md`](AGENTS.md) | The working agreement to drop into any repo driving Databricks |

## The short version

- ✅ **A coding agent runs entirely inside Databricks.** No local shell, no laptop install.
- ✅ **Governed SQL works** through `system.ai.dbsql` — queries run as the caller.
- ✅ **A custom MCP server closes the workspace-artefact gap** (18 tools, 14/14 pass).
- ❌ **Partner models (Claude/Gemini) are gated** until an account admin enables the Unity Gateway beta.
- ❌ **Silent failures are the real risk**: truncation produced a confident wrong answer; an empty grep result produced invented imports.

## Layout

```
docs/
  genie-code-replacement-spec.md   # the spec
  e2e/                             # evidence
    *.txt                          #   agent transcripts (ANSI stripped)
    mcp_conformance.json           #   tool test results
    mcp_tools.txt                  #   MCP surface inventory
    capture.py                     #   screenshot harness
mcp/
  databricks_notebook_mcp.py       # 18-tool MCP server
  test_mcp.py                      # conformance suite
experiments/
  dbx_mcp.py                       # MCP client helper
  sandbox_run.py                   # run a script inside a Databricks sandbox
  sandbox_put.py                   # upload a file into a sandbox
  collect_e2e.py                   # pull transcripts back out
  gemini_sig_shim.py               # thought_signature shim for Gemini 3.x
  steps/                           # numbered experiment scripts
```

## Prerequisites

- Databricks CLI ≥ 0.289 and a PAT in `.env` (`TOKEN=dapi…`)
- Python 3.12 with `mcp` and `httpx`
- Access to `system.ai.sandbox`, `system.ai.dbsql`, `system.ai.genie_one_mcp`

## Quick start

```bash
# 1. Inventory the MCP surface
python3 experiments/dbx_mcp.py list /ai-gateway/mcp-services/system.ai.sandbox

# 2. Spin up a sandbox and install OpenCode
python3 experiments/sandbox_run.py experiments/steps/01_start_proxy.sh --sandbox=<id>

# 3. Run the agent (see steps/04_opencode_fixed.sh for the working config)
python3 experiments/sandbox_run.py experiments/steps/04_opencode_fixed.sh --sandbox=<id>

# 4. Test the custom MCP server
.venv/bin/python3 mcp/test_mcp.py
```

## Notes on safety

- `.env` holds a live PAT and is git-ignored. Rotate it if it leaks.
- Never run an agent with `--auto` against production. See spec §10.
- `NBMCP_ALLOW_WRITES` defaults to off. Keep it off outside dev.
