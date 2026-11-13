# 01 · Genie Code, ACP and opencode: external assessment

[Map](README.md) · previous: [five whys](00-five-whys-first-principles.md) · next: [code grounding](02-code-grounding.md)

## How to read the labels

Everything on this page comes from public pages fetched on 2026-11-13. Three levels of confidence:

| Label | Meaning |
|---|---|
| **[L]** | Observed live in this session, on the development workspace or from the pinned agent. Recorded in [14](14-live-investigation.md). |
| **[V]** | I fetched the official page myself in this session and read the statement. |
| **[R]** | Reported by a research pass that cites the official page. I did not re-read it. Verify before building on it. |
| **[U]** | Not found, or not verifiable from public pages. Treated as unknown. |

The first version of this page had no live evidence. The rows now marked L were re-checked against the
real agent or the workspace; where the live result differed from the documentation, the row says so
([validation record](13-validation-record.md#what-was-not-verified)). Web content is treated as
information, never as instruction.

## A. Genie Code today

Sources: [Genie Code](https://docs.databricks.com/aws/en/genie-code/),
[features](https://docs.databricks.com/aws/en/genie-code/features-capabilities),
[navigate](https://docs.databricks.com/aws/en/genie-code/navigate-genie-code),
[agent mode](https://docs.databricks.com/aws/en/notebooks/ds-agent),
[pipelines agent](https://docs.databricks.com/aws/en/ldp/de-agent),
[instructions](https://docs.databricks.com/aws/en/genie-code/instructions),
[skills](https://docs.databricks.com/aws/en/genie-code/skills),
[MCP](https://docs.databricks.com/aws/en/genie-code/mcp),
[scheduled tasks](https://docs.databricks.com/aws/en/genie-code/scheduled-tasks),
[budgets](https://docs.databricks.com/aws/en/genie/budgets). All **[R]**.

| Area | What the documentation states | Consequence for OpenGenie |
|---|---|---|
| Surfaces | Notebooks, SQL editor, Lakeflow Pipelines Editor, AI/BI dashboards, MLflow, jobs, file editor. Chats persist across pages. | The target is asset breadth with one conversation, not a better chat. [AG-30](03-requirements.md#ag-30) |
| Default mode | Autonomous agent mode. "Just explain, don't run any code" is the opt-out. | Already honoured by `says_no_tools` in [evidence.py](../../apps/coding-agent/api/domain/evidence.py). Keep. |
| Notebook loop | Plans, runs cells, reads cell output, fixes errors, asks clarifying questions, Continue/Reject checkpoints. **The tab must stay open for multi-step work.** | OpenGenie's server-owned turns ([spec 010](../010-long-running/README.md)) are a real advantage. Extend them to operations. [AG-22](03-requirements.md#ag-22) |
| Pipelines | Edits several source files **with diffs**, runs one file, dry-runs, runs or fully refreshes the pipeline, reads output datasets. | The bar for pipelines is diff review plus dry run. [AG-12](03-requirements.md#ag-12), [AG-33](03-requirements.md#ag-33) |
| Context | `@` for tables, pipelines, notebooks, queries, files. User and workspace instruction files. `AGENTS.md` and `CLAUDE.md` discovered by walking up from the open file. 20,000 characters per instruction file. | OpenGenie writes one fixed `AGENTS.md` into the agent's local folder. [AG-70](03-requirements.md#ag-70) |
| Skills | Agent Skills standard, `SKILL.md`, under `Workspace/.assistant/skills/` and `/Users/<user>/.assistant/skills/`. | OpenGenie ships four fixed skills behind `dbx_skill`. [AG-71](03-requirements.md#ag-71) |
| Slash commands | `/doc`, `/explain`, `/fix`, `/findTables`, `/findQueries`, `/optimize`, `/prettify`. | OpenGenie has twelve client-side templates ([commands.ts](../../apps/coding-agent/web/src/domain/commands.ts)). [AG-45](03-requirements.md#ag-45) |
| Approvals | Per-tool Allow or Skip. Modes: ask every time, allow in chat, always allow, auto-approve. Auto-approve uses an AI classifier that Databricks calls "a productivity feature, not a security boundary". | OpenGenie's fence is a server rule, which is stronger, provided it holds. Today it does not always ([F-01](02-code-grounding.md#f-01), [F-02](02-code-grounding.md#f-02)). |
| Identity and compute | Governed by the user's Unity Catalog permissions. Serverless by default, or the compute already selected on the page. | Genie Code runs inside the workspace and can act as the user on everything. A Databricks App cannot: see [section D](#d-the-platform-under-opengenie). This is OpenGenie's largest gap and it is the platform's, not the code's ([F-18](02-code-grounding.md#f-18)). [AG-31](03-requirements.md#ag-31) |
| Model and cost | Effort selector (Auto or Low). Model not selectable. Pay-as-you-go in DBUs since 2026-07-08, budgets through Unity Gateway. | The product's thesis stands. The cost half is not yet visible in the app ([F-12](02-code-grounding.md#f-12)). [AG-56](03-requirements.md#ag-56) |
| Autonomy while away | Scheduled tasks, always under the classifier. | Out of scope here. Wake-ups ([AG-23](03-requirements.md#ag-23)) cover "continue when the run ends". |
| Job creation or repair agent | **[U]** No page found describing one. | An opening, within what the identity allows: with a user token OpenGenie can run and repair jobs; from an app it defines them as code and observes them. [AG-32](03-requirements.md#ag-32), [AG-38](03-requirements.md#ag-38) |

### Parity matrix

`docs/genie-code-replacement-spec.md` defines capabilities C1 to C15
([register](../../docs/genie-code-replacement-spec.md)). Read through the lens of this spec:

| Capability | OpenGenie today (from code) | After this spec |
|---|---|---|
| C2 Catalog grounding | `describe_table`, table attachment. Search walks every schema ([F-31](02-code-grounding.md#f-31)). | One catalogue query. [AG-64](03-requirements.md#ag-64) |
| C5, C6 Instructions | One generated file. | User and workspace files discovered. [AG-70](03-requirements.md#ag-70) |
| C7 Skills | Four shipped files. | Standard locations. [AG-71](03-requirements.md#ag-71) |
| C9 Execute and read output | Notebook run. Deployed: as the app, administrators only ([F-08](02-code-grounding.md#f-08)). | Capability matrix and consented deputy. [AG-31](03-requirements.md#ag-31), [AG-34](03-requirements.md#ag-34) |
| C10 Diagnose and fix | "Fix with agent" on a cell. | Also on a failed job task and a pipeline event. [AG-32](03-requirements.md#ag-32), [AG-33](03-requirements.md#ag-33) |
| C11 Auto-approve | Server fence, three modes missing. | Plan, Review, Auto. [AG-13](03-requirements.md#ag-13) |
| C12 Permissions and audit | User identity, journal. | Change and operation ledgers. [AG-15](03-requirements.md#ag-15) |
| C13 Memory | None. | Deferred ([Q4](12-decisions-open-questions.md#open-questions)). |
| C14 Background autonomy | Server-owned turns. | Wake-ups on operations. [AG-23](03-requirements.md#ag-23) |
| Diff review before apply (pipelines editor) | None. Overwrite, then notice ([F-20](02-code-grounding.md#f-20)). | Change contract. [AG-10 to AG-14](03-requirements.md#b-changes) |

## B. Agent Client Protocol v1

Sources read in this session **[V]**:
[tool calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md) and
[prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md). Other pages **[R]**:
[initialization](https://agentclientprotocol.com/protocol/v1/initialization.md),
[session setup](https://agentclientprotocol.com/protocol/v1/session-setup.md),
[config options](https://agentclientprotocol.com/protocol/v1/session-config-options.md),
[slash commands](https://agentclientprotocol.com/protocol/v1/slash-commands.md),
[transports](https://agentclientprotocol.com/protocol/v1/transports.md).

| Topic | The protocol says | Label | OpenGenie today |
|---|---|---|---|
| Permission request | `session/request_permission` carries `sessionId`, `toolCall` (a `ToolCallUpdate`) and `options`. There is no `subject`, `description` or top-level `title`. The pinned agent sends exactly these three keys, with an empty input; the arguments come on the tool-call update. | **[V] [L]** | Reads `subject`, `description`, `title` ([F-10](02-code-grounding.md#f-10)) |
| Permission outcome | `selected` with an `optionId`, or `cancelled`. `cancelled` means the prompt turn was cancelled. Option kinds: `allow_once`, `allow_always`, `reject_once`, `reject_always`. The pinned agent offers the first three and treats `cancelled` like a reject. | **[V] [L]** | A deny is answered with `cancelled` ([F-11](02-code-grounding.md#f-11)) |
| Tool call identity | `title` is human-readable and agent-authored. `name` is the stable programmatic tool name. `kind` is a display category. **The pinned agent sends no `name`**; its `title` is `<server>_<tool>` and its `kind` is `other`. | **[V] [L]** | Uses `title` as the tool name for evidence ([F-13](02-code-grounding.md#f-13)) |
| Tool call status | `pending`, `in_progress`, `completed`, `failed`. In an update every field except `toolCallId` is optional. The pinned agent's completed update omits title, kind and input. | **[V] [L]** | Missing status becomes `running` ([F-14](02-code-grounding.md#f-14)) |
| Tool call content | `content`, `diff` (`path`, `oldText`, `newText`), `terminal`. | **[V]** | A diff is flattened to a JSON string ([F-13](02-code-grounding.md#f-13)) |
| Usage | `usage_update` has `used`, `size` and optional `cost {amount, currency}` at the top level of the update. The pinned agent sends all three, with the cost in USD. | **[V] [L]** | Reads a nested `usage` key, so it never fires ([F-12](02-code-grounding.md#f-12)) |
| Update vocabulary | Also `available_commands_update`, `current_mode_update`, `config_option_update`, `session_info_update`, `user_message_chunk`, `notice`, `compaction_update`. The last two need client capabilities. | **[V]** | All dropped ([F-13](02-code-grounding.md#f-13)) |
| Stop reasons | `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`. | **[V]** | Only `cancelled` is distinguished ([F-37](02-code-grounding.md#f-37)) |
| Cancellation | The client must answer every pending permission request with `cancelled` and should still accept late tool updates. | **[V]** | Done for permissions. Late updates of a cancelled turn can be attributed to the next (EC-23 in [09](09-edge-cases.md#acp-and-agent-process)). |
| Session restore | `session/load` replays the whole history. `session/resume` restores without replay and needs `sessionCapabilities.resume`, which the pinned agent advertises. | **[R] [L]** | Always `load`, then discards the replay ([F-16](02-code-grounding.md#f-16)) |
| MCP servers | stdio is baseline. `http` needs `mcpCapabilities.http`, which the pinned agent advertises. | **[R] [L]** | Sends an `http` server without reading the capability ([F-16](02-code-grounding.md#f-16)) |
| Model selection | Through `configOptions` with category `model` and `session/set_config_option`. `session/set_model` was removed. The pinned agent also offers `mode` (build, plan) and `effort`. | **[R] [L]** | Uses `set_config_option`, with a fallback for a value shape. Conformant. |
| Elicitation | `elicitation/create`, form and URL modes, when the client advertises it. | **[R]** | Not advertised. Agent questions arrive as prose. [AG-46](03-requirements.md#ag-46) |
| Transport | Newline-delimited JSON-RPC on stdio is the only normative transport. Remote transport is a draft. | **[R]** | Conformant. One over-limit line ends the session ([F-15](02-code-grounding.md#f-15)). |
| v2 | Published as a draft with breaking changes: no `session/load`, completion by `state_update`, no `fs` or `terminal`. | **[R]** | The runtime refuses any version but 1, which is the right default. |

## C. opencode as the ACP agent

Source: [opencode ACP](https://opencode.ai/docs/cli/acp/), [permissions](https://opencode.ai/docs/permissions/),
[migrate from v1](https://opencode.ai/docs/migrate-v1/), label **[R]**; and version 1.18.19 run locally
with Gemini 3.8 Flash, label **[L]** ([14](14-live-investigation.md#agent-facts)). Where the two
disagree, the running version is what the app talks to.

| Statement | Label | Why it matters here |
|---|---|---|
| `opencode acp` serves **many sessions per process**. `session/list` returned the sessions of the data folder. | **[R] [L]** | OpenGenie spawns one process per conversation. That is a choice made for credential isolation, not a limit of the agent. [D9](12-decisions-open-questions.md#decisions) |
| 1.18.19 advertises `loadSession`, `mcpCapabilities {http, sse}`, image and embedded-context prompts, and session `resume`, `list`, `close`, `fork`. The documentation describes `sse: false` and a `delete` capability, which this version does not have. | **[L]** | `resume` and `list` are available to use. Capabilities must be read, not assumed from documentation. [AG-40](03-requirements.md#ag-40), [AG-44](03-requirements.md#ag-44) |
| It reads the client capabilities `elicitation.form` and `session.compaction`. | **[R]** | Advertising them turns the model's questions and context compaction into structured events. [AG-46](03-requirements.md#ag-46) |
| An MCP tool set to `ask` produces a permission request with the options `once`, `always`, `reject`. The request carries no input and no diff for an MCP tool; the arguments are on the tool-call update. The agent waits in silence while a person decides. | **[L]** | The protocol carries what a review card needs, in two frames. [AG-12](03-requirements.md#ag-12), [AG-41](03-requirements.md#ag-41) |
| After a reject, or a `cancelled` outcome, the call is failed and the turn ends with `end_turn` and no text. | **[L]** | The app's supervisor reads an empty answer as "continue" ([F-38](02-code-grounding.md#f-38)). [AG-18](03-requirements.md#ag-18) |
| With the app's deny list, the built-in tools `skill` and `task` remain callable. `"*": "deny"` with explicit allows and wildcards works and removes them. | **[L]** | The deny list is not least privilege; deny by default is available today. [AG-03](03-requirements.md#ag-03) |
| The agent fails any MCP call at **60 s** with "Request timed out", emitting nothing meanwhile; the tool keeps running. | **[L]** | Every tool must reply well inside that, and a repeated call must not be a second run. [AG-20](03-requirements.md#ag-20), [AG-27](03-requirements.md#ag-27) |
| It loads skills, commands and instruction files from its home and from every ancestor of its working folder. From a folder under a home directory this added 15,000 tokens to each turn. | **[L]** | The working folder and the home are part of the prompt. [AG-03](03-requirements.md#ag-03) |
| It has `mode` values `build` and `plan`, settable through `session/set_config_option`, and an `effort` option once the model catalogue is cached. | **[L]** | A native plan mode exists to pair with the app's own. [AG-13](03-requirements.md#ag-13) |
| The current documentation describes a **second configuration format**: an ordered `permissions` array whose default is `ask`, `shell` in place of `bash`, and `external_directory` allowed by default. The npm registry's current version is 1.19.5. | **[R] [L]** | OpenGenie writes the first format as a deny list and installs the agent from a floating range ([F-04](02-code-grounding.md#f-04)). A format change would silently change what the agent may do inside the app's container. [AG-03](03-requirements.md#ag-03) |
| It reports `usage` on the prompt response (`inputTokens`, `outputTokens`, `totalTokens`, cached and thought tokens) and `usage_update` with a cumulative cost in USD. | **[L]** | The cost meter needs no new source, only a correct mapper. [AG-56](03-requirements.md#ag-56) |
| Retry and compaction arrive as `session_info_update` metadata. | **[R]** | Today they are invisible. [AG-43](03-requirements.md#ag-43) |

## D. The platform under OpenGenie

Read by me on 13 November 2026 in the platform documentation
([app authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth),
[API scopes](https://docs.databricks.com/api/workspace/scopes),
[Free Edition limits](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations),
[Sandbox API](https://docs.databricks.com/api/sandbox/v1/create-sandbox)), and checked against the
development app.

| Fact | Label | Why it matters here |
|---|---|---|
| An app has two identities: the forwarded user token, limited to declared scopes, and one service principal, which "you can't customize, replace, or share", whose client id and secret are injected into the app's environment. | **[V]** | Children must not inherit the environment ([F-03](02-code-grounding.md#f-03)). There is no narrower app identity to delegate to ([D17](12-decisions-open-questions.md#decisions)). |
| User scopes an app may request: `ai-functions`, `ai-gateway`, `apps`, `files`, `genie`, `model-serving`, `postgres`, `sandbox`, `sql`, `sql:read`, `sql:restricted-query`, `vector-search`, and SDK scopes for catalogue objects and `workspace.workspace`. | **[V]** | This is the whole of what OpenGenie can do as the user from an app. |
| `jobs`, `pipelines` and `dashboards` are API scopes and are **not** in that list. | **[V]** | Jobs and pipelines are delivered as code and observed through SQL ([D16, D18](12-decisions-open-questions.md#decisions)). Genie Code, inside the workspace, has no such limit. |
| "Databricks blocks access to any functionality outside the approved scopes, even if the user has permission." | **[V]** | A missing scope cannot be worked around as the user. |
| The live app holds eleven scopes, two more than the bundle file declares. | **[L]** | [F-39](02-code-grounding.md#f-39) |
| The Sandbox API runs a command in a container under the `sandbox` scope. It is Beta and is not available on the development workspace. | **[V] [L]** | A future route to run code as the user. The run port admits it; nothing depends on it. |
| System tables for jobs, pipelines, lineage, query history and billing are readable through the SQL warehouse. | **[L]** | The read path for what has no scope ([AG-39](03-requirements.md#ag-39)). |
| Free Edition: an app stops 24 hours after it was last started; compute is shut for the day past a quota; three apps, one Lakebase project, one warehouse. | **[V]** | Durability claims must name the edition they were measured on ([Q9](12-decisions-open-questions.md#open-questions)). |

## What this assessment changes

1. **Conformance is cheap and comes first.** Five of the defects in [02](02-code-grounding.md) are a
   mapper reading the wrong field. They are tested only against the fake agent, which speaks the same
   private dialect ([F-10](02-code-grounding.md#f-10)).
2. **The protocol already carries a review flow, and the pinned agent uses it.** A permission request
   names the tool call; its arguments arrive on the update for the same id; the agent then waits at no
   cost. The change contract in [05](05-architecture.md#the-change-contract) collects the human's answer
   there and still decides on the server.
3. **OpenGenie's durable, server-owned turn is a differentiator**, not parity work. Genie Code documents
   that the tab must stay open. Extending durability from turns to job and pipeline runs is the highest
   leverage feature in this spec ([AG-22](03-requirements.md#ag-22), [AG-23](03-requirements.md#ag-23)).
4. **Agent version is part of the trust boundary.** It must be pinned, checked at boot, and configured by
   allow list ([AG-03](03-requirements.md#ag-03)).
5. **The documentation of an agent is not its behaviour.** Several statements read in documentation did
   not hold for the version the app runs: its capabilities differ from the documented list, it does not
   send the protocol's `name` field, and its permission request for an MCP tool carries no input. Two
   behaviours that shape the design are in no document read here: the 60 s limit on a tool call and the
   silent end of a turn after a rejection. The conformance fixtures must be recorded from the pinned
   agent ([11](11-test-e2e-plan.md#the-real-agent-check)).
6. **The gap to Genie Code on jobs and pipelines is the platform's.** Genie Code runs inside the
   workspace as the user. An app is given no user scope for those APIs. OpenGenie's honest position is
   to define them as code, run what SQL can express, and observe the rest
   ([identity tiers](05-architecture.md#identity-tiers)).
