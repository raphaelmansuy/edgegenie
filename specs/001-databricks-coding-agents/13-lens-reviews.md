[Index](README.md) · [00 Why](00-why-first-principles.md) · [01 Product](01-product-requirements.md) · [05 UX](05-ux-ui-wireframes.md) · [07 Back end](07-backend.md) · **13 Lenses** · [14 Decisions](14-decisions-risks.md)

# 13 · Lens reviews

Seven specialists reviewed the spec. Each section is what they objected to, what changed, and what they still do not like.
This is the document to read if you want to know where the design is weakest.

---

## 1 · Product Owner

**Objections**

1. *"This is a platform, not a feature. What can a user do on day one that they could not do yesterday?"* → Phase 0 delivers
   one thing end to end (a SQL answer with the query shown). The [empty state](05-ux-ui-wireframes.md#screen-2--empty-state-starting-a-session) offers six concrete tasks, not "chat".
2. *"The success metric is a pass rate on our own exams. That is circular."* → Added a pilot with real tasks and a
   **rework rate** ([01](01-product-requirements.md#product-metrics-the-honest-scoreboard)). The exam suite stays as a
   regression net, not as the definition of value.
3. *"You are promising 'as good as Genie Code' but the spec admits the ontology is missing."* → The honest boundary is stated
   in [00](00-why-first-principles.md#the-gap-this-product-must-close) and repeated in the UI copy
   ("where Genie is the better tool"). We will not claim semantic-layer parity.
4. *"Cost is a promise we cannot keep."* → No saving is quoted. Cost is shown as an estimate, and a 2-week pilot measures
   both sides.
5. *"Who owns this in a year?"* → One team, with the ACP adapter as the only place that needs an agent specialist.

**Still unresolved:** whether v1 should include the app-creation flow (M6). It is the most fragile mission (Lakebase + app
provisioning) and the least frequent. Owner: PO, before phase 3.

---

## 2 · Full-stack developer

**Objections**

1. *"A child process per session is an operational liability."* → Accepted, and bounded: max 4 per worker, a janitor for
   orphans (E-60), a restart counter, and a documented path to a separate agent service if it becomes a problem
   ([02](02-architecture.md#why-these-choices-and-the-alternatives-we-rejected)).
2. *"A durable Postgres queue is over-engineering for an internal app."* → Rejected the objection: our Axiom 5 says anything
   can be interrupted, and the platform *will* cut our connections. `create_task` would lose turns on every deploy.
3. *"Two sources of truth for the transcript (events and turns)."* → Kept, but with a repair job and an explicit statement
   that events win ([08](08-data-model.md#event-sourcing-but-pragmatic)).
4. *"The event vocabulary will drift between Python and TypeScript."* → One exporter generates the TS union; the build fails
   on drift ([10](10-implementation-plan.md#the-repository-structure-the-plan-produces)).
5. *"Cancellation across a process boundary is fiddly."* → Documented as cooperative with a 10 s hard kill, and covered by a
   contract test on both runtimes.

**Still unresolved:** whether to run the MCP server in-process (a library call) or as a real HTTP server. Chosen: HTTP,
because ACP requires a URL and because the process boundary is the fence. Cost: a port per session.

---

## 3 · Database expert

**Objections**

1. *"`EVENT.payload` as `jsonb` with 30-day retention will bloat quickly."* → Monthly partitions from day one, and payloads
   dropped after 30 days while keeping the envelope. Capacity table added ([08](08-data-model.md#capacity-estimate-proposal-to-be-confirmed-by-the-load-test)).
2. *"A per-session `seq` from the app is a race."* → Sequence assigned by Postgres in the insert, unique `(session_id, seq)`.
3. *"You store prompts for 90 days; that is user content."* → Explicit retention table, plus a deletion path (E-19). Flagged
   for the privacy owner; may drop to 30 days.
4. *"No foreign-key cascade policy is stated."* → Added: `ON DELETE CASCADE` for events/turns when a session is hard-deleted;
   approvals and artefacts are kept for audit with a soft-deleted session.
5. *"Where do SQL results live?"* → **Nowhere.** Deliberate ([08](08-data-model.md#retention-and-privacy)): it keeps the app
   out of the data-governance blast radius. Cost: a session cannot be replayed with results, only with the *shape* of them.

**Still unresolved:** whether artefacts need a materialised diff rather than a recomputation from events. At 200 artefacts
per session it is fine either way; measured in phase 4.

---

## 4 · UX and UI designer

**Objections**

1. *"Three panes at 1280 px is cramped."* → At < 1100 px the inspector collapses to a drawer; the transcript keeps full width.
   Added to the visual tests.
2. *"Users will not read the evidence panel."* → Evidence is collapsed to one line per requirement, and the *answer* carries a
   subtle "verified" badge that expands it. The badge is the invitation; the panel is the proof.
3. *"The approval sheet will train people to click Allow."* → Three mitigations: deny is equally prominent, "allow for
   session" is per object class not blanket, and every approval shows blast radius. Phase 6 measures approval behaviour.
4. *"What does 'blocked' look like to a non-technical user?"* → Plain words, three unblock options, no error codes
   ([05](05-ux-ui-wireframes.md#screen-4--blocked-the-agent-cannot-proceed)).
5. *"Streaming text plus appearing cards is motion-heavy."* → Cards animate height in 120 ms, respect reduced motion, and the
   transcript never scroll-jumps when the user has scrolled up.

**Still unresolved:** whether the file tree belongs on the right or as a tab. Both are built behind a flag; the pilot decides.

---

## 5 · Front-end designer (implementation)

**Objections**

1. *"Rendering markdown from an untrusted model is a security hole."* → Strict allow-list, no raw HTML, tests with `<script>`
   and `javascript:` payloads (E-50).
2. *"You will re-render the whole transcript on every token."* → Token batching at 16 ms, per-turn memoised selectors, and a
   virtualised list above 100 turns (FE-02/03).
3. *"Reconnection logic is where chat UIs rot."* → The reducer is pure and the resume cursor lives in `localStorage`; the
   four reconnect paths are E2E-tested (E-02, E-03, E-04, E-10).
4. *"Two tabs will double-post."* → A soft focus lock via a `session.focused` event; the second tab is read-only for
   submission.
5. *"Bundle size with Monaco."* → Lazy-loaded only when a diff or a notebook is opened; initial bundle budget 250 KB.

**Still unresolved:** whether to use `EventSource` (no custom headers) or `fetch` + `ReadableStream`. Chosen: `fetch` stream,
because we may need an auth header in non-Databricks deployments; `EventSource` remains the fallback.

---

## 6 · AI engineer

**Objections**

1. *"A single model per session is wrong; task difficulty varies within one conversation."* → Model routing is in the policy
   layer, and mid-session switching is available ([FR-09](01-product-requirements.md)). Automatic routing is deferred to v1.1
   with data from the pilot.
2. *"The supervisor's audit prompt is a prompt, so it can be ignored."* → True. That is why evidence is **verified** against
   the tool-call log (E-20), not just quoted. The prompt asks; the code checks.
3. *"Your tool count budget is arbitrary."* → Yes, and deliberately explicit: 24, with the count shown in the UI so it is
   argued about with data, not vibes.
4. *"Compaction loses information."* → The UI marks the cut, the transcript keeps the full history, and only the model's
   context is compacted.
5. *"Evaluation must include held-out tasks or you are just measuring your own prompt."* → X1–X3 are held out, and the app's
   release gate includes them.

**Still unresolved:** which model is the default. gpt-oss-120b is the only one reachable through the gateway in our workspace;
Gemini scored higher in our exams but needs an external key path ([06 results](../../docs/06-results-and-lessons.md)).

---

## 7 · Coding agent expert

**Objections**

1. *"ACP v4? v2? You are targeting a moving protocol."* → We speak v1 (what OpenCode implements) and normalise v1+v2 shapes
   in one mapper, with fixtures for both ([03](03-acp-integration.md#version-reality-we-speak-v1-plan-for-v2)).
2. *"You found two real defects in your own probe; there will be more."* → They are now rules R-ACP-01…07 and edge cases E-26,
   E-40. The conformance suite is the answer, not a hope.
3. *"Permission handling is the hardest part and you have not exercised it."* → Correct, and it is called out as unverified
   in [03](03-acp-integration.md#what-we-have-not-verified-and-must-before-shipping) and E-30…E-32. Phase 3 cannot ship
   without it.
4. *"The agent will try its built-in tools and bypass your fence."* → Built-in bash is off by default, the token is scoped,
   and E-39 tests the attempt. The residual risk is stated in [09](09-security-security.md#the-inconvenient-truth-about-the-fence-and-the-token).
5. *"Session resume after a process restart needs `loadSession`; not all agents have it."* → Adapter treats it as a
   capability: absent → resume disabled with a warning (E-09).

**Still unresolved:** whether to pin the OpenCode version or float. Chosen: pin, record the version per session, upgrade
deliberately with a conformance run.

---

## What the reviews changed (traceability)

| Change | From | Where |
|---|---|---|
| Blocked panel as a first-class screen | PO + UX | [05](05-ux-ui-wireframes.md#screen-4--blocked-the-agent-cannot-proceed) |
| Evidence verified against the tool log, not quoted | AI + Front end | [04](04-tools-skills-mcp.md#the-supervisor-how-done-is-decided) |
| Durable Postgres queue instead of `create_task` | Full-stack | [07](07-backend.md#request-lifecycle-with-the-durability-trick) |
| Event partitions and payload retention | DB | [08](08-data-model.md#retention-and-privacy) |
| Tool budget with a visible count | Coding agent + AI | R-ACP-06, [03](03-acp-integration.md) |
| Built-in bash off by default | Coding agent | [09](09-security-security.md) |
| Token batch + virtualisation | Front end | [06](06-frontend.md#performance-rules) |
| Cost labelled "estimate" | PO | [01](01-product-requirements.md) |
| Held-out tasks in the release gate | AI | [11](11-testing-edge-cases.md#live-mission-tests-the-ones-that-matter) |

Next: [14 Decisions and risks](14-decisions-risks.md).
