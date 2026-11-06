[Index](README.md) · [00 Why](00-why-first-principles.md) · [01 Product](01-product-requirements.md) · **02 Architecture** · [03 ACP](03-acp-integration.md) · [07 Back end](07-backend.md) · [12 Ops](12-operations.md)

# 02 · Architecture

## The shape: a host, not an agent

The app **hosts** agents. It never contains agent logic, model prompts or tool implementations. Three consequences:

1. The agent can be swapped (OpenCode → another ACP agent) without touching the UI, schema or governance.
2. The tool server is a separate process with its own credentials and its own policy: the fence is not in the same memory space as the loop that a model can influence.
3. Every boundary is a process boundary or a network call, so every boundary can be tested in isolation.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','clusterBkg':'#F8FAFC','clusterBorder':'#CBD5E1'}}}%%
flowchart TB
    subgraph BR["Browser · React + Vite"]
        direction LR
        UI1["Chat pane"]:::green
        UI2["File tree + diff"]:::green
        UI3["Trace + evidence"]:::green
        UI4["Approval sheet"]:::green
        STORE["Client store<br/>event reducer"]:::green
        UI1 --- STORE
        UI2 --- STORE
        UI3 --- STORE
        UI4 --- STORE
    end
    subgraph C["App container · FastAPI, 2 workers"]
        direction TB
        R1["REST<br/>/sessions, /messages, /files"]:::yellow
        R2["SSE<br/>/sessions/:id/stream"]:::yellow
        R3["Approvals<br/>/approvals/:id"]:::yellow
        ORCH["Orchestrator<br/>session lifecycle"]:::purple
        SUPP["Supervisor<br/>loop, audits, evidence"]:::purple
        ADPT["ACP adapter<br/>JSON-RPC over stdio"]:::teal
        MCPH["MCP host<br/>per-session tool server"]:::pink
        POL["Policy<br/>models, tools, scopes"]:::orange
        REPO["Repositories<br/>sessions, events, audit"]:::orange
    end
    DB[("Lakebase<br/>Postgres")]:::blue
    GW["AI Gateway"]:::blue
    WS["Workspace APIs<br/>UC, notebooks, jobs, apps"]:::blue
    R1 --> ORCH
    R2 --> ORCH
    R3 --> SUPP
    ORCH --> SUPP --> ADPT
    ORCH --> MCPH
    ORCH --> POL
    ADPT -->|"MCP http"| MCPH
    ADPT -->|"chat completions"| GW
    MCPH -->|"REST + SQL<br/>as the user"| WS
    REPO --> DB
    ORCH --> REPO
    SUPP --> REPO
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
    classDef teal fill:#E0F5F3,stroke:#9AD5CE,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
```

## Components and their single responsibility

| Component | Owns | Must not own | Home doc |
|---|---|---|---|
| **React app** | Rendering, local event reduction, optimistic UI, reconnection | Business rules, permissions decisions | [06](06-frontend.md) |
| **REST + SSE API** | Transport, auth extraction, request validation | Session logic | [07](07-backend.md) |
| **Orchestrator** | Session lifecycle: create, start, resume, cancel, delete | Prompting, tool policy | [07](07-backend.md) |
| **Supervisor** | Deciding when a turn is *done*: continue, audit, or stop | Executing tools | [04](04-tools-skills-mcp.md) |
| **ACP adapter** | Translating our `AgentRuntime` port to ACP JSON-RPC | Knowing about Databricks | [03](03-acp-integration.md) |
| **MCP host** | Starting, scoping and health-checking one tool server per session | Rendering, UI events | [04](04-tools-skills-mcp.md) |
| **Policy** | Which models, which tools, which scopes, which writes need approval | Enforcing the fence (the tool server does that) | [09](09-security-security.md) |
| **Repositories** | Persistence, event append, audit | Formatting for the UI | [08](08-data-model.md) |

## Ports and adapters (this is what makes it testable)

The design uses hexagonal architecture, not for elegance but because *the agent is the thing most likely to change*.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8'}}}%%
flowchart LR
    subgraph CORE["Domain core (no I/O)"]
        SESS["Session aggregate"]:::purple
        TURN["Turn / evidence rules"]:::purple
    end
    subgraph PORTS["Ports (interfaces)"]
        AR["AgentRuntime<br/>start, prompt, cancel, close"]:::teal
        TR["ToolRegistry<br/>scopes, approvals"]:::pink
        EV["EventStore<br/>append, replay"]:::orange
        ID["Identity<br/>user token, scopes"]:::blue
        MD["ModelCatalog<br/>allowed models"]:::blue
    end
    subgraph AD["Adapters"]
        ACP["AcpAgentRuntime<br/>(opencode acp)"]:::teal
        FAKE["FakeAgentRuntime<br/>(tests, demos)"]:::teal
        MCPA["McpToolRegistry"]:::pink
        PGA["PostgresEventStore"]:::orange
        OB["OboIdentity"]:::blue
        DBM["DbModelCatalog"]:::blue
    end
    SESS --> AR
    SESS --> EV
    SESS --> TR
    AR --> ACP
    AR --> FAKE
    TR --> MCPA
    EV --> PGA
    ID --> OB
    MD --> DBM
    classDef purple fill:#EFE7FB,stroke:#C9B6EC,color:#1F2937
    classDef teal fill:#E0F5F3,stroke:#9AD5CE,color:#1F2937
    classDef pink fill:#FDE7EF,stroke:#F2B5CB,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
```

