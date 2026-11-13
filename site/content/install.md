# Install

Three ways to run it. They are not a matter of taste: each exists because a different constraint makes
the other two impossible.

<p class="lede">OpenGenie is a Databricks App: one FastAPI process that serves the React front end and
starts an <code>opencode</code> agent and a fenced tool server for each conversation. All three paths
run the same code; they differ in who owns the process and what it can reach.</p>

## Which one is yours

<div class="grid-3 wide">
  <div class="card">
    <span class="num">A</span>
    <h3>As a Databricks App</h3>
    <p>The real deployment. The app runs in your workspace and acts as the signed-in user, so Unity
    Catalog permissions apply to the agent exactly as they apply to you.</p>
    <div class="card-foot">needs: app compute, Lakebase, a&nbsp;model</div>
  </div>
  <div class="card">
    <span class="num">B</span>
    <h3>On your machine</h3>
    <p>For development and for reading the code. Your CLI login stands in for single sign-on, so the
    app acts as you.</p>
    <div class="card-foot">needs: Python 3.12, Node 20+, the databricks&nbsp;CLI</div>
  </div>
  <div class="card">
    <span class="num">C</span>
    <h3>From a notebook only</h3>
    <p>The original study: an agent in the Databricks sandbox, driven from a notebook. No front end.
    The cheapest way to see whether the idea holds on your data.</p>
    <div class="card-foot">needs: serverless compute, a&nbsp;token</div>
  </div>
</div>

## A · As a Databricks App

### 1. Change what is specific to the author's workspace

The repository deploys the author's own instance, so a few values name his workspace. Change them
before anything else. Both files are in `apps/coding-agent/`.

| Setting | Set it to |
|---|---|
| `APP_LLM_ADMINS` in `app.yaml` | the e-mails allowed to edit the model catalogue for everyone. Empty means nobody. |
| `APP_DEFAULT_MODEL` in `app.yaml` | a model your workspace can reach, e.g. `databricks/databricks-llama-4-maverick` |
| `LLM_VERTEX_PROJECT` and `APP_LLM_VERTEX_PROJECT` in `app.yaml` | your Google Cloud project &mdash; or remove them, and the `vertex-sa` resource in `databricks.yml`, if you do not use Vertex |
| `APP_LLM_PG_ENDPOINT` in `app.yaml` | your Lakebase endpoint (step 2). It is a *project name*, so the same value in two workspaces is two independent databases |
| the `dev` branch of `scripts/env.sh` | your workspace's host and how its apps take their source — see below |

### 2. Create Lakebase and the encryption key

In production the app refuses to start without a durable journal, because a conversation that lives in
container memory is lost on the next redeploy. Lakebase also holds the model catalogue and the
encrypted provider keys.

```bash
# a Lakebase project for sessions, the model catalogue and stored keys
databricks postgres create-project coding-agent-llm \
  --json '{"spec":{"display_name":"coding-agent-llm"}}'

# the key that encrypts stored provider keys:
# a Databricks secret, never in the database
databricks secrets create-scope coding-agent-llm
python3 -c "import os,base64
print(base64.urlsafe_b64encode(os.urandom(32)).decode())" \
  | tr -d '\n' \
  | databricks secrets put-secret coding-agent-llm llm-kek
```

The app's service principal then needs a Postgres role on that project; the exact commands are in the
<a href="https://github.com/raphaelmansuy/opengenie/blob/main/specs/005-llm-models/12-operations-runbook.md" target="_blank" rel="noopener noreferrer">operations runbook</a>.

### 3. Deploy, and check it is really your code

```bash
git clone https://github.com/raphaelmansuy/opengenie.git
cd opengenie

# check the toolchain, the login, and which workspace + transport this environment uses
make -C apps/coding-agent doctor ENV=dev

# create the app, its scopes, its secret resources, and its Lakebase role
make -C apps/coding-agent deploy ENV=dev
```

`ENV` names an environment, and every environment's workspace and deployment transport are declared
in `apps/coding-agent/scripts/env.sh`. That indirection is not ceremony: some workspaces let an app
deploy only from Git, and others only from a Workspace folder, so the transport cannot be a flag.
Add your own environment there rather than editing a script.

`make deploy` ends by verifying, because &ldquo;SUCCEEDED&rdquo; from the platform means the process
started, not that it is serving the code you just wrote. It reads the platform's view of the app, and
through an in-workspace job it reads the app's own database — proof that it booted, authenticated as
its service principal, and ran its migrations. With an OAuth login it probes the live URL too. Run
`make -C apps/coding-agent` for the other targets: `status`, `url`, `logs`, `stop`, `start`.

The bundle requests the user scopes the agent needs (SQL, files, model serving, AI Gateway, workspace,
and read access to catalogues, schemas and tables). Requesting a scope is not granting it: grant them
on the app if your workspace does not do so automatically.

<div class="callout callout-warning"><p><strong>On a trial workspace.</strong> App compute and model
endpoints have daily quotas. When one is exhausted the error reads like a configuration problem. If a
deploy fails with a message about a Git repository or a daily limit, check the quota first.</p></div>

## B · Locally, against your workspace

```bash
cd apps/coding-agent
make setup        # venv, Python and npm dependencies

export DATABRICKS_HOST=https://YOUR-WORKSPACE.cloud.databricks.com
databricks auth login --host "$DATABRICKS_HOST"

make dev          # http://127.0.0.1:8062, scripted agent
make dev-real     # http://127.0.0.1:8071, real agent and model
```

Both take a fresh token from your `databricks auth login` session, so the workspace browser shows your
real files. `make dev` replaces the model with a deterministic agent that plays scripted scenarios,
which is how the interface is developed and tested; `make dev-real` runs the real `opencode` agent
against a real model. Before you deploy, run `make
check` (types and unit tests, no network).

<div class="callout callout-important"><p><strong>The token is the boundary.</strong> Locally, the app
acts as whoever owns the token. The fence limits <em>what the agent asks for</em>; the token limits what
it <em>may do</em>. Point it at a workspace where your rights are what you would give an agent.</p></div>

## C · From a notebook only

This is the path in <a href="/tutorial/">the tutorial</a>, and it needs no local shell. Import one
notebook, run its cells in order, and you have an agent that runs real SQL and a fence you can test by
trying to break it. One person, one session, no interface beyond the notebook.

## What none of the paths can do

| Not possible | Why |
|---|---|
| Run Python as you | Apps user authorisation has no compute scope. Python cells run on serverless as the app's service principal, only when an administrator starts them, and every result says where it ran. |
| Pick a cluster | The app runs SQL on a warehouse. A cluster picker for a choice it cannot honour would be a lie. |
| Schedule, comment or share | Those are workspace features. The app opens the same files, so do it in Databricks. |
| Inline completion | It needs a low-latency path the agent protocol does not have. |
| See what you cannot | The app acts as you. Its permissions are your permissions. |

## After it runs

<p>Test the fence first: ask the agent to write outside the folder you named, and read the
refusal. Then read <a href="../reference/doc-safety/">safety and governance</a> for what the fence does
not cover, and <a href="../reference/doc-decide/">the decision guide</a> if you are deciding whether to
roll it out.</p>

## Uninstalling

```bash
databricks bundle destroy -t dev
```

The agent's working folders and any table it created stay where they are. They are your data, in your
workspace, and a tool that deletes them on uninstall is a tool you cannot trust with them.
