# 01 · Current state audit

[Index](README.md) · prev: [00 Why](00-why-first-principles.md) · next: [02 Requirements](02-requirements.md)

Everything below was read in the repository at the paths and lines cited. Nothing here is inferred
from a vendor document. Where a behaviour is *measured*, the evidence file is named.

---

## What exists, in one picture

<!-- GEN:today -->

```text
┌───────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                              │
│  EmptyState  <select>  models.map(id)   Chrome.tsx:184-188            │
│  Topbar chip <select>  session.model    App.tsx:433-444               │
│  no groups · no search · no state · two naming styles                 │
└───────────────────────────────────────────────────────────────────────┘
                                   │ GET /api/models · POST /api/sessions · POST .../model
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│  FASTAPI                                                              │
├───────────────────────────────────────────────────────────────────────┤
│  GET /api/models                api/routers/api.py:105-112            │
│    allowed  StaticModelCatalog  api/services/identity.py:41-51        │
│    served   ServingBrowser      adapters/databricks/serving.py:18-32  │
│    filter   allowed ∩ served, or allowed when served is None          │
├───────────────────────────────────────────────────────────────────────┤
│  config_for(model_id, host)     agent_config.py:180-189               │
│    KNOWN_ENDPOINTS  (5 ids)     agent_config.py:96-102                │
│    else: string surgery         agent_config.py:185-186               │
│    ENDPOINT_LIMITS  (5 entries) agent_config.py:84-90                 │
├───────────────────────────────────────────────────────────────────────┤
│  AgentConfig.as_opencode_json() agent_config.py:37-66                 │
│    ONE provider block · ONE apiKey {env:DATABRICKS_TOKEN}             │
├───────────────────────────────────────────────────────────────────────┤
│  Orchestrator._provision        orchestrator.py:198-243               │
│    write config → tool server → agent                                 │
│    SessionSpec.env = {DATABRICKS_TOKEN: token}   :227-229             │
└───────────────────────────────────────────────────────────────────────┘
                                   │ stdio JSON-RPC (ACP)
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│  opencode acp                                                         │
│  provider dbx · @ai-sdk/openai-compatible                             │
│  baseURL {host}/serving-endpoints · model dbx/<endpoint>              │
│  NO DATABASE: the event store is a dict                               │
│  api/adapters/memory/store.py:11-13                                   │
└───────────────────────────────────────────────────────────────────────┘
```

<!-- /GEN:today -->

There is no database. The event store is a dict
([`api/adapters/memory/store.py:11-13`](../../apps/coding-agent/api/adapters/memory/store.py)), and
001's Lakebase schema ([001 08](../001-databricks-coding-agents/08-data-model.md)) was written but
not implemented — `rg psycopg apps/coding-agent/api` returns nothing.

---

## E1 · The catalogue is source code

```28:41:apps/coding-agent/api/config.py
    # models
    # Chosen by running the same tasks on every served model (specs 001/18): the non-reasoning
    # models call tools reliably; gpt-oss-120b often ended a turn after reasoning with no tool call.
    default_model: str = "databricks/databricks-llama-4-maverick"
    allowed_models: list[str] = Field(
        default_factory=lambda: [
            "databricks/databricks-llama-4-maverick",
            "databricks/system.ai.gpt-oss-120b",
            "databricks/system.ai.qwen3-next-80b-a3b-instruct",
            "databricks/databricks-meta-llama-3-3-70b-instruct",
            "databricks/databricks-claude-sonnet-4-5",
        ]
    )
```

**Consequence.** A gateway endpoint that appears in the workspace tomorrow is invisible to the app
until somebody edits this list, opens a PR and deploys. The registry exists to make that a
discovery pass.

**Also visible here:** the list already contains an id the app cannot serve. The fifth entry
`databricks/databricks-claude-sonnet-4-5` was added before the gating was known; the runtime guard
is the intersection with `served`, which quietly hides it
([`api/routers/api.py:108-112`](../../apps/coding-agent/api/routers/api.py)). Hiding is not the same
as knowing — the user cannot tell "not available in this workspace" from "not offered by the app",
which is requirement **R-9** in [02](02-requirements.md).

---

## E2 · String surgery as a resolver

```180:189:apps/coding-agent/api/adapters/acp/agent_config.py
def config_for(model_id: str, host: str) -> AgentConfig:
    """Turn an allow-listed model id into the agent's provider configuration."""
    endpoint = KNOWN_ENDPOINTS.get(model_id)
    if endpoint is None:
        # A user may also write the endpoint name directly: databricks/<endpoint>
        short = model_id.split("/", 1)[-1]
        endpoint = short.replace("system.ai.", "databricks-").replace(".", "-")
    context, output = ENDPOINT_LIMITS.get(endpoint, DEFAULT_LIMITS)
    return AgentConfig(host=normalize_host(host), endpoint=endpoint,
                       model_name=endpoint.replace("databricks-", ""), context=context, output=output)
```