**`FakeAgentRuntime` is a first-class citizen.** It replays recorded ACP transcripts, which gives us deterministic tests for
the whole UI and supervisor, and lets demos run without a model. Without it, every test would depend on a non-deterministic
model.

### The `AgentRuntime` port

```python
class AgentRuntime(Protocol):
    async def start(self, spec: SessionSpec) -> RuntimeHandle: ...          # spawn, initialize, session/new
    async def prompt(self, h: RuntimeHandle, blocks: list[ContentBlock]) -> str: ...  # returns messageId
    async def cancel(self, h: RuntimeHandle) -> None: ...
    async def set_model(self, h: RuntimeHandle, model_id: str) -> None: ...
    async def respond_permission(self, h: RuntimeHandle, request_id: str, outcome: Outcome) -> None: ...
    def events(self, h: RuntimeHandle) -> AsyncIterator[AgentEvent]: ...     # normalised updates
    async def close(self, h: RuntimeHandle) -> None: ...
```

Everything the rest of the system knows about an agent is in that interface. **No OpenCode flag, path or version string
appears outside `adapters/acp/`.**

## Data flow of one turn

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','actorBkg':'#E8F0FE','actorBorder':'#A8C0E8','noteBkgColor':'#FFF8E1','noteBorderColor':'#F2D98D'}}}%%
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI
    participant O as Orchestrator
    participant S as Supervisor
    participant A as ACP adapter
    participant P as opencode acp
    participant T as MCP tool server
    participant W as Workspace
    participant DB as Lakebase
    U->>API: POST /sessions/{id}/messages {text}
    API->>O: submit(text, user_token)
    O->>DB: append(turn.started)
    O->>S: run_turn()
    S->>A: prompt(blocks)
    A->>P: session/prompt (request)
    P-->>A: {messageId} + stopReason later
    loop streaming
        P->>A: session/update (thought, tool_call, message_chunk)
        A->>O: AgentEvent
        O->>DB: append(event)
        O-->>API: publish
        API-->>U: SSE data: event
        P->>T: MCP tools/call
        T->>W: REST / SQL as the user
        W-->>T: result
        T-->>P: result
    end
    S->>S: audit: every requirement has evidence?
    S->>A: prompt(audit) if not
    O->>DB: append(turn.completed + evidence)
    API-->>U: SSE data: turn.completed
