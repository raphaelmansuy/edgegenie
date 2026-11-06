# Databricks working agreement

Scope: this repository and any Databricks workspace work driven from it.
Read this before your first tool call and follow it for the rest of the session.

## Session start

1. Call `dbxnb_dbx_whoami` to confirm which identity and workspace you are using.
   Never assume you are in the workspace the user mentioned.
2. Call `dbxnb_dbx_list_warehouses`. Note the running warehouse; SQL will use it
   by default.

## Data rules

- **Never guess a column name.** Before writing SQL against a table you have not
  used in this session, call `dbxnb_dbx_describe_table`. If you cannot find the
  table, call `dbxnb_dbx_search_tables`.
- **State the grain** before aggregating ("one row per trip, so `avg(fare)` is a
  trip-level average").
- **Unity Catalog is the permission boundary.** If a query returns a permission
  error, do not attempt workarounds; report it.

## Tool choice

| Need | Tool |
|---|---|
| SQL you have already written | `system.ai.dbsql` |
| Question phrased in business terms | `system.ai.genie_one_mcp` |
| Notebooks, jobs, pipelines, lineage, grants | `dbxnb_*` |
| Run code / install packages | `system.ai.sandbox` |
| Current docs on a Databricks feature | `system.ai.web_search` |

## Reading tool results — non-negotiable

- If a response contains `next_offset`, you have **not** seen the whole resource.
  Page through it, or use `dbxnb_dbx_grep_notebook` to narrow the question.
- If a response contains `no_matches: true`, your pattern was wrong. Retry with a
  looser pattern before drawing any conclusion.
- **Never state a fact about a file you have not fully read.** If you only saw
  part of it, say which part.

## Writing

- Writes are disabled unless the server was started with `NBMCP_ALLOW_WRITES=1`.
  If a write fails with a permission error, that is expected — tell the user
  rather than retrying.
- Before overwriting a notebook, read it first and show the user what will change.

## Answering

- Cite line numbers when reporting on notebook content.
- If a tool fails twice, stop and report the failure instead of trying a third
  variation.
- Keep final answers short: what you did, what you found, what you could not do.
