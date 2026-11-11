[Index](README.md) · [01 Big picture](01-big-picture.md) · [02 Setup](02-setup-in-the-databricks-shell.md) · [03 Toolbox](03-toolbox-cli-skills-mcp.md) · [04 Safety](04-safety-and-governance.md) · [05 Exams](05-exam-suite.md) · [06 Results](06-results-and-lessons.md) · [07 Decide](07-decision-guide.md)

# Glossary

Plain-English meanings, in alphabetical order. Where a word has its own section, the link
takes you there.

| Term | Meaning |
|---|---|
| **Agent (coding agent)** | A program that lets a language model use tools in a loop: read, run a command, look at the result, decide the next step. Examples: OpenCode, GitHub Copilot CLI. |
| **AGENTS.md** | A plain text file of house rules that coding agents read at the start of a run. See [03](03-toolbox-cli-skills-mcp.md#layer-d--the-rules-file). |
| **AI Gateway** | The Databricks front door for models and tools. It gives one address and one login for many models and for services like the sandbox. |
| **ANSI mode** | A strict SQL setting that is on in serverless Databricks. Bad conversions such as turning `'N/A'` into a number **raise an error** instead of giving NULL. Use `try_cast` to stay safe. |
| **Approach** | The whole setup under test: tools, rules, skills, safeguards. We also call it a *variant*. |
| **Audit pass** | A message from the supervisor that asks the agent to name, for every requirement, the tool call that proves it. See [02](02-setup-in-the-databricks-shell.md#step-7--run-the-agent-with-a-supervisor). |
| **Canary table** | A table we place *outside* the agent's allowed area and check afterwards. If it changed, the agent broke the fence. |
| **CLI** | Command-line interface: a program you drive by typing commands. Here, the `databricks` command. |
| **Development set** | The exam tasks (M1 to M8) we used repeatedly while improving the setup. See [05](05-exam-suite.md#development-set-and-held-out-set). |
| **EXCEPT (both ways)** | An SQL comparison that lists rows present in one table and missing from the other, in both directions. Zero rows each way means the tables are identical. Our graders use it. |
| **Exam / mission** | One graded task. Ids starting with M are development tasks; X are held-out. |
| **Fence (scope)** | The limit on where the agent may write: one schema, one folder, one name prefix. See [04](04-safety-and-governance.md). |
| **Gateway rate limit (429)** | The error returned when too many requests arrive at once. We run at most two agents in parallel. |
| **Genie Code** | The built-in Databricks AI assistant for notebooks, SQL and pipelines. The thing we are comparing against. |
| **Genie One / `genie ask`** | A separate Databricks feature for asking questions about data. One official skill sends data questions to it. See [03](03-toolbox-cli-skills-mcp.md#the-genie-trap). |
| **Golden answer / golden query** | The known-correct result that a grader compares against. |
| **Grader** | The program that decides how many points a run earns, by inspecting the real workspace. |
| **Held-out set** | Three exam tasks (X1 to X3) kept out of all tuning, to check that improvements are real. |
| **Idempotent** | Safe to run twice: the second run gives the same result and does not double the data. |
| **Lakebase** | Databricks' managed Postgres database. Two APIs exist: older "database instances" and newer "projects". |
| **MCP (Model Context Protocol)** | A standard way for a program to offer tools to an agent. |
| **MCP server** | A small program that offers tools through MCP. Ours is `apps/coding-agent/tools/databricks_notebook_mcp.py`. |
| **Medallion (bronze, silver, gold)** | A common pipeline layout: raw data, cleaned data, business summaries. |
| **No-op** | An empty attempt. A good grader must fail it. |
| **OpenCode** | An open-source coding agent that runs in a terminal and supports any model and MCP servers. |
| **PAT** | Personal access token: a password-like string that lets a program act as you. Treat like a password. |
| **Post-tool stall** | A failure where the model stops, or returns an empty answer, right after using a tool, without finishing. Worst with `gpt-oss-120b` in our tests. |
| **Prompt injection** | Text hidden in data (a ticket, a web page, a cell) that tries to give the agent orders. See [04](04-safety-and-governance.md#prompt-injection-text-in-data-that-tries-to-give-orders). |
| **Reference solution** | A plain program that does a task correctly. Used to prove the grader can award full marks. |
| **Sandbox** | A temporary Linux machine provided through `system.ai.sandbox`. The agent runs in it. Its disk disappears afterwards. |
| **Serverless** | Databricks compute you do not manage. The only kind in our workspace. |
| **Shim (signature shim)** | A tiny local proxy that keeps Gemini's hidden "thought signature" intact. See [02](02-setup-in-the-databricks-shell.md#step-4--point-the-agent-at-a-model). |
| **Skill** | A folder with a `SKILL.md` how-to that the agent opens when a task needs it. Databricks publishes 34. See [03](03-toolbox-cli-skills-mcp.md#layer-b--official-skills). |
| **Supervisor** | Our wrapper script that checks the end of the agent's transcript and pushes it on if the answer is empty or unproven. |
| **Trial** | One full run of a variant over the tasks. Repeating trials shows how much the result moves by chance. See [06](06-results-and-lessons.md#how-much-is-chance). |
| **Unity Catalog (UC)** | The Databricks catalog of tables, with permissions and descriptions. |
| **`ug`** | Databricks' own launcher for coding agents through the AI Gateway. It needs a browser login, so it cannot be configured in a headless sandbox. |
| **Variant (V0 to V6)** | One tested setup. Table in [05](05-exam-suite.md#how-agents-are-compared-variants). |
