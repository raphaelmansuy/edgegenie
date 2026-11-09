# OpenGenie

<section class="hero wide">
  <div class="badges">
    <span class="badge"><span class="dot"></span><strong>Apache-2.0</strong></span>
    <span class="badge">Databricks App</span>
    <span class="badge">{{models}} models · {{providers}} providers · plus yours</span>
    <a class="badge" href="https://github.com/raphaelmansuy/opengenie" target="_blank" rel="noopener noreferrer">Source on GitHub</a>
  </div>

  <h1>The Databricks coding agent,<br /> on the model you choose.</h1>

  <p class="lede">Genie Code is the best coding agent for data engineering because it can see your
  workspace. OpenGenie gives an open-source agent the same kind of reach &mdash; Unity Catalog, SQL
  warehouses, notebooks, jobs &mdash; and hands back the two decisions Genie Code makes for you: which
  model does the work, and who you pay for it.</p>

  <div class="cta-row">
    <a class="btn primary" href="/tour/">Take the tour</a>
    <a class="btn" href="/install/">Deploy it</a>
    <a class="btn ghost" href="/evidence/">See the evidence &rarr;</a>
  </div>
</section>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440.png" width="2880" height="1800"
         alt="The OpenGenie shell at 1440 px: sessions and files in the left rail, a notebook in the centre, and the assistant docked on the right, labelled with the notebook it is bound to." />
  </div>
  <figcaption>
    The app deployed in a Databricks workspace. The notebook is the centre of the screen; the assistant
    sits beside it and knows which notebook the conversation is about.
  </figcaption>
</figure>

## Why it exists

Genie Code gets one thing right that most coding agents get wrong: the agent works *inside*
Databricks. It reads the catalogue, runs SQL on a warehouse, opens notebooks and inspects jobs, so its
answers come from your data instead of from a guess. That context is why it is good.

Two things come with it that a team cannot change. The model is chosen for you, and the bill is metered
by a product you do not configure. Raphael Mansuy built OpenGenie to keep the context and return those
two decisions to the team: use the model you already pay for, or the one that is best at the task, and
run the whole thing as a Databricks App in your own workspace.

<div class="measure-box wide">
  <p class="kicker">Measured, not assumed</p>
  <h3>The model is the biggest lever on whether the work gets done</h3>
  <p>Same agent, same tools, same rules, eight development tasks graded against a live workspace.
  Only the model changed.</p>
  <div class="claim-bars">
    <div class="claim-bar"><span class="label">gpt-oss-120b</span>
      <span class="track"><span class="fill is-weak" style="width:39%"></span></span>
      <span class="pct">39%</span></div>
    <div class="claim-bar"><span class="label">Gemini 3.8 Flash</span>
      <span class="track"><span class="fill" style="width:86%"></span></span>
      <span class="pct">86%</span></div>
  </div>
  <p><small>One run per model. The fractions, the caveats and the command that regenerates these
  numbers are on <a href="/evidence/">the evidence page</a>.</small></p>
</div>

## What the agent can reach

Each conversation starts its own tool server. It calls the Databricks APIs as **you**, the signed-in
user, so Unity Catalog permissions still decide what the agent can see.

