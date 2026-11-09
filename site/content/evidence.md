# Evidence

Every number OpenGenie publishes, with the fraction it was computed from, how many runs stand behind it,
and what it does not prove. Nothing here is typed by hand: `site/claims.py` reads
`exams/results/*.json` and produces this page, and the build fails if a figure and its source ever
disagree.

<p class="lede">There are eleven graded tasks (the harness calls them missions) and 174 saved run files. Every score below was produced by
seeding a real workspace, handing an agent a plain-language request, and then grading the workspace
afterwards &mdash; not by asking a model whether the work looked right.</p>

## The claims

{{claims}}

## How the score is produced

Three steps, and the third is the one that makes the number mean anything:

1. **Seed.** Each task creates real state: tables with deliberate traps, a broken job, a support ticket
   containing an instruction. The agent cannot tell the fixtures from a customer's workspace.
2. **Ask.** The agent receives a plain-language request and no grader.
3. **Grade.** Afterwards, the harness reads the live workspace: does the table match the golden answer in
   both directions, did the notebook actually run, is the job's latest run a success, was the injected
   instruction ignored. A grader is trusted only once a reference solution scores 100% on it and a
   do-nothing agent fails it.

<p>The full method, including how the graders could be wrong, is
<a href="../reference/doc-exams/">the exam suite</a>.</p>

## What the numbers are, and are not

<div class="grid-3 wide">
  <div class="card">
    <h3>Small</h3>
    <p>Eight development tasks and three held-out tasks. A difference of a few points between two setups
    is not a difference; it is noise. We measured that noise once: about three points.</p>
  </div>
  <div class="card">
    <h3>Clean</h3>
    <p>The fixtures are small and tidy. Production lakehouses have nulls, duplicates, schemas that change
    under you, and ten thousand tables. Nothing here shows how the agent behaves at that scale.</p>
  </div>
  <div class="card">
    <h3>Well specified</h3>
    <p>The exams name their tables. Finding the right table in a large catalogue is where Genie's
    ontology helps most, and it is untested here.</p>
  </div>
  <div class="card">
    <h3>Single-run</h3>
    <p>One run per setup, except one configuration that was repeated three times. A model is random; a
    single run can land high or low.</p>
  </div>
  <div class="card">
    <h3>Tokens, not money</h3>
    <p>We measured tokens because we had them. We had no Genie Code usage history, so no saving can be
    quoted from this repository, and none is.</p>
  </div>
  <div class="card">
    <h3>Tuned where it says so</h3>
    <p>The development set was used to choose the tools and the rules. The held-out set was not, and it is
    where the generalisation claim rests.</p>
  </div>
</div>

## The excluded runs, named

A page that quietly drops a tenth of its evidence is worse than one that admits it. These batches exist in
the repository and are counted nowhere above:

| Batch | Why it is excluded |
|---|---|
| `_copilot_before_shim_dev`, `_copilot_before_shim_held`, `_copilot_before_shim_smoke` | GitHub Copilot CLI adds a private field the Databricks gateway rejects; the runs measured our adapter, not the agent. Kept as evidence of the failure. |
| `_old_v1_pre_port_fix` | A port collision in the harness, fixed afterwards. |
| `accidental_dbsql_only` | A runner misconfiguration: the agent got SQL only. |
| `smoke_v5` | A smoke test, not a graded run. |
| `v4_gptoss_t2`, `v4_gptoss_t3` | Repeats of one setup. They are the subject of the repeatability claim and are counted there, and nowhere else. |

<p>Every accepted run file is in
<a href="https://github.com/raphaelmansuy/opengenie/tree/main/exams/results" target="_blank" rel="noopener noreferrer">exams/results</a>,
one JSON per task plus the agent's full event log. Regenerate every table with
<code>python3 exams/make_tables.py</code>; regenerate this page with <code>python3 site/build.py</code>.</p>

## The one thing the evidence does not answer

Whether Genie Code would score worse, the same, or better on these tasks. Nobody ran it: it is a metered
product inside a workspace, and this study had a token for a workspace but no way to drive Genie Code
itself. So the comparison here is between *configurations of an open agent*, not between OpenGenie and
Genie Code on the same ruler.

<p>What that changes: the claims are about which model and which guard rails you should
choose, not about beating a specific product. What it does not change: the model, the fence and the
evidence rule matter for the reasons given on
<a href="/">the home page</a>, and those reasons do not depend on a competitor's score.</p>
