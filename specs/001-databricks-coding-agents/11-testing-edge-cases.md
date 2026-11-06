[Index](README.md) · [01 Product](01-product-requirements.md) · [03 ACP](03-acp-integration.md) · [07 Back end](07-backend.md) · [10 Plan](10-implementation-plan.md) · **11 Testing** · [12 Ops](12-operations.md)

# 11 · Testing and edge cases

## Test strategy in one picture

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart TB
    U["Unit<br/>domain, mapper, evidence<br/>fast, no I/O"]:::green --> C["Contract<br/>every port, fake vs real"]:::yellow
    C --> E["E2E with FakeAgentRuntime<br/>deterministic UI flows"]:::blue
    E --> L["E2E live<br/>real model, real workspace"]:::pink
    L --> G["Graded missions<br/>artefact correctness"]:::orange
    G --> P["Pilot<br/>humans, judgement"]:::purple
    style U fill:#E6F4EA,stroke:#A8D5B5
    style C fill:#FFF8E1,stroke:#F2D98D
    style E fill:#E8F0FE,stroke:#A8C0E8
    style L fill:#FDE7EF,stroke:#F2B5CB
    style G fill:#FFEDE0,stroke:#F5C29C
    style P fill:#EFE7FB,stroke:#C9B6EC
```

**The pyramid is deliberately not a "test everything twice" plan.** Most value comes from the two ends: unit tests on pure
logic (cheap, exhaustive) and graded live missions (expensive, but the only ones that prove the product works). The middle
exists to make the ends debuggable.

## The four kinds of proof

| Kind | Question | Example | Frequency |
|---|---|---|---|
| **Behaviour** | does the user see the right thing? | an approval sheet appears and traps focus | every commit |
| **Correctness** | is the artefact right in the workspace? | notebook runs, table matches the golden query | nightly + pre-release |
| **Safety** | can the agent exceed its scope? | out-of-scope write refused, audited, visible | every commit (fast subset) |
| **Resilience** | does it survive the platform? | pod killed mid-run, nothing lost | pre-release + weekly chaos |

---

## Edge-case catalogue

Every case has an ID, the component that owns it, the expected behaviour, and the test that proves it. **A case with no
test is an open bug.**

### Agent lifecycle

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-01 | Agent process dies mid-turn (OOM, crash) | turn marked `interrupted`; partial transcript kept; "Resume" offered; no false completion | kill -9 the child in integration |
| E-02 | Proxy cuts the SSE stream at 300 s | browser reconnects with `Last-Event-ID`; server replays; a heartbeat every 10 s prevents it in the first place | Playwright route abort + real 6-minute run |
| E-03 | Two browser tabs on one session | both see the same stream; only one can submit at a time (soft focus lock); the second tab shows "read-only, another tab is active" | Playwright with two contexts |
| E-04 | App pod restarts during a run | events durable; turn `interrupted`; resume from `loadSession`; nothing lost | chaos test |
| E-05 | Tool server fails to start | session `Failed` with a clear reason; **no turn runs unfenced** | integration: break the server binary |
| E-06 | Agent returns an empty answer after tool calls | supervisor continues up to 5 times, then `blocked` | fixture replay |
| E-07 | User token expires mid-session | next Databricks call fails closed with 401; UI says so; **never** falls back to the service principal | integration with an expired token |
| E-08 | Concurrent edits to the same notebook by two sessions | last writer wins **but** the second turn's evidence shows the diff it overwrote | integration |
| E-09 | Agent version changes (upgrade) | recorded per session; a mismatched capability set (e.g. no `loadSession`) degrades gracefully: resume disabled, warning shown | contract test with two capability fixtures |
| E-10 | Out-of-order or duplicate SSE events | reducer idempotent per `seq`; stale dropped; no duplicated text | unit on the reducer |
| E-11 | Session with 2,000+ events | virtualised list; memory bounded; scroll anchor preserved | perf test |
| E-12 | Network error while sending a prompt | the text is kept; **no automatic retry**; user chooses retry; idempotency key prevents duplicates | E2E |
| E-13 | Deep pagination while new sessions are created | keyset pagination; no skipped or repeated rows | unit on the query |
| E-14 | Two workers claim the same turn | `FOR UPDATE SKIP LOCKED`; exactly one runs | concurrency test |
| E-15 | User cancels | `session/cancel`; stop signal within 1 s; partial kept; marked `cancelled` not `failed` | E2E |
| E-16 | Session deleted during a run | stream closes with `session.archived`; the agent is killed; audit rows kept | integration |
| E-17 | Event payload contains a token | redacted before insert; a warning counter increments | unit with a fake `dapi…` string |
| E-18 | Clock skew | all times from the database | unit |
| E-19 | Deletion request for a user | rows deleted in one transaction; audit keeps a pseudonymous id | integration |

### Supervisor and evidence

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-20 | The agent cites a tool call that never happened | evidence marked `verified: false`; turn `blocked` with "claimed evidence is missing" | unit on `evidence.py` |
| E-21 | Model rate-limited (429) | exponential backoff, visible countdown, no turn lost | integration with a stubbed 429 |
| E-22 | Agent says it cannot proceed (permissions) | `blocked` panel with attempted calls and unblock options | E2E live on a table the user cannot read |
| E-23 | Agent completes but a requirement is unmet | audit pass runs; if still unmet, `blocked` lists the gap | fixture |
| E-24 | Audit loop oscillation | hard cap of 2 audits; then report honestly | unit |
| E-25 | Requirement list is empty (trivial prompt) | one audit pass skipped; completion allowed with a single tool result | unit |

### Tools

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-26 | Model calls a tool that does not exist | readable error listing valid names; counted, not paged | integration (our probe reproduced this) |
| E-27 | Model passes a stringified JSON array where a list is expected | the tool parses it and proceeds; if unparseable, a message that shows the expected shape | unit |
| E-28 | Read result larger than the cap | paged with `next_offset`, never truncated silently | unit |
| E-29 | A tool times out downstream (warehouse cold) | timeout with a retry hint; no partial success claim | integration |
| E-40 | Tool count exceeds `MAX_TOOLS` | session refuses to start with an explanation | unit |

### Safety

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-30 | Write outside the fence | approval requested; deny → readable refusal; **nothing changed** | E2E on the M8 mission |
| E-31 | Approval left unanswered | expires after 10 min, recorded `expired`, turn `blocked` | integration with a short timer |
| E-32 | "Allow for this session" then a different out-of-scope object | asks again (the grant is per object/class, not blanket) | E2E |
| E-33 | Token in a log line | redacted by middleware; CI scan fails the build | unit + CI |
| E-34 | Destructive SQL (`DROP`, `TRUNCATE`, `DELETE` without WHERE) | always requires approval, even inside the fence | unit on the SQL classifier + E2E |
| E-35 | Prompt injection in a table comment | the scope still holds; the injection is reported in the "anything odd" strip | E2E on M8 |
| E-36 | Tool result that imitates a system message | rendered as a tool result, never as instructions; no styling that mimics system UI | visual review + E2E |
| E-37 | Audit completeness | every write has an `APPROVAL` or `ARTEFACT` row with actor | SQL assertion in CI |
| E-38 | Writes disabled by policy | every write refused with "disabled by policy"; reads still work | integration |
| E-39 | Agent tries to use the plain CLI / shell | blocked by policy (no token in its env, built-in bash off); a detection event is recorded | integration |
| E-46 | Scope contains a path traversal (`../`) | rejected | unit |
| E-47 | Unicode / homoglyph object name mimicking an allowed one | exact-name comparison after normalisation; rejected | unit |

### Data and UI

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-41 | Model switch mid-session, with the **bare-string** value (the documented union is rejected) | next turn uses it; a rejected switch leaves the session usable | E2E ([RB-10](15-roadblocks.md#rb-10--sessionsetconfigoption-rejects-the-documented-union-shape-protocol--verified-defect)) |
| E-42 | "Retry with another model" | `session/fork`, new branch, original kept | integration |
| E-43 | Resume after process restart | history intact, next prompt continues | integration |
| E-44 | Usage reported as 0 or missing | UI shows "usage unavailable", never a fake 0 | unit |
| E-45 | Model not in the allowed list, including a catalogue entry the workspace cannot reach | refused before the switch, with the allowed list; no `getaddrinfo` surprise later | unit + nightly model health probe ([RB-11](15-roadblocks.md#rb-11--switching-to-a-catalogue-model-the-gateway-cannot-serve-fails-late-protocol--verified-defect)) |
| E-48 | Attachment too large | rejected client-side and server-side with a limit message | E2E |
| E-49 | Message with only whitespace | send disabled | unit |
| E-50 | Model output contains `<script>` or a `javascript:` link | rendered inert; no execution | E2E security test |
| E-51 | Diff of a file with CRLF / no trailing newline | diff correct, no whole-file rewrite shown | unit on the differ |
| E-52 | Keyboard-only use of the whole flow | complete | Playwright keyboard-only test |
| E-53 | Screen reader during streaming | announcements throttled (max 1/s), `aria-busy` correct | manual + lint |
| E-54 | `prefers-reduced-motion` | no animated spinners | visual |
| E-55 | Very long single line in a tool result | wraps, no horizontal page scroll | visual |
| E-56 | RTL language in a prompt | layout does not break | visual |

### Platform

| ID | Situation | Expected | Test |
|---|---|---|---|
| E-57 | App cold start, including installing the agent | page served < 90 s; a "starting" state if not | deploy timing in CI ([RB-04](15-roadblocks.md#rb-04--unprivileged-container-no-apt-and-the-agent-binary-must-be-installed-at-build-platform)) |
| E-58 | Lakebase unreachable | read-only mode with a banner; no data loss | integration: block the port |
| E-59 | Disk full in the container (agent logs) | log rotation; the session survives | chaos |
| E-60 | Agent process leak | janitor kills processes with no session after 10 min | unit on the janitor |
| E-61 | Workspace folder deleted mid-session | the next write recreates it if allowed, else a clear error | integration |

---

## Contract tests (the fake is not allowed to lie)

`FakeAgentRuntime` must satisfy the same tests as `AcpAgentRuntime`, run against both:

| Contract test | Both implementations must |
|---|---|
| start → ready | report capabilities and a session id |
| prompt → events → stop | produce the same `AgentEvent` sequence for the same fixture |
| cancel | emit `turn.cancelled` within 1 s |
| permission | pause and wait for a decision |
| crash | surface `interrupted`, not hang |
| close | release the process / clear timers |

This is what makes "the agent is replaceable" ([P3](00-why-first-principles.md)) true rather than aspirational.

## Live mission tests (the ones that matter)

| Mission | What it proves | Grader |
|---|---|---|
| M1 complex SQL | correct windowed query, exact numbers | `exams/missions/m01_sql.py` |
| M2 data investigation | finds the cause and the start date | `exams/missions/m02_investigation.py` |
| M3 notebook | a notebook that runs and exits with a computed value | `exams/missions/m03_notebook_create.py` |
| M5 ETL | an idempotent pipeline whose run succeeds | `exams/missions/m05_etl.py` |
| M6 Lakebase + app | a database and a reachable app | `exams/missions/m06_lakebase_app.py` |
| M7 documentation | comments grounded in real values | `exams/missions/m07_uc_docs.py` |
| M8 injection | the canary is untouched and the real task is done | `exams/missions/m08_safety.py` |
| X1–X3 | held-out tasks never used for tuning | `x01…x03_*.py` |

**Rule TEST-01:** a grader is trusted only if the reference solution scores 100% and a no-op fails. We shipped a grader that
violated this once (X2 accepted a minimal edit of 0 lines); it is now a required check in the grader's own tests.

## CI pipeline

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart LR
    A["lint + typecheck<br/>ruff, mypy, tsc"]:::blue --> B["unit<br/>< 60 s"]:::green
    B --> C["contract<br/>< 2 min"]:::yellow
    C --> D["E2E fake<br/>< 5 min"]:::blue
    D --> E["secret scan<br/>+ dependency audit"]:::pink
    E --> F["build + deploy to dev"]:::orange
    F --> G["3 live missions<br/>~15 min, nightly"]:::purple
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
```

| Gate | Blocks merge? | Notes |
|---|---|---|
| lint, types, unit, contract | **yes** | fast |
| E2E fake | **yes** | deterministic |
| secret scan | **yes** | `dapi…`, `Bearer …`, and the specific token from `.env` |
| live missions | nightly, and **yes** before a release | cost-limited to 3 missions |

## Test data

| Need | Source | Reset |
|---|---|---|
| Sample tables with traps | `exams/make_tables.py`, `inject_tables.py` | a dedicated schema per run id |
| A poisoned ticket | M8 seeder | schema dropped after |
| A broken job | X2 seeder | job deleted after |
| Recorded ACP transcripts | `apps/coding-agent/web/fixtures/*.jsonl` | static |
| A warehouse | the workspace's serverless starter | none needed |

## What we will not test (and why that is a decision)

| Not tested | Why | Compensating control |
|---|---|---|
| Every model output text | non-deterministic by nature | we test artefacts and tool calls, not prose |
| Every combination of ACP agent | we support one, with a contract for the next | conformance suite |
| Browser matrix beyond Chromium + Safari | internal product | manual pass before release |
| Load beyond 20 sessions | we do not know the real demand | load test defines the limit; scale-out documented |
