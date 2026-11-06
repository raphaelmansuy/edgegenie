[Index](README.md) · [02 Architecture](02-architecture.md) · [03 ACP](03-acp-integration.md) · [07 Back end](07-backend.md) · [09 Security](09-security-security.md) · [11 Testing](11-testing-edge-cases.md) · [12 Ops](12-operations.md) · **15 Roadblocks**

# 15 · Roadblock register

Every roadblock between this design and a running product, each with the **official document** that establishes it, the
design decision it forces, and how it is tested. Edge-case IDs (`E-xx`) refer to [11](11-testing-edge-cases.md).

**Reading the "kind" column:**

| Kind | Meaning | Our freedom |
|---|---|---|
| **PLATFORM** | a property of Databricks Apps we cannot change | adapt the design |
| **PROTOCOL** | a property of ACP or OpenCode | adapt the adapter |
| **PRODUCT** | a property of our own design or the market | we can change it |
| **RESOURCE** | a limit we can raise with money or an admin | budget or escalate |

---

## A · Platform roadblocks (Databricks Apps)

### RB-01 · The proxy cuts streamed responses at 300 s, and plain responses at 60 s \[PLATFORM]

*Official:* Databricks Apps proxy behaviour, as documented in Databricks' own agent-skills
[platform guide](https://github.com/databricks/databricks-agent-skills/blob/main/skills/databricks-apps/references/platform-guide.md):
container apps cut streamed responses at 300 s; the Apps gateway returns **502 if no response headers within 60 s**;
WebSocket upgrades fail on Spaces apps. Databricks' [best practices](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/best-practices)
say the same thing differently: "avoid synchronous requests that wait for operations to complete… make an initial request to
start the operation, then periodically query".

**Roadblock:** a turn routinely takes 30 s to 9 min (our measured exam runs: 75–429 s per task).

**Design it forces:** headers immediately, heartbeat every 10 s, SSE + `Last-Event-ID` replay, work detached from the
request ([OPS-01…05](12-operations.md#streaming-and-timeouts)). **No WebSocket, ever.**

**Test:** E-02 with a real 6-minute turn.

### RB-02 · SIGTERM → SIGKILL after 15 seconds, and no scale-to-zero \[PLATFORM]

*Official:* [Best practices for Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/best-practices)
("Your app must shut down within 15 seconds after it receives a `SIGTERM`… or it forcibly terminates with `SIGKILL`") and the
[builder's guide](https://www.databricks.com/blog/builders-guide-scaling-databricks-apps) ("Databricks sends SIGTERM, then
SIGKILL if the app hasn't exited within 15 seconds"). Idle: Databricks Apps stays **Running and billed** until stopped;
[no GA idle timeout or auto-stop](https://community.databricks.com/t5/data-engineering/query-on-databricks-apps-idle-time-out/td-p/174694).

**Roadblock:** we cannot "just finish the turn" on shutdown, and an idle chat app burns DBUs all night.

**Design it forces:** checkpoint continuously (every event is already persisted), `--timeout-graceful-shutdown 10`,
in-flight turns marked `interrupted` and resumable ([E-04](11-testing-edge-cases.md)). Cost: a scheduled stop/start job, or
accept the idle cost ([12](12-operations.md#scaling)). **Correction applied to [12](12-operations.md): the drain budget was
25 s; the platform allows 15.**

**Test:** kill -9 mid-turn; SIGTERM drain timed in CI.

### RB-03 · `command` is not run through a shell; only `DATABRICKS_APP_PORT` is substituted \[PLATFORM]

*Official:* [Configure app execution with app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)
("Because Databricks doesn't run the command in a shell, environment variables defined outside the app configuration aren't
available to your app. The one exception is `DATABRICKS_APP_PORT`").

**Roadblock:** the obvious design ("start uvicorn and the agent with `sh -c`") is not expressible in `app.yaml`.

**Design it forces:** one entry command; the app spawns the agent itself with `asyncio.create_subprocess_exec` and an explicit
`env` dict. All configuration comes from `app.yaml` `env:` or secrets, never from the ambient environment.

**Test:** deploy gate asserts the agent starts with no shell.

### RB-04 · Unprivileged container: no `apt`, and the agent binary must be installed at build \[PLATFORM]

*Official:* best practices ("Apps run as non-privileged users… You can't install system-level packages using package
managers like `apt-get`, `yum`, or `apk`") and [dependencies](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies)
(libraries in `requirements.txt` / `package.json` are installed on the container).

**Roadblock:** OpenCode ships as an npm package (and as standalone binaries). At runtime we cannot `apt install` anything, and
installing at request time would blow the start-up window.

**Design it forces:** declare `@opencode-ai/...` (or the agent package) in `package.json` so it is installed at build; a root
`package.json` also triggers `npm install` + `npm run build` ([deploy logic](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)).
Pin the version. **Failure mode to expect:** "Large npm installs may exceed the 10-minute startup window" (Databricks
agent-skills, other-frameworks reference) — so measure it in phase 0.

**Test:** E-57 cold start timed; a build that omits the agent must fail the deploy gate, not the first user turn.

### RB-05 · Egress may be denied by default; a policy change needs a restart \[RESOURCE]

*Official:* [Configure networking for Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/networking)
(required egress: `*.databricksapps.com`, `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`; restricted egress is
deny-by-default) and the note that **egress changes do not apply to already-running compute** — stop and start the app.

**Roadblock:** in a locked-down workspace the build fails with `Temporary failure in name resolution`, and the *agent's* model
calls go not to the internet but to the workspace AI Gateway — which is a different path that also has to be allowed.

**Design it forces:** a documented allow-list ([12](12-operations.md)), a dry-run before rollout, and a startup self-test
that calls the gateway once and reports a clear error instead of failing on the first user turn.

**Test:** deploy in a restricted-egress workspace as part of phase 6.

### RB-06 · The app's compute is for UI and orchestration, not heavy work \[PLATFORM]

*Official:* best practices ("App compute is optimized for UI rendering. Use Databricks SQL for queries… Lakeflow Jobs for
batch processing, and Model Serving for AI inference").

**Roadblock:** an agent process per session is *exactly* the kind of work this guidance discourages, and the default compute
is 2 vCPU / 6 GB (Medium).

**Design it forces:** hard cap of concurrent agents, an explicit escape hatch (an agent service, or a Job-based executor) and
the acknowledgement in [13](13-lens-reviews.md) that this is the biggest architectural risk.

**Test:** load test at 20 sessions; the cap must refuse gracefully, not OOM.

### RB-07 · Only stdout/stderr logs, one instance per log view \[PLATFORM]

*Official:* best practices ("Log to stdout and stderr… Databricks captures logs from standard output and error streams") and
the platform guide (scaled apps: "one instance per view"; app telemetry writes `otel_logs`, `otel_spans`, `otel_metrics` to
Unity Catalog).

**Design it forces:** structured JSON logs to stdout with the trace id; no files; rely on telemetry tables for multi-instance
correlation. The agent's own logs (`--print-logs`) must be captured and re-emitted, not written to a file.

### RB-08 · File size and app count limits \[RESOURCE]

*Official:* platform limits — **no source file over 10 MB**, 100 apps per workspace, immutable app names, and for horizontally
scaled apps "no preinstalled Python libraries".

**Roadblock:** the agent kit plus a bundled front end can approach the file limit; and scaling out changes the Python
environment.

**Design it forces:** vendor dependencies at build (never commit `node_modules`), keep fixtures out of the app source, and
explicitly test the scaled configuration rather than assuming one instance.

---

## B · Protocol roadblocks (ACP and OpenCode)

### RB-09 · We must speak ACP **v1**, which has a different lifecycle from the published v2 schema \[PROTOCOL]

*Official:* [ACP v2 migration guide](https://agentclientprotocol.com/protocol/v2/migration) — in v2 the prompt response
acknowledges *insertion* and progress/completion move to `state_update`; in v1 the prompt response carries `stopReason`.
[OpenCode's ACP documentation](https://opencode.ai/docs/acp/) states `opencode acp` speaks **protocol version 1**.

*Verified:* our probe returned `protocolVersion: 1` and `stopReason` + `usage` on the prompt response
([19](../../docs/e2e/19_acp_probe.txt)).

**Design it forces:** one mapper, two dialects, with fixtures for both ([03](03-acp-integration.md#version-reality-we-speak-v1-plan-for-v2)).

**Test:** the same transcript normalises to identical `AgentEvent` streams under v1 and v2 frames.

### RB-10 · **`session/set_config_option` rejects the documented union shape** \[PROTOCOL · verified defect]

*Official:* [ACP v2 schema](https://agentclientprotocol.com/protocol/v2/schema) defines the value as a discriminated union
(`type: "id" | "boolean"`).

*Verified:* opencode 1.19.5 returns `-32602 Invalid params` for `{"type":"id","value":"…"}` **and** for
`{"type":"string","value":"…"}`, but accepts a **bare string** and returns the updated `configOptions` plus a
`config_option_update` notification ([20](../../docs/e2e/20_acp_config_probe.txt)).

**Design it forces:** send a bare string for `select` options; on `-32602` retry once with the primitive shape; never treat a
config error as fatal (the session is still usable on the old model).

**Test:** E-41 asserts the switch works and that a rejected switch leaves the session usable.

### RB-11 · Switching to a catalogue model the gateway cannot serve fails **late** \[PROTOCOL · verified defect]

*Verified:* after switching to `databricks/databricks-claude-haiku-4-5`, the next prompt failed with
`-32603 Internal error: getaddrinfo ENOTFOUND https` — a DNS resolution failure inside the model call, not a refusal at
switch time ([20](../../docs/e2e/20_acp_config_probe.txt)).

**Roadblock:** the agent advertises a model catalogue that includes endpoints this workspace cannot reach.

**Design it forces:** the app **never** renders the agent's catalogue verbatim. It intersects it with a workspace allow-list
that has been proven by a health check, and it surfaces the underlying error text — "internal error" is a bug in our UI.

**Test:** E-45 (unknown model refused) and a nightly probe that validates every allow-listed model with a one-token call.

### RB-12 · MCP tool names are prefixed with the server name, and models mangle them \[PROTOCOL · verified defect]

*Verified:* tools appear as `dbxnb_dbx_run_sql`; the model called `dbxnb_run_sql` and the agent answered
`Model tried to call unavailable tool`. Registering one server twice produced two full copies of every tool
([19](../../docs/e2e/19_acp_probe.txt)).

**Design it forces:** R-ACP-01…07 ([03](03-acp-integration.md#two-defects-we-found-and-the-rules-they-produce)), a hard
tool budget of 24 shown in the UI, and server-side de-duplication.

**Test:** E-26, E-40.

### RB-13 · A permission request is a **blocking** round trip into a human \[PROTOCOL]

*Official:* [ACP schema — `session/request_permission`](https://agentclientprotocol.com/protocol/v2/schema): the client
"should present the options to the user and return their decision"; option kinds are `allow_once`, `allow_always`,
`reject_once`, `reject_always`. `session/cancel` "MUST stop waiting for pending `session/request_permission` requests and treat
them as not approved".

**Roadblock:** the agent stalls until a person answers, and the answer may never come (tab closed, user asleep).

**Design it forces:** approvals are durable rows with an expiry (E-31), the request survives a reconnect, and cancellation
resolves any pending request. Because `reject_always` exists, "don't ask again" is a protocol-level outcome, not a client hack.

**Test:** E-30, E-31, E-32; a permission prompt arriving after a cancel must be answered `cancelled`.

### RB-14 · `session/cancel` is cooperative: updates may still arrive \[PROTOCOL]

*Official:* schema — "Clients SHOULD continue accepting tool call updates even after sending a `session/cancel`"; the agent
MUST report `cancelled`, not `error`, for aborted work.

**Design it forces:** the UI keeps consuming after a cancel and shows the tail; the turn closes only on the stop signal, with a
10 s hard kill ([03](03-acp-integration.md#concurrency-and-cancellation-details)).

### RB-15 · The agent's own shell and file tools bypass our fence \[PROTOCOL]

*Official:* [OpenCode ACP support](https://opencode.ai/docs/acp/) — "All features are supported: built-in tools (file
operations, terminal commands, etc.)" over ACP too.

**Roadblock:** this is the hole in [09](09-security-security.md#the-inconvenient-truth-about-the-fence-and-the-token).

**Design it forces:** built-in bash off by default, scoped token, per-session MCP capabilities, and a detection event when the
agent attempts a direct Databricks call (E-39).

### RB-16 · The agent needs provider credentials it can actually use \[PROTOCOL]

*Official:* [OpenCode ACP docs](https://opencode.ai/docs/cli/acp/) — if a provider needs authentication, OpenCode returns
ACP's `auth_required` error, and its only auth method is a **terminal** login (`opencode auth login`), which a headless
container cannot perform.

**Roadblock:** any misconfiguration of the gateway credentials becomes an unusable agent with an error the user cannot act on.

**Design it forces:** configure the provider with the gateway base URL and an env-var API key at session start (proved in our
tutorial), treat `auth_required` as a **configuration** incident with an admin-facing message, and never render a login prompt.

**Test:** E-07 / a startup self-test that performs one minimal completion.

---

## C · Product roadblocks

### RB-17 · A convincing wrong answer is the default failure mode \[PRODUCT]

*Evidence:* our own runs: a truncated read made an agent report 1 import out of 5; an empty grep made it invent imports; a
V1 setup scored 20% while sounding confident ([06](../../docs/06-results-and-lessons.md)).

**Design it forces:** evidence verified against the tool log (not quoted), a `blocked` state, and execution-based grading.

### RB-18 · There is no ontology, so business-term questions will disappoint \[PRODUCT]

**Design it forces:** say so in the UI and link to Genie for definitions ([00](00-why-first-principles.md#the-gap-this-product-must-close)).

### RB-19 · Approval fatigue \[PRODUCT]

**Design it forces:** per-class grants (`allow_always`), blast-radius copy, deny prominence, and a measured approval-outcome
metric ([12](12-operations.md)).

### RB-20 · Two sources of truth for a session (our database and the agent's own store) \[PRODUCT]

*Verified:* `session/list` returns the agent's sessions with cwd, title and `updatedAt` ([20](../../docs/e2e/20_acp_config_probe.txt)).

**Design it forces:** our database is authoritative for the product; the agent's list is only used to reconcile after a
restart (E-43). Never show the agent's title as the product's title.

---

## D · Resource roadblocks (raise with money or an admin)

### RB-21 · Lakebase connection ceiling and autoscaling constraints \[RESOURCE]

*Official:* [Manage computes](https://docs.databricks.com/aws/en/oltp/projects/manage-computes) — **1 CU = 218 connections**;
under autoscaling the limit is "the smaller of your maximum CU and 8× your minimum CU"; the range `max − min` cannot exceed
16 CU. [Configuration](https://developers.databricks.com/docs/lakebase/configuration) — scale-to-zero only for computes of
32 CU or smaller.

**Roadblock:** connection-per-SSE-stream would exceed 218 quickly, and a 0.5→8 CU autoscale range is illegal (7.5 CU is fine;
0.5→32 is not).

**Design it forces:** a pool sized per worker and asserted at startup (`pool × instances ≤ 0.8 × limit`), and a compliant
autoscale range in the deployment config ([08](08-data-model.md)).

**Test:** a startup assertion plus a load test that reads `max_connections` and compares.

### RB-22 · No GPU, no root, no system packages; inference only via endpoints \[PLATFORM/RESOURCE]

*Official:* best practices and the platform guide. **Design it forces:** all model calls go through the AI Gateway; nothing
local.

### RB-23 · Compute sizing is coarse \[RESOURCE]

Medium (2 vCPU / 6 GB) to XLarge (12 / 48); no fine-grained control, and horizontal scaling is 1–5 instances with best-effort
affinity. **Design it forces:** an explicit per-instance agent cap and a queue, rather than a hope that memory is enough.

---

## E · What we deliberately do **not** attempt (and why)

| Not attempting | Reason | What the user gets instead |
|---|---|---|
| Scale-to-zero | not available for standard Databricks Apps | a scheduled stop/start job, documented |
| WebSocket streaming | rejected on Spaces apps | SSE with replay |
| A separate agent service in v1 | one more system to operate; the container works | a documented seam (`AgentRuntime` port) for v2 |
| Running the agent as a Databricks Job per turn | minutes of job start latency per turn | in-container process, capped |
| Interactive provider login inside the app | `auth_required` needs a terminal | gateway credentials configured by the admin |
| Semantic layer / Genie parity | we do not have the ontology | deep links to Genie for definitions |

---

## Register summary

| Roadblock | Kind | Severity | Handled in | Test | Status |
|---|---|---|---|---|---|
| RB-01 300 s / 60 s proxy | PLATFORM | High | 12, 07 | E-02 | designed |
| RB-02 15 s SIGTERM, no idle stop | PLATFORM | High | 12, 07 | E-04 | designed |
| RB-03 no shell in `command` | PLATFORM | Medium | 07 | deploy gate | designed |
| RB-04 unprivileged, build-time install | PLATFORM | High | 10, 12 | E-57 | **must measure in phase 0** |
| RB-05 egress deny-by-default | RESOURCE | High | 12 | phase 6 | needs an admin |
| RB-06 app compute not for heavy work | PLATFORM | High | 02, 13 | load test | accepted risk |
| RB-07 stdout-only logs | PLATFORM | Low | 12 | — | designed |
| RB-08 10 MB files, 100 apps | RESOURCE | Low | 10 | CI | designed |
| RB-09 ACP v1 vs v2 | PROTOCOL | High | 03 | mapper fixtures | **verified** |
| RB-10 config option shape | PROTOCOL | Medium | 03 | E-41 | **verified defect** |
| RB-11 unreachable model catalogue | PROTOCOL | Medium | 03, 04 | E-45 | **verified defect** |
| RB-12 tool name mangling | PROTOCOL | Medium | 03, 04 | E-26, E-40 | **verified defect** |
| RB-13 blocking permission round trip | PROTOCOL | High | 03, 05 | E-30…E-32 | **unverified** |
| RB-14 cooperative cancel | PROTOCOL | Medium | 03 | E-15 | designed |
| RB-15 agent shell bypasses fence | PROTOCOL | Critical | 09 | E-39 | partly mitigated |
| RB-16 `auth_required` | PROTOCOL | Medium | 09, 12 | E-07 | designed |
| RB-17 confident wrong answer | PRODUCT | High | 04 | graded missions | mitigated |
| RB-18 no ontology | PRODUCT | Medium | 00, 05 | — | accepted |
| RB-19 approval fatigue | PRODUCT | High | 05 | pilot metric | **must measure** |
| RB-20 two session stores | PRODUCT | Low | 07 | E-43 | designed |
| RB-21 Lakebase connection ceiling | RESOURCE | Medium | 08 | load test | designed |
| RB-22 no GPU/root | PLATFORM | Low | 12 | — | designed |
| RB-23 coarse sizing | RESOURCE | Medium | 12 | load test | accepted |

**Three roadblocks are unproven and must be closed before phase 3 ships:** RB-04 (does the agent install and start inside the
app container within the window), RB-13 (permission round trip through the UI), and RB-05 (egress in the target workspace).

Next: [11 Testing](11-testing-edge-cases.md) for the cases, [12 Operations](12-operations.md) for the runbooks.
