[Index](README.md) · [00 Why](00-why-first-principles.md) · **01 Product** · [02 Architecture](02-architecture.md) · [05 UX](05-ux-ui-wireframes.md) · [10 Plan](10-implementation-plan.md)

# 01 · Product requirements

## Who it is for

| Persona | What they do today | What they need | What would make them abandon it |
|---|---|---|---|
| **Data engineer "Amina"** | Writes and debugs notebooks and jobs; uses Genie Code inside notebooks | "Take a request in English, build it, run it, show me it worked" | An answer she has to verify herself, or a tool that breaks her job |
| **Analyst "Ben"** | Writes SQL, investigates numbers | "Answer the question with the SQL visible" | Guessing at columns, or a confident wrong number |
| **Platform lead "Chen"** | Owns governance and cost | Per-user permissions, an audit trail, a cost per session, no data leaving the boundary | A shared service account with god-mode |
| **Newcomer "Dara"** | Learning the lakehouse | Explanation, the skills the agent used, a file tree of what was made | A black box that only says "done" |

Primary user: **Amina**. If a feature does not help Amina ship a correct pipeline, it is not in scope.

## Jobs to be done

1. *When I am handed a data request,* I want to turn it into a running artefact in the workspace **without leaving Databricks**, so I do not lose 40 minutes to boilerplate.
2. *When something breaks,* I want the agent to find the cause and prove the fix by re-running, not to suggest a fix.
3. *When I doubt an answer,* I want to see the SQL and the tool calls behind it, so I can defend the number in a meeting.
4. *When I ask for something risky,* I want to be asked first, in terms I understand, not to discover it afterwards.
5. *When I come back tomorrow,* I want my session, its files and its history, exactly where I left them.

## In scope, out of scope

| In scope (v1) | Out of scope (v1, and why) |
|---|---|
| Chat with an ACP agent, streamed | Voice input |
| File tree of everything the session created, with diffs | A full IDE: no code editing by hand in the app (v1.1) |
| Notebook create / read / run, SQL, jobs, pipelines, Lakebase, Apps | Genie ontology / business-term answers (link out instead) |
| Evidence cards and an audit trail | Multi-agent orchestration (one agent per session) |
| Approval before a write outside the fence | Scheduled / headless runs (v2) |
| Model choice per session, with a policy | Model fine-tuning |
| Session export (Markdown + JSONL) | Real-time collaboration on one session |

## Requirements

Priorities: **M** must, **S** should, **C** could. Each has an acceptance test in [11](11-testing-edge-cases.md) and a
design home in the document named.

### Functional

| ID | Requirement | Pri | Acceptance (plain words) | Design |
|---|---|---|---|---|
| FR-01 | A user can start a session in a chosen workspace folder with a chosen model | M | Session appears in the sidebar; the agent's first tool call uses the chosen folder | [05](05-ux-ui-wireframes.md), [03](03-acp-integration.md) |
| FR-02 | Messages stream token by token, including reasoning and tool calls, in order | M | A 60-second answer renders incrementally and never appears all at once at the end | [07](07-backend.md), [06](06-frontend.md) |
| FR-03 | Every tool call is shown with its name, arguments summary, status and duration | M | A run with 12 tool calls shows 12 cards in order, each with a final status | [05](05-ux-ui-wireframes.md) |
| FR-04 | Tool results that change the workspace are shown as **evidence cards** linking to the artefact | M | Creating a notebook yields a card that opens the notebook in Databricks | [05](05-ux-ui-wireframes.md) |
| FR-05 | A file tree shows everything created or modified in the session, with before/after diffs | M | Diff of a 3-line notebook edit shows exactly 3 changed lines | [05](05-ux-ui-wireframes.md), [08](08-data-model.md) |
| FR-06 | A write outside the allowed scope triggers an approval request the user can allow once, allow always for this session, or deny | M | Deny produces a tool error the agent can read; allow proceeds and is audited | [04](04-tools-skills-mcp.md), [09](09-security-security.md) |
| FR-07 | The user can cancel a run; the partial transcript is kept | M | Cancel within 1 s marks the run cancelled and keeps the events received | [03](03-acp-integration.md), [07](07-backend.md) |
| FR-08 | A session can be resumed after a page reload, a pod restart, or a proxy timeout | M | Reload during a run reattaches and replays from the last event | [07](07-backend.md), [08](08-data-model.md) |
| FR-09 | The model can be changed mid-session, and the UI shows which model produced which message | S | Switching model changes the next message; earlier messages keep their label | [03](03-acp-integration.md) |
| FR-10 | The agent reads on-demand skills; the UI can show which skills were used | S | A notebook task shows `notebook-authoring` in the trace | [04](04-tools-skills-mcp.md) |
| FR-11 | Session history lists past sessions with a title generated from the first message | S | The list shows "Top zips by revenue", not "Session 47" | [08](08-data-model.md) |
| FR-12 | The user can open, rename, delete and export a session; exports are Markdown and JSONL | S | Export reproduces the transcript with tool calls but no secrets | [08](08-data-model.md) |
| FR-13 | Long runs survive the 300-second proxy limit | M | A 9-minute job run finishes; the UI shows progress the whole time | [12](12-operations.md) |
| FR-14 | A completed task shows proof: for each requirement, the tool result that satisfied it | M | The "Evidence" panel lists one row per requirement with a link | [04](04-tools-skills-mcp.md), [05](05-ux-ui-wireframes.md) |
| FR-15 | The app tells the user when the agent is blocked on something it cannot do, rather than inventing success | M | A blocked task shows "cannot: needs permission on X" and the attempted call | [04](04-tools-skills-mcp.md) |
| FR-16 | The user can see token use and estimated cost per session | C | Session header shows tokens and cost, labelled "estimate" | [12](12-operations.md) |
| FR-17 | The agent can be asked to explain its last action | C | "Why did you do that?" answers from the trace | [03](03-acp-integration.md) |
| FR-18 | A slash command palette invokes skills and canned tasks | C | `/notebook`, `/review`, `/explain` appear and work | [03](03-acp-integration.md) |

