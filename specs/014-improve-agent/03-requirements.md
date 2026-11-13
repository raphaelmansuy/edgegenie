# 03 · Requirements

[Map](README.md) · from: [principles](00-five-whys-first-principles.md#first-principles), [findings](02-code-grounding.md#findings-register) · to: [architecture](05-architecture.md), [edge cases](09-edge-cases.md), [tests](11-test-e2e-plan.md)

## Personas and jobs to be done

| Persona | Job | Measured by |
|---|---|---|
| **Data engineer** (primary) | Change a notebook, a query, a job or a pipeline and know it is right before it lands. | Share of agent changes applied without a manual redo. |
| **Analytics engineer** | Turn a question into a saved, repeatable SQL asset. | Time from prompt to a verified result with a kept query. |
| **Platform owner** | Let people use an agent without widening what they can touch or spend. | Zero writes outside the fence; spend per user against budget. |
| **Reviewer or auditor** | See what an agent changed, on whose authority, with what result. | Every change and run reachable from the session in two clicks. |

## Reading a requirement

Each has a stable ID, a statement that uses "must", an acceptance criterion that a test can observe, the
phase in the [plan](10-implementation-plan.md), and its traces. IDs are grouped by tens and are not
contiguous on purpose, so a group can grow.

## A. Trust boundary

### AG-01

**The fence fails closed.** A session with no writable schema must refuse every SQL write, and a session
with no writable folder must refuse every workspace write, in the tool server itself.
*Acceptance:* with an empty schema, `DROP`, `CREATE`, `INSERT`, `MERGE`, `ALTER`, `COPY INTO` are each
refused with a reason; the same statements are refused when the policy cannot parse them.
*Phase 0. Closes [F-01](02-code-grounding.md#f-01). Edge cases: [trust](09-edge-cases.md#trust-boundary-and-policy).*

### AG-02

**One path rule.** A workspace path must be normalised, must not contain a `..` segment, and must lie
strictly inside the session folder, by one function used by the tool server, the save route and the
materialise route. A folder of `/` or empty is "no folder".
*Acceptance:* the three callers import the same function; a mutation test that makes it always deny
makes all three refuse; traversal, doubled slashes, a sibling prefix (`/agentX`) and a trailing-slash
variant are each tested.
*Phase 0. Closes [F-02](02-code-grounding.md#f-02), part of [F-05](02-code-grounding.md#f-05).*

### AG-03

**The agent is pinned, configured by allow list, and given a folder and a home the app owns.** The agent
version must be exact and locked, checked at boot against a supported list, and its built-in tools must
be denied by default with planning as the only stated exception. Each session must have its own
working folder under a root the app created, and the agent's home must be a folder the app created.
*Acceptance:* the app refuses to start an agent whose version is not on the list and says which one it
found; the generated configuration is `"*": "deny"` plus explicit allows, and a test with the real
agent shows `skill` and `task` are not callable; no instruction, skill or agent configuration file
exists in the working folder's ancestors or in the agent's home that the app did not write; two
concurrent sessions never share a rules file.
*Phase 0. Closes [F-04](02-code-grounding.md#f-04), [F-36](02-code-grounding.md#f-36),
[F-40](02-code-grounding.md#f-40). Deny by default was verified on the pinned agent (A-08 in
[14](14-live-investigation.md#agent-facts)).*

### AG-04

**Children get an environment built from nothing.** The agent and the tool server must start with an
explicit allow list of variables plus what their session needs. No app secret, service-principal
credential or key-encryption key may be present.
*Acceptance:* a test spawns both children with sentinel secrets in the parent and asserts none is
visible in the child's environment.
*Phase 0. Closes [F-03](02-code-grounding.md#f-03).*

### AG-05

**One SQL policy.** The parser-based policy of spec 013 must be the only classifier, used by the SQL
editor, the tool server and any preview. It returns read, write with targets, destructive, or unknown;
unknown is refused. Dead rules are deleted.
*Acceptance:* `domain/scope.py` contains no SQL rule; the tool file contains no SQL regular expression;
a shared table of statements (including `COPY INTO`, `ALTER … RENAME TO`, `EXECUTE IMMEDIATE`,
`REFRESH`, CTE with DML, comments before the verb) yields the same verdict at every caller.
*Phase 1. Closes [F-05](02-code-grounding.md#f-05).*

### AG-06

**Attached context cannot close its own fence.** The delimiter must be unguessable per turn, and
references must be escaped.
*Acceptance:* content and paths containing the previous literal tags, and the current turn's tag
pattern, leave exactly one opening and one closing delimiter in the rendered block.
*Phase 0. Closes [F-06](02-code-grounding.md#f-06).*

### AG-07

**A session id is only ever accepted from its owner.** Any route that takes a session id, in the path or
the body, must check ownership through one function.
*Acceptance:* a second user sending another user's `sessionId` to save, materialise or any future route
receives 404 and the journal is unchanged.
*Phase 0. Closes [F-09](02-code-grounding.md#f-09).*

## B. Changes

### AG-10

**Every agent write carries a base revision.** A write to an existing asset must state the revision it
was planned against and must be refused if the asset has moved.
*Acceptance:* a write without a base revision to an existing notebook, file, query, job, pipeline or app
is refused; a stale base returns both revisions; a create needs none.
*Phase 1. Closes [F-20](02-code-grounding.md#f-20). Edge cases: [changes](09-edge-cases.md#changes-and-concurrency).*

### AG-11

**Edits are operations, not rewrites.** The agent must be able to replace, insert, delete and move
notebook cells, and to replace a range in a file, without sending the rest.
*Acceptance:* changing one cell of a 60-cell notebook sends one cell; the other 59 are byte-identical
afterwards, including cells the user edited and saved in the meantime elsewhere in the notebook when the
base revision still matches.
*Phase 1. Closes [F-20](02-code-grounding.md#f-20).*

### AG-12

**A change can be reviewed before it lands.** In Review mode the user must see the asset, the base
revision, the fence verdict and a diff, and choose apply, apply and run, or reject, per change.
*Acceptance:* nothing is written before the choice; reject leaves the asset byte-identical and tells the
agent; the card is usable by keyboard and announces its state.
*Phase 1. Wireframe [W3](04-ux-wireframes.md#w3-change-review-card).*

### AG-13

**Three autonomy modes, chosen by the user, enforced by the server.** *Plan*: no mutating or running tool
is offered. *Review*: every change waits for the user. *Auto*: changes inside the fence apply; anything
outside is refused; destructive actions always wait. A new session starts in Review; the choice is
remembered per user.
*Acceptance:* the mode is stored with the session, shown at the composer, changeable between turns, and
a tool-server test proves each mode's verdict table. Destructive is defined in
[05](05-architecture.md#policy). In Plan the agent's own plan mode is also set, as a second layer and
never the only one.
*Phase 1.*

### AG-14

**A conflict is a choice.** When the base revision is stale the change must become "conflicted", never
merged silently, and the user must see theirs, the agent's and the current.
*Acceptance:* an unsaved local edit plus an incoming agent change shows both; neither is lost on reload.
*Phase 1.*

### AG-15

**Every change is in a ledger.** Asset, base and new revision, verdict, who decided, state, the turn and
tool call that produced it.
*Acceptance:* the ledger survives a restart and is readable through a paged route; every applied change
in an end-to-end run has exactly one row.
*Phase 1. Wireframe [W4](04-ux-wireframes.md#w4-changes-ledger). Model in [06](06-data-model.md).*

### AG-16

**The session accounts for what it created.** Each created job, pipeline, app, instance, table, notebook
and file must be recorded, and the user must be able to remove them, with the same fence and identity.
*Acceptance:* archiving a session lists what it leaves behind and what it costs to leave; cleanup deletes
only ledger rows, refuses anything renamed out of the prefix, and reports each result.
*Phase 3. Closes part of [F-22](02-code-grounding.md#f-22).*

### AG-17

**Workspace changes can be undone.** For notebooks, files and definitions the previous content must be
kept and restorable if the asset is still at the revision the change produced.
*Acceptance:* undo restores byte-identical content; undo on a moved asset is a conflict; a table write
states that it has no undo.
*Phase 1.*

### AG-18

**A refusal ends the matter.** When the owner rejects a change or a tool call, the agent must be told
once, the supervisor must not prompt it to continue that work, and the turn must end as "stopped by
your decision" with what was done before.
*Acceptance:* with the pinned agent's real behaviour (failed call, empty answer, `end_turn`) no further
prompt is sent; the same tool call is not requested again in that turn; the turn's outcome names the
rejected change.
*Phase 0. Closes [F-38](02-code-grounding.md#f-38).*

## C. Capability and identity

### AG-30

**One asset contract.** Each asset kind must be implemented once, behind one interface, and that single
implementation must serve the tool catalogue, attachments, routes and the fence.
*Acceptance:* adding a kind touches one new handler module, one viewer and one registration line; an
architecture test fails if a second module names the kind in a conditional.
*Phase 3. Closes [F-23](02-code-grounding.md#f-23). Design in [05](05-architecture.md#the-asset-contract).*

### AG-31

**The session knows what it can do, and offers only that.** At start the app must probe what the current
identity can read, change and run per asset kind, show it, and register only tools that can succeed.
The scopes the deployment declares must be the scopes the deployed app holds.
*Acceptance:* with a token lacking a scope, no tool that needs it is advertised and the capability sheet
says why, distinguishing "not granted" from "no such scope for apps"; the tool count shown is the count
registered; a re-check after a scope is granted adds the tools without a new session; a deployment
check fails when the bundle and the live app disagree on scopes.
*Phase 3. Closes [F-18](02-code-grounding.md#f-18), [F-26](02-code-grounding.md#f-26),
[F-39](02-code-grounding.md#f-39). Wireframe [W8](04-ux-wireframes.md#w8-capability-sheet). The scope
list is recorded in [14](14-live-investigation.md#workspace-facts).*

### AG-32

**Jobs have a lifecycle, at the tier the identity allows.** Where the session's identity may call the
Jobs API (a local token, or a platform that grants it): read a definition; create or update
declaratively by name; notebook, SQL and pipeline tasks; parameters; run; read per-task results; repair
a failed run; pause; delete. Where it may not (an app deployment today): the definition is written as
code ([AG-38](#ag-38)) and runs are observed through system tables ([AG-39](#ag-39)).
*Acceptance:* the X2 exam ("diagnose a nightly job") passes through the app at both tiers; a repair
re-runs only the failed task where the API is available; an update is a change with a diff of the
definition at either tier.
*Phase 3. Closes part of [F-22](02-code-grounding.md#f-22). Wireframe [W6](04-ux-wireframes.md#w6-job-view).*

### AG-33

**Pipelines have a lifecycle, at the tier the identity allows.** With the Pipelines API: read definition
and source files; edit source files as changes; validate (dry run); run an update; read the event log
and output datasets; full refresh only with approval. Without it: source files and definition as code,
updates observed through system tables.
*Acceptance:* a new mission ("fix a failing materialized view") passes; a full refresh always waits for a
person, in every mode; an update uses the platform's own conditional write.
*Phase 3. Wireframe [W7](04-ux-wireframes.md#w7-pipeline-view).*

### AG-34

**Model-written code never runs under an identity that holds the app's secrets.** The agent may run
code as the user. It must not run code as the app's service principal unless the deployment declares a
separate run identity that cannot read the app's secret scope or database. The human Run button for
administrators is unchanged and says whose identity it uses.
*Acceptance:* with the default configuration an agent-initiated run that would execute as the app is
refused with the reason and what to do instead; a deployment check fails if a declared run identity
can read the key-encryption secret; every operation row carries `ran_as`.
*Phase 0 (switch off), Phase 2 (run identity). Closes [F-08](02-code-grounding.md#f-08). Decision D17.*

### AG-35

**Apps have a lifecycle.** Scaffold, deploy, read status and logs, stop, delete.
*Acceptance:* the M6 exam passes through the app including an honest report of a refused deployment.
*Phase 3.*

### AG-36

**SQL uses the service of spec 013.** The agent's SQL must go through the same execution service as the
editor: named parameters, a statement handle, total row count, cancellation and a result that is paged,
not cut.
*Acceptance:* a statement longer than the wait returns a handle that can be polled and cancelled; the
row count is the manifest's total; the grid payload is valid JSON at any size.
*Phase 2. Closes [F-21](02-code-grounding.md#f-21).*

### AG-37

**Anything the agent can work on can be attached.** Job, job run, pipeline, pipeline update and app must
be attachable, resolved by their handler with the user's token.
*Acceptance:* "Fix with agent" on a failed task attaches the run and the task's error; an unreadable
attachment is reported to the model as unread.
*Phase 3. Closes [F-23](02-code-grounding.md#f-23).*

### AG-38

**Where the app cannot act as the user, it writes the definition as code.** For a job or a pipeline on a
deployment with no user scope for it, the agent must produce a Databricks Asset Bundle definition
inside the fence, as a reviewable change, with the command the user runs to deploy it. It must not
create the resource under another identity.
*Acceptance:* the bundle validates with the Databricks CLI in a test; the change card shows the
definition diff; the report says "defined, not deployed" and never "created"; the resource ledger
records the definition as a file, not as a job.
*Phase 3. Closes part of [F-18](02-code-grounding.md#f-18). Decision D16.*

### AG-39

**What cannot be read through an API scope is observed through SQL.** Job runs, task results, pipeline
updates, lineage and compute usage must be readable from the system tables with the user's `sql` scope,
and shown with their lag.
*Acceptance:* the job view lists recent runs with task states on a deployment that has no Jobs scope;
each row says it comes from system tables and when it was last refreshed; a user without the grant sees
"not readable by you", not an empty list.
*Phase 3. Decision D18. Tables listed in L-12 of [14](14-live-investigation.md#workspace-facts).*

## D. Operations and long-running work

### AG-20

**Every run returns within 30 seconds.** A tool must return a result or an operation handle; no tool may
wait longer, whatever the caller asks. The bound is half the pinned agent's own 60 s limit on a tool
call, so that the workspace request inside it has room. The playbooks must say "poll".
*Acceptance:* `wait_seconds=300` is clamped and the reply says so; no shipped skill or tool reply
recommends a wait above the clamp; a lint test enforces it; a test with the real agent shows a
30 s wait returns and a 100 s wait is never attempted.
*Phase 0. Closes [F-19](02-code-grounding.md#f-19), [F-21](02-code-grounding.md#f-21).*

### AG-21

**Silence is judged by what is happening.** The app's idle guard must use a tool limit while a tool call
is in progress and the model limit otherwise, and must treat the agent's own tool timeout as a failed
call with an unknown effect, never as a finished one.
*Acceptance:* a model that is silent for the model limit with no tool in progress fails with the agent's
own error line; a call the agent timed out leaves its operation in the ledger, observable.
*Phase 0. Closes [F-19](02-code-grounding.md#f-19).*

### AG-22

**Operations are durable and observed without a browser.** Each SQL statement, notebook run, job run,
pipeline update, app deployment and instance creation must have a ledger row with its native id, identity
and state, updated by the server while a valid credential exists.
*Acceptance:* close every tab during a job run; on return the state and per-task results are present; a
restart does not lose the native id and never resubmits.
*Phase 2. Wireframe [W5](04-ux-wireframes.md#w5-operation-card). States in
[07](07-sequences-statecharts.md#operation-states).*

### AG-23

**The mission can continue when an operation settles.** The user may choose, per operation, to have the
result queued as the next turn or only to be told.
*Acceptance:* with "continue", a turn starts after the run ends and its context holds the result; with
"tell me", none starts; cancelling the session cancels the wake-up; a wake-up never fires twice.
*Phase 2.*

### AG-24

**A turn can outlive one token while someone is present.** Any authenticated request from the owner must
refresh the session's delegated credential, and the turn's deadline must follow it.
*Acceptance:* with a tab open a turn runs past the first token's expiry; with no tab it is interrupted
at expiry with a restorable state and no repeated operation.
*Phase 2. Closes [F-33](02-code-grounding.md#f-33).*

### AG-25

**Stop reaches the workspace.** Stopping a turn must offer to cancel the operations it started, and a
cancelled SQL statement or run must be cancelled natively.
*Acceptance:* after stop, the statement is `CANCELED` at the warehouse; a run the user chose to keep is
still tracked.
*Phase 2.*

### AG-26

**An unknown outcome is a state.** If a submission's response is lost, the operation must be "unknown",
never retried automatically, and resolvable by lookup.
*Acceptance:* a fault injected after submit and before the handle is stored yields "unknown" and one
native run.
*Phase 2.*

### AG-27

**A repeated submit is the same operation.** If the agent asks to run the same thing with the same
arguments while an operation from that request is unsettled in the same turn, it must receive the
existing handle, not a second run.
*Acceptance:* after a tool call that the agent timed out, an identical call returns the first
operation's id and state; the workspace has one run; changing any argument is a new operation.
*Phase 2. Closes part of [F-19](02-code-grounding.md#f-19). Evidence A-12 in
[14](14-live-investigation.md#agent-facts).*

## E. Evidence, evaluation and cost

### AG-50

**Evidence binds to a call and its result.** The server must keep, per tool call, its id, the tool's
programmatic name, its final status and a bounded digest of its result, and must grade a claim against
that digest.
*Acceptance:* a quoted number absent from the cited call's result is graded "contradicted"; the agent's
own summary is never stored as the result.
*Phase 4. Closes [F-07](02-code-grounding.md#f-07).*

### AG-51

**A refusal is a failure.** A tool that refuses or errors must report a failed call, and a failed call
must never verify a claim.
*Acceptance:* a fenced write that is refused has status `failed` end to end; citing it yields
"unverified".
*Phase 0. Closes part of [F-07](02-code-grounding.md#f-07).*

### AG-52

**Proof follows what happened, in any language.** If a turn changed or ran something, it is complete only
when a later successful observation of that asset exists. The wording of the prompt may add
requirements; it may not remove this one.
*Acceptance:* a non-English "create a notebook" turn with no tool call is not "done"; a write with no
read-back or run is audited.
*Phase 4. Closes [F-25](02-code-grounding.md#f-25).*

### AG-53

**Four grades, shown as they are.** Verified, supported, unverified, contradicted.
*Acceptance:* the mission proof list shows the grade and the result excerpt that produced it; a
contradicted row blocks "completed".
*Phase 4.*

### AG-54

**The exams run through the app.** The eleven missions must be driven through the app's HTTP interface
and graded on the workspace as today.
*Acceptance:* one command produces a score for a model through the app; the published numbers name which
path produced them; a release is blocked by a regression beyond the measured noise.
*Phase 4. Closes [F-27](02-code-grounding.md#f-27).*

### AG-55

**New missions cover the new verbs.** In-place edit of a long notebook, job repair, pipeline fix,
long-running run with continuation, saved query, cleanup.
*Acceptance:* each has a reference solution scoring 100% and a do-nothing agent that fails, as the
existing graders require.
*Phase 4.*

### AG-56

**Context and cost are visible.** Context used and size, tokens and money for the turn and the session,
with the unit the agent reports.
*Acceptance:* a spec-shaped `usage_update` moves the meter; an agent that reports no cost shows tokens
and says cost is unknown.
*Phase 0 (mapping), Phase 4 (display). Closes [F-12](02-code-grounding.md#f-12).*

### AG-57

**A turn's usage is the sum of its passes.** Continuations and audits add.
*Acceptance:* a turn with two audits stores three passes and their total.
*Phase 0.*

### AG-58

**A budget stops work before it is exceeded.** Per session, in tokens or money, set by the user within a
ceiling set by the owner.
*Acceptance:* the supervisor does not start a pass that the remaining budget cannot cover; the turn ends
"budget reached" with what was done; raising the budget allows a continuation.
*Phase 4.*

## F. ACP conformance

### AG-40

**Negotiate, do not assume.** Read the agent's capabilities before using `http` MCP servers, images,
embedded context, resume or list; advertise only what the client implements.
*Acceptance:* an agent without `mcpCapabilities.http` gets a stated failure at start, not a silent
session with no tools.
*Phase 0. Closes [F-16](02-code-grounding.md#f-16).*

### AG-41

**Permissions as the protocol defines them.** Build the approval from `toolCall` and from the tool-call
update that carries its arguments; answer a deny with the offered reject option; answer `cancelled`
only when the turn is cancelled.
*Acceptance:* a request shaped as the pinned agent sends it (empty input in the request, arguments on
the update for the same id) shows the tool, its target and its input; fixtures come from the published
schema and from recorded frames; the fake agent uses the same shape.
*Phase 0. Closes [F-10](02-code-grounding.md#f-10), [F-11](02-code-grounding.md#f-11).*

### AG-42

**Tool calls as the protocol defines them.** Identity from `name` when the agent sends it, else from
`title`; an update changes only the fields it carries; an error is read from the output; `diff` and
`locations` are kept structured.
*Acceptance:* a content-only update after `completed` leaves the status `completed`; the pinned agent's
completed update, which has no title and no kind, keeps both; a failed call's error text is in the
event's error field; a diff block renders in the diff viewer.
*Phase 0. Closes [F-13](02-code-grounding.md#f-13), [F-14](02-code-grounding.md#f-14),
[F-41](02-code-grounding.md#f-41).*

### AG-43

**Every defined update is mapped or counted.** Commands, configuration, session information, notices and
compaction become events; an unknown kind increments a counter and is logged once per kind.
*Acceptance:* the mapper is a table keyed by kind; a test enumerates the published kinds and fails on an
unmapped one.
*Phase 0 (table), Phase 6 (display).*

### AG-44

**Restore without replay when the agent can.** Use `session/resume` when advertised, `session/load`
otherwise.
*Acceptance:* a restore of a 200-turn session sends no history over the pipe when resume is available.
*Phase 6.*

### AG-45

**Commands come from the agent and the user's skills.** The slash menu must merge them with the built-in
templates and say where each comes from.
*Acceptance:* a command the agent advertises appears without a client release.
*Phase 6. Closes [F-24](02-code-grounding.md#f-24).*

### AG-46

**The agent can ask a question.** When the agent supports elicitation the client must advertise it and
render a form.
*Acceptance:* a question is answered by keyboard; skipping returns a decline; a restart expires it.
*Phase 6. Wireframe [W9](04-ux-wireframes.md#w9-question-card).*

### AG-47

**The transport survives bad input and cleans up.** An over-limit or malformed line fails that message,
not the session; closing a session releases all of its state; each stop reason has its own outcome.
*Acceptance:* an over-limit line is followed by a normal update that is delivered; after close no map
holds the session id; `max_tokens` and `refusal` are shown as such and are not audited.
*Phase 0. Closes [F-15](02-code-grounding.md#f-15), [F-17](02-code-grounding.md#f-17),
[F-37](02-code-grounding.md#f-37).*

## G. Scale

### AG-60

**Streaming cost does not depend on history.** Text deltas must be coalesced before they are committed.
*Acceptance:* a 20,000-token answer produces at most one commit per 100 ms or 2 KB; no text is lost on a
crash beyond the last flush window, and the window is stated.
*Phase 5. Closes [F-28](02-code-grounding.md#f-28).*

### AG-61

**The snapshot is written on transitions.** Turn boundaries, tool terminal states, approvals, changes,
operations.
*Acceptance:* commits that carry a snapshot per turn are bounded by its transitions, not its tokens;
recovery tests of spec 010 still pass.
*Phase 5.*

### AG-62

**Sessions are loaded when used and listed by index.** Boot must not read every session; the list must
be per user, newest first by last activity, paged.
*Acceptance:* boot time is flat from 10 to 10,000 stored sessions; the list order is by `updated_at`.
*Phase 5. Closes [F-29](02-code-grounding.md#f-29).*

### AG-63

**The stream uses what it was sent.** A subscriber must take the event from its queue when it is the
next sequence and read the journal only on a gap.
*Acceptance:* a healthy viewer causes no journal read per event; an overflow still heals from the
journal.
*Phase 5. Closes [F-30](02-code-grounding.md#f-30).*

### AG-64

**Catalogue search is one bounded query.**
*Acceptance:* a search issues one statement with a limit, as the user; results state when they are
capped.
*Phase 5. Closes [F-31](02-code-grounding.md#f-31).*

### AG-65

**The tool server reuses connections and exports.** One pooled client; a notebook export cached per
revision for the life of a turn.
*Acceptance:* paging a notebook in five reads issues one export.
*Phase 5.*

### AG-66

**The interface stays linear.** Reducer updates by index; long transcripts and ledgers are windowed.
*Acceptance:* applying an event is independent of turn count; a 200-turn session scrolls at frame rate
in the existing stress script.
*Phase 5. Closes [F-32](02-code-grounding.md#f-32).*

### AG-67

**An agent process exists only while it is needed.** Spawn on the first prompt, not on session creation.
*Acceptance:* creating ten sessions and using none starts no agent.
*Phase 5.*

## H. Context and parity

### AG-70

**Instruction files are discovered.** The user's and the workspace's instruction files, and `AGENTS.md`
found by walking up from the session folder, must be read with the user's token, capped, and placed
after the working agreement as data about preferences, never above the safety rules.
*Acceptance:* a preference in the user's file changes behaviour; an instruction in it to ignore the
fence does not.
*Phase 6.*

### AG-71

**Skills live where Databricks users already keep them.**
*Acceptance:* a `SKILL.md` under the user's skills folder is listed by the skill tool with its
description and loaded on request.
*Phase 6.*

## I. Engineering constraints

### AG-80

**One source for the tool server and its policy.** The repository must hold one copy; anything else is
generated and checked for drift.
*Phase 1. Closes [F-34](02-code-grounding.md#f-34).*

### AG-81

**Services depend on ports.** No service imports an adapter or reads a private attribute; the
orchestrator is split along its responsibilities.
*Acceptance:* an import-graph test enforces it.
*Phase 1 onward. Closes [F-35](02-code-grounding.md#f-35). Design in
[05](05-architecture.md#solid-and-dry-as-rules).*

### AG-82

**Every requirement has a test that fails without it.** Unit for rules, contract for ports, scripted
agent for flows, browser for screens.
*Acceptance:* the matrix in [11](11-test-e2e-plan.md#traceability) has no empty row.

## Non-functional targets

| Property | Target | Measured by |
|---|---|---|
| First event after send | under 2 s at the median, excluding the model | scripted agent timing |
| Tool reply bound | 30 s | [AG-20](#ag-20) |
| Commits per streamed answer | at most 10 per second per session | [AG-60](#ag-60) |
| Boot | independent of stored sessions | [AG-62](#ag-62) |
| Accessibility | WCAG 2.2 AA on the new surfaces | existing `audit:a11y` |
| Recovery | no automatic repeat of any operation | spec 010 tests plus [AG-26](#ag-26) |

## Out of scope

Stated with reasons in [00](00-five-whys-first-principles.md#what-follows-and-what-does-not).