<div class="grid-3 wide tools-grid">
  <div class="card">
    <h3>Unity Catalog</h3>
    <p>Lists tables, reads columns, types and comments, and searches table and column names across
    the catalogue &mdash; so it looks a column up instead of guessing it.</p>
    <div class="card-foot"><span class="nw">dbx_describe_table</span><span class="sep" aria-hidden="true"> · </span><span class="nw">dbx_search_tables</span></div>
  </div>
  <div class="card">
    <h3>SQL warehouses</h3>
    <p>Runs the query rather than describing it, reads the result or the engine's error, and corrects
    the next attempt from what actually came back.</p>
    <div class="card-foot">dbx_run_sql</div>
  </div>
  <div class="card">
    <h3>Notebooks</h3>
    <p>Reads, searches and writes notebooks, then runs them and reports the first failing cell in the
    engine's own words.</p>
    <div class="card-foot"><span class="nw">dbx_write_notebook</span><span class="sep" aria-hidden="true"> · </span><span class="nw">dbx_run_notebook</span></div>
  </div>
  <div class="card">
    <h3>Jobs</h3>
    <p>Creates and runs jobs under the conversation's name prefix, then checks that the latest run
    succeeded rather than assuming it did.</p>
    <div class="card-foot"><span class="nw">dbx_create_job</span><span class="sep" aria-hidden="true"> · </span><span class="nw">dbx_job_run_status</span></div>
  </div>
  <div class="card">
    <h3>Lakebase and Apps</h3>
    <p>Creates a Lakebase Postgres instance, runs SQL against it, and scaffolds a Databricks App
    &mdash; each named inside the same prefix.</p>
    <div class="card-foot"><span class="nw">dbx_lakebase_sql</span><span class="sep" aria-hidden="true"> · </span><span class="nw">dbx_create_app</span></div>
  </div>
  <div class="card">
    <h3>Skills</h3>
    <p>{{skills}} written playbooks &mdash; notebook authoring, ETL pipelines, Lakebase and Databricks
    Apps &mdash; that the agent loads only when a task needs one.</p>
    <div class="card-foot">dbx_skill</div>
  </div>
</div>

<p><small>That is the {{core_tools}}-tool core profile the app starts. The tool server
has {{tools}}; catalogue and schema listings, lineage, grants, pipelines and warehouse lookups are in
its full profile, and left out of the app by default because an agent advertises every tool on every
request and pays for it in tokens.</small></p>

## Three rules the server enforces

Not instructions in a prompt. Each one is code you can read, with tests.

<div class="grid-3 wide">
  <div class="card">
    <span class="num">1</span>
    <h3>The model is a setting</h3>
    <p>{{models}} models from {{providers}} providers ship in the catalogue &mdash; Databricks serving
    endpoints, OpenAI, Anthropic and Google Vertex &mdash; and the serving endpoints your workspace
    exposes are discovered at run time. A personal provider key is stored encrypted, with the key
    held in a Databricks secret.</p>
    <div class="card-foot">seed/llm_models.yaml</div>
  </div>
  <div class="card">
    <span class="num">2</span>
    <h3>Writes stay inside the fence</h3>
    <p>A conversation's tool server is started with one folder, one schema and one job-name prefix. A
    write anywhere else is refused by that server, with the reason; a write you make from the app
    outside the folder waits for your approval.</p>
    <div class="card-foot"><span class="nw">adapters/mcp/registry.py</span><span class="sep" aria-hidden="true"> · </span><span class="nw">domain/scope.py</span></div>
  </div>
  <div class="card">
    <span class="num">3</span>
    <h3>Done means proven</h3>
    <p>When the agent says a requirement is met, the claim is matched against the tool calls it
    actually made. A citation to a call that never happened is reported as exactly that.</p>
    <div class="card-foot">domain/evidence.py</div>
  </div>
</div>

## How it fits together

