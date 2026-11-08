# Tour

What the app looks like. Every picture below is a real screenshot of OpenGenie running against a
Databricks workspace, captured with Playwright, not a mock-up. Each one names the width it was taken at,
because a layout is the thing screenshots are best at proving and the thing mock-ups are worst at.

<p class="lede">Five screens make up the whole application: the shell, the notebook, the assistant dock,
the model picker, and the fence. Everything else is a state of one of those.</p>

## The shell at 1440 px

The three-pane shell, light theme. Sessions and files on the left; the notebook in the centre; the
assistant docked on the right. The dock is a **zone**, not a tab, so opening a notebook does not unmount
the conversation that is about it.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440.png" width="2880" height="1800"
         alt="The shell at 1440 px: a left rail listing sessions and files, a notebook with four cells in the centre, and the assistant dock on the right headed 'in context: parity_demo'." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    <span class="shot-meta">deployed</span>
    The starting screen. The folder named under the greeting is the only place this session may write.
  </figcaption>
</figure>

## The shell at 800 px — one zone at a time

Below 860 px two panes cannot both be honest, so one of them becomes a drawer the user summons. The
drawer never opens by itself, and the control that opens it is always on screen.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-800.png" width="1600" height="1000"
         alt="The shell at 800 px: the left rail and the assistant are collapsed into buttons, and the notebook takes the full width." />
  </div>
  <figcaption>
    <span class="shot-meta">800 px</span><span class="shot-meta">light</span>
    Same application, narrower. Nothing is hidden that cannot be reached in one press.
  </figcaption>
</figure>

## The notebook

Four cells: a markdown heading, two SQL queries, and one that is about to fail. Every cell carries its
own **Ask** and **Run**, because the unit of the work is the cell, not the file.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/notebook-1440.png" width="2880" height="1800"
         alt="A notebook named parity_demo with two markdown-free SQL cells, each showing Ask and Run buttons, and a bar above with Run all and the warehouse name." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The notebook bar carries <strong>Run all</strong> and the name of the warehouse it will use.
  </figcaption>
</figure>

## Running all of it, and stopping at the first failure

Three cells run in order. The third fails against a table that does not exist. The bar says
&ldquo;2 ran · 1 failed&rdquo; and the failing cell offers **Fix with agent**, which sends the engine's own
error text rather than the user's paraphrase of it.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/run-all-1440.png" width="2880" height="1800"
         alt="A notebook after Run all: two cells succeeded, the third shows an error from the SQL engine, and a button labelled Fix with agent sits beside it." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Run all stops at the first failure, because later cells usually read what earlier ones made.
  </figcaption>
</figure>

## Asking about one cell, from the cell

`⌘I` opens a prompt on the cell itself, with four one-click actions and a reminder that only this cell
may change. The conversation still happens in the dock — the inline prompt is a faster way in, not a
second chat — so Stop, approvals and the audit trail stay in one place.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/cell-prompt-1440.png" width="2880" height="1800"
         alt="A prompt open on cell three with the placeholder naming that cell, and chips for Explain, Fix, Optimise and Comment." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The message is bound to <strong>parity_demo · cell 3</strong>, and the dock is what receives it.
  </figcaption>
</figure>

## The message that was actually sent

Worth showing separately, because it is the part users never see and always wonder about: the prompt is
short, it names the cell, and it states the one constraint that matters &mdash; leave every other cell
alone.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/prompt-sent.png" width="2880" height="1800"
         alt="The assistant dock showing the sent message, with a chip reading cell 3 and a sentence saying to change only that cell." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    What the user said, plus one constraint. No scaffolding presented as the user's own words.
  </figcaption>
</figure>

## What is offered after an answer

Up to three next steps, derived from what the turn actually did. &ldquo;Run it&rdquo; appears only if a
notebook was written and not run; a fixed menu would be marketing, a derived one is help.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/follow-ups.png" width="2880" height="1800"
         alt="The dock scrolled to the end of a turn, with three follow-up chips under the answer." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Derived from the turn, not from a list.
  </figcaption>
</figure>

## Fixing an error with the engine's own words

The failing cell's **Fix with agent** sends the error code and message exactly as the warehouse returned
them, bound to that cell.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/fix-agent.png" width="2880" height="1800"
         alt="The dock after Fix with agent: the sent message quotes the SQL engine's error and is bound to cell four." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The agent starts from the cause, not from &ldquo;it didn't work&rdquo;.
  </figcaption>
</figure>

## The model picker