### Non-functional

| ID | Requirement | Target | How measured |
|---|---|---|---|
| NFR-01 | Time to first token | p50 < 2.5 s, p95 < 6 s | Server timestamps in the audit record |
| NFR-02 | UI stays responsive during a long run | 60 fps; no jank on a 2,000-event session | React profiler in E2E |
| NFR-03 | Concurrent sessions per app instance | 20 active, 5 streaming per vCPU | Load test ([12](12-operations.md)) |
| NFR-04 | Survives proxy timeouts and pod restarts | 0 lost messages | Chaos test: kill the pod mid-run |
| NFR-05 | Every write is attributable to a user and a session | 100% | Query the audit table: no null `actor` |
| NFR-06 | No secret appears in any stream, log or export | 0 occurrences | Automated scan in CI, as in our exam harness |
| NFR-07 | App start (cold) | < 10 min (platform limit); our target < 90 s | Deploy measurement |
| NFR-08 | Accessibility | WCAG 2.2 AA for all interactive elements | axe-core in CI |
| NFR-09 | Session event write | < 50 ms p95 | Postgres metrics |
| NFR-10 | Cost per session visible within 5 s of each turn | 100% of turns | Token usage from ACP (`usage` on the prompt response) |

### Product metrics (the honest scoreboard)

| Metric | Definition | Baseline | Target after 8 weeks |
|---|---|---|---|
| **Task success rate** | Graded tasks passed / attempted, on our exam suite | 94% for the manual setup with a strong model | ≥ 90% in the app, with the same graders |
| **Evidence coverage** | Completed tasks whose every requirement has a linked tool result | not measured yet | ≥ 95% |
| **Time to first correct artefact** | From prompt to a passing artefact | not measured | −40% vs working in a notebook by hand (pilot) |
| **Rework rate** | Runs followed by "that's wrong, try again" within 2 minutes | not measured | < 20% |
| **Fence violations reaching the workspace** | Writes outside the declared scope that actually happened | 0 in our exams | 0 (**a single occurrence is a Sev-1**) |
| **Session cost** | Tokens × price, per completed task | 2–9 M tokens per 8 tasks in our exams | Within the pilot's agreed budget |

We will not quote a Genie Code saving until a two-week pilot measures both sides on the same tasks
([07 decision guide](../../docs/07-decision-guide.md#cost-in-plain-words)).

## User stories that shape the design

> **US-1 (Amina).** "Build a job that recomputes revenue daily at 06:00." → The agent writes the notebook, creates the job,
> **runs it once**, and the evidence card links to the successful run. If the run fails, the card is red and the next
> message is a diagnosis, not a claim of success.

> **US-2 (Ben).** "Which three zip codes have the highest fare revenue?" → The answer shows the SQL that produced it, and a
> "verified by a second query" badge when the agent cross-checked (our rules ask it to).

> **US-3 (Chen).** "Who ran what yesterday?" → The audit view filters by user, session, tool and object, with the agent
> version and model recorded per call.

> **US-4 (Dara).** "Why is this notebook failing?" → The trace shows the failing cell, the error text, and the diff of the
> fix; the evidence card shows the re-run succeeded.

## The permission moment (the most important interaction)

Most products treat permission as a modal they hope never appears. Here it is the trust-building moment. Design rules:

1. **Say what, where and why** in the user's vocabulary: "Write `workspace.agent_scratch.taxi_hours`" — not `PUT /api/2.0/workspace/import`.
2. **Show the blast radius**: what else could change, and what will not.
3. **Offer the smallest sufficient grant**: this object / this folder / this session.
4. **Never re-ask the same thing twice** in a session (remember "allow always for this session").
5. **Deny is a normal outcome**, not an error: the agent gets a readable refusal and continues with a different plan.

## Success definition (definition of done for v1)

The app is shippable when, in one workspace, with real users:

- [ ] All **M** requirements pass their acceptance tests.
- [ ] The exam suite runs **through the app** (not the harness) and scores ≥ 90% with the configured strong model.
- [ ] A deliberate attempt to write outside the fence is blocked, logged, and visible in the UI as a refusal.
- [ ] Killing the app pod mid-run loses no message and the session resumes.
- [ ] No secret appears in logs, traces, exports or the front end (automated scan).
- [ ] The audit table answers "who changed this table, in which session, with which model" for every write.
- [ ] The cost of a 20-task pilot is measured and agreed with the platform lead.

## Risks the product owner accepts, on the record

| Risk | Accepted because | Mitigated by |
|---|---|---|
| Agents are non-deterministic: the same prompt may fail twice | The alternative (deterministic templates) cannot handle open requests | Supervisor + evidence + retry guidance ([04](04-tools-skills-mcp.md)) |
| A wrong answer can look right | Our tests are execution-based, not text-based | Graders ([11](11-testing-edge-cases.md)) |
| ACP v1 will be replaced by v2 | The app speaks its own interface | Adapter + conformance suite ([03](03-acp-integration.md)) |
| Cost per task is variable | It is still cheaper than a developer's hour | Model routing, tool budget, visible cost |
| The app is another system to operate | It replaces a per-seat premium | Ops plan ([12](12-operations.md)) |

Next: [02 Architecture](02-architecture.md).