```

The SSE stream is **derived from the event store**, not from the agent process. That is the trick that makes reconnection,
multi-tab and pod restarts work: the browser asks "give me events after N" and the server replays from Postgres.

## Why these choices (and the alternatives we rejected)

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| **Where the agent runs** | Child process inside the app container, spawned per session | A separate service / a Databricks job / a sandbox VM per session | Fewest moving parts; the container is already isolated and has the app's identity. A separate service is the v2 path if we outgrow one container ([12](12-operations.md)). |
| **Streaming transport** | SSE (`text/event-stream`) | WebSocket | Databricks' proxy cuts streamed responses at 300 s but Spaces apps **reject WebSocket upgrades**; SSE works on both and reconnects natively ([12](12-operations.md#streaming-and-timeouts)) |
| **Agent protocol** | ACP over stdio | OpenCode's HTTP API; driving the CLI and parsing stdout; the vendor SDK | ACP is an open contract, gives structured tool calls and permissions, and outlives any one agent ([03](03-acp-integration.md)) |
| **Tools** | Our MCP server, injected via `session/new` | Let the agent use its built-in shell/file tools only | The built-in tools are unfenced; our server enforces scope and returns real errors ([04](04-tools-skills-mcp.md)) |
| **State** | Lakebase Postgres, append-only events | In-memory + Redis; the agent's own session store | Audit and replay are requirements, not features ([08](08-data-model.md)) |
| **Front-end state** | A pure reducer over the event stream | Server-rendered HTML; a state library with side effects everywhere | Replay and reconnection become free; the UI can be tested against recorded transcripts ([06](06-frontend.md)) |
| **Identity** | On-behalf-of-user token per request | A single service principal for everything | Per-user permissions are the point ([09](09-security-security.md)) |
| **Long runs** | Background task + polling on the event stream | Holding the HTTP request open | Proxy limit of 300 s is not configurable ([12](12-operations.md)) |

## Deployment shape

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#E8F0FE','primaryTextColor':'#1F2937','primaryBorderColor':'#A8C0E8','lineColor':'#94A3B8','clusterBkg':'#F8FAFC','clusterBorder':'#CBD5E1'}}}%%
flowchart TB
    subgraph W["Databricks workspace"]
        subgraph A["Databricks App (container)"]
            F["React static build<br/>served by FastAPI"]:::green
            S["FastAPI workers x2"]:::yellow
            X["Agent processes<br/>(child, per session)"]:::teal
        end
        LB[("Lakebase instance")]:::blue
        UC["Unity Catalog<br/>+ workspace APIs"]:::blue
        GW["AI Gateway"]:::blue
        V["App secret scope<br/>SP creds, config"]:::orange
    end
    A --> LB
    A --> UC
    A --> GW
    A --> V
    classDef blue fill:#E8F0FE,stroke:#A8C0E8,color:#1F2937
    classDef green fill:#E6F4EA,stroke:#A8D5B5,color:#1F2937
    classDef yellow fill:#FFF8E1,stroke:#F2D98D,color:#1F2937
    classDef teal fill:#E0F5F3,stroke:#9AD5CE,color:#1F2937
    classDef orange fill:#FFEDE0,stroke:#F5C29C,color:#1F2937
```

| Resource | Sizing (starting point) | Notes |
|---|---|---|
| App compute | Medium (2 vCPU, 6 GB) | One agent process ≈ 150–250 MB; cap at 4 concurrent agent processes |
| Lakebase | CU_1, autoscaling | Connection pool per worker; never a connection per request |
| AI Gateway | Model per session | gpt-oss-120b default; a stronger model for hard tasks ([04](04-tools-skills-mcp.md)) |

All sizing numbers are **[proposal]**: the load tests in [12](12-operations.md) replace them.

## Edge cases this architecture must survive

Each is handled by a specific component and tested in [11](11-testing-edge-cases.md).

| Edge case | Handled by | Reference |
|---|---|---|
| E-01 Agent process dies mid-turn | Orchestrator detects EOF, marks turn failed, offers resume | [07](07-backend.md) |
| E-02 Proxy cuts the stream at 300 s | SSE reconnects with `Last-Event-ID`; server replays | [12](12-operations.md) |
| E-03 Two tabs on one session | Both subscribe to the same event stream; no duplicate prompts | [06](06-frontend.md) |
| E-04 App pod restarts during a run | Events are durable; the turn is marked interrupted; the user can resume or retry | [07](07-backend.md) |
| E-05 MCP server fails to start | Orchestrator refuses the turn with a clear error instead of running unfenced | [04](04-tools-skills-mcp.md) |
| E-06 Model refuses or returns empty | Supervisor retries with a continue message, then reports honestly | [04](04-tools-skills-mcp.md) |
| E-07 User token expires mid-session | Next Databricks call fails closed; UI prompts re-auth; nothing falls back to the SP | [09](09-security-security.md) |
| E-08 Concurrent writes to the same notebook | Fence is per user + folder; conflict detection on read-back | [04](04-tools-skills-mcp.md) |

Next: [03 ACP integration](03-acp-integration.md).