One control, identical in the composer and the top bar, at every width. Grouped by provider, searchable,
and honest about what it knows: a limit that was measured is labelled as measured, and one that is
unknown says so.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440-picker.png" width="2880" height="1800"
         alt="The model picker open over the shell, listing models grouped by provider with their context and output limits." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Sixteen models from four providers, plus whatever the gateway discovers.
  </figcaption>
</figure>

## The workspace browser

The same app can browse the workspace, so the starting point is never a blank prompt. Choosing a folder
sets the fence for the session &mdash; the choice and the permission are the same act.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/app-1440-tree.png" width="2880" height="1800"
         alt="The workspace tree open, showing folders and notebooks, with a chooser for the working folder." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Picking a folder is picking the boundary.
  </figcaption>
</figure>

## A conversation that opens with a notebook

Starting from an open notebook rather than an empty chat: the dock already knows what it is about, and
offers three things worth asking.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/session-1440.png" width="2880" height="1800"
         alt="A session opened on a notebook: the dock is headed with the notebook name and offers three starter questions." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The subject of the conversation is a value the app holds, not an inference from the viewport.
  </figcaption>
</figure>

## The same conversation at 800 px

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/session-800.png" width="1600" height="1000"
         alt="The same session at 800 px, with the assistant available as a drawer over the notebook." />
  </div>
  <figcaption>
    <span class="shot-meta">800 px</span><span class="shot-meta">light</span>
    One zone at a time, and a visible way back.
  </figcaption>
</figure>

## Dark

Dark is a restated palette, not an inversion of the light one. The assistant, the notebook and the rail
keep their relationships, and the contrast was measured on the painted colours rather than declared.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/notebook-dark.png" width="2880" height="1800"
         alt="The notebook and the assistant in dark theme, with the in-cell prompt open and readable." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">dark</span>
    The same components, a different set of values.
  </figcaption>
</figure>

## Markdown renders LaTeX, because notebooks have formulae

A markdown cell with LaTeX renders as typeset maths, in the answer and in the file.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/math-dark.png" width="2880" height="1800"
         alt="A markdown cell rendering LaTeX as typeset mathematics in dark theme." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">dark</span>
    KaTeX, in the cell and in the assistant's answer.
  </figcaption>
</figure>

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/math-narrow.png" width="1120" height="900"
         alt="The same LaTeX rendering at a narrow width, with the formula still legible and no horizontal scroll on the page." />
  </div>
  <figcaption>
    <span class="shot-meta">560 px</span><span class="shot-meta">light</span>
    A wide formula scrolls inside its block; the page itself never scrolls sideways.
  </figcaption>
</figure>

## Slash commands

A bare `/` lists every command with its description, and the arrows move the selection. The list is the
command registry, so a command that is not registered cannot appear.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/slash-1440.png" width="2880" height="1800"
         alt="The composer with a slash typed, showing a list of commands with descriptions." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Discoverable without documentation.
  </figcaption>
</figure>

## Conversation history

The same list the left rail shows, available from the dock's own header, because at 760 px the rail is
not on screen and the person working in the dock still needs their history.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/history.png" width="2880" height="1800"
         alt="A history popover over the dock: a search field, a day heading, and a list of conversations with the active one marked." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    Search, day groups, delete.
  </figcaption>
</figure>

## The fence, when it refuses

The refusal is the feature. A write outside the named folder is not attempted and then reported; it is
classified before it leaves the server, and the message says which folder would have been allowed.

<figure class="shot wide">
  <div class="frame">
    <img src="/assets/shots/zones-1440.png" width="2880" height="1800"
         alt="The shell with all zones visible, showing the working folder and the fence notice in the inspector." />
  </div>
  <figcaption>
    <span class="shot-meta">1440 px</span><span class="shot-meta">light</span>
    The boundary is stated on screen, not only in a log.
  </figcaption>
</figure>

## What these screenshots do not show

- **The Python cells, the cluster picker, scheduling, comments and sharing.** They are workspace features
  this app does not offer, and a control for a capability that does not exist would be a lie.
- **Inline completion.** It needs a low-latency completion path the agent protocol does not have.
- **A hosted demo.** There is none: the app needs a token for your own workspace.

<p class="wide">The decisions behind each screen are in
<a href="../reference/spec-006/">spec 006</a> (the dock, the model control, the drawer) and
<a href="../reference/spec-007/">spec 007</a> (zones, keys, scrolling, focus). The fence is in
<a href="../reference/spec-001/">spec 001</a> and <a href="../reference/doc-safety/">safety and governance</a>.</p>
