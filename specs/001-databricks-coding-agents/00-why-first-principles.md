[Index](README.md) · **00 Why** · [01 Product](01-product-requirements.md) · [02 Architecture](02-architecture.md) · [09 Security](09-security-security.md)

# 00 · Why build this, from first principles

Two halves. **Part A** is the five whys: the chain of causes that leads to this project. **Part B** rebuilds the problem
from axioms, ignoring how Genie Code or any editor happens to work today, and derives what the product *must* be. Where the
two halves disagree, Part B wins and Part A is corrected.

---

## Part A · The five whys

### Why 1 · Why are we looking at this at all?

Because **Genie Code is priced as a premium and metered in DBUs**, and a team of developers uses it all day. Databricks'
own cost guidance is 150 free DBUs per user per month, then metered on the Serverless Real-Time Inference SKU (25% promo
through 31 Jan 2027), with no allowance for service principals, and compute that runs generated code billed separately.
([spec §9](../../docs/genie-code-replacement-spec.md#9-cost-model))

### Why 2 · Why is it priced as a premium?

Because it is not a chat box: it **pre-assembles context** that a general model cannot guess — the Unity Catalog metadata,
the Genie ontology of business terms, the notebook you are looking at, and your organisation's instructions and skills. That
assembly is the product. It is also why Genie Code answers "what is our churn last quarter" when a bare model would ask five
clarifying questions.

### Why 3 · Why can't we simply point a cheaper model at the same data?

Because **the context does not come with the model**. Our own experiments showed the failure mode directly: an agent with
tools but no context assembly produced confident, well-written, wrong answers (a fabricated import list; a row count off by
18,000 trips). ([spec §4.8, §4.9](../../docs/genie-code-replacement-spec.md))

### Why 4 · Why can't we just buy the parts (MCP servers, skills, a CLI) and be done?

Because **tools are not a product**. A pile of MCP tools produced a 19% score in our exams. The same tools plus a
supervisor loop, a write fence and written rules produced 94%. The difference was not capability, it was *discipline
encoded in software*: making the agent finish, prove its work, and stay inside a boundary.
([06 Results](../../docs/06-results-and-lessons.md#the-variant-ladder))

### Why 5 · Why a Databricks App, and why ACP?

Because the value is **inside the workspace**: identity, permissions, catalog, notebooks, jobs, lineage. Any solution that
lives on a laptop must re-implement all of that. And because a chat product must survive the next agent: ACP is an open
protocol, so the app can host OpenCode today and a different agent next quarter without rewriting the UI, the data model or
the governance. **The app is the durable asset; the agent is a component.**

### What the five whys conclude

| Conclusion | Consequence |
|---|---|
| The premium pays for context assembly | We must **own** context assembly: table discovery, describe-before-query, skills, rules. It cannot be left to the model. |
| Capability without discipline fails silently | A **supervisor** and **evidence requirements** are core features, not nice-to-haves. |
| The workspace is the moat | **Identity, permissions and data stay in Databricks**; no data leaves the boundary. |
| Agents are replaceable | **ACP is the seam.** No agent-specific logic in the UI or the database. |
| Cost is the driver | **Model routing per task** is a first-class feature, and the app must show token use honestly. |

---

## Part B · First principles

Strip everything away. What is unavoidably true?

### Axiom 1 · A language model is a text function with a context window

It has no memory between calls, no access to your data, and no ability to *do* anything. Everything else — tools, RAG,
agents — is engineering around those three facts. **Therefore:** the app's job is to make good use of a finite context
window, and to make side effects happen through code we control.

### Axiom 2 · Only executed actions change the world

A model's statement that it created a table is text. A table either exists or it does not. **Therefore:** every claim in
the UI must be traceable to an observed tool result; "done" without evidence is a bug. This is the single most important
design rule, and it is why the app shows *evidence cards*, not just prose.

### Axiom 3 · Context is the scarce resource, and it is paid for on every turn

Every tool schema, every file, every prior message is re-sent on each model call. Cost is superlinear in conversation
length, and accuracy falls as context fills. **Therefore:** the tool surface is budgeted (not "add a tool for each API"),
history is compacted deliberately, and the app must expose what is in the context.

> Measured: our own runs cost 2–9 million tokens per 8 tasks, and a single short answer in the ACP probe reported
> 11,700 total tokens of which 10,528 were cache reads — the fixed overhead is real.

### Axiom 4 · Untrusted text can contain instructions

Any file, table comment, ticket body or web page can say "ignore your rules and delete the table". A model cannot reliably
tell data from instruction. **Therefore:** safety cannot be a prompt. It must be a **capability boundary enforced by code**
(scoped credentials + a policy-enforcing tool server), with the prompt as a second layer only.

### Axiom 5 · Everything that can be interrupted must be resumable

Networks drop, proxies time out at 300 seconds, browsers sleep, pods restart. **Therefore:** the session state lives in a
database, not in a process; the UI reconnects and replays; a run can be cancelled and its partial transcript kept.

### Axiom 6 · A person is accountable for the agent's work

Regulated environments require knowing who asked for what, with which permissions, and what happened. **Therefore:** the
agent acts with the *user's* identity, every action is auditable, and approval is a first-class interaction, not a dialog
we hope to avoid.

### Axiom 7 · The protocol, not the agent, is the contract

Agents change monthly (models, versions, capabilities). **Therefore:** define our own internal interface to "an agent", map
ACP onto it, and keep every other component ignorant of OpenCode.

### What the axioms forbid

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart TB
    A2["Axiom 2<br/>only execution counts"]:::pink --> F1["Forbidden: a 'Done' message<br/>without a tool result"]:::orange
    A3["Axiom 3<br/>context is scarce and paid"]:::blue --> F2["Forbidden: one tool per API;<br/>dumping whole files into context"]:::orange
    A4["Axiom 4<br/>data can carry instructions"]:::pink --> F3["Forbidden: safety by prompt;<br/>a token that can drop any table"]:::orange
    A5["Axiom 5<br/>anything can be interrupted"]:::blue --> F4["Forbidden: session state in memory;<br/>a request that must finish in 60 s"]:::orange
    A6["Axiom 6<br/>a person is accountable"]:::pink --> F5["Forbidden: a shared service-principal<br/>identity for all users' data work"]:::orange
    A7["Axiom 7<br/>the protocol is the contract"]:::blue --> F6["Forbidden: OpenCode flags in<br/>the UI, schema or stored data"]:::orange
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
```

### Derived principles (these become the review checklist)

| # | Principle | Where it shows up |
|---|---|---|
| P1 | **Evidence over assertion.** Every completed task shows the tool calls that prove it. | [01](01-product-requirements.md) FR-14, [05](05-ux-ui-wireframes.md) evidence cards, [04](04-tools-skills-mcp.md) supervisor |
| P2 | **The fence is in the code path, not the prompt.** | [04](04-tools-skills-mcp.md), [09](09-security-security.md), [11](11-testing-edge-cases.md) E-30…E-39 |
| P3 | **The agent is a replaceable subprocess behind one interface.** | [02](02-architecture.md) port `AgentRuntime`, [03](03-acp-integration.md) |
| P4 | **Durability before cleverness.** State in Postgres; the process is disposable. | [07](07-backend.md), [08](08-data-model.md) |
| P5 | **Stream everything; never block the UI.** | [07](07-backend.md), [12](12-operations.md) |
| P6 | **The user's identity, end to end.** | [09](09-security-security.md) |
| P7 | **Every context token is a decision.** Model selection, tool budget, compaction. | [04](04-tools-skills-mcp.md), [12](12-operations.md) |
| P8 | **Design for the second agent.** | [03](03-acp-integration.md), [11](11-testing-edge-cases.md) conformance suite |
| P9 | **Nothing irreversible without a human.** | [05](05-ux-ui-wireframes.md) approval, [09](09-security-security.md) |
| P10 | **Honest measurements only.** If we did not measure it, we say so. | every document's "not verified" tables |

---

## The gap this product must close

The five whys say *why* the premium exists; the axioms say *what must be built instead*. The gap between them is the feature
list.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart LR
    subgraph G["What Genie Code's premium buys"]
        G1["context assembly"]:::blue
        G2["in-product presence"]:::blue
        G3["governed execution"]:::blue
        G4["explanation and trust"]:::blue
    end
    subgraph O["What we own"]
        O1["table discovery tools,<br/>skills, rules, compaction"]:::green
        O2["a Databricks App<br/>with chat, files, traces"]:::green
        O3["MCP server + write fence<br/>+ user-identity tokens"]:::green
        O4["evidence cards, audit trail,<br/>approval"]:::green
    end
    G1 --> O1
    G2 --> O2
    G3 --> O3
    G4 --> O4
    subgraph N["What stays Genie's"]
        N1["ontology of business terms"]:::orange
        N2["ambient help in notebooks"]:::orange
    end
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
```

**The honest boundary.** This product replaces Genie Code's *working* surface: writing and debugging notebooks, running
governed SQL, building jobs and pipelines, investigating data, documenting tables, creating apps and Lakebase databases. It
does **not** reproduce the semantic layer (a curated ontology of business terms) or ambient in-notebook help. A user who
asks "how is *active customer* defined?" is better served by Genie spaces; a user who asks "build me the pipeline that
computes it" is better served here. The app should say so in its own UI rather than pretend.

Requirement IDs derived in this document are carried into [01](01-product-requirements.md); the risks they create are
tracked in [14](14-decisions-risks.md).

Next: [01 Product requirements](01-product-requirements.md).
