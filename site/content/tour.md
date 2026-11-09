# Tour

What the app looks like, from real screenshots captured with Playwright. Every figure says the width
it was taken at and where it ran: **deployed** means a Databricks workspace; **local run** means the
same app on a laptop, and **scripted agent** means a deterministic stand-in for the model, used where
the screen matters more than the answer.

<p class="lede">The shell has three parts: your sessions and files on the left, the notebook in the
centre, and the assistant beside it. Everything below is a state of one of those.</p>

## The shell

The assistant is a zone next to the notebook, not a tab, so opening a file does not close the
conversation that is about it. The folder named under the greeting is the only place this conversation
may write.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440.png" width="2880" height="1800"
         alt="The shell at 1440 px: a left rail listing sessions and files, a notebook with four cells in the centre, and the assistant dock on the right headed 'in context: parity_demo'." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    The starting screen.
  </figcaption>
</figure>

### Choosing where it may write

The workspace browser is how a conversation starts. Picking a folder sets the fence for the session:
the choice and the permission are the same act.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440-tree.png" width="2880" height="1800"
         alt="The workspace tree open, showing folders and notebooks, with a chooser for the working folder." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    Picking a folder is picking the boundary.
  </figcaption>
</figure>

## The notebook

Every cell has its own **Ask** and **Run**, because the unit of the work is the cell, not the file. The
bar above carries **Run all** and the compute the SQL will run on.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/notebook-1440.png" width="2880" height="1800"
         alt="A notebook named parity_demo with SQL cells, each showing Ask and Run buttons, and a bar above with Run all and Serverless SQL." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    <strong>Run all</strong> and the compute it will use, always visible.
  </figcaption>
</figure>

### Run all stops at the first failure

Later cells usually read what earlier ones made, so Run all stops at the first failure. The bar says
&ldquo;2 ran · 1 failed&rdquo;, and the failing cell offers **Fix with agent**, which sends the
engine's own error text rather than a paraphrase of it.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/run-all-1440.png" width="2880" height="1800"
         alt="A notebook after Run all: two cells succeeded, the third shows an error from the SQL engine, and a button labelled Fix with agent sits beside it." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    The agent starts from the cause, not from &ldquo;it didn't work&rdquo;.
  </figcaption>
</figure>

### The run map

On a long notebook, the map lists what ran, what was skipped on purpose and what failed, with the
failing statement in full. <strong>First failed</strong> and <strong>Last run</strong> jump to the cell.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/run-map-1440.png" width="2880" height="1800"
         alt="The notebook run map open: cell 2 done, cell 3 skipped, cell 4 failed with its statement shown in full, and buttons for First failed and Last run." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    Where the failure is, without scrolling for it.
  </figcaption>
</figure>

### Python cells and their plots

Python runs on serverless compute, started by an administrator, as the app's own service principal
&mdash; every result says so, because it did not run as you. The output is drawn under the cell, and
matplotlib figures the cell leaves open appear there as images, with a download button.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/plot-1440.png" width="2880" height="1800"
         alt="A finished Python cell with its output drawn directly under it: three KPI figures." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    Output under the cell, as in Databricks and Jupyter. Figures are static images; widgets are not supported.
  </figcaption>
</figure>

## The assistant

### Asking about one cell, from the cell

`⌘I` opens a prompt on the cell itself, with four one-click actions and a reminder that only this cell
may change. The conversation still happens in the dock, so Stop, approvals and the audit trail stay in
one place.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/cell-prompt-1440.png" width="2880" height="1800"
         alt="A prompt open on cell three with the placeholder naming that cell, and chips for Explain, Fix, Optimise and Comment." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    The message is bound to <strong>parity_demo · cell 3</strong>.
  </figcaption>
</figure>

### What was actually sent

The part users never see and always wonder about: the prompt is short, it names the cell, and it states
the one constraint that matters &mdash; leave every other cell alone.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/prompt-sent.png" width="2880" height="1800"
         alt="The assistant dock showing the sent message, with a chip reading cell 3 and a sentence saying to change only that cell." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    What you said, plus one constraint. No hidden scaffolding presented as your words.
  </figcaption>
</figure>

### Next steps derived from the turn

Up to three suggestions, derived from what the turn actually did. &ldquo;Run it&rdquo; appears only if a
notebook was written and not run.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/follow-ups.png" width="2880" height="1800"
         alt="The dock scrolled to the end of a turn, with three follow-up chips under the answer." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    Derived from the turn, not from a fixed menu.
  </figcaption>
</figure>

### Slash commands and history

A bare `/` lists every registered command with its description. History is available from the dock's
own header, because on a narrow screen the left rail is not there.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/slash-1440.png" width="2880" height="1800"
         alt="The composer with a slash typed, showing a list of commands with descriptions." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">deployed</span>
    Discoverable without documentation.
  </figcaption>
</figure>

## Long-running work

The work runs on the server, not in the browser tab, and every step is written to a journal. That is
what makes the next three screens possible.

### The mission view

One accepted request becomes a mission: the objective, where it is now, what it wrote, and which tool
call proves each requirement. Earlier missions stay selectable.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/mission-achieved.png" width="1440" height="960"
         alt="The mission view after a completed request: the objective, the notebook the agent wrote, three requirements each marked verified, and the plan it followed." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    Results first, then the plan that produced them.
  </figcaption>
</figure>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/mission-evidence.png" width="1440" height="960"
         alt="A requirement's evidence expanded, showing the exact tool input and the result it returned." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    Open any proof to see the exact input and the result it returned.
  </figcaption>
</figure>

### Approvals, inline