**Consequence.** Three separate defects in one function:

| Input | Produces | Should produce |
|---|---|---|
| `databricks/gemini-3-8-flash` | endpoint `gemini-3-8-flash` (a serving endpoint that does not exist) | a 422 at the boundary |
| `openai/gpt-5` | endpoint `gpt-5` | a 422 (today the allow-list catches it; the resolver cannot) |
| `vertex/google/gemini-3.8-flash` | endpoint `google-gemini-3-8-flash`, written to `serving-endpoints` | a Vertex provider block |

The middle row is caught only because `StaticModelCatalog.check` refuses ids not in the list
([`api/services/identity.py:55-57`](../../apps/coding-agent/api/services/identity.py)). If the list
were ever opened up — which is the whole point of this spec — the resolver would silently invent
endpoints. That is Axiom A1's failure mode, live.

---

## E3 · One provider is expressible

```37:66:apps/coding-agent/api/adapters/acp/agent_config.py
    def as_opencode_json(self) -> dict:
        return {
            "$schema": "https://opencode.ai/config.json",
            "model": f"dbx/{self.endpoint}",
            ...
            "provider": {
                "dbx": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Databricks serving endpoints",
                    "options": {
                        "baseURL": f"{self.host.rstrip('/')}{GATEWAY_PATH}",
                        # The token is read from the environment of the agent process, never
                        # written into this file: a config on disk is a secret on disk.
                        "apiKey": "{env:DATABRICKS_TOKEN}",
                    },
```

The dict has no place for a second provider, a second `baseURL`, or a second credential variable.
The `apiKey` is a literal string `{env:DATABRICKS_TOKEN}` — one fixed variable name, hardcoded in the
middle of a data structure. `GATEWAY_PATH = "/serving-endpoints"` is a module constant
([`:20`](../../apps/coding-agent/api/adapters/acp/agent_config.py)), also fixed.

**What the repository already proves is possible.** `templates/opencode.gemini.json` and
`experiments/steps/06_opencode_vertex_gemini.sh` both build a config with **two** provider blocks
(`vertex` and `dbx`) and two different credentials. The capability exists in the agent; only the
app cannot express it.

---

## E4 · The agent receives exactly one secret

```225:229:apps/coding-agent/api/services/orchestrator.py
        # 3. The agent process itself. It authenticates as the USER: the forwarded token is the only
        # credential in a deployed app, and the tool server needs it for the workspace too.
        token = live.extra.get("user_token") or os.environ.get("DATABRICKS_TOKEN", "")
        spec = SessionSpec(session_id=s.id, cwd=cwd, model=s.model, mcp_url=live.mcp_url,
                           env={"DATABRICKS_TOKEN": token} if token else {})
```

One key in `env`. A Vertex key has nowhere to go. Note that the plumbing is already correct and must
be reused rather than replaced: `SessionSpec.env` is merged into the child's environment at
[`api/adapters/acp/runtime.py:42-43`](../../apps/coding-agent/api/adapters/acp/runtime.py)
(`env = {**os.environ, **self._extra_env, **spec.env}`). This spec **widens the payload** of an
existing, working channel — it does not add a new one.

---

## E5 · Two id dialects already coexist

| Where | Value written | Line |
|---|---|---|
| Agent config | `model: "dbx/<endpoint>"` | `agent_config.py:40` |
| Session record | `model: "databricks/<something>"` | `config.py:32-41` stored at `orchestrator.py:182` |
| `set_model` over ACP | the raw session id, e.g. `databricks/system.ai.gpt-oss-120b` | `orchestrator.py:280` |
| Advertised by the agent | whatever `session/new` returns in `configOptions` | `mapper.py:207-213` |

So the app has an "internal id" (`dbx/…`) that it writes, and a "public id" (`databricks/…`) that it
stores and sends to the agent. `model_options` intersects the agent's advertised list with the
allow-list ([`orchestrator.py:264-269`](../../apps/coding-agent/api/services/orchestrator.py)) — an
intersection that can only succeed for models where the two dialects happen to coincide.

---

## E6 · A model switch can be sent in the wrong dialect

