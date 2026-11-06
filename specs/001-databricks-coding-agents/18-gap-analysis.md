# 18 · Gap analysis: Genie Code class assistant

Verified on the deployed app with the real agent (OpenCode 1.19.5, 19 tools):
15/15 end-to-end steps pass; screenshots in `e2e/screenshots/genie-deployed/`.

## Gaps found and closed

| # | Gap vs. Genie Code | Fix | Proof |
|---|---|---|---|
| G1 | No workspace tree: only a folder text box | Lazy, keyboard-navigable tree (WAI-ARIA), search, new folder, "work here" | e2e 2-5 |
| G2 | The assistant could not see what the user was looking at | Open notebook, file, folder or table rides along as context (references only; server re-reads with the user's token, fenced as untrusted data, size-capped) | e2e 8-9 |
| G3 | No notebook view | Cells with syntax highlighting, parsed from SOURCE format | e2e 5 |
| G4 | No Unity Catalog browsing | Catalog tab: schema, columns, 10 sample rows (names validated, no SQL injection) | e2e 6-7 |
| G5 | `@` mentions | Picker in the composer; chips in the transcript | e2e 8 |
| G6 | Plan was invisible | ACP `plan` updates render as a checklist | e2e 11 |
| G7 | Read-only questions were blocked ("Still missing: Do not change anything.") | Constraint sentences are not requirements; read-only mode with attached context | pytest, e2e 10 |
| G8 | Cost and time unseen | Per-turn time and tokens in the footer | e2e 12 |
| G9 | Agent touched a notebook, no way to look | "Open" button on notebook tool cards | e2e 13 |

## Defects found only on the deployed app, and fixed

| Symptom | Root cause | Fix |
|---|---|---|
| Files tab: "cannot reach the workspace" | The platform may give `DATABRICKS_HOST` without `https://`; httpx raised and the API returned 500 | `normalize_host`; transport errors become 502; the UI shows the server's reason |
| Home folder was `/Users/78760067054768@7474654624275247` | Behind the proxy `x-forwarded-user` is `<id>@<app id>`, not a folder name | Home is named by `x-forwarded-email`; the id stays the audit identity |
| Tree: "you do not have access to /" | The app declared no user scopes, so the forwarded token only had `iam.*` | Scopes added (below). **The app must be restarted** (stop, start, deploy) for them to apply to the forwarded token |
| 503 "tool server did not start", no output | Tool server started with bare `python3`, which in the container is not the interpreter with our dependencies; stderr went to `/dev/null` | Use `sys.executable`; stderr to a log file and reported; wait up to 15 s |

User authorization scopes the app needs:
`sql`, `files`, `model-serving`, `ai-gateway`, `genie`, `workspace.workspace`,
`catalog.catalogs:read`, `catalog.schemas:read`, `catalog.tables:read`
([docs](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)).
Set with `databricks apps update coding-agent --json '{"user_api_scopes":[...]}'`.

## Second round: agent quality and links (found by using the deployed app)

| Symptom | Root cause | Fix |
|---|---|---|
| Agent: "set DATABRICKS_HOST and DATABRICKS_TOKEN", then gave up | The tool server never received the user's token; a deployed app has no PAT | The user's forwarded token goes to the tool server through a private 0600 file, refreshed every turn, removed on archive. Never in the agent's working folder |
| Agent tried to write to `/Shared` | Nobody told it where it may write | Per-session rules in `AGENTS.md`: working folder, schema, name prefixes, what to do on refusal |
| Four identical retries of a failing call | A 403 reached the model as an httpx trace | The tool server turns 401/403 into "permission denied ... do not retry"; the rules say a refusal is final |
| Turn hung on a built-in `read` | opencode's own file and shell tools wait for a human and touch the container, not the workspace | Built-ins denied (least privilege); planning stays on |
| `gpt-oss-120b` ended turns after reasoning with no tool call, five times | Reasoning-only completions; the same continue prompt gave the same result | Continue prompt differs when no tool was called. Same task on every served model: Llama 4 Maverick, Qwen3-Next and Llama 3.3 all completed; **Maverick** was fastest and best (2.9 s explain, describe then write). Now the default |
| Llama and Qwen failed at once: "max_tokens 24000 cannot exceed 8192" | One output limit for every model | Per-endpoint limits |
| The model list offered Claude, which this workspace does not serve | Static allow-list | `/api/models` intersects with the workspace's ready chat endpoints |
| Error list showed raw `[{"type":"content",...}]` | Serialised ACP blocks | Unwrapped to the message |
| Message did not appear until the server echoed it | Waited for the event | Shown at once, replaced by the server's turn |
| Files footer overlapped the tree | Scroll container and footer shared a box | Tree scrolls, footer is fixed |

**Links into Databricks** (from the tree, viewer, tool cards, the session strip and any workspace path in
an answer): a notebook goes to `/editor/notebooks/<id>`, a file to `/editor/files/<id>`, a folder to
`/browse/folders/<id>`, a table to `/explore/data/<c>/<s>/<t>`. Without an id the link uses
`/#workspace/<path>`, which needs no lookup. All open in a new tab with `noopener`.

## Residual gaps (not done)

- **Running notebooks.** Jobs are not an Apps user scope, so `run notebook` is refused. The agent now
  reports the notebook as written, not executed. Options: a service-principal run path (a design
  decision, because it runs as the app, not the user), or SQL-only execution.

- **Jobs, pipelines, clusters under the user's identity.** No supported Apps scope covers them, so the
  tool server's job and pipeline tools may be refused with the user's token. Not tested end to end.
- Inline diff with accept/reject on a notebook edit; running a cell from the viewer.
- Sessions do not survive an app restart (in memory).
- `@` search covers notebooks and files, not tables. No rename or delete in the tree (by design:
  the app never deletes workspace objects).
- `/Shared` is not listed as a root.
- Real-agent e2e used an OAuth bearer, not a browser SSO session.
