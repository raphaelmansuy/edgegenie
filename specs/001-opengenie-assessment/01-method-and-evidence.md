[Index](README.md) · next: [02 OpenGenie, measured](02-assessment-opengenie.md)

# 01 · Method and evidence

Every claim in this set is either **executed** (a command was run on this checkout and its output is
quoted), **read** (a file and line in this repository), or **sourced** (a dated URL). Nothing is
recalled. This page exists so a reviewer can re-derive any number here in under a minute, and so that
a claim which later turns out to be wrong can be found and corrected rather than argued about.

---

## 1 · What was inspected

### 1.1 The checkout

| Fact | Value | How |
|---|---|---|
| Commit | `2063af3` — *"State the version the app is, and publish where it lives"* | `git log --oneline -1` |
| Working tree | clean | `git status --short` → empty |
| Python, `apps/coding-agent/api` | 18 132 lines across 45 adapter files, 28 domain modules, 12 services, 6 routers (7 files, 82 routes), 13 protocols in one ports file | `find api -name '*.py' \| xargs wc -l`; `rg -c '@router\.(get\|post\|put\|delete\|patch)' api/routers/*.py` |
| Python, the tool server | 2 516 lines, 41 tools, 28 in `core` | `wc -l tools/databricks_notebook_mcp.py`; `python3` AST-free count of `_CORE` |
| TypeScript, `apps/coding-agent/web/src` | 26 857 lines; 55 non-test domain modules; 6 230 lines in `domain/` | `find web/src -name '*.ts*' \| xargs wc -l` |
| Python tests | 53 files, 12 562 lines, **1 310 collected**, 1 303 passing, 7 skipped | `pytest --collect-only -q`; `pytest -q` |
| Front-end tests | 69 files, **959 passing** | `npx vitest run` |
| Skills | 4 markdown playbooks | `ls tools/skills/*.md` |

### 1.2 The baselines, run for this assessment

Both suites were executed on this commit, in this order, and both were green before any document was
written. This matters for a different reason than "the tests pass": **a phase gate in
[11](11-implementation-plan.md) is unambiguous only when there is no pre-existing red to hide behind.**

```
cd apps/coding-agent && .venv/bin/python -m pytest -q
→ 1303 passed, 7 skipped, 11 warnings in 17.77s

cd apps/coding-agent/web && npx vitest run
→ Test Files  69 passed (69)
  Tests       959 passed (959)
  Duration    14.43s
```

