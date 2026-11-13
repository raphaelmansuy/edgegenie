# 12 · Decisions, spikes, open questions and risks

[Map](README.md) · principles: [00](00-five-whys-first-principles.md#first-principles) · evidence: [14](14-live-investigation.md) · architecture: [05](05-architecture.md) · plan: [10](10-implementation-plan.md)

**Revised on 13 November 2026 after the live investigation.** Six of the eight spikes are answered, all
eight open questions are decided, six decisions were added (D16 to D21) and two changed (D3, D7). Each
decision names the principle that forces it and the observation (`L-nn` on the workspace, `A-nn` from
the pinned agent, in [14](14-live-investigation.md)) that it rests on. "Decided" means decided by this
spec from first principles; the owner can overrule any of them, and the last column says what evidence
would justify it.

## How a decision is made here

1. State the principle that applies ([FP-1 to FP-11](00-five-whys-first-principles.md#first-principles)).
2. State the fact, with where it was observed.
3. Choose the option that keeps the principle true at the least cost to the user.
4. Say what would change the choice.

A preference that cannot be traced to a principle and a fact is listed under
[open questions](#open-questions), not here.

## Decisions

| ID | Decision | Principle and evidence | Rejected alternative | Revisit if |
|---|---|---|---|---|
| **D1** | The app is the single enforcement point. The tool server becomes a protocol facade that holds a session key and nothing else. | FP-4. Two rules already disagree ([F-05](02-code-grounding.md#f-05)). | Harden the fence in both places. | A measured latency cost of the loopback hop that users notice. |
| **D2** | The shell kit under `/mcp` stays as the tutorial's tool; the app stops shipping a copy. The kit vendors the policy package with a drift check. | FP-4. The copies have diverged ([F-34](02-code-grounding.md#f-34)). | Keep two copies in step by hand. | The tutorial is retired. |
| **D3** | **Changed.** In Review mode the human's answer is collected **in the protocol**: the agent is configured to ask before each mutating tool and blocks on `session/request_permission`. The server still decides: the tool call that follows an approval is applied only if a matching grant exists. Decisions that depend on the arguments (SQL class, irreversible actions in Auto) are collected by the server. | FP-2, FP-4. A-09: the pinned agent asks, with options allow once, always, reject, and waits at no token cost; the arguments arrive on the tool-call update. | Server-mediated polling as the only channel (costs tokens while a person thinks). Relying on the agent's configuration alone (safety would rest on a third party's format, [F-04](02-code-grounding.md#f-04)). | The pinned agent stops asking, or stops sending arguments before the answer. The conformance fixtures detect both. |
| **D4** | Every write carries a base revision. A stale base is a conflict shown to the user. Nothing is merged. For workspace objects the revision is `(object_id, modified_at)`, and the write is check, write, read back. Pipelines use the platform's own `expected_last_modified`. | FP-2. L-07, L-10. | Three-way merge of cells. | [Spec 004](../004-crdt-collaboration/README.md) ships a merge the editor trusts, or the workspace gains a conditional import. |
| **D5** | Evidence is graded against the app's own invocation record. Tool identity for display is `name` when the agent sends it, else `title`. | FP-3. A-05: the pinned agent sends no `name`. A-11: a refusal returned as content is a completed call. | Grade against the agent's tool events. | Never. |
| **D6** | Tables are the state; the journal is the history; the snapshot becomes a cache. | FP-10. [F-28](02-code-grounding.md#f-28), [F-29](02-code-grounding.md#f-29). | One document per session. | Never. |
| **D7** | **Changed.** No tool waits beyond **30 s**. A wake-up creates the next turn. A repeated submit with the same arguments returns the existing operation. | FP-5. A-12: the agent fails any tool call at 60 s, in silence, while the tool keeps running. | The earlier bound of 45 s (too close: a 50 s statement wait plus one more call crosses 60). A long-held call with progress notifications. | The agent's limit is shown to be configurable for servers passed over ACP (S12) and the product needs longer waits; the design does not. |
| **D8** | **Confirmed.** The agent version is exact and locked, checked at boot against a supported list, and configured `"*": "deny"` with explicit allows. | FP-4. A-07: the deny list leaves `skill` and `task` callable. A-08: deny by default works, with wildcards. L-16: the registry's current version differs from the tested one. | A semver range; a deny list. | Never. |
| **D9** | One agent process per conversation stays, started on the first prompt and released when idle. Pooling, and mounting the facade in-process, are deferred. | FP-1. Credential isolation is certain; the saving is unmeasured once spawn is lazy. | Pool sessions in one agent process. | Measured memory pressure with lazy spawn in place. |
| **D10** | Three modes: Plan, Review, Auto. Irreversible actions ask in every mode. Outside the fence is refused for the agent in every mode. | FP-2, FP-4. Genie Code's documentation calls its classifier "not a security boundary" ([01](01-genie-code-acp-assessment.md#a-genie-code-today)). | A classifier that decides what is in scope. | Never for the boundary. |
| **D11** | Generic verbs with a `kind` parameter limited to what the session can use. Old tool names are aliases for one release. | FP-9. A-08: removing two unused tools cut the context by 19%; tool count is paid on every request. | One named tool per asset and verb. | The exams through the app show a loss with generic verbs. |
| **D12** | Undo is a content restore for workspace assets, kept 30 days. Tables have no undo and say so. | FP-2, FP-8. | Delta time travel as undo. | A reviewed design for table restore with its own approval. |
| **D13** | Superseded by D17. | | | |
| **D14** | The supervisor stays deterministic. | FP-3. | A model that judges completion. | Never as a replacement. |
| **D15** | The journal stays single-owner. | [Spec 010](../010-long-running/README.md). | Leases per session now. | A second app instance becomes a requirement. |
| **D16** | **New. Identity tiers.** The agent acts as the user wherever a user scope exists (SQL, workspace objects, catalogue reads, apps, Lakebase). Where none exists (Jobs, Pipelines on an app deployment) it does **not** substitute another identity: it writes the definition as a Databricks Asset Bundle inside the fence for the user to deploy ([AG-38](03-requirements.md#ag-38)). The same handler uses the API directly when the identity allows it (a local token). | FP-1: where the app cannot act as the user, the other identity must be named, narrower and consented; here no narrower identity exists. L-04: Apps have no `jobs` or `pipelines` user scope. | Create and run jobs as the app's service principal for everyone (every user would share one identity's data access, and see D17). Drop jobs and pipelines from scope (abandons the goal). | The platform adds a Jobs or Pipelines scope for apps. The capability probe then switches tier with no redesign. |
| **D17** | **New. No model-written code under the app's identity.** Agent-initiated runs as the app's service principal are off by default. They can be enabled only by declaring a separate run identity that cannot read the app's secret scope or database. The administrators' Run button is unchanged. | FP-1. L-06: the service principal can read the key-encryption key and is the database role; an app has one service principal and it cannot be narrowed. [F-08](02-code-grounding.md#f-08). | Keep it for administrators with a consent prompt per run (one approved hostile run exposes every user's stored key). | Spike S13 shows a second, secret-free app works as a run identity, or the Sandbox API (L-14) becomes available to run code as the user. |
| **D18** | **New. Observe through SQL.** Job runs, task results, pipeline updates, lineage and compute usage are read from `system.lakeflow`, `system.access` and `system.billing` with the user's `sql` scope, and shown with their lag. | FP-1, FP-5. L-12: the tables are queryable. L-04: no API scope to read them otherwise. | Read them as the app's service principal (wrong identity). Show nothing. | A user-scoped read API appears; or non-administrators cannot be granted these tables (then the view says so). |
| **D19** | **New. Review is the default.** A new session starts in Review. The choice is remembered per user. Sessions created before the change keep applying inside the fence, which is their present behaviour. In Plan mode the agent's own `plan` mode is also set. | FP-2: nothing lands that its owner has not seen until they choose otherwise. The protocol text read on 13 November says an agent "should not switch to a mode or configuration that reduces user oversight without user action". A-09: review costs one keystroke and no tokens. A-02: the agent has a `plan` mode. | Auto by default because changes are reversible (true, but trust in an undo comes after seeing a change). | Mode usage shows nearly everyone switches to Auto at once: then offer the choice on first run instead of defaulting. |
| **D20** | **New. The budget is in the unit the agent reports.** Money when the agent reports a cost for the session's model, tokens otherwise. Both meters are always shown. No price table is maintained. | FP-9. A-06: the pinned agent reports cumulative cost in USD for the Vertex model. L-12: compute cost is in `system.billing`, a separate, later addition. | A price table per model in the catalogue (a second source of truth that goes stale). | A provider reports no cost and users need a money budget for it. |
| **D21** | **New. The agent's folder and home belong to the app.** Each session's working folder is created under a root the app owns, outside any user's home; the agent's `HOME` and configuration folders are created by the app; nothing in them is inherited. | FP-7, FP-9. A-04: a folder under a home directory added 15,000 tokens of someone's personal skills to every turn and would load any `AGENTS.md` above it. A-13: the agent runs with an isolated home. | Trust the container's layout. | Never. |

## Spikes

| ID | Question | Status | Answer and evidence | Effect |
|---|---|---|---|---|
| **S1** | Does the pinned agent send `session/request_permission` for an MCP tool set to ask, with its input? | **Answered** | Yes. The request has `sessionId`, `toolCall`, `options`. Its `rawInput` is empty; the arguments arrive on the tool-call update for the same id at the same moment. A reject fails the call and ends the turn with no text. (A-09, A-10) | D3 changed. [AG-18](03-requirements.md#ag-18) added. |
| **S2** | Which user scopes can an app request for jobs, pipelines, apps, database instances? | **Answered** | `apps` and `postgres` exist and the live app holds them. `jobs` and `pipelines` are not offered to apps. (L-03, L-04, L-05) | D16, D18 added. [F-18](02-code-grounding.md#f-18) corrected. |
| **S3** | Does the agent's configuration support deny by default? | **Answered** | Yes: `"*": "deny"` with explicit allows and wildcards. The present deny list leaves `skill` and `task` callable. (A-07, A-08) | D8 confirmed. Task 0.3 no longer waits. |
| **S4** | Can a pipeline be created and run as the user? Can SQL alone deliver incremental ETL? | **Partly** | Not from an app (L-04). The API has a conditional update (L-10). SQL-defined scheduled tables were not tried: it needs a write. | D16. Remaining half is S9. |
| **S5** | Can runs execute under an identity that cannot read the app's secrets? | **Partly** | Not within one app: it has exactly one service principal, which holds `READ` on the secret scope (L-06). The Sandbox API would run code as the user and is not available on this workspace (L-14). | D17. Remaining half is S13. |
| **S6** | What revision do assets expose, and can a write be conditional? | **Answered** | Workspace objects: `object_id` and `modified_at`, no conditional import. Jobs: no modification time. Pipelines: `expected_last_modified`. (L-07, L-09, L-10) | D4 made precise. Risk R2 is now certain, not hypothetical. |
| **S7** | How is a lost statement submit resolved? | **Answered** | A comment tag survives into query history, whose `query_id` is the statement id; job submits take an idempotency token. (L-09, L-11) | [AG-26](03-requirements.md#ag-26) is implementable as written. |
| **S8** | Does the workspace normalise `..`? | **Answered for reads** | A read with `..` is refused with "Bad Request"; a doubled slash resolves. Writes untested. (L-08) | None. The fence does not depend on it. |
| **S9** | Can a scheduled materialized view and a streaming table be created and refreshed from the SQL warehouse as the user? | **Open: needs a write** | | Would make "incremental ETL as you" a first-tier capability on app deployments. |
| **S10** | Does `object_id` survive an overwrite, and is a write with `..` refused? | **Open: needs a write** | | Sharpens D4 and [AG-02](03-requirements.md#ag-02)'s tests. |
| **S11** | What does the app's forwarded token receive from a Jobs call? | **Open: needs the app started** | | Confirms [F-18](02-code-grounding.md#f-18) on the real token. |
| **S12** | Is the agent's 60 s MCP timeout configurable for servers passed over ACP? | **Open** | | Only informative; D7 does not need it. |
| **S13** | Does a second, secret-free app work as a run identity? | **Open: needs a deployment** | | Could relax D17. |

The open spikes that write to the workspace are listed with exactly what they would write in
[14](14-live-investigation.md#what-still-needs-your-permission).

## Open questions

All eight questions from the first version are decided. They are kept here with their answers so the
reasoning can be challenged.

| ID | Question | Decided | Why |
|---|---|---|---|
| **Q1** | What is the default mode? | Review for new sessions; existing sessions unchanged (D19). | FP-2, and the protocol's own guidance on oversight. |
| **Q2** | What is the budget unit? | The unit the agent reports (D20). | FP-9; A-06 shows cost is reported. |
| **Q3** | Should cleanup run on archive? | Never automatically. The archive dialog lists what remains and asks. | FP-8 says account for, not destroy. Deletion is irreversible, so it asks in every mode (D10). On Free Edition the app stops after 24 hours (L-13); nothing may be tied to its lifetime. |
| **Q4** | Memory across sessions? | No. | FP-7: memory the agent writes is data that later reads as instruction. A notes file the user edits is an instruction file ([AG-70](03-requirements.md#ag-70)) and needs no new mechanism. The platform's AgentKit memory scope is not offered to apps (L-04). |
| **Q5** | Dashboards as an asset kind? | No, until the platform allows it as the user. | FP-1. The `dashboards` scope is not offered to apps (L-04). The asset contract admits the kind later. |
| **Q6** | Export a mission as a bundle? | Yes, and it moves from "later" to the main path for jobs and pipelines (D16, [AG-38](03-requirements.md#ag-38)). | FP-1 leaves no other way to deliver them from an app without borrowing an identity. |
| **Q7** | May a teammate review a change? | No. | The owner gate of [spec 010](../010-long-running/README.md). Review by others belongs to Git. |
| **Q8** | Assets inside a Git folder? | Files and notebooks with a base revision. Commit and push are out of scope. | FP-2 applies unchanged; Git operations are a separate consent. |

New questions raised by the investigation, for the owner:

| ID | Question | Proposed answer |
|---|---|---|
| **Q9** | Is Free Edition the reference deployment, or only the development one? | Development only. Its limits (L-13) make "continues while you are away" true for at most 24 hours. The design recovers from a stopped app; the claim on the site should say which edition it was measured on. |
| **Q10** | Should the bundle be the source of truth for app scopes, or the live app? | The bundle, with a deployment check that fails on a difference ([AG-31](03-requirements.md#ag-31)). Add `postgres` and `apps` to it now ([F-39](02-code-grounding.md#f-39)). |
| **Q11** | May I run the write tests S9, S10, S11 and S13 on the development workspace? | Each is small and listed with what it writes. S9 has the most product value. |
| **Q12** | Should compute cost from `system.billing` be shown beside model cost? | Later. It is the honest total cost of a mission and the data is readable (L-12), but attribution to one session needs tagging that does not exist yet. |

## Risks

| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|---|
| **R1** | Renamed, generic tools lower a model's success rate. | Medium | High | Aliases for one release; exams through the app before removal (D11). | A weaker model may need the specific names longer. |
| **R2** | The workspace has no conditional write, so another writer can land between the revision check and the import. **Confirmed (L-07).** | Low | High | Check immediately before the write; read back after; if the content is not ours, mark `Conflicted` and offer the stored previous content. | A lost update inside that window is detected after the fact, not prevented. Stated on the change card. |
| **R3** | Pinning slows adoption of agent fixes. | Medium | Low | Upgrading is "run the conformance fixtures and the exams"; the supported list can hold two versions. | Lag of days. |
| **R4** | Polling spends tokens. | Medium | Low | Review waits in the protocol at no cost (D3). Long runs use wake-ups. Replies are compact. | Some cost per run that is polled inside a turn. |
| **R5** | The capability probe reads a transient failure as a missing scope. | Low | Medium | Only an explicit 403 downgrades; anything else is "unknown, will retry"; the user can re-check. | A short period with fewer tools. |
| **R6** | Ledgers and previous content grow in Lakebase. | Medium | Low | Caps, 30-day retention, per-session size report. Free Edition allows one project (L-13). | Operators must still size storage. |
| **R7** | Nine asset kinds stretch the work. | High | Medium | A setting per kind; each ships when its contract suite and mission pass. | Pipelines and apps may land after jobs. |
| **R8** | Spec 013 work is in progress in the same tree and owns `sqlpolicy.py`. | High | Low | Task 1.1 moves the file without changing it; sequence after 013's merge. | A rebase. |
| **R9** | Changing the agent configuration invalidates the published scores, measured on a byte-identical file. | Certain | Medium | Baseline through the app first; publish kit and app numbers side by side ([10](10-implementation-plan.md#p4-proof-and-cost)). | The headline number may move. |
| **R10** | Review as the default is felt as friction. | Medium | Medium | One keystroke; "for the session" grants per tool and asset; measured after release (D19). | Some users switch to Auto on day one, by their own choice. |
| **R11** | A wake-up continues a mission the user no longer wants. | Low | Medium | Chosen per operation, capped at five, cancelled with the session, bounded by the budget. | One unwanted turn at most. |
| **R12** | **New.** The platform lets an app do less as the user than the product's title promises: no jobs, no pipelines, no Python run. | Certain today | High | Say so in the product (capability sheet), deliver jobs and pipelines as code (D16), observe through SQL (D18), and keep the handlers ready for the API tier. | On an app deployment OpenGenie authors and observes jobs; it does not run them. A local deployment with a user token does. |
| **R13** | **New.** A person approves a bundle they do not read, and deploys it. | Medium | Medium | The definition is a reviewed change with a diff; the fence applies to every path and name in it; schedules are created paused; the report says "defined, not deployed". | The deploy is the user's own act, under their own identity. |
| **R14** | **New.** The agent times out a call and the model repeats it. | Medium | High | 30 s bound; repeated submit returns the same operation ([AG-27](03-requirements.md#ag-27)); submits carry idempotency tokens or tags. | A repeat with different arguments is a second run, as it should be. |
| **R15** | **New.** System tables lag, or a user has no grant on them. | Medium | Low | Show the refresh time; say "not readable by you" instead of an empty list ([AG-39](03-requirements.md#ag-39)). | Job state is minutes old on an app deployment. |
| **R16** | **New.** The reference workspace stops the app after 24 hours or when a quota is hit (L-13). | Certain on Free Edition | Medium | Operations are recoverable by native id; wake-ups fire on the next start; the site states the edition. | Nothing continues while the app is stopped. |
