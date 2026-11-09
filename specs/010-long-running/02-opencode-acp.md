# OpenCode, ACP and the repository

[Product contract](01-product.md) → this investigation → [architecture](03-architecture.md) → [implementation](06-implementation-plan.md).

## Code evidence

Paths are relative to the repository root and link to the implementation.

| Code | Observed behavior and implication |
|---|---|
| [orchestrator.py](../../apps/coding-agent/api/services/orchestrator.py) | `submit` schedules a retained asyncio task. `_drain` consumes agent progress; `_settle` applies the existing evidence supervisor. Browser streams never own this task. The change adds atomic journal commits, recovery and execution budgets here rather than inventing another agent loop. |
| [runtime.py](../../apps/coding-agent/api/adapters/acp/runtime.py) | Spawns the ACP process, negotiates v1, sends prompts without a turn-wide RPC timeout, drains updates before completion and now loads a recorded session. Permission futures belong to this server process. |
| [jsonrpc.py](../../apps/coding-agent/api/adapters/acp/jsonrpc.py) | Newline framed JSON-RPC; request IDs are transport identifiers. Notification backpressure now waits instead of silently dropping agent progress. |
| [mapper.py](../../apps/coding-agent/api/adapters/acp/mapper.py) | Normalizes agent messages/tool calls/usage to the application event vocabulary. Mapping support for a v2-shaped state event does not constitute v2 runtime negotiation. |
| [agent_config.py](../../apps/coding-agent/api/adapters/acp/agent_config.py) | Builds OpenCode provider configuration and server-enforced workspace rules. It is reused on restore; no independent provider configuration path. |
| [main.py](../../apps/coding-agent/api/main.py) | Previously selected only MemoryEventStore. Now chooses the durable adapter, restores before serving, and closes runners before storage. |
| [api.py](../../apps/coding-agent/api/routers/api.py) | HTTP acceptance and browser replay. Queue notifications are wakeups; replay reads the committed journal. |
| [useSessionStream.ts](../../apps/coding-agent/web/src/hooks/useSessionStream.ts) | Fresh pages replay from zero because the view is fresh; in-page reconnect uses its last sequence. Online/offline events now update observation state. |
| [package.json](../../apps/coding-agent/package.json) | OpenCode dependency is `^1.18.19`; this is a version range, not a reproducible exact release pin. Protocol support is negotiated instead of inferred from that range. |

The implementation retains three different identifiers: the application session ID, the agent conversation ID, and per-transport RPC IDs. Only the first two belong in a recovery checkpoint. New transport request IDs do not resume an in-flight remote effect.

## Verified protocol facts

`opencode acp` is a JSON-RPC stdio subprocess. `opencode serve` is a separate headless HTTP/OpenAPI surface; the existing HTTP ACP adapter must not be described as a direct client of that REST API. Sources: [OpenCode ACP](https://docs.opencode.ai/docs/acp/), [OpenCode server](https://docs.opencode.ai/docs/server/).

ACP v1 initialization advertises `loadSession`. Only when true may a client send `session/load` with the saved session ID, working directory and current MCP servers. Loading replays history before returning; OpenGenie consumes that replay without inserting it as a new turn, because its own journal already holds the transcript. Source: [ACP v1 session setup](https://agentclientprotocol.com/protocol/v1/session-setup).

In v1 the prompt response ends the turn and carries a stop reason; updates arrive while it is pending. Permission requests are agent-to-client RPCs, so the server must hold their futures even when no browser is attached. Cancellation is a protocol notification and may race with final tool updates. Source: [ACP v1 prompt lifecycle](https://agentclientprotocol.com/protocol/v1/prompt-turn).

v2 is presented as a draft in the official protocol navigation at research time. It changes prompt acceptance and restoration semantics. The runtime explicitly negotiates v1 and rejects an incompatible version. Future v2 support requires a separate tested negotiation/lifecycle change, not fallback parsing. Source: [ACP migration](https://agentclientprotocol.com/protocol/v2/migration).

## Transferable cloud-agent patterns

Separate the user’s client from the session and execution environment; show activity logs and return to the same reviewable work. GitHub documents those boundaries and cross-client continuation. OpenGenie applies that pattern to Databricks identities and workspace tools. Source: [GitHub Copilot cloud sessions](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-on-github).

Cursor documentation could not be retrieved in this session; no undocumented Cursor behavior is assumed. An attempted OpenCode GitHub source path returned 404, so this report claims understanding of the repository’s adapter and the official contracts, not an unverified audit of OpenCode’s latest upstream internals.

## Recovery limits

Persisting the ACP conversation ID does not persist OpenCode’s own database or local files. Preserve OpenCode’s data directory and the agent working directory alongside SQLite, or restore can fail even while all application history remains readable in Lakebase. Failure must never silently create a new agent conversation and pretend it recovered the old one. See [storage operations](08-operations.md).
