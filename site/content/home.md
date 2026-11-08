# OpenGenie

<section class="hero wide">
  <div class="badges">
    <span class="badge"><span class="dot"></span><strong>Apache-2.0</strong></span>
    <span class="badge">Databricks App</span>
    <span class="badge"><strong>16</strong> models · 4 providers</span>
    <a class="badge" href="https://github.com/raphaelmansuy/opengenie" target="_blank" rel="noopener noreferrer">Source</a>
  </div>

  <h1>Genie Code gives you one model. You cannot choose it, and you cannot see the bill coming.</h1>

  <p class="lede">OpenGenie is a Databricks App that does the same work with the model you pick, writes only
  inside the folder you name, and proves what it did before it says done.</p>

  <div class="cta-row">
    <a class="btn primary" href="/tour/">Read the tour</a>
    <a class="btn" href="/install/">Install it</a>
    <a class="btn ghost" href="/evidence/">See the evidence &rarr;</a>
  </div>
</section>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440.png" width="2880" height="1800"
         alt="The OpenGenie shell at 1440 px: sessions and files in the left rail, a notebook in the centre, and the assistant docked on the right, labelled with the notebook it is bound to." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The three-pane shell. The notebook is the centre column, the assistant is a zone beside it rather
    than a tab, and the header says what the conversation is about.
  </figcaption>
</figure>

## Three things you cannot get from the default

<div class="grid-3 wide">
  <div class="card">
    <span class="num">1</span>
    <h3>The model is yours</h3>
    <p>Sixteen models across four providers, plus whatever your AI Gateway serves &mdash; discovered at run
    time, not compiled in. Gemini, Claude, GPT, llama, qwen, and your own endpoint on the same list.</p>
    <div class="card-foot">seed/llm_models.yaml + live discovery</div>
  </div>
  <div class="card">
    <span class="num">2</span>
    <h3>The fence is real</h3>
    <p>A write is allowed only inside the folder and the schema you named when you started. Everything
    else is classified <em>ask</em> or <em>deny</em> before it reaches the workspace &mdash; not by asking
    the model to be careful.</p>
    <div class="card-foot">api/domain/scope.py</div>
  </div>
  <div class="card">
    <span class="num">3</span>
    <h3>Proof, not promises</h3>
    <p>A requirement counts as done only when a tool call proves it. A citation to a call that never
    happened is an explicit verdict, not a warning.</p>
    <div class="card-foot">api/domain/evidence.py</div>
  </div>
</div>

## Why the model is the first claim

Because it is the largest lever we could measure, and it is the one a workspace does not control. The
same agent, the same stock tools and the same rules, run on two models:

<div class="claim-bars wide" style="margin:22px 0 8px;max-width:640px">
  <div class="claim-bar"><span class="label">gpt-oss-120b</span>
    <span class="track"><span class="fill is-weak" style="width:39%"></span></span>
    <span class="pct">39%</span></div>
  <div class="claim-bar"><span class="label">Gemini 3.8 Flash</span>
    <span class="track"><span class="fill" style="width:86%"></span></span>
    <span class="pct">86%</span></div>
</div>

<p class="wide"><small>Eight development tasks, one run per model, scored against a live workspace.
One run each, and the second task has the widest natural spread of the eight. The full card, with the
fractions and the command that regenerates it, is on <a href="/evidence/">the evidence page</a>.</small></p>

## What it does, concretely

<div class="grid-3 wide">
  <div class="card">
    <h3>Answers by running SQL</h3>
    <p>It does not describe a query. It runs it on a warehouse, sees the error if there is one, and
    corrects itself &mdash; the loop is the product, not the first attempt.</p>
  </div>
  <div class="card">
    <h3>Builds notebooks that run</h3>
    <p>Writes the cells, runs them in order, stops at the first failure, and quotes the engine's own
    words when one fails.</p>
  </div>
  <div class="card">
    <h3>Finds the table</h3>
    <p>Searches the catalogue, reads the columns and the comments, and says which table it used. It
    never guesses a column name.</p>
  </div>
  <div class="card">
    <h3>Documents what exists</h3>
    <p>Writes comments grounded in real queries rather than in the model's imagination, and shows the
    query behind each one.</p>
  </div>
  <div class="card">
    <h3>Debugs a failing job</h3>
    <p>Reads the run history, finds the cause, fixes it, and re-runs &mdash; because a fix that was never
    re-run is a guess.</p>
  </div>
  <div class="card">
    <h3>Says when it cannot</h3>
    <p>Refuses Python on a cluster it does not have, a cluster picker it cannot honour, and any write
    outside the fence &mdash; with the reason.</p>
  </div>
</div>

## What this is not

<ul class="not-list wide">
  <li><strong>Not a replacement for Genie's business-term understanding.</strong> Our exams named the
  tables. We did not test finding the right table in a catalogue of ten thousand, which is where an
  ontology earns its keep.</li>
  <li><strong>Not a cost comparison.</strong> We measured tokens, not money, and we hold no Genie Code
  usage history. Any saving you read elsewhere, including here, would be invented.</li>
  <li><strong>Not a hosted demo.</strong> The app needs a token for <em>your</em> workspace, so there is
  nothing to click on this page. The tour shows real screenshots of it running.</li>
  <li><strong>Not a guarantee.</strong> One run per setup on most configurations, small and clean data,
  and tasks that name their own tables. Where that matters, it is written on the claim.</li>
</ul>

<p class="wide">Every number on this site is computed at build time from the saved run files in
<a href="https://github.com/raphaelmansuy/opengenie/tree/main/exams/results" target="_blank" rel="noopener noreferrer">exams/results</a>,
by one function. If a figure and its source ever disagreed, the build would fail rather than publish.
<a href="/evidence/">Read the evidence</a>, or
<a href="https://github.com/raphaelmansuy/opengenie/blob/main/site/claims.py" target="_blank" rel="noopener noreferrer">read the function</a>.</p>

## Start

<div class="grid-3 wide">
  <a class="card" href="/tutorial/"><h3>Tutorial</h3><p>From a notebook in Databricks to an agent that
  runs real SQL and proves it. About thirty minutes, no local shell.</p>
  <div class="card-foot">docs/tutorial.md</div></a>
  <a class="card" href="/install/"><h3>Install</h3><p>A Databricks App with the asset bundle, a local
  run against your workspace, or the shell-only setup.</p>
  <div class="card-foot">three paths, what each needs</div></a>
  <a class="card" href="/reference/"><h3>Reference</h3><p>Nine documents and five specifications,
  rendered from the repository, each linking to its source.</p>
  <div class="card-foot">docs/ + specs/</div></a>
</div>