Two doc-vs-code drifts were found while reading the docs for this page, and are recorded in
[02 §7](02-assessment-opengenie.md#7--documentation-drift): `docs/08-architecture.md:660,770` names
`web/src/domain/reduce.ts`, which does not exist (the reducer is `reduce()` in `events.ts`), and the
same page calls the 959 front-end tests "959 assertions" while the suite contains 1 594 `expect(`
calls.

**The front-end flake: found, named, fixed.** It failed **once** in four runs during the first baseline —
one test, unnamed at the time because the run was piped through a filter that dropped the name. Later, under
the full 1 012-test suite, it failed again and was identified:
`JobsPages.test.tsx::says what Run now starts and how long the last run took`.

The cause was a **race, not flakiness**. `findByRole("button", { name: /Run now/ })` returns the button as
soon as the page mounts, and the button's `title` — which carries the duration the test asserts — is filled
only when the run block arrives, so the test read a title that was still the fallback. It passed in
isolation because the run block resolved in the first tick, and failed about one run in five under the load
of 74 parallel test files.

The fix waits on the **attribute the test is about**, not on the element:

```ts
const runNow = await screen.findByRole("button", { name: /Run now/ });
await waitFor(() => expect(runNow.getAttribute("title")).toContain("1 m 42 s"));
```

Verified by running the **full suite three times**: 1 012/1 012 each time, 0 failures. The fix was proved
under the condition that broke it, because a gate that is passed by pressing Enter again is not a gate.

**A second lesson, learned while recording the first.** Twice during this assessment a *passing* suite
was reported as a failure, because the command was
`vitest run 2>&1 | grep -E "^ +Tests"` — and `grep` exits `1` when it prints nothing, which it did once
because the reporter had changed shape. A command whose exit code describes the **filter** rather than
the **test run** cannot be a gate. Every number in this section was therefore re-derived from machine-readable
output, not from a filtered transcript:

```bash
cd apps/coding-agent/web
npx vitest run --reporter=json --outputFile=/tmp/v.json
python3 -c "import json;d=json.load(open('/tmp/v.json'));print(d['numTotalTests'],d['numPassedTests'],d['numFailedTests'],d['success'])"
# 959 959 0 True
```

That is the form a phase gate must take in [11](11-implementation-plan.md): a structured result, or the
raw exit code of the runner itself — never the exit code of a pipe into `grep`.

### 1.3 What was deliberately not inspected

- **Genie Code itself was not driven.** It requires SSO into a workspace with partner-powered AI
  enabled. Every statement about it is sourced from Databricks documentation dated in §3, and is
  labelled as such in [03](03-comparison-genie-code.md). Where the documentation and this
  repository disagree, both are quoted.
- **No live workspace call was made.** The fence experiments in [02](02-assessment-opengenie.md) load
  the tool server as a module with a test environment, which is how `tests/test_fence_parity.py`
  already does it. They prove the *code path*, not a workspace's behaviour.
- **No cost measurement was run.** The repository holds no Genie Code billing history and no
  `system.billing` access from this checkout. `docs/genie-code-replacement-spec.md §9.3` says the same
  thing and this set does not contradict it.

---

## 2 · How the code claims were produced

Four techniques, in order of how much they can be trusted.

### 2.1 Executed: a property of the code, measured

Used where a claim is behavioural and a unit test would not settle it. The two that matter most:

**The fence fails open (F-1), proved by loading both sides and asking each the same question.**

```
.venv/bin/python - <<'PY'
import sys, os, importlib.util
sys.path.insert(0,'.')
from api.domain.scope import Scope, check_path, check_sql
s = Scope.for_session("abcdef1234567890", "/", None)
print(repr(s.folder), s.schema)
print(check_path(s, "/Users/victim/x.py").verdict.value)      # ask
print(check_sql(s, "DROP TABLE main.other.t").verdict.value)  # ask

os.environ.update({"NBMCP_ALLOW_WRITES":"1","NBMCP_WRITE_PATHS":"/","NBMCP_WRITE_SCHEMAS":"","NBMCP_PROFILE":"core"})
spec=importlib.util.spec_from_file_location("t","tools/databricks_notebook_mcp.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m._check_path_scope("/Users/victim/x.py") is None)      # True  ← in scope
print(m._check_sql_scope("DROP TABLE main.other.t"))          # None  ← no restriction
PY
```

Output, quoted verbatim:

```
A folder: '' schema: None
   app check_path('/Users/victim/x.py') -> ask
   app check_sql('DROP TABLE main.other.t') -> ask
   tool _check_path_scope('/Users/victim/x.py') -> in scope
   tool _check_sql_scope('DROP TABLE main.other.t') -> in scope
```

The environment values are not hypothetical: `registry.start` computes
`"NBMCP_WRITE_PATHS": folder.rstrip("/") + "/"` and `"NBMCP_WRITE_SCHEMAS": schema or ""`
(`api/adapters/mcp/registry.py:64-65`), and `Scope.for_session` maps both `"/"` and `""` to an empty
folder string (`api/domain/scope.py:56-60`).

**A truncated tool result is not JSON (F-2), proved on a real payload shape.**

```
payload = {"tables":[{"name":…, "type":"MANAGED", "comment":…} for i in range(200)]}
out = m._trim(payload)
json.loads(out)   # JSONDecodeError: Invalid control character at: line 204 column 29 (char 6000)
```

`_trim` is the function every read tool returns through (`tools/…:279-284`, called 20+ times).

### 2.2 Executed: a scale, computed from a real object

Where the claim is "this is quadratic", the shape was taken from the code and the arithmetic shown,
so the reader can substitute their own constants.

```
# the snapshot the journal writes, built from the real whitelist in _snapshot()
S = len(json.dumps({"version":1,"session":{…},"turns":[one turn with a 60k answer and 40k context],"calls":{…}}))
→ 121 088 bytes
events = len(answer)//4      # one message.delta per ~4 characters
→ 15 000
S * events → 1 816 MB per turn
```

A caveat stated here rather than buried: the "4 characters per delta" is an assumption about the
agent's chunking, not a measurement of opencode. The conclusion is therefore stated as a **shape**
(O(n²), because the snapshot contains the answer and is written once per delta) and the absolute
figure as an **order of magnitude**. Both `F-4` and `F-5` hold at any chunk size above one.

### 2.3 Read: a file and a line

Where a claim is structural ("nothing calls this", "the docstring says X, the code does Y"), the
evidence is a `rg` that found the definition and *no* caller.

```
rg -n "check_sql\(" api tools tests
→ api/domain/scope.py:204  (def)
  tests/test_domain.py:201,206,212
  tests/test_scope_targets.py:54,78,142,196,217
```

No production call site. That is `F-7`, and it is also why the fence "in two runtimes held to one
table" is, in the request path, one runtime.

### 2.4 Read: a contradiction between two artefacts

Where two files in the repository disagree, both are quoted with their lines. `F-3` is the type case:
`docs/08-architecture.md:147` says *"the agent does not hold a workspace token"*, and
`api/services/orchestrator.py:578` sets `env["DATABRICKS_TOKEN"] = user_token` on the child's
environment, which `api/adapters/acp/runtime.py:45` passes to `create_subprocess_exec`. Both quotes
are in [02](02-assessment-opengenie.md); the reader decides which one is the intent.

---

## 3 · The external sources, with their dates

A comparison against a product that ships weekly is only as good as its date. Every source below was
fetched for this assessment.

### 3.1 Databricks — Genie Code

| Source | Date on the page | Used for |
|---|---|---|
| [Genie Code](https://docs.databricks.com/aws/en/genie-code/) | **Last updated 9 Nov 2026** | It is "an autonomous agent"; "governed by your Unity Catalog permissions"; the full-page command centre exists; billing from 8 Jul 2026 |
| [Features and capabilities](https://docs.databricks.com/aws/en/genie-code/features-capabilities) | **9 Nov 2026** | Autocomplete, Quick Fix, Diagnose Error, `/slash` commands, documentation citations, Genie Ontology, Genie Migrate; and the disclaimer that it "is not intended to be a general-purpose programming assistant" |
| [Navigate Genie Code](https://docs.databricks.com/aws/en/genie-code/navigate-genie-code) | **9 Nov 2026** | The pane as **tabs** of parallel chats; the command centre's lists (chats, schedules); approval modes and the auto-approve classifier; sharing with ACLs; branch/edit with `/btw`; attach file types; **level of effort** (Auto / Low) |
| [Agent mode — approve tool actions](https://learn.microsoft.com/en-us/azure/databricks/genie-code/agent-mode) | 2026 | The four approval modes and the verbatim sentence *"Auto-approve is a productivity feature, not a security boundary"* |
| [Genie Code task for jobs](https://docs.databricks.com/aws/en/jobs/tasks/genie-code) | 2026 | Auto-approval is always on for job tasks and **cannot be disabled**; Jobs-UI only |
| [Genie Code scheduled tasks](https://learn.microsoft.com/en-us/azure/databricks/genie-code/scheduled-tasks) | 2026 | Scheduled runs, one new chat per run, **runs use the creator's permissions** |
| [Personalizing Genie Code](https://www.databricks.com/blog/personalizing-genie-code-instructions-skills-memory-and-mcp) | **1 Jun 2026** | Instructions (global), user skills in `~/.assistant/skills/`, workspace skills in `Workspace/.assistant/skills/`, `AGENTS.md`/`CLAUDE.md` discovery, MCP marketplace, connector OAuth in beta |
| [What's new at Data + AI Summit 2026](https://www.databricks.com/blog/whats-new-genie-code-data-ai-summit-2026) | **17 Jun 2026** | The command centre rationale ("~15 parallel threads"), ML integration, scheduled tasks |
| [Genie Ontology](https://docs.databricks.com/aws/en/genie/genie-ontology/) | 2026 | Modeled knowledge (metric views, domains, Pages, certification) + learned knowledge; shared with external agents through Genie One MCP |
| [Monitor and understand your Genie cost](https://docs.databricks.com/aws/en/genie/monitor-cost) | 2026 | 150 DBU/user/month free; `GENIE_FREE_USAGE` SKU; 25% promo to 31 Jan 2027; **service principals get no allowance** |
| [Manage budgets and cost controls](https://docs.databricks.com/aws/en/genie/budgets) | 2026 | Budgets are a **ceiling, not a cap** — "Do not use this feature as a way to ensure an absolute spend cap" |
| [Databricks platform release notes](https://docs.databricks.com/aws/en/release-notes/product/) | rolling | *Centrally configure coding agents*; *Unified tracing now includes coding agent activity*; *Connect coding agents to Unity Gateway with the `ug` CLI*; *Managed agent memory and sessions (Beta)* |
| [ug CLI reference](https://docs.databricks.com/aws/en/ai-gateway/coding-agent-ug-cli) | 2026 | `ug claude`, `ug codex`, `ug opencode`, `ug cursor`; `ug mcp add`; `ug skills add` |

### 3.2 The general coding agents

| Source | Date | Used for |
|---|---|---|
| [Where Cursor, Claude Code and Codex actually differ](https://developertoolkit.ai/en/compare/) | checked **2026-10-12** | Permission modes, sandbox mechanisms, hook counts (33 / 12 / Cursor's documented set), subagents, worktrees, background sessions, org policy layers |
| [Cursor hooks](https://cursor.com/docs/hooks) | 2026 | The hook event names and the "can observe, block or modify" contract |
| [Claude Code vs Codex vs Cursor 2026](https://vynula.com/claude-code-vs-codex-vs-cursor-2026/) | 2026 | Centre of gravity per tool |
| [Cursor vs Claude Code for data engineering](https://dataworkers.io/resources/cursor-vs-claude-code-data-engineering/) | 2026 | The data-engineering read: subagents, terminal-native workflows, hooks for `dbt test` |

**A rule this set follows.** Where a product's own documentation and a third-party comparison
disagree, the product's documentation wins and the comparison is cited only for a *category* of
behaviour. Where neither exists, the cell says **unknown**, and [03](03-comparison-genie-code.md) and
[04](04-comparison-best-agents.md) mark it `?` rather than guessing.

---

## 4 · The limits of this assessment

Stated plainly, because an assessment that presents itself as complete is less useful than one that
says where it stops.

| Limit | Consequence | Where it shows |
|---|---|---|
| Genie Code was not driven | Every Genie Code cell is documentation, not observation. A feature shipped after 9 Nov 2026 is not in this set | [03](03-comparison-genie-code.md) marks `[doc]` per row |
| No live workspace in these experiments | The fence findings prove code paths, not a deployment's configuration. `app.yaml` may set a schema for every session, which would mask `F-1` in production and leave it latent for a user who creates a session without one | `[RB-2]` |
| No billing data | No cost comparison is made. `[R-6]` is a *measurement plan*, not a saving | [05 §4](05-gaps-and-improvements.md) |
| Chunk size is assumed | `F-4`/`F-5` are stated as shape + order of magnitude, not a precise byte count | §2.2 above |
| One reviewer | The lenses in [09](09-lenses.md) are roles, not people. A real database review may find what the database lens missed | [09](09-lenses.md) |
| The 1 303 tests are the tests that exist | A green suite says what it covers; it does not say the product is correct. Four of the seventeen findings are in code the suite exercises | [02 §6](02-assessment-opengenie.md#6--why-the-tests-did-not-catch-these) |

---

## 5 · Reproducing this page

```bash
cd /Users/raphaelmansuy/Github/03-working/opengenie/apps/coding-agent

# the baselines
.venv/bin/python -m pytest -q
( cd web && npx vitest run )

# the counts
find api -name '*.py' | xargs wc -l | tail -1
find web/src -name '*.ts*' | xargs wc -l | tail -1
rg -c '@router\.(get|post|put|delete|patch)' api/routers/*.py | awk -F: '{s+=$2} END {print s}'
.venv/bin/python -m pytest --collect-only -q | tail -1

# F-1, F-2: the two experiments, verbatim, in 02 §5
# F-7: the missing callers
rg -n "check_sql\(|check_job\(|check_app\(|check_instance\(" api tools

# the spec verifiers used for 06 and 07
cd web
node scripts/verify-spec-ascii.mjs /Users/raphaelmansuy/Github/03-working/opengenie/specs/001-opengenie-assessment
NODE_PATH=/tmp/mmd/node_modules JSDOM_PATH=/tmp/mmd/node_modules/jsdom \
  node scripts/verify-spec-mermaid.mjs /Users/raphaelmansuy/Github/03-working/opengenie/specs/001-opengenie-assessment
```

Next: [02 · OpenGenie, measured](02-assessment-opengenie.md).
