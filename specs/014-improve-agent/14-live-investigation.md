# 14 · Live investigation: the workspace and the pinned agent

[Map](README.md) · decisions it produced: [12](12-decisions-open-questions.md) · findings it changed: [02](02-code-grounding.md#findings-register) · record of every call: [13](13-validation-record.md#live-investigation)

On 13 November 2026 the owner gave access to the development workspace and to a Gemini 3.8 Flash
endpoint on Vertex. This page records what was observed, what it corrects in the first version of this
spec, and which questions it settles. Decisions are made from the
[first principles](00-five-whys-first-principles.md#first-principles) and recorded in
[12](12-decisions-open-questions.md#decisions).

## Rules of engagement

- **Workspace: reads only**, through the Databricks CLI profile `opengenie-dev`, as the signed-in owner.
  Two statements were executed on the SQL warehouse: a tagged `SELECT 1` and a metadata query on
  `system.information_schema`. Nothing was created, changed, started, stopped or deleted. The app was
  not started.
- **Agent: local only.** The installed `opencode` 1.18.19 was run in a throwaway folder with an isolated
  home, against a do-nothing MCP server, with Gemini 3.8 Flash. Eleven short turns, about eight US cents
  in total by the agent's own report.
- **Identity caveat.** The CLI token carries every API scope. It shows what the platform does and how
  its APIs behave; it does **not** show what the app's forwarded user token may do. Scope statements
  below come from the app's own configuration and from the platform documentation.
- The scripts and configurations are in [tools](tools): `acp_spike_client.py`, `acp_spike_mcp.py` and three
  `opencode.*.json` files. They were re-run from that folder and reproduce the results.

## Workspace facts

`L` rows were observed on the workspace. `V` rows were read by me in the platform documentation on the
same day ([app authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth),
[API scopes](https://docs.databricks.com/api/workspace/scopes),
[Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations),
[Sandbox API](https://docs.databricks.com/api/sandbox/v1/create-sandbox)).

| ID | Fact | Source | Consequence |
|---|---|---|---|
| L-01 | The signed-in identity is a workspace administrator. The workspace is Free Edition: one serverless 2X-Small warehouse (auto-stop 10 minutes), catalogues `workspace`, `samples`, `system`. | L | Every limit in L-13 applies to the reference deployment. |
| L-02 | The app's compute is stopped ("stopped due to workspace or account status") and it has no active deployment. The last of 20 deployments was built from Git, commit `d2d4754`, source path `apps/coding-agent`. | L | A Git deployment runs `npm install` on the caret range: see L-16. |
| L-03 | The live app declares eleven user scopes: the nine in [databricks.yml](../../databricks.yml) **plus `postgres` and `apps`**. | L | The bundle and the deployment disagree. The file's own comment says an update is a full replacement, so a bundle deployment would remove both ([F-39](02-code-grounding.md#f-39)). |
| L-04 | Scopes an app can request for user authorization: `ai-functions`, `ai-gateway`, `apps`, `files`, `genie`, `model-serving`, `postgres`, `sandbox`, `sql`, `sql:read`, `sql:restricted-query`, `vector-search`, and the SDK scopes `catalog.catalogs`, `catalog.connections`, `catalog.schemas`, `catalog.tables`, `workspace.workspace`. **`jobs` and `pipelines` exist as API scopes and are not in that list.** | V | An app cannot create, run, read or repair a job or a pipeline as the user. Not a missing grant: no grant exists. Settles spike S2. |
| L-05 | The `sql` scope covers statement execution, saved queries, alerts and warehouses (including start and stop). Query history is folded into `sql`. `apps` covers create, deploy, start, stop, delete. `postgres` covers both Lakebase APIs. | V | Four of the twenty core tools are unusable as the user on the live app (the Jobs ones); eight with the bundle as written. |
| L-06 | The app's service principal has `READ` on the secret scope that holds the key-encryption key and the Vertex key. Its OAuth client id and secret are injected into the app's environment. | L, V | Code run "as the app" can read the key that decrypts every user's stored provider key. An app has exactly one service principal and it cannot be replaced or narrowed ([F-08](02-code-grounding.md#f-08) becomes High; [D17](12-decisions-open-questions.md#decisions)). |
| L-07 | A workspace object's status has `object_id`, `created_at`, `modified_at`. There is no version tag, and `workspace import` has no conditional option. | L | Revision is `(object_id, modified_at)`. A write is check, write, read back; the remaining window is risk R2. Settles spike S6. |
| L-08 | A read with a `..` segment in the path is refused by the workspace with "Bad Request". A doubled slash resolves to the same object. | L | The platform rejects traversal on reads. Writes were not tested. The fence still must not depend on it ([F-02](02-code-grounding.md#f-02)). Settles spike S8 for reads. |
| L-09 | A job's definition has no modification time. `run-now` and `submit` accept an idempotency token. A job records `run_as_user_name`. | L | Job revision is a hash of its settings. A lost submit of a run is resolvable. |
| L-10 | `pipelines update` accepts `expected-last-modified`. The workspace has no pipeline. Free Edition allows one active pipeline per type. | L, V | Pipelines are the one asset with a native conditional write. |
| L-11 | Every statement response carries `statement_id`, and the manifest carries `total_row_count` and `truncated`. A comment tag survives into query history, where `query_id` equals the statement id. | L | A lost statement submit is resolvable by tag, as the same user. Settles spike S7. Confirms [F-21](02-code-grounding.md#f-21): the id and the total are there and the tool discards them. |
| L-12 | `system.lakeflow` (`jobs`, `job_tasks`, `job_run_timeline`, `job_task_run_timeline`, `pipelines`, `pipeline_update_timeline`), `system.query.history`, `system.billing` (`usage`, `list_prices`) and `system.access` (`table_lineage`, `column_lineage`, `audit`) are queryable. | L | **Jobs, pipelines, lineage and compute cost can be observed as the user through the `sql` scope alone** ([D18](12-decisions-open-questions.md#decisions)). Grants for non-administrators were not checked. |
| L-13 | Free Edition: an app stops 24 hours after it was started, updated or redeployed; compute is shut for the day when the quota is exceeded; at most three apps, five concurrent job tasks, one Lakebase project. | V | "Continues while you are away" is bounded by the app's uptime. Recovery by native id is a requirement, not an optimisation (EC-75 in [09](09-edge-cases.md#operations-and-long-running-work)). |
| L-14 | The Sandbox API (run a command in a container, scope `sandbox`) is documented as Beta. `GET /api/2.0/sandboxes` answers "The requested API is not available" here. | V, L | A route to run code as the user exists on the platform and not on this workspace. The run port must admit it; nothing may depend on it. |
| L-15 | The user's home has an `.assistant` folder holding `.mcp_servers.json`. There is no skills folder and no instruction file. | L | Confirms the Genie Code folder convention live. |
| L-16 | The npm registry's current `opencode-ai` is 1.19.5. The app declares `^1.18.19` with no lockfile. The local binary is 1.18.19. | L | The next build would install a version nobody tested here ([F-04](02-code-grounding.md#f-04)). |
| L-17 | The workspace serves eleven Databricks-hosted models and no Gemini. The app's default model is on Vertex. | L | The default model depends on a credential outside the workspace. |
| L-18 | The older Lakebase instances API answers with an empty list; the app's own storage is a project in the newer API. | L | The agent's Lakebase tools and the app's storage use different API generations. With one project per account on Free Edition, exam M6 may not be runnable here. Not tested. |

## Agent facts

Observed from `opencode` 1.18.19 with Gemini 3.8 Flash. Every row is a frame the client received.

| ID | Fact | Consequence |
|---|---|---|
| A-01 | `initialize` answers protocol 1 with `loadSession`, `mcpCapabilities {http, sse}`, `promptCapabilities {image, embeddedContext}`, `sessionCapabilities {close, fork, list, resume}`. | `resume` and `list` can be used today ([AG-44](03-requirements.md#ag-44)). No `delete` in this version. |
| A-02 | `session/new` returns `configOptions`: `model`, `mode` with the values `build` and `plan`, and `effort` (low, medium, high) once the model catalogue is cached. `session/set_config_option` with `mode: plan` succeeds. `session/list` works. | The agent has a native plan mode ([D19](12-decisions-open-questions.md#decisions)). |
| A-03 | An `available_commands_update` arrives before the first prompt: `customize-opencode`, `init`, `review`. | Commands are available to surface ([AG-45](03-requirements.md#ag-45)). |
| A-04 | With the spike's folder under the home directory, the agent also advertised every personal skill it found by **walking up from its working folder**, and the context for a two-tool turn was 20,598 tokens. From a folder outside the home it was 5,414. | Ancestor folders are part of the prompt and of the bill ([F-40](02-code-grounding.md#f-40)). |
| A-05 | A tool call arrives as `tool_call` (status `pending`, empty input), then `tool_call_update` (`in_progress`, with the arguments), then `tool_call_update` (`completed`) carrying **no title, no kind and no input**. There is **no `name` field** in this version; `title` is `<server>_<tool>`. The result is in `content` and in `rawOutput.output`; an error is in `rawOutput.error`. | Partial updates are real ([F-14](02-code-grounding.md#f-14)). Identity must be `name` when present, else `title` ([F-13](02-code-grounding.md#f-13), corrected). The mapper looks for the error in the input ([F-41](02-code-grounding.md#f-41)). |
| A-06 | `usage_update` is `{used, size, cost: {amount, currency: "USD"}}` at the top level; the cost is cumulative for the session. The prompt response carries `usage` with `inputTokens`, `outputTokens`, `totalTokens`, and `cachedReadTokens` or `thoughtTokens` when relevant. | Confirms [F-12](02-code-grounding.md#f-12) against the real agent: the app drops the meter. A trivial turn cost 0.3 to 0.8 cents. |
| A-07 | With the app's deny list the model lists these callable tools: the MCP tools, `todowrite`, **`skill` and `task`**. | Two built-ins the list does not name are live, one of which starts sub-agents ([F-04](02-code-grounding.md#f-04), confirmed). |
| A-08 | With `"*": "deny"`, `"todowrite": "allow"`, `"probe_*": "allow"` the model lists only the MCP tools and `todowrite`, the MCP tools still work, and the context falls from 5,414 to 4,374 tokens. | Deny by default works on the pinned version, wildcards included. Settles spike S3. |
| A-09 | With one MCP tool set to `ask`, the agent sends `session/request_permission` with exactly `sessionId`, `toolCall`, `options`. `toolCall` has `toolCallId`, `title`, `kind`, `status`, `locations` and an **empty `rawInput`**. The arguments arrive on a `tool_call_update` for the same id at the same instant, before the person answers. Options: `once` (allow_once), `always` (allow_always), `reject` (reject_once). The tool runs only after an allow. | The protocol-native review works. Settles spike S1. The card must take its arguments from the tool-call update, not from the request (EC-20 in [09](09-edge-cases.md#acp-and-agent-process)). Through the app's mapper this request has no call id and reads "write … an object" ([F-10](02-code-grounding.md#f-10), confirmed). |
| A-10 | After a reject, and identically after the `cancelled` outcome, the tool call is `failed` with "The user rejected permission to use this specific tool call", and **the turn ends with `end_turn` and no text**. | [F-11](02-code-grounding.md#f-11) changes nothing observable on this agent. But an empty answer makes the app's supervisor send "continue the task" ([F-38](02-code-grounding.md#f-38)). |
| A-11 | A refusal returned as ordinary content is a `completed` call. A refusal raised by the tool is a `failed` call. | Confirms the second half of [F-07](02-code-grounding.md#f-07) on the real agent. |
| A-12 | A tool that sleeps 100 s is **failed by the agent at exactly 60 s** with "MCP error -32001: Request timed out". Nothing is emitted in between. The tool keeps running on the server. | The binding limit on a tool call is the agent's, and it is 60 s ([F-19](02-code-grounding.md#f-19), corrected). A call that times out has an unknown effect, and the model may repeat it ([AG-27](03-requirements.md#ag-27)). |
| A-13 | The agent starts and works with an environment of `PATH`, an isolated `HOME`, the XDG folders and the three Vertex variables. | An allow-listed environment is feasible ([AG-04](03-requirements.md#ag-04)). |

## Corrections to this spec

The first version was written from the code and the documentation. Three statements in it were wrong or
incomplete, and are corrected where they stood.

| Was | Is | Where |
|---|---|---|
| "The ETL skill tells the agent to wait 300 s, and the app's idle guard fails the turn at 180 s." | The agent itself fails any MCP call at 60 s (A-12). The app's guard is never reached by a tool wait. The run continues with no id returned, so the agent may launch it again. | [F-19](02-code-grounding.md#f-19), [AG-20](03-requirements.md#ag-20) |
| "Eight of twenty tools need scopes the deployed app does not request." | The live app has `apps` and `postgres`, so four are unusable; the bundle as written would make it eight. The Jobs ones cannot be fixed by a grant: the platform offers apps no such user scope. | [F-18](02-code-grounding.md#f-18), [F-39](02-code-grounding.md#f-39) |
| "Tool identity should come from the protocol's `name` field." | The pinned agent does not send `name`. Use it when present, fall back to `title`, and never let evidence depend on either. | [F-13](02-code-grounding.md#f-13), [AG-42](03-requirements.md#ag-42) |
| Tool reply bound of 45 s. | 30 s: half the agent's limit, leaving room for the workspace call inside it. | [AG-20](03-requirements.md#ag-20) |

## Spikes answered

| Spike | Answer | Evidence |
|---|---|---|
| S1 protocol-native permission | **Yes.** Arguments come on the tool-call update. | A-09, A-10 |
| S2 user scopes for jobs, pipelines, apps, databases | **Apps and databases: yes. Jobs and pipelines: no such scope for apps.** | L-03, L-04, L-05 |
| S3 deny by default | **Yes**, with wildcards. | A-07, A-08 |
| S4 pipelines as the user | **Not from an app.** The API has a conditional update. SQL-defined scheduled tables were not tried: that needs a write. | L-04, L-10 |
| S5 a narrower run identity | **Not within one app.** The Sandbox API would run code as the user and is not available here. | L-06, L-14 |
| S6 revisions and conditional writes | **`(object_id, modified_at)`; no conditional import. Pipelines have one.** | L-07, L-09, L-10 |
| S7 lost statement submit | **Resolvable by tag in query history.** | L-11 |
| S8 `..` in a path | **Refused on reads.** Writes untested. | L-08 |

## What the evidence decides

Each line is a decision recorded in [12](12-decisions-open-questions.md#decisions), with the principle
that forces it.

1. **Identity tiers** (D16, [FP-1](00-five-whys-first-principles.md#first-principles)). The agent acts as
   the user wherever a user scope exists: SQL, workspace objects, catalogue reads, apps, Lakebase. Where
   none exists, jobs and pipelines, it does not borrow another identity: it writes the definition as
   code for the user to deploy, and observes through system tables.
2. **No model-written code under the app's identity** (D17, FP-1). L-06 shows that identity can read the
   key that protects every user's credentials. Agent-initiated runs as the app are off unless a
   deployment provides a separate run identity.
3. **Observe through SQL** (D18, [FP-5](00-five-whys-first-principles.md#first-principles)). Job runs,
   pipeline updates, lineage and compute cost are read from system tables with the user's `sql` scope.
4. **Review by default, collected in the protocol** (D19, D3,
   [FP-2](00-five-whys-first-principles.md#first-principles)). A-09 shows the agent blocks on a human
   answer at no token cost. The server still decides.
5. **A refusal ends the matter** (new [AG-18](03-requirements.md#ag-18)). A-10 shows the agent goes
   silent after a rejection; the supervisor must not push it to try again.
6. **Thirty seconds, and a repeated submit is the same operation** (D7, new
   [AG-27](03-requirements.md#ag-27)). A-12.
7. **The agent's folder is part of its prompt** ([AG-03](03-requirements.md#ag-03)). A-04.

## What still needs your permission

These would settle the remaining unknowns and each needs a write or a start on the workspace. None was
done.

| ID | Test | What it writes | Settles |
|---|---|---|---|
| S9 | Create and drop a scheduled materialized view and a streaming table in a scratch schema, from the SQL warehouse. | Two tables in a scratch schema, removed afterwards. | Whether incremental ETL can be delivered as the user through `sql` alone (S4, second half). |
| S10 | Import a notebook over an existing scratch notebook, once with a `..` path. | One scratch notebook. | Whether `object_id` survives an overwrite, and traversal on writes (L-07, L-08). |
| S11 | Start the app and send one agent turn that calls a Jobs tool. | App compute for the test. | The exact refusal the forwarded token receives ([F-18](02-code-grounding.md#f-18) on the real token). |
| S12 | Read whether the agent's 60 s MCP timeout is configurable for servers passed over ACP. | Nothing on the workspace. | Whether the bound could be raised; the design does not need it. |
| S13 | Deploy a second, secret-free app as a run identity. | One app (Free Edition allows three). | Whether D17 can be relaxed. |
