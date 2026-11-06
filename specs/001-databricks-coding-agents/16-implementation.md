[Index](README.md) · [10 Plan](10-implementation-plan.md) · **16 Implementation** · [11 Testing](11-testing-edge-cases.md) · [E2E screenshots](e2e/README.md)

# 16 · Implementation: what was built, and what it proved

This document is the companion to the plan: it records the code that now exists, the decisions taken while building it,
and — more usefully — **the nine real defects that only surfaced by running it.** Several of them were invisible to the
spec and one would have shipped a broken product.

Everything below is runnable from this repository. No part of it is a mock-up of a design.

## What exists

```
apps/coding-agent/
├── api/
│   ├── domain/            events.py · evidence.py · supervisor.py · session.py · scope.py   (pure, no I/O)
│   ├── ports/             AgentRuntime · ToolRegistry · EventStore · Identity · ModelCatalog
│   ├── services/          orchestrator.py · identity.py
│   ├── adapters/
│   │   ├── acp/           jsonrpc.py · mapper.py · runtime.py (stdio) · http_runtime.py
│   │   ├── fake/          agent.py + 5 recorded scenarios (deterministic tests and demos)
│   │   ├── mcp/           registry.py (one scoped tool server per session)
│   │   └── memory/        store.py (same contract as Postgres)
│   ├── routers/api.py     REST + SSE
│   ├── config.py          one validated settings object
│   └── main.py            the only place that chooses adapters
├── web/
│   ├── src/domain/        events.ts (mirrors the Python vocabulary) + pure reduce()
│   ├── src/hooks/         useSessionStream.ts (SSE with replay)
│   ├── src/components/    Transcript · Markdown · Chrome (composer, approval, inspector, empty state)
│   └── scripts/           genie-e2e.mjs (19-step live run) · shoot.mjs (UI states) · deployed-e2e.mjs
├── tests/                 68 Python tests (unit, contract, API)
├── app.yaml               Databricks App runtime contract
└── databricks.yml         bundle, including user_api_scopes
```

| Metric | Value |
|---|---|
| Python tests | **68 passing** |
| Front-end tests | **16 passing** (Vitest) |
| Python coverage | **71%** overall; 92–98% on the domain |
| Bundle | 77 KB gzipped (budget 250 KB) |
| Type check | `tsc -b` clean, `mypy` configured |
| Screenshots | 10 real UI states, captured by a script |

## How the design held up

The ports-and-adapters split paid for itself three times:

1. **`FakeAgentRuntime` made the UI testable.** Every screenshot and every front-end test runs without a model, against a
   recorded transcript. Without it, "test the UI" would have meant "hope the model behaves".
2. **The ACP mapper absorbed two protocol dialects** without the orchestrator noticing (see D-02 below).
3. **Swapping stdio for HTTP** cost one file (`http_runtime.py`), because nothing else knew how the agent was started.

DRY held where it mattered: one event vocabulary, generated once in Python and mirrored (with a parity test) in TypeScript;
one `reduce()` on the client; one place (`scope.py`) that decides what a write may touch.

## The nine defects that only running found

Each was found by testing, not by review. Each has a regression test.

| # | Symptom | Root cause | Fix | Test |
|---|---|---|---|---|
| 1 | Reasoner output missing; transcript half-empty | A parked `queue.get()` was **cancelled**, silently discarding the item it was about to return | Start the read once and reuse it; drain queued notifications before honouring the end signal | `test_no_event_is_lost_when_the_end_signal_arrives_first` |
| 2 | UI stream empty while the agent clearly worked | Events were stored under the **agent's** session id (`ses_fake_1`), not ours | Translate to our id at the boundary | `test_events_are_stored_under_our_session_id_not_the_agents` |
| 3 | "9 of 9 requirements proven" on a 3-requirement task | Evidence rows **accumulated** across supervisor passes | Record once, at the end; `dedupe()` + `limit_to()` | `test_duplicate_claims_collapse_to_one_row` |
| 4 | Blank page: `Cannot read properties of undefined (reading 'length')` | The server omits `turns` for a fresh session; a bare spread replaced defaults with `undefined` | Explicit `hydrate()`; the reducer defends against a missing `turns` | `missing-turns.test.ts` |
| 5 | Renderer process crashed intermittently | `useEffect` + a `useCallback` whose identity changed each render → **fetch loop** | Stable deps; scroll throttled to a timeout | manual + capture run |
| 6 | New session showed the *previous* transcript | Session switch did not reset client state | Reset in the effect keyed on `sessionId` | capture run |
| 7 | Every demo turn ended **blocked** | The demo marker `[[scenario:…]]` was parsed as an unfulfillable requirement | Strip it before extracting requirements | `test_a_demo_marker_is_not_a_requirement` |
| 8 | Each tool appeared twice in the trace | Tool-call card appended on every `started` with no id check | Upsert by `callId` | `dup.test.ts` |
| 9 | Tool cards showed `{}` for arguments | opencode sends arguments on the *update*, and I discarded them for completed calls | Show arguments whatever the status | manual inspection |

**The one that would have shipped:** #2. The backend reported success, the agent behaved, the tests for the orchestrator
passed — because they asserted on the orchestrator's own view. Only the browser showed an empty transcript. That is the
argument for the E2E-with-screenshots discipline in one sentence.

## Decisions taken during the build

| ID | Decision | Why |
|---|---|---|
| D-16 | The event vocabulary is generated once and **mirrored** in TypeScript with a parity test | A cross-language contract with no build step; the test fails if they drift |
| D-17 | The reducer tolerates missing fields and unknown events | An older tab must not crash on a newer server |
| D-18 | The demo agent chooses its behaviour **per session** from the prompt | One server, every state — and it is how a real agent works |
| D-19 | The ACP adapter is deliberately chatty in comments about *why* each rule exists | Rules 08–10 came from probing; without the reason they get "cleaned up" later |
| D-20 | No test asserts on model prose | Non-deterministic by nature; we assert on artefacts and tool calls |

## What is deliberately still open

| Item | Why it is not done | Consequence |
|---|---|---|
| Postgres event store | The in-memory store satisfies the `EventStore` port and the whole test suite runs against it | Swapping it in is one adapter; durability across restarts is untested until then |
| Real MCP tool server in the loop | The app starts it (`tool_mode: subprocess`) but the demo path does not need it | Tool-count and fence behaviour are unit-tested, not yet E2E against a live workspace |
| Approval round trip | The adapter answers permission requests; no scenario raises one yet | `E-30…E-32` remain unproven end to end |
| Deployment to a live app | `app.yaml` and `databricks.yml` are written and validated as YAML | Not deployed from this session |
| Screenshots of the Databricks chrome | SSO blocks automation | The app's own UI is captured; the surrounding workspace is not |

## How to run it

```bash
cd apps/coding-agent
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest tests/ -q                     # 68 tests
cd web && npm install && npm run build && npx vitest run # 16 tests + bundle

# demo mode: no model, no workspace, every state reproducible
APP_AGENT_MODE=fake APP_ALLOWED_MODELS='["fake/model-a"]' APP_DEFAULT_MODEL=fake/model-a \
  ../.venv/bin/python -m uvicorn api.main:app --port 8000
```

To capture the screenshots: `node web/scripts/shoot.mjs <outdir>` (starts its own server).

Next: [E2E screenshots](e2e/README.md) · [11 Testing](11-testing-edge-cases.md).
