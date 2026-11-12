[Index](README.md) · prev: [03 Against Genie Code](03-comparison-genie-code.md) · next: [05 Gaps and improvements](05-gaps-and-improvements.md)

# 04 · OpenGenie against the best coding agents

The second half of the request: *how does it compare with the best coding agent on the market for data
engineering?* The honest answer has three parts, and the middle one is the one people skip.

1. **On the mechanics of coding, it loses badly** — and it should not try to win. Worktrees, subagents,
   hooks, a sandboxed shell and background sessions are years of work by teams of hundreds.
2. **On the mechanics that matter for *data* — a warehouse, a catalog, a schedule, a permission model —
   it wins, because the others are visitors there.** Claude Code and Cursor reach Databricks through an
   MCP server that runs as *you, on your laptop*, with a PAT on disk. OpenGenie's tool server runs
   inside the workspace, as the signed-in user, with the token in a `0600` file that is re-read on
   every call and deleted on archive.
3. **On proof, it is alone.** None of the three matches an answer against the tool calls that
   happened.

---

## 1 · Which three, and why these

| Agent | Why it is the benchmark | Source date |
|---|---|---|
| **Claude Code** | The most configurable agent for repo/terminal work: 33 hook events, five permission modes, OS sandbox (Seatbelt / bubblewrap), subagents, `--worktree`, `--bg` sessions, cloud sessions, org policy via managed settings | [compare](https://developertoolkit.ai/en/compare/) checked 2026-10-12 |
| **Codex** | One agent across CLI, IDE, desktop, cloud and Slack/Linear hand-offs; `/subagents` on by default; OS sandbox with permission profiles; `requirements.toml` for org policy | same |
| **Cursor** | Editor-centred, Cloud Agents on isolated VMs, hooks that can block, `.cursorignore` deny rules, three run modes (Auto-review / Allowlist / Run Everything) | [cursor.com/docs/hooks](https://cursor.com/docs/hooks), [compare](https://developertoolkit.ai/en/compare/) |

And one more, because it is the *specific* competitor for this product's shape and the README does not
mention it: **Databricks' own `ug` CLI**, which configures Claude Code, Codex, OpenCode, Gemini CLI,
Copilot CLI and Cursor Agent against Unity Gateway, with `ug mcp add` for Databricks MCP servers and
`ug skills add` for Unity Catalog skills
([overview](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-quickstart),
[CLI reference](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-ug-cli)). That is the
"best agent + Databricks context" combination a customer can assemble *today*, with no app to deploy,
and it is the real competitive reference — not Genie Code.

---

## 2 · The comparison, by axis

Verdicts as in [03](03-comparison-genie-code.md): **Theirs**, **Parity**, **Ours**, **Different**.

### 2.1 The coding loop

| Axis | Claude Code | Codex | Cursor | OpenGenie | Verdict |
|---|---|---|---|---|---|
| **Runs on the user's own files** | yes, cwd | yes | yes, workspace | **No** — it runs inside a container; the user's "files" are Databricks *workspace objects*, and a repo is only reachable as a workspace folder | **Theirs**, structurally. `[G-16]` |
| **Shell** | sandboxed bash (Seatbelt / bubblewrap) | `--sandbox read-only\|workspace-write\|danger-full-access` | sandboxed in Auto-review via `sandbox.json` | **Denied on purpose** — `bash: deny` in `opencode.json` and `terminal: false` in the ACP handshake, asserted by `tests/test_agent_isolation.py` | **Different, and correct here.** A shell in the app container reads the user's token file. The *cost* is real: no `pip install`, no `dbt run`, no `git` |
| **Subagents** | built-in Explore / Plan / general-purpose + `.claude/agents/` | `/subagents`, multi-agent on by default | yes, incl. cloud VMs | **None.** One agent per session; no spawning | **Theirs**, and it is the most consequential loss for data work — *"audit three dbt projects simultaneously"* is a real pattern ([dataworkers](https://dataworkers.io/resources/cursor-vs-claude-code-data-engineering/)) |
| **Worktrees** | `--worktree` | `--worktree` | yes | **No** (no git) | **Theirs** |
| **Hooks** | 33 events, `command`/`http`/`mcp_tool`/`prompt`/`agent` handlers | 12 events | `preToolUse`, `afterFileEdit`, `beforeMCPExecution`, `beforeSubmitPrompt`, … | **No user hook.** The *equivalent* is the fence and the supervisor, which are built in and not extensible | **Different** — see §3.3: this is a genuine improvement opportunity, and the cheapest one that is not a rewrite |
| **Background / parallel sessions** | `--bg`, `claude attach/logs/stop`, cloud sessions | `codex agents` command centre, `codex cloud` | Cloud Agents on isolated VMs | **No.** One foreground stream per page (`useSessionStream(active)`) | **Theirs**, and `C2` in [03](03-comparison-genie-code.md) |
| **Inline completion** | n/a (terminal) | n/a | **Tab, best in class**, with its own hook surface | **No** | **Theirs** in an editor; **refused** here (`[G-19]`) |
| **Accept / reject a proposed edit** | yes, diff in editor | yes | yes, best in class | **No** — `editor/diff.ts::minimalChange` maps a remote edit, it does not propose one | **Theirs**. `[G-15]` |
| **Plan mode** | `plan` permission mode | yes | yes | A plan *rendered* from the agent's `todowrite`, not a mode that withholds tools | **Parity in display, theirs in control** |
| **Undo** | git + checkpoints | git | git + timeline | **Structural undo only** — `NotebookEditor.tsx:144-207` keeps 50 cell-shape snapshots; a *content* undo is CodeMirror's | **Theirs** |

**Score: theirs on 9 of 11 axes, ours on none, different on 2.** That is the true shape and no
roadmap changes it.

### 2.2 Data engineering, specifically

This is where the comparison inverts. The question is not "can it write a PySpark job" — all four can —
but "can it *see the data* the job reads, and can you prove what it did".

| Axis | Claude Code + Databricks MCP | Codex + `ug` | Cursor + MCP | Genie Code | OpenGenie | Verdict |
|---|---|---|---|---|---|---|
| **Identity for tool calls** | The PAT on your laptop, or `ug`'s loopback proxy | `ug` proxy adds a fresh token per request; *"no Databricks token is written to disk"* | the PAT you configured | The workspace's OBO session | **The forwarded user token**, in a `0600` file the tool server re-reads per call (`orchestrator.py:618-666`) | **Parity with `ug`**, better than a raw PAT |
| **Where tools run** | Your machine, reaching the workspace over the network | Your machine + `ug` proxy | Your machine | Inside the workspace | **Inside the app container inside the workspace** | **Ours** — no egress, no laptop tooling |
| **Unity Catalog as the ACL** | Whatever the PAT can see | same | same | Yes | **Yes, per call**, and nothing re-implements it | **Parity with Genie** |
| **A fence** | permission prompts (a policy the model asks) | same | run modes + `.cursorignore` | an AI classifier that *"is not a security boundary"* | **A process started with one folder, one schema, one name prefix**; a refusal names the reason | **Ours** — with `F-1`'s caveat fixed |
| **Proving a claim** | none | none | none | none | **Supervisor + evidence table**: a requirement with no completed call triggers an audit pass, then `blocked` | **Ours, alone** |
| **A durable record** | local transcripts | local transcripts | local + cloud | platform tables | **Append-only Postgres journal, monotonic `seq`, replay is the connection** | **Ours** |
| **Which model** | Claude | OpenAI or gateway models via `ug` | Cursor's models | Databricks-chosen | **13 models × 4 providers**, per session, pinned per turn | **Ours** (tie with `ug`) |
| **Lineage, grants, jobs, pipelines as tools** | via MCP servers you assemble | via `ug mcp add` | via MCP | built in | **41 tools including lineage, grants, jobs, pipelines, Lakebase, apps** | **Parity**, and self-contained |
| **Ontology / business terms** | no | no | no | **yes** | no | **Genie** (`C11`) |
| **Scheduled / unattended** | cloud sessions, cron | `codex cloud` | Cloud Agents | **scheduled tasks GA** | no (`C27`) | **Theirs** |
| **dbt / git / local repo** | **yes** — the whole point | **yes** | **yes** | no | **no** (`G-16`) | **Theirs** |

**Score: ours on 4 axes (where tools run, the fence, the proof, the journal), parity on 3, theirs on 4.**
That is a defensible product — not a general coding agent, but the only one of the five that can say
*"this answer was produced by this model, using these Unity Catalog calls, as this user, and here is the
call that proves each claim."*

### 2.3 The mechanics the others have and this one should not chase

| Capability | Why not |
|---|---|
| **Worktrees / branches** | Requires a git checkout inside the container. The container has no repo; the workspace *is* the repo, and its history is Databricks'. `[G-16]` |
| **Sandboxed shell** | The denial is load-bearing (`F-3`): a shell reads the token file. A sandbox would be a new security boundary to build and defend, for a capability the tool server already provides in a *fenced* way |
| **Inline completion** | Needs a second, low-latency model route (a completion endpoint, a debounce, a cancel path, an accept path). It is a product, not a feature, and it competes with a best-in-class implementation |
| **Connector marketplace** | Every connector is an OAuth client, a scope model, a data-egress decision and a revocation story. Genie's is a beta behind a workspace setting. `[RB-7]` |
| **Cloud agents on isolated VMs** | The app *is* the isolation. Adding VMs adds a control plane, a network policy and a way to leak between users |

---

## 3 · What to learn from them, exactly

Nothing above says "copy them". Three specific things are worth taking, and each is cheap because the
substrate exists.

### 3.1 Hooks: the one mechanism that fits this architecture

Cursor's hooks *"let you observe, control, and extend the agent loop … They run before or after defined
stages of the agent loop and can observe, block, or modify behavior"* — formatters after edits, PII
scans, **gating risky operations**, injecting context at session start
([cursor.com/docs/hooks](https://cursor.com/docs/hooks)). Claude Code has 33 such events.

OpenGenie has **one** hook point, hard-coded: the fence in the tool server, and the supervisor after a
turn. There is nowhere for a *workspace* to say "after every notebook write, run `ruff`" or "before any
`dbx_run_sql`, refuse `DELETE` on `main.gold`". That is a real gap for a governed product — it is the
difference between "the vendor decided the rules" and "the platform team decided the rules".

And the substrate makes it cheap: the tool server already sees every call, already classifies it, and
already returns a structured refusal. A hook is **a declarative rule evaluated in the same place**, not
a new process. `[G-21]`, `[R-13]`.

### 3.2 Subagents: the pattern this product can afford

A generic coding agent spawns subagents for *parallelism* (audit three projects). A data agent needs
them for a different reason: **context isolation on a large catalog**. "Find the table that holds
revenue" across 4 000 tables should not put 4 000 names in the main conversation.

The ACP runtime already supports one child process per session (`runtime.py:start`). A subagent is
**a second tool server scoped tighter** plus a bounded prompt — not a new architecture. But it is a
phase-4 item, not phase 1, because the budget and the process model need to be settled first. `[G-22]`.

### 3.3 The `ug` threat, and what it means

`ug` is the competitive answer nobody in this repository has written down: **a customer can get
"Claude Code + Unity Gateway models + Databricks MCP servers + UC skills" without deploying anything.**
It has no fence, no evidence and no journal — but it has Claude Code's loop.

The strategic consequence is that OpenGenie cannot win by being *a better agent*. It wins by being
**the agent a platform team can approve**: identity per call, a fence that is a mechanism, an audit
trail the customer owns, and a proof attached to every answer. That is the same conclusion as [03 §5](03-comparison-genie-code.md#5--two-honest-paragraphs),
reached from the other direction, which is a good sign for it.

---

## 4 · The scoreboard, both comparisons

| Against | Win | Parity | Lose |
|---|---|---|---|
| **Genie Code** (37 rows) | 3 structural (model, audit, fence) | 7 | **16** |
| **Claude Code / Codex / Cursor** (11 coding axes) | 0 | 2 | **9** |
| **Them + Databricks MCP** (11 data axes) | 4 | 3 | 4 |

The shape of that table is the product's actual position: **a narrow product that is better where it is
narrow, and much worse where it is not.** The roadmap in [05](05-gaps-and-improvements.md) only
improves the middle row where the cost is a phase, and it never pretends the first row can be closed.

---

## 5 · The one-sentence answer to "how does it compare with the best coding agent for data engineering"

> For writing and running SQL against a governed catalog, and for being able to show afterwards who ran
> what with which model and which evidence, OpenGenie is the best of the five. For editing a dbt
> project in a git repo, exploring a large codebase with subagents, or getting completions while you
> type, it is not in the same class — and the gap is architectural, not a missing screen.

Next: [05 · Gaps and improvements](05-gaps-and-improvements.md).