One Databricks App process. For each conversation it starts an
[opencode](https://opencode.ai) agent over the Agent Client Protocol and a fenced tool
server beside it.

<ol class="flow wide" aria-label="The path of a request">
  <li><strong>You</strong>in the browser, signed in to Databricks</li>
  <li><strong>OpenGenie App</strong>FastAPI and React, acting as you</li>
  <li><strong>Agent</strong><code>opencode acp</code>, one per conversation</li>
  <li class="is-fence"><strong>Tool server</strong>fenced to your folder, schema and prefix</li>
  <li><strong>Your workspace</strong>Unity Catalog, warehouses, notebooks, jobs</li>
</ol>
<div class="flow-side wide">
  <div><strong>The model</strong> is called by the agent: a Databricks serving endpoint or AI Gateway
  route, OpenAI, Anthropic, or Vertex. You pick it in the composer.</div>
  <div><strong>Lakebase</strong> holds what must survive a restart: the conversation journal, the model
  catalogue, and encrypted provider keys.</div>
</div>

## What working with it looks like

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/mission-achieved.png" width="1440" height="960"
         alt="The mission view after a completed request: the objective, the notebook the agent wrote, three requirements each marked verified, and the plan it followed." />
  </div>
  <figcaption>
    One request, one view: what was asked, what was written, and which tool call proves each
    requirement. (A local run with a scripted agent.)
  </figcaption>
</figure>

<div class="grid-3 wide">
  <div class="card">
    <h3>It keeps working when you leave</h3>
    <p>The work runs on the server and is journalled. Close the tab and come back to the result; after
    a restart, the app says what was interrupted instead of replaying it blindly.</p>
  </div>
  <div class="card">
    <h3>A notebook, not a chat log</h3>
    <p>Run all stops at the first failure and shows where it is. <strong>Fix with agent</strong> sends
    the engine's own error, bound to that cell. Python cells, run on serverless by an administrator,
    draw their plots under the cell.</p>
  </div>
  <div class="card">
    <h3>Show it, don't describe it</h3>
    <p>Attach a file or paste a screenshot of a failing dashboard. If the chosen model cannot see
    images, the app names that model and tells you to pick one that can, instead of sending pixels
    nobody reads.</p>
  </div>
</div>

## Genie Code or OpenGenie?

They solve the same problem with different trade-offs. Pick on the trade-off, not on the logo.

<div class="grid-2 wide">
  <div class="card choose">
    <h3>Stay on Genie Code if</h3>
    <ul>
      <li>you want nothing to deploy, configure or operate;</li>
      <li>one model is fine for your work, and the metered cost is acceptable;</li>
      <li>your hardest problem is finding the right table among thousands, where Genie's business
      semantics help most;</li>
      <li>you need inline completion, or Python running as you on your own clusters.</li>
    </ul>
  </div>
  <div class="card choose is-ours">
    <h3>Use OpenGenie if</h3>
    <ul>
      <li>you want to choose the model per task, or use one you already pay for;</li>
      <li>writes must stay inside a named folder and schema, enforced by the server;</li>
      <li>you want the agent's &ldquo;done&rdquo; checked against what it actually ran;</li>
      <li>you want to read, change and self-host the code under Apache&#8209;2.0.</li>
    </ul>
  </div>
</div>

## What this is not

<ul class="not-list wide">
  <li><strong>Not a replacement for Genie's understanding of business terms.</strong> The exams named their
  tables. Finding the right table in a catalogue of ten thousand is where an ontology earns its keep,
  and it is untested here.</li>
  <li><strong>Not a cost comparison.</strong> We measured tokens, not money, and hold no Genie Code
  usage history. Any saving quoted from this repository would be invented, so none is.</li>
  <li><strong>Not a hosted demo.</strong> The app needs your workspace, so there is nothing to click
  here. The tour shows real screenshots of it running.</li>
  <li><strong>Not a guarantee.</strong> Small, clean data; one run per setup on most configurations;
  tasks that name their own tables. Where that matters, it is written on the claim.</li>
</ul>

<p>Every score on this site is computed at build time from the run files in
<a href="https://github.com/raphaelmansuy/opengenie/tree/main/exams/results" target="_blank" rel="noopener noreferrer">exams/results</a>,
and every count of models and tools is read from the application's source. If a figure and its source
disagreed, the build would fail rather than publish.</p>

## Start here

<div class="grid-3 wide">
  <a class="card" href="/tour/"><h3>Tour</h3><p>Real screenshots: the notebook, the assistant, the
  mission view, approvals, recovery and the model picker.</p>
  <div class="card-foot">five minutes</div></a>
  <a class="card" href="/install/"><h3>Deploy</h3><p>Put it in your workspace as a Databricks App,
  run it locally against your workspace, or start from a single notebook.</p>
  <div class="card-foot">what to change before you deploy</div></a>
  <a class="card" href="/tutorial/"><h3>Tutorial</h3><p>From a notebook in Databricks to an agent
  that runs real SQL and proves it. No local shell.</p>
  <div class="card-foot">about thirty minutes</div></a>
</div>