```271:282:apps/coding-agent/api/services/orchestrator.py
    async def set_model(self, session_id: str, model: str) -> dict:
        live = self.get(session_id)
        self._models.check(live.state.session.user_id, model)
        try:
            config_for(model, os.environ.get("DATABRICKS_HOST", "")).write(
                live.agent_cwd or tempfile.mkdtemp(prefix="agent-model-"))
        except OSError:
            pass
        if live.handle:
            await self._rt.set_model(live.handle, model)
        live.state.session = updated(live.state.session, model=model)
        return await self.model_options(session_id)
```

Three problems in eleven lines:

1. **Line 279-280** sends `model` (a `databricks/…` id) to `session/set_config_option`, where the
   agent expects its own catalogue value. The probe shows what a bad value costs: `-32603` with a
   DNS error from a provider that was never reachable
   ([`docs/e2e/20_acp_config_probe.txt`](../../docs/e2e/20_acp_config_probe.txt) §C).
2. **Lines 275-278** rewrite `opencode.json` in the running session's cwd. Nothing re-reads that
   file — the agent read it at startup. The write is dead code that *looks* like the switch, and the
   `except OSError: pass` hides it failing.
3. **`_write_token`** is not called here, so a model switch to another provider does not refresh
   that provider's credential in the agent's environment. A key that expires in an hour would go
   stale with no path to renew it short of a new session.

The ACP switch itself is a known-shape call with a documented fallback
([`runtime.py:248-270`](../../apps/coding-agent/api/adapters/acp/runtime.py): a bare string first, the
union shape second), which is correct and stays.

---

## E7 · Limits are a dict, and the guard is one test

```84:91:apps/coding-agent/api/adapters/acp/agent_config.py
ENDPOINT_LIMITS: dict[str, tuple[int, int]] = {
    "databricks-gpt-oss-120b": (128_000, 24_000),
    "databricks-gpt-oss-20b": (128_000, 24_000),
    "databricks-qwen3-next-80b-a3b-instruct": (128_000, 10_000),
    "databricks-llama-4-maverick": (128_000, 8_000),
    "databricks-meta-llama-3-3-70b-instruct": (128_000, 8_000),
}
DEFAULT_LIMITS = (64_000, 4_000)
```

The numbers are right and measured. What is wrong is the container: it is keyed by *serving endpoint*
only, so it cannot hold a Vertex model's 1,000,000-token context, and an unlisted model silently
gets `(64_000, 4_000)` — a guess presented as a fact.

The guard is a test over `Settings().allowed_models`
([`tests/test_genie_features.py:512-519`](../../apps/coding-agent/tests/test_genie_features.py)):

```512:519:apps/coding-agent/tests/test_genie_features.py
def test_every_offered_model_asks_for_no_more_output_than_its_endpoint_allows():
    from api.adapters.acp.agent_config import config_for
    from api.config import Settings
    caps = {"databricks-llama-4-maverick": 8192, "databricks-meta-llama-3-3-70b-instruct": 8192,
            "databricks-qwen3-next-80b-a3b-instruct": 10000}
    for m in Settings().allowed_models:
        c = config_for(m, "h")
        assert c.output <= caps.get(c.endpoint, 24000), (m, c.output)
```

