# 13 · Validation record

[Map](README.md) · findings: [02](02-code-grounding.md) · external assessment: [01](01-genie-code-acp-assessment.md)

What was actually checked to write this specification, on 2026-11-13, and what was not. Nothing in the
application was changed; the only files written are in this folder. The record has two parts: the
first pass, from the code and documentation alone, and the [live investigation](#live-investigation)
that followed when the owner gave access to the workspace and to a model.

## Session start

The repository's working agreement ([AGENTS.md](../../AGENTS.md)) asks for `dbxnb_dbx_whoami` and
`dbxnb_dbx_list_warehouses` before any work. Those tools were not available in this session: two tool
searches returned no match, and per the agreement I stopped there. Consequently, during the first pass
**no workspace identity, warehouse, table, scope or API behaviour was verified** and no SQL was run. In
the second pass the same two checks were made with the Databricks CLI, as recorded
[below](#live-investigation).

## What was read

| Source | Coverage |
|---|---|
| `api/services/orchestrator.py` | all 1,105 lines |
| `api/adapters/acp/`: `runtime.py`, `mapper.py`, `jsonrpc.py`, `agent_config.py`, `blocks.py` | all |
| `api/adapters/mcp/registry.py`, `api/adapters/memory/broadcast.py`, `api/adapters/durable/postgres.py`, `sqlite.py` | all |
| `api/ports/__init__.py`, `api/config.py` | all |
| `api/domain/`: `supervisor.py`, `evidence.py`, `events.py`, `session.py`, `scope.py`, `context.py`, `reaper.py` | all |
| `api/services/context.py`, `run_bridge.py`; `api/routers/internal.py` | all |
| `tools/databricks_notebook_mcp.py` | all 1,104 lines |
| `api/main.py` | lines 36 to 262 of 344 |
| `api/routers/api.py` | lines 36 to 128, 176 to 442, 740 to 900 of 1,213; the route list by search |
| `api/domain/sqlpolicy.py` | first 30 lines |
| `api/adapters/fake/agent.py` | first 40 lines, and the permission branch by search |
| `app.yaml`, `databricks.yml`, `package.json`, `scripts/prepare-app.sh`, `migrations/004_session_journal.sql`, `tools/skills/etl-pipelines.md` | all |
| Front end | The first 22 lines of `changes.ts`, `reconcile.ts`, `commands.ts`, `followups.ts`, `artifacts.ts`, `toolview.ts`, `mission.ts`, `useFresh.ts`, `cellprompt.ts`, `binding.ts`, `workingset.ts`; `events.ts` lines 41 to 53 and 227 to 243; `EditorSurface.tsx` by search only |
| `README.md`, `specs/013-sql-query-support/README.md` | all |
| `specs/006-databricks/README.md` | lines 1 to 60 |
| `specs/010-long-running/07-edge-cases-tests.md` | lines 1 to 47, truncated at 300 characters per line |
| `docs/genie-code-replacement-spec.md` | lines 155 to 200 |
| `exams/run_exam.py` | by search (lines 108 to 131, 165, 209, 240, 290) |

Statements about a file are limited to the part read. Where a finding rests on a partial read it says so
([F-32](02-code-grounding.md#f-32)).

## Delegated reading

Three background passes were used. Their reports are inputs, not evidence, and each declared its limits.

| Pass | Scope | Declared limit | How it is used here |
|---|---|---|---|
| Front-end audit | `apps/coding-agent/web` | Read `route.ts`, `events.ts`, `mission.ts`, `client.ts`, `useSessionStream.ts`, `App.tsx` lines 1 to 220, and search results elsewhere. Did not read every component. | Route list and reducer observations in [04](04-ux-wireframes.md) and [F-32](02-code-grounding.md#f-32), labelled. |
| Prior specs and exams | `specs/001` to `013`, `docs/`, `exams/` | READMEs and selected documents only; "cannot claim to list every deferred item". | Conventions (identifier schemes, Mermaid palette, wireframe checks) and the mission list. Not used for claims about what earlier specs deferred. |
| External research | Databricks, ACP and opencode documentation | Marked each statement verified, secondary or unverified; did not read opencode source. | [01](01-genie-code-acp-assessment.md), labelled R. I re-read two ACP pages myself, below. |

## External pages read directly

| Page | Read for |
|---|---|
| [ACP tool calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md), first 9,000 characters | `session/request_permission` shape, outcomes, option kinds, `name` versus `title`, statuses, partial updates, `diff` content |
| [ACP prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md), characters 0 to 12,000 and 15,500 to 22,500 | The list of `sessionUpdate` kinds, `usage_update` shape, stop reasons, cancellation rules |

Every row labelled V in [01](01-genie-code-acp-assessment.md#b-agent-client-protocol-v1) comes from those
two pages. Nothing on either page was treated as an instruction.

## Probes

Each probe imported the repository's own function and called it. They ran in the app's virtual
environment, wrote nothing, and contacted nothing. The tool module was imported with
`NBMCP_WRITE_SCHEMAS=""`, `NBMCP_WRITE_PATHS="/Users/me/agent/"`, `NBMCP_ALLOW_WRITES=1`.

| Probe | Call | Observed | Finding |
|---|---|---|---|
| P1 | `_check_path_scope("/Users/me/agent/../../other/secret_nb")` | allowed; `/Users/me/agentX/nb` refused | [F-02](02-code-grounding.md#f-02) |
| P2 | `_check_sql_scope("DROP TABLE main.prod.orders")` with no schema | `None` (no error). With `main.agent` set: blocked. `ALTER TABLE main.agent.t RENAME TO main.prod.t`: `None`. `len(_CORE)` is 20. | [F-01](02-code-grounding.md#f-01), [F-05](02-code-grounding.md#f-05), [F-26](02-code-grounding.md#f-26) |
| P3 | `mapper.from_permission` with a protocol-shaped request for a `DROP TABLE` | `callId ''`, `action 'write'`, `target 'an object'`, `reason 'the agent asked for permission'` | [F-10](02-code-grounding.md#f-10) |
| P4 | `mapper.from_update` with `usage_update {used, size, cost}` | `[]` | [F-12](02-code-grounding.md#f-12) |
| P5 | `mapper.from_update` with a `tool_call_update` carrying only content | `status 'running'` | [F-14](02-code-grounding.md#f-14) |
| P6 | `mapper.from_update` with `available_commands_update`, `current_mode_update`, `config_option_update`, `session_info_update`, `user_message_chunk` | `[]` for each | [F-13](02-code-grounding.md#f-13) |
| P6b | `mapper.from_update` with a `diff` content block | the diff as a JSON string in `summary` | [F-13](02-code-grounding.md#f-13) |
| P7 | `supervisor.decide` with one completed `db_dbx_run_sql` call whose result has 3 rows, and a report claiming "1,240,000 rows" | verdict `done`; evidence `verified: True`, summary "1,240,000 rows" | [F-07](02-code-grounding.md#f-07) |
| P7b | The same with a French request to create a notebook and no tool call | `needs_evidence` false; verdict `done` | [F-25](02-code-grounding.md#f-25) |
| P8 | `scope.classify_sql` on `COPY INTO …`, `REFRESH MATERIALIZED VIEW …`, `EXECUTE IMMEDIATE …` | `read` for each | [F-05](02-code-grounding.md#f-05) |
| P9 | `context.render` with a path and a body containing the closing tags; `context.parse` on that path | three closing tags in the block; the path is accepted | [F-06](02-code-grounding.md#f-06) |
| P10 | `StdioChannel` over a reader with a 1,024-byte limit, fed one 4,000-byte line then a normal line | first notification is `$/closed`; channel closed; reader raised `ValueError('Separator is found, but chunk is longer than limit')` | [F-15](02-code-grounding.md#f-15) |

One reading was checked and **withdrawn**: the session routes do enforce ownership, in the identity
middleware ([main.py](../../apps/coding-agent/api/main.py) line 214), so there is no cross-user access
to a session by id. Only the body-supplied id in [F-09](02-code-grounding.md#f-09) remains.

Other facts established by command: the two tool-server copies differ (`diff -q`); there is no
`package-lock.json` at the app root; 559 test functions in 32 Python test modules; 67 browser scripts;
11 scripted scenarios; the scripted permission fixture and its unit test use `subject`
([test_adapters.py](../../apps/coding-agent/tests/test_adapters.py) line 94).

## Live investigation

Second pass, the same day, after the owner gave access. The findings are in
[14](14-live-investigation.md); this is the list of what was done.

### Identity and warehouses

Checked first, with the CLI profile `opengenie-dev`, the only valid profile on the machine and the one
whose host matches the workspace the owner named. The identity is an active member of `admins`. One
warehouse exists: Serverless Starter Warehouse, 2X-Small, stopped at the time. No other profile was
used.

### Calls made to the workspace

All reads, except the two statements listed after the table.

| Call | Purpose |
|---|---|
| `current-user me`, `warehouses list` | The working agreement's two checks |
| `apps get coding-agent`, `apps list`, `apps list-deployments coding-agent` | Scopes, identity, compute state, source of the deployment |
| `secrets list-acls`, `secrets list-secrets` on the app's scope (names and ACLs only, no value read) | What the app's identity can read |
| `jobs list`, `jobs get`, `jobs list-runs`, `pipelines list-pipelines` | Shapes of definitions and runs |
| `workspace list` and `get-status` on the owner's home, once with a `..` segment and once with a doubled slash | Revision fields, path handling |
| `postgres list-projects`, `GET /api/2.0/database/instances`, `serving-endpoints list`, `catalogs list` | Lakebase APIs, models, catalogues |
| `query-history list`, `GET /api/2.0/sql/history/queries` | Shape of history, lookup by tag |
| `GET /api/2.0/sandboxes` and three guessed variants | Whether the Sandbox API exists here (it does not) |
| CLI `--help` for `workspace import`, `pipelines update`, `jobs run-now`, `jobs submit`, `jobs reset`, `jobs update`, `apps update`, `query-history list`, `postgres` | Conditional writes, idempotency, options |

Two statements were executed on the warehouse, which started it; it stops itself after ten minutes:

| Statement | Purpose | Result |
|---|---|---|
| `SELECT 1 AS probe` with a comment tag, 5 s wait, continue on timeout | What a response carries; whether a tag can be found again | `SUCCEEDED`; `statement_id`, `total_row_count`, `truncated` present; found in history by tag, `query_id` equal to the statement id |
| A query on `system.information_schema.tables` for four `system` schemas | Whether system tables are reachable | 21 tables listed across `lakeflow`, `query`, `billing`, `access` |

Nothing was created, modified, started (other than the warehouse by those two statements), stopped or
deleted. The app was not started. No secret value was read or printed.

### The agent spike

`opencode` 1.18.19, already installed, run with [tools/acp_spike_client.py](tools/acp_spike_client.py)
against [tools/acp_spike_mcp.py](tools/acp_spike_mcp.py), with Gemini 3.8 Flash on the Vertex project the
owner activated. The child process had an allow-listed environment and an isolated home; the service
account key was passed as a file path and never read by me.

| Scenario | Configuration | Observed |
|---|---|---|
| Two tool calls | the app's deny list | Frame shapes, usage, cost (A-05, A-06) |
| "Which tools can you call?" | the app's deny list | `skill` and `task` listed (A-07) |
| Same | deny by default | Only the MCP tools and `todowrite` (A-08) |
| One tool call | deny by default | The MCP tool still works (A-08) |
| Write with `ask`, rejected | ask | Request shape; failed call; silent end of turn (A-09, A-10) |
| Write with `ask`, allowed | ask | Tool runs after the allow (A-09) |
| Write with `ask`, allowed after 8 s | ask | Arguments arrive at the request, before the answer; silence while waiting (A-09) |
| Write with `ask`, answered `cancelled` | ask | Same as a reject (A-10) |
| Refusal as content, then by raising | the app's deny list | `completed`, then `failed` (A-11) |
| A 100 s tool | deny by default | Failed by the agent at 60.0 s (A-12) |
| Handshake only | deny by default | `mode` values, `effort` values, `set_config_option`, `session/list` (A-02) |
| Re-run from the committed scripts | ask | Reproduced A-09 and A-10 |

The first attempt ran from a folder under the home directory and with a wrong model id. The first
mistake produced A-04, which is a finding; the second produced the "Not Found" error cited in EC-79.
Eleven turns reached the model, for about eight US cents by the agent's own report. The spike's
temporary folders were removed.

### Probes added

| Probe | Call | Observed | Finding |
|---|---|---|---|
| P11 | The pinned agent's failed update after a rejection through `mapper.from_update`; then `supervisor.decide` with that failed call and an empty answer | `error` is empty and the text is in `summary`; verdict `continue`, "Continue the task from where you left off" | [F-38](02-code-grounding.md#f-38), [F-41](02-code-grounding.md#f-41) |
| P12 | The pinned agent's completed update (no title, no kind) and its `usage_update` through the mapper | status `completed` kept; usage yields `[]` | [F-12](02-code-grounding.md#f-12) |
| P13 | The pinned agent's permission request through `mapper.from_permission` | `callId ''`, `action 'write'`, `target 'an object'` | [F-10](02-code-grounding.md#f-10) |

### Pages read directly in the second pass

[App authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth) (the first
16,000 characters, which include the list of supported scopes),
[HTTP headers](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/http-headers),
[Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations),
the [Sandbox API](https://docs.databricks.com/api/sandbox/v1/create-sandbox) reference (first 6,000
characters), and the [API scopes](https://docs.databricks.com/api/workspace/scopes) page, of which the
first 14,000 characters were read and the rest parsed by script for the operations under each scope.

## Checks on this document set

| Check | Tool | Result |
|---|---|---|
| Internal links and heading anchors | `web/scripts/verify-spec-links.mjs` | see [README](README.md#checks) |
| ASCII wireframes on a grid | `web/scripts/verify-spec-ascii.mjs` | see [README](README.md#checks) |
| Mermaid blocks parse | `web/scripts/verify-spec-mermaid.mjs` | see [README](README.md#checks) |
| Reference-style code links resolve | a path check over the definitions at the foot of [02](02-code-grounding.md) | see [README](README.md#checks) |

The results are recorded once, in the README, so they cannot disagree with this page.

## What was not verified

- **What the app's forwarded user token is answered.** The CLI identity has every API scope; the app was
  not started. That the Jobs tools are refused for a user of the app rests on the platform's list of
  supported scopes, not on an observed refusal.
- **Anything that needs a write on the workspace:** whether a scheduled materialized view can be
  created from the warehouse as the user, whether `object_id` survives an overwrite, how a write with
  `..` is treated, whether the agent's Lakebase tools can create an instance on Free Edition. Listed
  with what each would write in [14](14-live-investigation.md#what-still-needs-your-permission).
- **Whether a non-administrator can read the system tables.** The owner is an administrator.
- **Whether the agent's 60 s limit can be configured.** It was observed, not traced to a setting.
- **Other agent versions and other models.** Every agent fact is from 1.18.19 with one model.
- The Genie Code statements, and the opencode statements still labelled R.
- The test suites were not run. Counts are of functions in files, not of passing tests.
- Performance of the app. Every complexity statement in [08](08-lenses-complexity.md#the-on-lens) is
  derived from the code path. The only measurements are the token counts and timings of the spike.
- Parts of files outside the ranges listed above.
