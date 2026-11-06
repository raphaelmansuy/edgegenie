[Index](README.md) · [00 Why](00-why-first-principles.md) · [09 Security](09-security-security.md) · [10 Plan](10-implementation-plan.md) · [13 Lenses](13-lens-reviews.md) · **14 Decisions**

# 14 · Decision log and risks

## Decisions

Format: **D-nn · decision — because — alternatives rejected — revisit when.**

| ID | Decision | Because | Rejected | Revisit when |
|---|---|---|---|---|
| D-01 | Build a Databricks App, not an editor extension | identity, permissions and data already live there | VS Code extension; a standalone web app | if users demand in-IDE work (then: ACP client in the IDE, same backend) |
| D-02 | Drive the agent over **ACP**, not its HTTP API or CLI stdout | an open contract that outlives one agent; structured tool calls and permissions | OpenCode HTTP server; screen-scraping the CLI | ACP v2 adoption is widespread (then: bump the mapper only) |
| D-03 | One `opencode acp` process, many sessions | fewer processes, one model connection pool | one process per session | if a session can hang the process (then: isolate) |
| D-04 | **SSE**, not WebSocket | Databricks proxy: streamed HTTP works, WS is rejected on Spaces apps | WebSocket | never, for this platform |
| D-05 | The tool server is the only advertised path to Databricks objects | it is the fence | letting the agent use its own CLI | never |
| D-06 | Events in Postgres, append-only | durability, replay, audit | in-memory; the agent's own store | never |
| D-07 | A durable queue in Postgres | survives deploys and pod restarts | `asyncio.create_task`; Celery/Redis (extra moving part) | if throughput exceeds Postgres |
| D-08 | On-behalf-of-user identity for data work | per-user permissions are the product | service principal for everything | if a user-scoped flow proves impossible for a needed API |
| D-09 | Evidence must be verifiable against the tool log | a model's "done" is a claim | trust the report | never |
| D-10 | Tool budget of 24, shown in the UI | context is the scarce resource | "add a tool per API" | after the pilot's tool-usage data |
| D-11 | Built-in agent shell **off** by default | it bypasses the fence | always on for convenience | for scratch-folder sessions only, opt-in |
| D-12 | A `FakeAgentRuntime` in production code | deterministic tests and demos | test-only doubles | never |
| D-13 | Cost shown as an **estimate** until measured | honesty | estimate presented as truth | after the pilot measures both sides |
| D-14 | Pin the agent version, record it per session | reproducibility | floating latest | on a deliberate upgrade with a conformance run |
| D-15 | Model choice visible per message | makes routing legible and debuggable | hide it in settings | never |

## Risks

Likelihood × impact, with a named mitigation and an owner. **Bold** rows are the ones that could sink the project.

| ID | Risk | L | I | Mitigation | Owner | Residual |
|---|---|---|---|---|---|---|
| **R-01** | **The fence is bypassed** through the agent's shell or a bug | M | **Critical** | scoped token; built-in bash off; per-session capabilities; E-30/E-39 tests; `fence.refusals_total` alert | Security | Medium: a determined agent with a broad token could still act |
| **R-02** | **A confident wrong answer** reaches a decision | H | **High** | evidence verification; blocked state; graded missions | AI | Medium: prose can still mislead |
| **R-03** | ACP changes under us (v2 or an agent upgrade) | M | High | mapper + contract tests + pinned version | Coding agent | Low |
| R-04 | Process-per-session is unstable at load | M | High | cap, janitor, restart counter, path to a separate service | Full-stack | Low |
| R-05 | Cost per task is higher than expected | M | Medium | tool budget, skills on demand, model allow-list, visible cost | AI + PO | Medium |
| R-06 | The 300 s proxy limit produces a bad experience | H | Medium | heartbeat, replay, resume, "leave the page" copy | Ops | Low |
| R-07 | Users compare it with Genie Code and find the semantic layer missing | H | Medium | be explicit in the UI; link out to Genie for definitions | PO | Medium |
| R-08 | Approval fatigue trains users to click Allow | M | High | blast-radius copy, deny prominence, per-class grants, measure in the pilot | UX | Medium |
| R-09 | Lakebase app-creation flow is fragile | H | Medium | keep M6 out of the v1 gate; degrade to "instructions" | Full-stack | Medium |
| R-10 | Secret leaks into a trace or an export | L | **Critical** | redaction middleware, CI scan, `redactions_total` alert | Security | Low |
| R-11 | The spec's assumptions about platform streaming are wrong in our workspace | L | High | phase 0 measures it on day one, before building on it | Ops | Low |
| R-12 | Model choice is dictated by what the gateway exposes | M | Medium | allow-list; document how to add an external model path | AI | Medium |

## Open questions (blocking or near-blocking)

| # | Question | Blocks | Who decides | By when |
|---|---|---|---|---|
| Q-1 | Which model is the default, and is a non-gateway model allowed? | Phase 1 | PO + platform | before phase 1 |
| Q-2 | Does the workspace allow OBO scopes (`sql`, `files`, `catalog.*:read`)? | Phase 0 | workspace admin | before phase 0 |
| Q-3 | Is a token-exchange (scoped token for the agent) available? | R-01 mitigation | platform + security | before phase 3 |
| Q-4 | Is M6 (Lakebase + app) in v1 scope? | Phase 3 planning | PO | before phase 3 |
| Q-5 | Prompt retention: 30 or 90 days? | Schema | privacy owner | before phase 4 |
| Q-6 | Does the pilot want a "production schema" approval path? | Phase 4 | platform lead | before phase 6 |

## Claims we will not make

1. **"Cheaper than Genie Code"** — until measured on the same tasks.
2. **"As good as Genie Code at business questions"** — we do not have the ontology.
3. **"Safe against prompt injection"** — we can say *contained within scope*, not *immune*.
4. **"Production ready"** — until the phase 6 criteria pass.

## How this spec stays true

| Mechanism | Detail |
|---|---|
| Tables generated from data | results tables are injected from saved runs, never hand-typed ([`exams/inject_tables.py`](../../exams/inject_tables.py)) |
| Every claim labelled | `[verified]`, `[documented]`, `[proposal]` |
| Unverified work is listed, not hidden | each document has a "what we have not verified" section |
| The cross-reference matrix | a change in one document names the documents to re-read ([index](README.md#cross-reference-matrix)) |
| This log | every significant change gets a D-nn entry or amends one |
