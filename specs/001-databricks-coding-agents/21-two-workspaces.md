[Index](README.md) · prev: [17 Deployment](17-deployment.md) · [E2E](e2e/README.md)

# 21 · Two workspaces, two transports

Deployed 10 November 2026 to `dbc-cb61f1e1-bd8e.cloud.databricks.com`, the development workspace,
**without touching the live deployment** on `dbc-1e111e44-3334.cloud.databricks.com`.

## The one thing that could not be a flag

The two workspaces disagree about how an app gets its source, and neither accepts the other's answer:

| | live (`dbc-1e111e44`) | dev (`dbc-cb61f1e1`) |
|---|---|---|
| `apps create` without `git_repository` | accepted | **refused** — *"Git repository is required for Databricks Apps in this workspace"* |
| `apps deploy --source-code-path <Workspace folder>` | accepted | **refused** — *"Apps in this workspace can only be deployed from Git"* |

So the transport is a property of the workspace. Before this change the repository had exactly one
answer — a Workspace folder, synced by `scripts/sync-app-source.sh` — hard-coded in the Makefile, the
deploy script and the docs. A second workspace made that answer wrong half the time, and a wrong
answer here does not fail loudly: it deploys a stale snapshot and reports `SUCCEEDED`.

The fix is one file that says where each environment is and how its source arrives
([`scripts/env.sh`](../../apps/coding-agent/scripts/env.sh)), and scripts that read it. Nothing else
in the repository decides either fact.

## What was provisioned, in the order it had to happen

| Step | Why it is not optional | Evidence it worked |
|---|---|---|
| **Lakebase project** `coding-agent-llm` | the app refuses to boot in production without a durable journal, and holds its model catalogue here | `projects/coding-agent-llm/branches/production/endpoints/primary` exists |
| **Secret scope** `coding-agent-llm` | two app resources are `valueFrom` that scope | `llm-kek`, `vertex-sa` |
| **Postgres role for the app's SP** | the app connects as *itself*, not as the deployer | role `coding-agent-sp` → `ad7545de-…` |
| **`GRANT CONNECT, CREATE` on the database** | the app creates its own `llm` and `agent` schemas at boot | both schemas exist, owned by the app's SP |
| **App with a git source** | the workspace refuses anything else | deployment built from commit `824158d` |
| **Scopes + secret resources** | `apps update` is a full replacement; omitting them clears them | 9 scopes effective, 2 resources attached |

### The grant could not run from a laptop

The first deploy reported `SUCCEEDED` and the app then **crashed at boot**. The cause was the missing
`CONNECT`/`CREATE` privilege — but the reason it took a while to prove is worth recording:

```
$ nc -zv endpoint:5432            → open
$ psql ... connect_timeout=45     → timeout expired (all three ingress IPs)
```

Port 5432 is open to the internet and the endpoint is not routable from outside. The endpoint resolves
through `us-east-2.service-direct.privatelink.cloud.databricks.com`. In-workspace serverless compute
reaches it; a laptop does not.

So the grants run as a **notebook on in-workspace compute**
([`scripts/lakebase_grants.notebook`](../../apps/coding-agent/scripts/lakebase_grants.notebook)), and
`provision-lakebase.sh` decides which path to use by trying the direct one first. A tool that assumes
it can reach the database is a tool that fails on the first workspace that says no.

## Verification that does not depend on the browser

The app sits behind the Databricks OAuth proxy, which **refuses a personal access token**:

```
$ curl -H "Authorization: Bearer $PAT" $APP_URL/api/health
HTTP/2 401
server: databricks          ← the proxy, not the app
content-length: 2           ← "{}"
```

That is a real limitation of a CI deploy, and the honest response is not to call the deployment
verified. Two things replace the HTTP probe:

1. **`verify-deployed.sh`** reads the platform's own view — deployment `SUCCEEDED`, app `RUNNING`, all
   9 scopes effective, both secret resources attached — and **skips** the HTTP checks with a stated
   reason rather than silently passing them.
2. **`app_health_probe.notebook`** reads the app's own database, which proves more than `/health`
   would: the app booted, authenticated to Lakebase *as its service principal*, and ran its
   migrations.

```
PASS the app ran its migrations — llm schema version 4
PASS the model catalogue is seeded — 13 enabled models, 4 providers
PASS the session journal is live — 2 snapshot(s)
PASS the app owns its schemas — llm owner ad7545de-066b-4768-971e-93a305e02608
```

With an OAuth login the HTTP probes also run. `make verify ENV=dev` says which of the two it managed.

## What the deployment serves

| Check | Result |
|---|---|
| Deployment | `SUCCEEDED`, built from commit `824158dd9d54c8ff04cacfe40a4788ecf2b3b65d`, branch `main` |
| App | `RUNNING` |
| Scopes | 9/9 effective |
| Secret resources | `vertex-sa`, `llm-kek` attached |
| Lakebase | `llm` at schema version 4, `agent` journal live, both owned by the app's SP |
| Catalogue | 13 models over 4 providers, including `gemini-3.8-flash`, `gemini-3.8-pro`, `gemini-3.5-flash` |
| Gemini 3.8 Flash reachable | **yes** — a direct token exchange with the `mobioos-506015` service account returned `200` and the completion `ready` |

## Two traps, both measured

1. **A bundle target's `workspace.host` overrides `DATABRICKS_HOST`, silently.** With a literal host in
   the target and `DATABRICKS_HOST=https://invalid.example.com`, `databricks apps list` still answered
   from the target's workspace. An operator who exported the wrong host would deploy to the right one
   and never learn it. The host is now declared only in `scripts/env.sh`, which asserts the identity it
   finds; `test_deployment_envs.py` fails if a host reappears in `databricks.yml` or the Makefile.

2. **A `.py` file with a notebook header becomes a notebook when deployed.** The header that makes a
   file work when *imported into the workspace* also makes the app drop the `.py` and fail the import
   at boot. This took the app down once before, and `test_packaging.py` guards against it. The two new
   deployment notebooks are therefore stored as `.notebook` — the extension keeps them out of
   packaging while the header keeps them importable.

## What is still not verified

| Item | Why |
|---|---|
| The app answering HTTP with a *user's* credentials | needs an OAuth login; a PAT is refused by the proxy. The UI opens after a browser sign-in. |
| A turn running end to end against Gemini in the **deployed** app | the model is reachable (proved directly) and its key is attached, but exercising a full turn needs a signed-in browser session. |
| `databricks apps logs` | the logs API refuses a PAT (`OAuth Token not supported for current auth type pat`). Local reproduction of the boot path was used instead. |

The first two are the same shape: **anything behind the OAuth proxy needs a human sign-in.** That is a
property of the platform, not of this deployment.