When an action needs a human, the conversation waits on one decision card that names the target and
the reason. There is no modal, and closing the tab does not lose the question.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/mission-approval.png" width="1440" height="960"
         alt="The assistant waiting for approval: a card in the dock naming the target of the action, the reason it needs approval, and the decision buttons." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    The decision, its target and its reason, in one place.
  </figcaption>
</figure>

### Coming back, and recovering

Close the page and return later: the plan, the full answer and its status are there. If the server
restarted mid-turn, the app says what was interrupted and offers to restore the agent; it does not
replay an uncertain operation behind your back.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/durable-return.png" width="1440" height="960"
         alt="A fresh browser window showing a finished turn: the completed plan, the full answer, and a ready-for-review status." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    After the page was closed: nothing lost, nothing duplicated.
  </figcaption>
</figure>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/durable-restart.png" width="1440" height="960"
         alt="After a server restart: a Restore action, a disabled composer, the partial plan preserved, and a sentence explaining what is uncertain." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    After a restart: the uncertainty is stated, and the next move is yours.
  </figcaption>
</figure>

## Files and screenshots

Attach a file, drop it on the composer, or paste an image from the clipboard. The attachment travels
with the message as a chip, and is kept with the conversation.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/attach-answer.png" width="2880" height="1800"
         alt="A sent message carrying a pasted image as a chip named shot.png, followed by the agent's answer." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    The pasted image, on the message it belongs to.
  </figcaption>
</figure>

If the selected model cannot see images, the app says which model cannot and asks for one that can,
rather than sending pixels that nobody will read.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/attach-refused.png" width="2880" height="1800"
         alt="The composer refusing to send an image, with a sentence naming the selected model and saying a vision model is needed." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run, scripted agent</span>
    A capability is a declared fact about the model, not a hope.
  </figcaption>
</figure>

## The model picker

One control, identical in the composer and the top bar. Grouped by provider, searchable, and honest
about what it knows: a limit that was measured is labelled as measured, and an unknown one says so.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/model-picker.png" width="2880" height="1800"
         alt="The model picker open: the Databricks AI Gateway group listing llama-4-maverick as current, gpt-oss-120b, meta-llama-3-3-70b and qwen3-next-80b, and a group of models not available here." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    The picker shows what this workspace can actually use, and says why the rest is unavailable.
    The catalogue ships {{models}} models from {{providers}} providers, plus the serving endpoints the workspace
    exposes.
  </figcaption>
</figure>

## The fence, on screen

The working folder is stated where you work. A notebook the agent writes outside it is not overwritten
in place: the app saves a copy inside the folder and says so. A write the agent attempts through its tools
outside the folder is refused by the tool server; a write that needs a person waits for one, as in
[the approval above](#approvals-inline).

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/fence-copy.png" width="1720" height="600"
         alt="A notebook banner saying the agent wrote a different file which is outside the folder it may write to, so it made a copy instead, with an Open it button." />
  </div>
  <figcaption>
    <span class="shot-meta">860 px crop</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    The fence, as a reader meets it: a sentence, and a way to the copy.
  </figcaption>
</figure>

## Every width, both themes

### 800 px: one zone at a time

Below 860 px, two panes cannot both be readable, so one becomes a drawer you open. It never opens by
itself, and the control for it is always on screen.

<figure class="shot is-narrow">
  <div class="frame">
    <img src="/assets/shots/drawer-800.png" width="1600" height="1720"
         alt="The app at 800 px: files and chat collapsed to slim rails at the edges, and the context panel open as a drawer on the right saying where this agent can write." />
  </div>
  <figcaption>
    <span class="shot-meta">800 px</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    Nothing is hidden that cannot be reached in one press.
  </figcaption>
</figure>

### A phone

<figure class="shot is-phone">
  <div class="frame">
    <img src="/assets/shots/mission-mobile.png" width="390" height="960"
         alt="The mission view on a 390 px phone screen: the objective, status and results stacked in one column." />
  </div>
  <figcaption>
    <span class="shot-meta">390 px</span><span class="shot-meta">light</span><span class="shot-meta">local run</span>
    Check on a long job from your phone.
  </figcaption>
</figure>

### Dark

Dark is a restated palette, not an inversion of the light one, and its contrast was measured on the
painted colours.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/notebook-dark.png" width="2880" height="1800"
         alt="The notebook and the assistant in dark theme, with the in-cell prompt open and readable." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">dark</span><span class="shot-meta">deployed</span>
    The same components, a different set of values.
  </figcaption>
</figure>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/mission-dark.png" width="1920" height="960"
         alt="The mission view in dark theme at 1920 px: an achieved outcome, three of three requirements verified, and the conversation beside it." />
  </div>
  <figcaption>
    <span class="shot-meta">1920 px</span><span class="shot-meta">dark</span><span class="shot-meta">local run, scripted agent</span>
    On a wide screen the content keeps a readable measure instead of stretching.
  </figcaption>
</figure>

## What these screenshots do not show

- **Python running as you, or a cluster picker.** Databricks Apps user authorisation has no compute
  scope, so the app cannot submit a run in your name. Python runs as the app's service principal, and
  says so.
- **Scheduling, comments and sharing.** These are workspace features; the app opens the same files, so
  use Databricks for them.
- **Inline completion.** It needs a low-latency completion path the agent protocol does not have.
- **A hosted demo.** There is none: the app needs your own workspace.

<p>The decisions behind each screen are in
<a href="../reference/spec-006/">spec 006</a> (the dock, the model control, the drawer) and
<a href="../reference/spec-007/">spec 007</a> (zones, keys, scrolling, focus). The fence is in
<a href="../reference/spec-001/">spec 001</a> and <a href="../reference/doc-safety/">safety and governance</a>.</p>