This test is valuable and this spec keeps it — **generalised** into a property of the resolver over
whatever the registry contains, not over a Python list ([10 §Limits](10-edge-cases-testing.md#model-identity-and-limits)).

---

## E8 · The picker is two `<select>` elements

```433:444:apps/coding-agent/web/src/App.tsx
                <span aria-hidden>model</span>
                <select
                  aria-label="Model"
                  value={session.model}
                  onChange={async (e) => {
                    const r = await api.setModel(active, e.target.value);
                    setSession((s) => ({ ...s, model: r.current }));
                  }}
                >
                  {(models.length ? models.map((m) => m.id) : [session.model]).map((id) => (
                    <option key={id} value={id}>{id.split("/").pop()}</option>
                  ))}
                </select>
```

and

```184:188:apps/coding-agent/web/src/components/Chrome.tsx
        <label>Model
          <select value={model} onChange={(e) => onModel(e.target.value)}>
            {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
```

Both render `id.split("/").pop()`. With the current ids that yields `databricks-llama-4-maverick`,
`gpt-oss-120b`, `qwen3-next-80b-a3b-instruct`, `databricks-meta-llama-3-3-70b-instruct`,
`databricks-claude-sonnet-4-5` — **two naming conventions in one dropdown**, in an unsorted,
ungrouped, unlabelled list. Add four providers and it becomes unusable. There is no place for
capability, cost, health, or "this one needs your key".

The stylesheet already anticipates the constraint this must respect: at ≤1100 px the chip hides
because "the model is in the inspector"
([`web/src/styles.css:209-212`](../../apps/coding-agent/web/src/styles.css)), and the meta cluster is
explicitly allowed to compress
([`:198-208`](../../apps/coding-agent/web/src/styles.css)). Any picker added to the topbar must obey
that, and the inspector must carry the truth.

---

## E9 · There is no durable store

`rg -l "psycopg|postgres" apps/coding-agent/api` → **no matches**. The only event store is
`MemoryEventStore`. 001 decided Postgres ([D-06](../001-databricks-coding-agents/14-decisions-risks.md))
and 004 plans Lakebase for CRDT ([004 03](../004-crdt-collaboration/03-implementation-plan.md)), but
neither is built.

**Why this matters for a model registry specifically.** A provider key cannot live in a process
dictionary: it must survive a deploy, and it must be the same key on every replica. So this spec is
also the first piece of the persistence 001 assumed. That raises its cost and must be stated plainly
rather than hidden: **P1 in [09](09-implementation-plan.md) ships a database dependency**, and the
registry must degrade to the seed file when the database is absent, or local development and the demo
mode break ([10 E-14](10-edge-cases-testing.md#storage-and-degradation)).

---

## E10 · Discovery reads three fields, and ignores the rest

```29:31:apps/coding-agent/api/adapters/databricks/serving.py
        names = frozenset(
            e["name"] for e in d.get("endpoints", [])
            if e.get("task", "llm/v1/chat") == "llm/v1/chat"
            and (e.get("state") or {}).get("ready", "READY") == "READY")
```

Good behaviour, with one documented decision to preserve: if the list cannot be read, return `None`
and **do not filter**
([`:22-32`](../../apps/coding-agent/api/adapters/databricks/serving.py), asserted by
`tests/test_genie_features.py:497-507`). Today the endpoint list is consumed only as a set of names.
A registry wants more: the foundation-model name, the task type, the ready state, and — if the API
offers it — limits. Everything beyond `name`, `task`, `state.ready` is **[unverified]** and is
handled by an explicit probe in [09 P2](09-implementation-plan.md#p2-discovery-with-provenance).

The 300-second TTL cache ([`:17`](../../apps/coding-agent/api/adapters/databricks/serving.py)) is also
a decision to keep: discovery is not a per-request call.

---

## What already works and must not be broken

| Mechanism | Where | Why it must survive |
|---|---|---|
| Secrets never written to the agent config | `agent_config.py:55-56` | Axiom A4 |
| Token to the tool server through a `0600` file | `orchestrator.py:250-262` | Axiom A4 |
| `set_model` string-then-union fallback | `runtime.py:248-270` | ACP dialect drift |
| Discovery failure does not filter the list | `serving.py:22-32` | usability under a permission error |
| Per-model output cap guard | `tests/test_genie_features.py:512-519` | Axiom A3 |
| Working agreement written beside the config | `agent_config.py:67-79` | task success rate |
| `permission` denies on builtin tools | `agent_config.py:46` | the fence |
| Discovery TTL cache | `serving.py:13` | cost and latency |

Every phase in [09](09-implementation-plan.md) names the item above it must leave working.

---

## What we have not verified

| # | Unverified | Why it matters | Where it is probed |
|---|---|---|---|
| U1 | Whether `/api/2.0/serving-endpoints` returns per-model limits or foundation name | decides whether P3's limits come from discovery or from measurement | [09 P2](09-implementation-plan.md#p2-discovery-with-provenance) |
| U2 | Whether Lakebase is available in this workspace for an app (001 R-09 calls it fragile) | decides whether P1 is a hard dependency | [09 P1](09-implementation-plan.md#p1-the-registry-store-and-degradation) |
| U3 | Whether the Anthropic-native gateway route accepts a **user** token (partner models are gated) | decides whether Anthropic is reachable at all here | [09 P2](09-implementation-plan.md#p2-discovery-with-provenance) |
| U4 | Whether a Vertex service-account JSON key can authenticate the OpenAI-compatible Vertex endpoint directly | decides whether the signature shim is required in production | [04 §Gemini](04-providers.md#gemini-on-vertex-ai) |
| U5 | Whether `opencode` accepts several provider blocks and switches between them at runtime through ACP | decides whether one process can serve a cross-provider switch | [09 P0](09-implementation-plan.md#p0-the-multi-provider-probe) |

U5 is the one that can invalidate the architecture, and it is a one-hour probe. See
[09 §P0](09-implementation-plan.md#p0-the-multi-provider-probe).
