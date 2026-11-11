[Index](README.md) · prev: [12 Edge cases](12-edge-cases.md) · next: [14 Coherence check](14-coherence.md)

# 13 · Roadblocks

What is in the way, grounded in code and in the platform's own documentation, and the way past each.
Each is classified:

| Class | Meaning |
|---|---|
| **remove** | a change inside this repository settles it |
| **work around** | it cannot be removed, but a design makes it harmless |
| **report** | it cannot be removed or avoided; the product must say so |

An `[RB-n]` cited from a requirement is defined here and nowhere else.

| # | Roadblock | Class | What it costs if ignored |
|---|---|---|---|
| `[RB-1]` | The tool server cannot import `api.domain`, so every fence rule exists twice | **work around** | drift, and `F-1` is drift |
| `[RB-2]` | A workspace may set a schema for every session, hiding `F-1` | **report + test** | a latent critical defect that only appears for a user who omits a field |
| `[RB-3]` | `_snapshot()` is versioned and `restore()` raises on an unknown version | **work around** | a deploy that cannot roll back |
| `[RB-4]` | Removing the workspace token from the child requires a loopback proxy | **work around** | the documentation must describe the current design honestly |
| `[RB-5]` | The app's SQL/job/app fence has no production caller, and wiring it is expensive | **remove** (by deleting) | a document that claims two layers where there is one |
| `[RB-6]` | Python execution is administrators-only because it runs as the app's SP | **report** | a user who cannot run a Python cell, and no honest way to say yes |
| `[RB-7]` | A second MCP server cannot be fenced by a prefix, so `[R-19]` must not merge it | **work around** | the whole fence model, for the sake of one capability |
| `[RB-8]` | Conversation sharing needs an ACL model the journal does not have | **report** | `[G-3]` stays unbuilt, and the reason is stated |
| `[RB-9]` | Persistent memory must be editable and deletable, or it is a liability | **report** | `[G-10]` stays unbuilt without a design |
| `[RB-10]` | There is no git checkout in the container, so dbt/git work is out of reach | **report** | the comparison in [04](04-comparison-best-agents.md) must say so plainly |
| `[RB-11]` | The single-writer advisory lock is a throughput ceiling, and parallel chats raise the demand | **work around** | a dozen concurrent turns that feel slow |

---

## `[RB-1]` · The tool server cannot import `api.domain`

**The obstacle.** `tools/databricks_notebook_mcp.py` runs as a **separate process** started with
`sys.executable` by `SubprocessToolRegistry.start` (`api/adapters/mcp/registry.py:85-92`). Its working
directory is not the app's, and importing `api.*` from it would couple a sandboxed child to the server
that supervises it — the wrong direction of dependency, and a packaging problem in a deployment that
ships only the app folder.

The codebase already states this:

> `tests/test_fence_parity.py:1-8` — *"The tool server is a separate process: it cannot import
> `api.domain.scope`, so the rule exists twice (spec 013 [RB-5]). Duplication with no guard is drift, so
> this file is the guard."*

**What this costs.** Every fence rule is written twice, and `F-1` is exactly the drift the guard was
supposed to catch: the table has no row for an unset dimension, so the drift happened in the cells.

**The way past it: a mirror plus a table, not a shared module.**

