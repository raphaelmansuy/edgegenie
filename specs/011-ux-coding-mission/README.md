# 011 — Agentic mission workspace

## Five whys

1. **Why a mission screen?** A returning user needs to know what the agent is doing or achieved without reading an entire chat.
2. **Why is chat insufficient?** Objectives, plans, tools, files and proof arrive at different times and are scattered across turns.
3. **Why do scattered facts hurt?** The reader must reconstruct which work is current, what is trustworthy and whether intervention is needed.
4. **Why does reconstruction matter?** Agent work continues without the viewer; an ambiguous “done” or spinner can cause duplicate work or misplaced trust.
5. **Why solve this at the mission level?** One accepted user instruction already has an identity, a lifecycle and evidence: the existing turn. A projection of that record supplies a stable place to orient, inspect and act.

## First principles

- A mission is one accepted **turn within a session**, not a new execution engine or database entity.
- Execution, observation and verification are independent. A disconnect cannot turn running work into failed work; a completed answer cannot manufacture proof.
- Every visible number has a denominator and source: plan entries, tool calls, evidence rows or written artifacts in the selected turn.
- The screen answers, in order: **what is the objective; where is it now; what changed; what proves it; what can I do next?**
- The running/auditing turn wins over queued follow-ups. Otherwise show the latest turn; earlier completed/achieved missions remain selectable.
- Human decisions and write boundaries keep their existing server contracts.

## Document graph

| Read | Purpose | Next |
|---|---|---|
| [Product](01-product.md) | Outcomes, research, scope and acceptance IDs | [Design](03-ux-ui.md) |
| [Code and lenses](02-code-and-lenses.md) | Current code and six professional viewpoints | [Architecture](04-architecture.md) |
| [UX/UI](03-ux-ui.md) | ASCII screens, navigation, tokens, interactions | [Edge cases](06-edge-cases-tests.md) |
| [Architecture](04-architecture.md) | Mermaid sequence, E/R and state models; projection contract | [Implementation](05-implementation-plan.md) |
| [Implementation](05-implementation-plan.md) | Ordered DRY/SOLID work and release gates | [Validation](07-validation.md) |
| [Edge cases and tests](06-edge-cases-tests.md) | Requirement-to-test risk matrix | [Evidence](e2e/README.md) |
| [Validation](07-validation.md) | Actual verification and remaining limits | [Evidence](e2e/README.md) |

This extends [durable missions](../010-long-running/README.md), [the shell](../007-ux-ui-improve/README.md) and [document navigation](../010-tab-management/README.md). Local implementation only; workspace identity/warehouse tools are unavailable in this session. No connected Databricks operations are needed or claimed.
