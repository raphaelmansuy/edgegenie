# Product contract

Start with the [five whys and first principles](README.md). Code grounding and discipline-specific decisions are in [02](02-code-and-lenses.md); visual behavior in [03](03-ux-ui.md).

## Research and interpretation

Primary sources checked on 2026-11-09:

- [Linear issue properties](https://linear.app/docs/issue-properties-home) separates status, priority, relations and optional properties. **Design inference:** present a clear status and a small, stable facts row around one objective.
- [Cursor Agent](https://cursor.com/help/ai-features/agent) documents visible edits, stop, queued instructions and review. **Design inference:** pair live work with inspectable results and explicit intervention; preserve the conversation as the detailed record.

These are inspiration, not a claim of pixel equivalence or a ranking of products. The local design-skill search suggested a documentation landing page, which does not fit this task; retain the repository's warm neutral tokens, vector icons and light/dark themes instead.

## Outcomes and requirements

| ID | Contract | Acceptance |
|---|---|---|
| M-01 | Active session opens a useful mission overview at every width, independent of dock visibility | Objective and state visible after sending, returning and reload |
| M-02 | Running/auditing turn is selected ahead of queued turns; latest terminal otherwise | Queued follow-up cannot masquerade as foreground |
| M-03 | Current, historical, last completed and last achieved work are accessible | Native mission picker and explicit current/last-achieved shortcuts; historical selection stays put during live updates |
| M-04 | Completion and achievement are distinct | Achieved only for a completed turn with nonempty, entirely verified evidence whose call IDs and tool names match completed calls |
| M-05 | Show real plan counts and statuses; no inferred ETA or success percentage | Missing, unknown and unfinished plans remain honest |
| M-06 | Outputs and proof belong to the selected mission | Per-turn artifacts; written/read distinction; evidence opens the exact source tool result |
| M-07 | Full activity and original request remain reachable | Keyboard-operable Overview/Activity tabs and complete request disclosure |
| M-08 | Offline, approval, stop, restore and archive remain actionable and truthful | Existing RunStatus/InlineApproval contracts reused; offline disables mutations; explicit restore never replays work |
| M-09 | Documents can be reviewed and mission overview can be reached again | Persistent Mission overview return control when documents exist; writes refresh documents without stealing the current view |
| M-10 | Responsive, accessible, restrained and theme-aware | No overflow at 320–1920px; keyboard focus; textual statuses; reduced motion; light/dark contrast checks |
| M-11 | Mission UI cannot initiate speculative work | No new agent calls, database queries, migrations or extra polling; no reasoning excerpts in overview |
| M-12 | Verification is reproducible and visually reviewed | Unit/component tests, real HTTP/SSE/ACP local E2E, fixture edge cases, screenshots and inspection ledger |

## Scope and non-goals

A mission is one turn, not an invented cross-session project. A session may contain several missions. The new view does not add task mutation, deploy controls, fabricated costs, elapsed live clocks, approval automation, transcript export formats or a second persistence store. Cross-session navigation remains the existing Sessions rail. [Architecture](04-architecture.md) describes the exact boundaries; [test matrix](06-edge-cases-tests.md) records limitations.
