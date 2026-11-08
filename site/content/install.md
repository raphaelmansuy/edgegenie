# Install

Three ways to run it. They are not alternatives to choose by taste: each one exists because a different
constraint makes the other two impossible.

<p class="lede">The application is a Databricks App: a FastAPI server that serves a React front end and
spawns an ACP agent per session. All three paths end in the same application; they differ in who owns the
process and what it can reach.</p>

## Which one is yours

<div class="grid-3 wide">
  <div class="card">
    <span class="num">A</span>
    <h3>As a Databricks App</h3>
    <p>The real deployment. The app runs in your workspace, with your permissions, and the browser
    reaches it over single sign-on. This is the only path where the app can act as the signed-in user.</p>
    <div class="card-foot">needs: a workspace, app compute, a model endpoint</div>
  </div>
  <div class="card">
    <span class="num">B</span>
    <h3>Locally, against your workspace</h3>
    <p>For development and for reading the code. A token stands in for single sign-on, which means the
    app acts as whoever owns the token.</p>
    <div class="card-foot">needs: python 3.12, node 20+, a token</div>
  </div>
  <div class="card">
    <span class="num">C</span>
    <h3>The shell-only setup</h3>
    <p>The original study: an agent in a Databricks sandbox, driven from a notebook. No front end, no
    app. It is the fastest way to try the idea and the slowest way to work.</p>
    <div class="card-foot">needs: serverless compute, a token</div>
  </div>
</div>

## A · As a Databricks App

The repository carries a Databricks asset bundle, so this is three commands and one setting.

```bash
git clone https://github.com/raphaelmansuy/opengenie.git
cd edgegenie
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

Then set two things in the workspace, because neither can be guessed:

| Setting | What it is | Where |
|---|---|---|
| A model endpoint | The app does not carry a key for a model. Grant its service principal access to at least one serving endpoint. | Unity Catalog grants, or the AI Gateway |
| The admin list | Who may change the catalogue for everyone. Empty means nobody, because a catalogue anyone can rewrite is a finding. | `APP_LLM_ADMINS` in `apps/coding-agent/app.yaml` |

<p class="wide">The bundle definition is
<a href="https://github.com/raphaelmansuy/opengenie/blob/main/databricks.yml" target="_blank" rel="noopener noreferrer">databricks.yml</a>;
the app's runtime contract and its environment are in
<a href="https://github.com/raphaelmansuy/opengenie/blob/main/apps/coding-agent/app.yaml" target="_blank" rel="noopener noreferrer">apps/coding-agent/app.yaml</a>,
and each line there has a comment saying why it exists.</p>

<div class="callout callout-warning"><p><strong>A note on the free tier.</strong> The app needs app compute
and a model endpoint. On a workspace that has exhausted its daily free allowance, both are refused
independently, and the failure reads as a quota message rather than as a configuration problem. That is
what happened when this repository first tried to deploy.</p></div>

## B · Locally, against your workspace

```bash
cd apps/coding-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..

export DATABRICKS_HOST=https://YOUR-WORKSPACE.cloud.databricks.com
export DATABRICKS_TOKEN=dapi...            # never commit this
export APP_AGENT_MODE=stdio
export APP_DEFAULT_MODEL=databricks/databricks-llama-4-maverick

python -m uvicorn api.main:app --port 8071
```

Open `http://127.0.0.1:8071`. The front end is served by the API, so there is no second dev server and no
CORS configuration to get wrong.

<div class="callout callout-important"><p><strong>The token is the boundary.</strong> Locally there is no
single sign-on, so the app acts as the token's owner. A token with write rights on production is a token
that can write to production &mdash; the fence limits <em>what the agent asks for</em>, not what the token
may do. Use a token from a service principal with rights on one scratch schema.</p></div>

## C · The shell-only setup

This is the path in <a href="/tutorial/">the tutorial</a>, and it needs no local shell at all. Import one
notebook into your workspace, run its cells in order, and you have an agent that runs real SQL and a
fence you can test by trying to break it.

<p class="wide">It is the original study, kept because it is the cheapest way to see whether the idea
holds on your data before you deploy anything. It has no user interface beyond the notebook, and it is
one person's session at a time.</p>

## What none of the three paths can do

| Not possible | Why |
|---|---|
| Run Python cells on a cluster | The app runs SQL on a warehouse. Running arbitrary code on its own compute would be a hole, and a cluster picker for a choice the app does not offer would be a lie. |
| Schedule, comment or share the notebook | Those are workspace features. The app opens the same files, so schedule and share them in Databricks. |
| Inline completion | It needs a low-latency path the agent protocol does not have. |
| Reach Unity Catalog objects you cannot | The app acts as you. Its permissions are your permissions, which is the point and also the limit. |

## After it runs

<p class="wide">The fence is the thing to test first, and the tutorial ends with exactly that: an
instruction to write outside the named folder, and the refusal. Then read
<a href="../reference/doc-safety/">safety and governance</a> for what the fence does not cover, and
<a href="../reference/doc-decide/">the decision guide</a> if you are deciding whether to roll it out.</p>

## Uninstalling

Nothing outside the workspace is touched. Delete the app and the bundle's resources:

```bash
databricks bundle destroy -t dev
```

The agent's scratch folder and any table it created stay where they are: they are your data, in your
workspace, and a tool that deletes them on uninstall is a tool you cannot trust with them.
