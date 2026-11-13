# 08 · Seven lenses, and the cost of everything

[Map](README.md) · findings: [02](02-code-grounding.md#findings-register) · requirements: [03](03-requirements.md) · plan: [10](10-implementation-plan.md)

Each lens answers the same four questions about the same design: what is right today, what is wrong,
what this spec decides, and what that lens would refuse to ship. Where two lenses disagree, the
disagreement and its resolution are stated at the end.

## Product owner

**The bet.** A team picks OpenGenie over Genie Code for model choice, cost control, a server-enforced
fence and proof of "done" ([README](../../README.md)). Those four are the product; everything else is
table stakes.

| Question | Answer |
|---|---|
| What is right | Two of the four are real and differentiated: the model is a setting, and turns survive a closed tab, which Genie Code's documentation says its multi-step work does not ([01](01-genie-code-acp-assessment.md#a-genie-code-today)). |
| What is wrong | The other two are weaker than the README says. The fence has two holes ([F-01](02-code-grounding.md#f-01), [F-02](02-code-grounding.md#f-02)) and "proven" means "a tool of that name ran" ([F-07](02-code-grounding.md#f-07)). Cost is invisible ([F-12](02-code-grounding.md#f-12)). And the headline score was not measured on the product ([F-27](02-code-grounding.md#f-27)). |
| What this spec decides | Fix the promises before adding features: phases 0 and 1 add no asset kind and close eight of ten High findings. Then lead where Genie Code is thin: reviewable changes on every asset, and runs that continue while the user is away. Say plainly what the platform does not allow: on a Databricks App the agent cannot act as the user on jobs or pipelines, so it defines them as code and watches them through SQL ([identity tiers](05-architecture.md#identity-tiers)). |
| What I would refuse | Shipping jobs, pipelines and apps on the current fence. Publishing a score that the deployed app did not produce. Creating a user's jobs under the app's identity to make a demo work. Saying "runs your ETL" where the product can only define it. |

**Outcome measures.** They are few on purpose, and each has a source.

| Measure | Source | Target for release |
|---|---|---|
| Writes outside the fence | Toolbox refusals versus applied changes, by test and in production | zero applied |
| Agent changes applied without a manual redo | change ledger: applied and not reverted or superseded by a human within the session | reported, then improved |
| Claims contradicted by the record | evidence grades | every one visible to the user |
| Exam score through the app | [AG-54](03-requirements.md#ag-54) | within measured noise of the kit score, per model |
| Cost per completed mission | usage passes | visible; budget honoured |
| Runs that finished while nobody watched | operations settled with zero viewers | works, and is shown in the tour |

**Sequencing by value and risk.** Trust (cheap, urgent) → changes (the visible leap) → operations (the
differentiator) → breadth (the goal in the title) → proof and cost (the thesis) → scale (before growth).

## Full-stack developer

| Question | Answer |
|---|---|
| What is right | Ports and adapters, a pure domain with tests, a scripted agent that makes the interface testable without a model, an event vocabulary with a parity test between Python and TypeScript. |
| What is wrong | The seams have eroded where the agent path grew fastest. One 1,105-line service imports an adapter ([F-35](02-code-grounding.md#f-35)). The tool server is a second application with its own client and rules ([F-05](02-code-grounding.md#f-05), [F-34](02-code-grounding.md#f-34)). The fake agent defines the protocol the client is tested against ([F-10](02-code-grounding.md#f-10)). Adding an asset kind edits six places ([F-23](02-code-grounding.md#f-23)). |
| What this spec decides | One vertical slice per asset kind: handler, registration, viewer. The Toolbox, attachments, routes and capability probe are generic over the registry ([05](05-architecture.md#the-asset-contract)). The client and server share types generated from one event list. |
| What I would refuse | A second policy "just for the UI preview". A handler that decides its own verdict. A test that passes against a private dialect. |

**The vertical slice, concretely.** To add pipelines:

| Layer | File | What is written |
|---|---|---|
| Handler | `api/adapters/databricks/handlers/pipeline.py` | `describe`, `read`, `find`, `plan`, `apply`, `submit`, `observe`, `cancel`, `remove` |
| Registration | `api/adapters/databricks/handlers/__init__.py` | one line |
| Contract test | `tests/test_handlers_contract.py` | parametrised: the new kind joins the list |
| Viewer | `web/src/components/assets/PipelineView.tsx` | the W7 template |
| Route kind | `web/src/domain/route.ts` | one entry |
| Scenario | `api/adapters/fake/scenarios/pipeline-fix.json` | recorded frames |

Nothing in `services/`, `policy/`, `toolbox.py`, `context.py` or the reducer changes. That is the test of
the design.

## Database expert

| Question | Answer |
|---|---|
| What is right | An append-only journal with a per-session sequence, committed before publish. A single-owner lock that refuses a second writer instead of corrupting. A retry receipt stored in the same transaction as acceptance. |
| What is wrong | A `jsonb` document rewritten per event ([F-28](02-code-grounding.md#f-28)). No column to index by owner ([F-29](02-code-grounding.md#f-29)). One connection and one lock for reads and writes of every session. State that users act on (changes, runs) exists only inside event text. |
| What this spec decides | Tables with a stated grain for everything a user can list or act on; natural unique keys for remote things; state guards on every mirrored row; two-phase recording around every remote write ([06](06-data-model.md)). |
| What I would refuse | An "exactly once" claim across the database and the workspace. A backfill that infers changes from old tool text. A table without a bound. |

Decisions that follow: a small read pool separate from the writer connection (reads do not need the
owner lock); partial indexes for the three "what needs attention" queries; `previous_content` encrypted
with the existing envelope and capped at 2 MB; cascade delete from `session`.

## UX and UI designer

| Question | Answer |
|---|---|
| What is right | The document is the centre and the assistant is beside it. One decision surface. Honest states ("needs attention", "interrupted", not a spinner). |
| What is wrong | The agent's most important act, changing the user's work, has no screen: it happens, and the editor notices ([F-20](02-code-grounding.md#f-20)). The approval card can say "write … an object" ([F-10](02-code-grounding.md#f-10)). The user cannot tell what the agent is able to do before asking ([F-18](02-code-grounding.md#f-18)). Jobs, pipelines and apps have no place to be looked at. |
| What this spec decides | Four objects, each with one card and one list ([04](04-ux-wireframes.md#design-position)). Three modes named for what the user feels (Plan, Review, Auto), not for an implementation. Identity shown on every run. Copy that states the cause in the user's terms. |
| What I would refuse | A second place to approve. A badge whose meaning needs a legend. A mode switch buried in settings. A diff the keyboard cannot reach. |

**The interaction budget.** A reviewed single-cell fix is: read the card (one glance), `Enter` to open the
diff if wanted, `A` to apply. Three keystrokes at most, no pointer, no navigation.

## AI engineer

| Question | Answer |
|---|---|
| What is right | Rules that were measured, not guessed: describe before writing, verify after, a four-part report. A supervisor in code, not in a prompt. A small tool set, because every tool is paid for on every request. Attached context labelled as data. |
| What is wrong | The supervisor reasons over strings: requirements by English regular expression ([F-25](02-code-grounding.md#f-25)), evidence by display name, the agent's summary as the result ([F-07](02-code-grounding.md#f-07)). Eight tools are advertised that cannot work ([F-18](02-code-grounding.md#f-18)), which is prompt budget spent on teaching the model to fail. The model must re-emit a whole notebook to change a line ([F-20](02-code-grounding.md#f-20)). The delimiter around untrusted text is forgeable ([F-06](02-code-grounding.md#f-06)). The evaluation harness and the product are different programs ([F-27](02-code-grounding.md#f-27)). |
| What this spec decides | Ground the supervisor in what the server did: invocations, changes and operations are facts; the answer is a claim graded against them. Compute the tool catalogue from capability and mode. Make edits operations. Evaluate through the app. |
| What I would refuse | Any rule that only exists in a prompt. A model-judged "is this done" with no deterministic floor. Adding a tool without a mission that needs it. |

**The supervisor's new floor**, language-independent ([AG-52](03-requirements.md#ag-52)):

| Fact from the ledgers | Consequence |
|---|---|
| The turn applied a change and no later invocation observed that asset successfully | Audit: "read it back or run it" |
| The turn started an operation that is not terminal | Pause, not done |
| A number in the report's Done section is absent from the cited invocation's tokens | Contradicted: block, show both |
| The turn made no invocation and the prompt names an asset or the session is not in Plan mode | Continue once with the act instruction, as today |
| Every change observed, every operation terminal, no contradiction | Done, with grades |

The English heuristics remain as *additional* requirement extraction. They can ask for more proof, never
less.

**Token economics.** Three changes, each measurable on the exams: fewer advertised tools (15, and fewer
when capabilities are missing); cell operations instead of whole notebooks (output tokens proportional
to the edit); a short poll that returns a compact state instead of a long silent wait.

Measured on the pinned agent with Gemini 3.8 Flash ([14](14-live-investigation.md#agent-facts)):

| Observation | Tokens of context per turn | Lesson |
|---|---|---|
| Five small MCP tools, the app's deny list (three built-ins still visible) | 5,414 | The floor today, before any Databricks tool description. |
| The same with deny by default | 4,374 | Two unused built-ins cost 19% of the prompt on every request. |
| The same from a folder under a home directory | 20,598 | Whatever sits above the working folder is paid for on every turn, and read as instruction. |
| A person takes eight seconds to approve a change | 0 extra | Waiting in the protocol is free; polling is not. |

The first row is why the catalogue must be computed from capability and mode: on an app deployment four
Jobs tools are described to the model on every request and can never succeed.

**Prompt-injection posture.** Unchanged in principle, tightened in mechanism: nonce delimiters
([AG-06](03-requirements.md#ag-06)); irreversible actions always ask, in every mode; run-as-app needs
consent and a narrow identity ([AG-34](03-requirements.md#ag-34)); tool titles are shown as the agent's
words, while asset, class and verdict come from the server.

## System design expert

| Question | Answer |
|---|---|
| What is right | Work owned by the server. Journal before publish. No replay after a crash. A reaper with a pure policy. A per-session key for the internal bridge. |
| What is wrong | Process per session created eagerly ([AG-67](03-requirements.md#ag-67)). Children inherit the parent's environment ([F-03](02-code-grounding.md#f-03)). The agent's version floats ([F-04](02-code-grounding.md#f-04)). A turn's lifetime is tied to one token ([F-33](02-code-grounding.md#f-33)). Blocking waits collide with a liveness guard ([F-19](02-code-grounding.md#f-19)). One bad line kills a session ([F-15](02-code-grounding.md#f-15)). |
| What this spec decides | One enforcement point; children with nothing to steal; handles instead of waits; two-phase recording around remote effects; explicit "unknown" and "unobserved" states; lazy processes; pinned and verified agent. |
| What I would refuse | Any automatic retry of a non-idempotent call. A guard that cannot tell "busy" from "dead". A secret in a child that does not need it. A bound chosen without measuring the component that enforces it: the first version of this spec set 45 s against a limit that turned out to be 60. |

**Failure model.** What can fail, and where it lands:

| Failure | Detected by | State | Recovery |
|---|---|---|---|
| Agent process dies | pipe closed | turn `Failed`, session `NeedsRestore` | user restores; nothing repeated |
| Agent silent, no tool running | model idle limit | same, with the agent's error line | same |
| Tool running long | bounded at 30 s by design | operation `Running` | poll |
| The agent times out a tool call (60 s, observed) | the call is reported failed while the server still works | operation `Running`, the call's effect unknown to the model | an identical call returns the same operation |
| App restarts, or the platform stops it (24 hours after its last start on Free Edition) | boot | turns `Interrupted`; changes in `Applying` become `Unknown`; operations keep native ids | lookup, then user decides; wake-ups fire once |
| Token expires | deadline follows refreshes | turn `Interrupted`, operations `Unobserved` | any authenticated request resumes observation |
| Workspace 429 or 5xx | adapter retry rules | retried for reads; writes only when provably not processed | as today |
| Journal unavailable | commit fails | message not accepted (no 202) | client retries with its key |
| Lost response on a write | no confirmation | `Unknown` | read, never write |

**Capacity.** With lazy spawn the binding limits are concurrent *prompting* agents (the existing
semaphore) and observed operations (a few requests per minute each). Idle sessions cost a row. The
facade process per live agent remains until D9.

## The O(n) lens

Symbols: `T` turns in a session (capped at 200), `E` events in a session, `K` tool calls in a turn,
`S` sessions stored, `V` viewers of a session, `c` cells, `N` characters in a notebook, `p` page size,
`M` tables in the metastore, `d` size of an edit.

| # | Operation | Today | Why | Target | How | Requirement |
|---|---|---|---|---|---|---|
| 1 | Commit one streamed delta | **O(T·K)** bytes, serialised, redacted and written | full snapshot per event ([F-28](02-code-grounding.md#f-28)) | **O(1)** amortised | coalesce deltas; snapshot on transitions | [AG-60](03-requirements.md#ag-60), [AG-61](03-requirements.md#ag-61) |
| 2 | A whole answer of `E` deltas | **O(E·T·K)** | 1 repeated | **O(E)** | same | same |
| 3 | Boot | **O(S)** rows read and held | `restore` loads all ([F-29](02-code-grounding.md#f-29)) | **O(active)** | lazy hydration; active operations by partial index | [AG-62](03-requirements.md#ag-62) |
| 4 | List my sessions | **O(S log S)**, wrong order | scan and sort by id | **O(log S + page)** | index on owner and time | [AG-62](03-requirements.md#ag-62) |
| 5 | Deliver one event to viewers | **O(V)** journal queries on one connection | queue used as a wake-up only ([F-30](02-code-grounding.md#f-30)) | **O(V)** memory, zero queries | take from queue when next in sequence | [AG-63](03-requirements.md#ag-63) |
| 6 | Search tables | **O(M)** sequential HTTP calls | walk ([F-31](02-code-grounding.md#f-31)) | **O(1)** statements, O(limit) rows | one catalogue query | [AG-64](03-requirements.md#ag-64) |
| 7 | Read a notebook in pages | **O(N²/p)** bytes transferred | export per page | **O(N)** | cache export per revision per turn | [AG-65](03-requirements.md#ag-65) |
| 8 | Change one cell | **O(N)** output tokens | whole overwrite ([F-20](02-code-grounding.md#f-20)) | **O(d)** | cell operations | [AG-11](03-requirements.md#ag-11) |
| 9 | Restore a session | **O(E)** over the pipe, discarded | `session/load` replay ([F-16](02-code-grounding.md#f-16)) | **O(1)** | `session/resume` | [AG-44](03-requirements.md#ag-44) |
| 10 | Apply one event in the browser | **O(T + K)** | linear scans ([F-32](02-code-grounding.md#f-32)) | **O(1)** | index maps | [AG-66](03-requirements.md#ag-66) |
| 11 | Render a long transcript | **O(T)** nodes mounted | no windowing | **O(visible)** | windowed list | [AG-66](03-requirements.md#ag-66) |
| 12 | Wait for a run of duration `D` | one call of **D** seconds, failed by the agent at 60 with the run still going | blocking wait ([F-19](02-code-grounding.md#f-19)) | **D/30** bounded calls, or zero with a wake-up | operations | [AG-20](03-requirements.md#ag-20), [AG-23](03-requirements.md#ag-23) |
| 13 | HTTP connections per tool call | **O(1) new** each time | client per call | **O(1) reused** | pooled adapter | [AG-65](03-requirements.md#ag-65) |
| 14 | Idle sessions | **O(open)** processes | eager spawn | **O(prompting)** | lazy spawn | [AG-67](03-requirements.md#ag-67) |
| 15 | Reconcile cell identities | O(c²) time and memory | LCS table in [reconcile.ts](../../apps/coding-agent/web/src/domain/reconcile.ts) | O(c²) up to a cap, then O(c) hash match | guard at 400 cells | [EC-63](09-edge-cases.md#scale-and-persistence) |
| 16 | Evidence grading | O(R·rows) tokenising | fine | O(claims + tokens), bounded 16 and 512 | digests precomputed at dispatch | [AG-50](03-requirements.md#ag-50) |

Rows 1 and 2 are the ones that matter first: they are the only costs that grow with *both* the length
of the answer and the length of the conversation, on the path every token takes, through one
connection.

**Bounds that make the rest safe.** These are constants in the design, each enforced in code:

| Quantity | Bound | Where |
|---|---|---|
| Turns per session | 200 | existing `MAX_TURNS` |
| Supervisor passes per turn | 8 | existing limits |
| Tool reply wait | 30 s, half the pinned agent's 60 s limit | Toolbox |
| Attachment text | 6,000 each, 16,000 total | existing |
| Invocation result digest | first 64 KB, 512 tokens | Toolbox |
| Diff stored | 64 KB summary; full diff recomputed from content | ChangeService |
| Previous content | 2 MB | ChangeService |
| Event page | 2,000 | existing |
| Coalescing window | 100 ms or 2 KB | TurnService |
| Poll interval | 2 s growing to 30 s | OperationService |
| ACP line | 16 MB, survivable | transport |

## Where the lenses disagree

| Tension | Positions | Resolution |
|---|---|---|
| **Review friction versus autonomy** | UX wants no interruptions; the platform owner wants a person on every write. | Three modes, chosen per session, default Review for a new user and remembered. Irreversible always asks. |
| **Generic tools versus named tools** | The AI engineer notes models do better with specific names; the developer wants one verb per capability. | Generic verbs with a `kind` parameter whose allowed values are only the kinds this session can use; measured on the exams before the old names are removed. |
| **Normalised tables versus one document** | The database lens wants grain and keys; the developer likes one snapshot to restore from. | Tables are the state; the snapshot stays as a cache during migration and is then derived. |
| **Durable coalescing versus zero loss** | Coalescing can lose up to 100 ms of text on a crash. | Accepted and stated. Tool results, changes and operations are never coalesced. |
| **One process per session versus pooling** | System design sees cost; security sees isolation. | Keep isolation; remove the cost with lazy spawn; revisit pooling per user only with a measured need (D9). |
| **Product wants breadth now; trust work is invisible** | | Phase 0 is small and shipped first; the tour shows the change card in phase 1, which is the visible proof of the trust work. |