1. The **pure** rule lives in `api/domain/fence_rules.py` (§[10 §3](10-architecture.md)).
2. The tool server carries a **twelve-line mirror** with the source path in its docstring — the pattern
   `tools/pipeline_body.py` already follows ("`check_path` is passed in rather than imported so this
   module stays pure").
3. `tests/test_fence_parity.py` gains `UNSET_CASES`, one row per dimension × unset spelling, asserted
   against **both**.

**Why not a shared package.** A `fence_rules` module that both processes import would have to be
installed into the tool server's path, which means the tool server now depends on a distribution built by
the app. In a Databricks App, that is a build step the deployment does not have — and the failure mode is
the tool server failing to start, i.e. no tools at all.

**Why not IPC.** Asking the app "may I write here?" on every tool call is a network round trip in the
hot path of every write, and it makes the tool server unable to work if the app's loop is busy — including
while it is committing the very event the tool call produced. That is a deadlock shaped like a design.

---

## `[RB-2]` · A workspace may hide `F-1` by always setting a schema

**The obstacle.** `app.yaml` does not set a per-session schema; the *user* chooses it when starting a
conversation. So `F-1` is latent in a deployment whose users always fill the field, and a workspace that
fronts this app with a default schema would never see it.

**Why this is a roadblock and not a comfort.** A latent critical defect is worse than an obvious one,
because the evidence for it disappears. A reviewer who tries the app and finds the fence working will
conclude that the *test* asserting the fix is unnecessary.

**The way past it.** Two things, both cheap:
1. `[R-1]`'s test constructs the scope **in a unit test**, not through a deployment, so it cannot be
   masked by configuration.
2. The UI refuses to create a session with an empty schema **unless** the user chose "read-only" — so the
   unset case becomes an explicit mode (`[R-9]`) rather than an accident, and the refusal has a sentence.

---

## `[RB-3]` · The snapshot is versioned and `restore()` raises

**The obstacle.**

```181:186:apps/coding-agent/api/services/orchestrator.py
        for row in await self._store.snapshots():
            if not row:
                continue
            if row.get("version") != 1:
                raise RuntimeError("unsupported session snapshot version")
            s = Session(**{**row["session"], "status": SessionStatus(row["session"]["status"])})
```

`_snapshot()` writes `version: 1`. Adding a field to `body` means either lying about the version (and
`Session(**row["session"])` failing on an unknown key) or bumping it (and refusing to start against every
existing row).

**The way past it: columns, not JSON.** Every new session fact `[R-9]` `[R-10]` `[R-24]` adds is a
**nullable column on `agent.session_snapshot`**, read separately from `body`:

```
ALTER TABLE agent.session_snapshot ADD COLUMN IF NOT EXISTS write_mode text NOT NULL DEFAULT 'fenced';
ALTER TABLE agent.session_snapshot ADD COLUMN IF NOT EXISTS resume_reason text;
ALTER TABLE agent.session_snapshot ADD COLUMN IF NOT EXISTS checkpoint_seq bigint NOT NULL DEFAULT 0;
```

A defaulted `NOT NULL` column is additive: old rows read as `fenced`, which is today's behaviour, so the
deploy is safe in both directions and `version` **stays 1**.

**Why not bump the version and migrate.** Because a rollback would then meet a row it cannot read. The
`version` field's purpose is to refuse a *shape* it does not understand; the fix is not to teach it the
new shape, it is to not change the shape.

---

## `[RB-4]` · Removing the token from the child needs a loopback proxy

**The obstacle.** A Databricks model is authenticated by the workspace token
(`agent_config.py:39`, `"apiKey": "{env:DATABRICKS_TOKEN}"` at `:162`), and `opencode` reads it from the
environment. So the child **must** have a credential to call a model. `F-3` is that the documentation
says it does not.

**The way past it, two options.**

| Option | Cost | Risk |
|---|---|---|
| **A. A loopback proxy**: a small HTTP server in the app forwards model requests with a fresh token; the child holds a per-session secret | a new process-per-app (not per session), a latency hop, a new failure mode, and a per-session secret to rotate | **medium.** It is what Databricks' own `ug` does for Copilot — *"Copilot holds only a random session secret … the proxy adds a fresh Databricks token to each gateway request … no Databricks token is written to disk"* ([unity-gateway README](https://github.com/databricks/unity-gateway)) — so it is a proven design |
| **B. Correct the documentation**: the child holds the token; the boundary is the two deny-lists | one paragraph, one test | **low**, and it is honest *today* |

**This spec takes B in phase 1 and A in phase 4**, and says why: B is true now and costs nothing; A is a
runtime change with a latency cost that should be measured, not assumed. `[R-4]` requires the test either
way, so the claim and the code cannot drift again while A waits.

**The residual risk, stated.** Under B, the security property is "the model cannot reach a tool that
uses the token". That rests on `permission: {bash: deny, …}` in a config file and
`clientCapabilities: {fs: false, terminal: false}` in the ACP handshake. Both are asserted
(`tests/test_agent_isolation.py`), and both are *instructions to a process*, not a kernel boundary. A
reviewer is entitled to say that is not enough; that is what A is for.

---

## `[RB-5]` · The app's SQL fence has no production caller, and wiring it is expensive

**The obstacle.** `check_sql`, `check_job`, `check_app`, `check_instance` are called only by tests
(`F-7`). To wire `check_sql` in the request path, the app would have to see the SQL — but the SQL is
created *inside the agent* and sent *to the tool server*. The app never sees it.

**Why wiring is expensive.**

| Path | What it would take |
|---|---|
| A bridge call per SQL statement | the tool server asks the app before every `run_sql`: a round trip, a new `/internal/` endpoint, a new per-session key, and the app's loop is the one committing the events — the deadlock in `[RB-1]` |
| Parse the SQL from the event stream | `tool_call.started` carries a **summarised** argument string (`mapper.py:117-120`, `_summarise(..., 160)`), truncated. A fence over a truncated statement is worse than none |
| Move the fence entirely into the app | the tool server would have to be a library, not a process, which forfeits the per-session process model |

**The way past it: delete, and tell the truth.** `[R-8]` requires that no function in `scope.py` has a test
as its only caller. The four functions go; their **cases** move into `test_fence_parity.py`, where they
guard the implementation that runs. The documentation changes from "two implementations held to one table"
to **"one implementation, held to one table, and a test that the table has a row for every dimension"** —
which is a weaker claim and a true one.

**What is genuinely lost.** `check_sql` could answer `ASK` for a destructive statement *inside* the fence
(`DROP TABLE main.agent_scratch.t` → `ask`). The tool server cannot ask a human, so today that statement
executes. `[R-9]`'s `ask` mode restores it — not by calling the app, but by having the tool server return
a structured "needs human" result the app turns into an approval. That is the same capability by a path
that does not deadlock, which is why `[R-9]` is in phase 2 and not optional.

---

## `[RB-6]` · Python execution is administrators-only

**The obstacle.** A Python cell runs on serverless compute as the **app's service principal**, not the
user:

```1149:1151:apps/coding-agent/api/routers/api.py
    The run is as the app's service principal, not as the caller, so it is an administrator's
    capability: anyone allowed to run code there could read whatever the app can.
    """
```

That is correct and it is a wall. `[G-13]`.

**Why it cannot be removed here.** A Databricks App's user authorization has **no compute scope**; the
tool server already documents the measurement (`tools/…:1115-1119`: *"A Databricks App's user
authorization has no jobs scope, so the user's token cannot submit a run"*). So there is no way to run a
notebook *as the user* from this app. The bridge exists because the app *can* run code as itself.

**The way past it: report, and offer the honest alternative.** The refusal already names the remedy
(`python_run_policy`: *"Ask the agent to run it, or ask an administrator"*) and the agent's `dbx_run_notebook`
falls back to the app's identity **only for administrators**. What `[R-9]` adds is that a non-administrator
in `fenced` mode gets a clear sentence instead of a permission error three layers down.

---

## `[RB-7]` · A second MCP server cannot be fenced by a prefix

**The obstacle.** The fence's whole mechanism is: *the tool server was started with one folder, one
schema and three name prefixes* (`registry.py:55-80`). A third-party or Databricks-provided MCP server is
started with none of that, and its tools can do anything its own auth allows.

**Why this matters for `[R-19]`.** Attaching `system.ai.genie_one_mcp` to the same session means the
agent has **two** tool surfaces, one of which the app cannot classify. Any claim that "writes stay inside
the fence" would then be false for the second.

**The way past it: a second server, read-only by construction, in its own process.**

1. **Separate process**, started with **no write scope at all** — a Genie server is read-only, so the
   fence has nothing to enforce and the mode is `read-only` unconditionally.
2. **Separate tool budget**: the 28-tool `core` is a count of *this* server's tools; a second server's
   schemas are counted separately and shown separately in the UI, or the budget test becomes a lie.
3. **Attribution**: an event from the second server carries its name, so the evidence table says which
   surface proved what.

**The residual.** A customer's own MCP server cannot be admitted on these terms, because "read-only by
construction" is a property this app cannot verify about someone else's server. That is why `[G-11]`
refuses a connector marketplace and `[R-19]` admits exactly one, named, known server.

---

## `[RB-8]` · Conversation sharing needs an ACL model

**The obstacle.** Every session is keyed by `user_id` and the ownership check is one regex over the path
plus one comparison (`main.py:262-271`). There is no notion of a second viewer.

**Why it is not a small change.** Sharing means: a grant table, a check on **every** route that names a
session, a decision about whether the grantee sees the *events* (which contain the original user's data
access) or only a rendered transcript, and a revocation story. Genie Code's sharing rides on workspace
ACLs, which this app does not have.

**The way past it: report.** `[G-3]` stays unbuilt. The product should say what it can do instead: a
conversation can be **exported** to Markdown (`domain/transcript.ts` already does this) and shared as a
file, which is a real workflow and needs no ACL.

---

## `[RB-9]` · Persistent memory must be editable and deletable

**The obstacle.** Memory that outlives a conversation is a data store about a person. To be defensible it
needs: a list, an edit, a delete, a retention rule, and a way to know why a memory was recalled.

**Why it is not "just a table".** The product's own principles (`docs/08` §12.1) require a **pure rule**
for anything that deletes, with a `Disposition` and a test. Memory deletion is user-initiated, which is
simpler, but memory *expiry* is not.

**The way past it: report, with the design constraint written down.** `[G-10]` is deferred until there is
a rule as testable as `reaper.reapable`. Storing memory without it would be the one place in this
codebase where data about a user is destroyed by a timer nobody asserts.

---

## `[RB-10]` · There is no git checkout in the container

**The obstacle.** The agent's shell is denied (`bash: deny`) and its filesystem is the app container. The
user's "files" are **workspace objects**, reachable only through REST. A Git folder in the workspace is
explicitly not copyable or renamable by this app (`adapters/databricks/workspace.py:335,362`).

So: no `git`, no `dbt build`, no `pre-commit`, no branch, no worktree. `[G-16]`.

**Why it cannot be worked around.** A git checkout needs a working tree, which needs a filesystem the
agent may write, which needs a sandbox, which needs a token that is not in it (`[RB-4]`), which is a
different product. That is the honest reason the comparison in
[04 §2.1](04-comparison-best-agents.md#21-the-coding-loop) loses nine of eleven axes.

**The way past it: report.** The README's comparison should say "for notebook, SQL and pipeline work
inside the workspace; not for repositories". A customer who needs repo work should use `ug` + Claude
Code, and this product should be the one that tells them so.

---

## `[RB-11]` · The single-writer lock is a throughput ceiling

**The obstacle.** One connection holds `pg_try_advisory_lock(0x4F50454E47454E49)` — the constant spells
`OPENGENI` — and every commit takes one asyncio lock (`postgres.py:14,43,58-74`). That is the correct
design: a second server cannot write behind a replacement's back.

**What `[R-14]` does to it.** Parallel chats multiply the number of streams and the number of concurrent
turns. `APP_MAX_CONCURRENT_AGENTS` is 4 and `APP_REAP_KEEP_MINIMUM` is 8; five tabs will start evicting
each other.

**The way past it, three parts.**
1. `[R-5]` `[R-6]` remove the per-delta commit, which is what made the lock contended.
2. The kept-session count becomes a function of the open tabs, not a constant: a session with a live
   subscriber is `WATCHED` and never reaped (`domain/reaper.py:73-75` already says this).
3. If more than ~8 concurrent turns are needed, that is a **sharding** conversation (`pg_try_advisory_lock`
   per shard, a routing table), and it belongs in its own spec — not in this one.

**What must not be done.** Relax the lock. It is the reason a redeploy cannot produce two writers, and
the failure it prevents (interleaved `seq` for one session) is unrecoverable.

---

## The summary a reviewer needs

| Question | Answer |
|---|---|
| How many roadblocks are platform rules? | **four**: `[RB-6]` (no compute scope), `[RB-7]` (a foreign server cannot be fenced), `[RB-8]` (no ACL), `[RB-10]` (no checkout) |
| How many are this repository's own decisions? | **four**: `[RB-1]` (process boundary), `[RB-3]` (versioned snapshot), `[RB-5]` (the fence's shape), `[RB-11]` (single writer) |
| How many are documentation debts? | **one**: `[RB-4]` — removed by telling the truth now, paid off by the proxy later |
| How many block phase 1? | **none**. Phase 1 is `[RB-1]` work-around, `[RB-3]` work-around, `[RB-5]` deletion |
| What is the one roadblock that would change the architecture? | `[RB-7]`. If a second MCP server had to be merged into the fenced one, the fence would have to become a *policy over tools it does not control*, which is a different and much weaker product |

Next: [14 · Coherence check](14-coherence.md).
