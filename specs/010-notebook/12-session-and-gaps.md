# 12. Session and gaps

[Index](README.md) · before [11](11-outcome.md)

This note says what was built to close the gaps with Databricks notebooks, what was measured on real
compute, and what is still not true.

## What was built

| Gap | What exists now |
|---|---|
| Variables did not survive between cells | A Python session: one serverless job that stays up. The app and the job talk through files in a Unity Catalog volume |
| `%pip`, `%sh`, `%md`, `%run` | The session runs them. `%run` is read and expanded by the app with the signed-in user's token. The job never fetches code |
| Nested values showed as raw JSON | Array, map and struct values are drawn with typed leaves. Long values expand and copy |
| No chart | A chart view of a result table: bar, line, area, scatter, pie. It is SVG, drawn from the rows, and the choice is saved with the result |
| No widgets | `dbutils.widgets` (text, dropdown, combobox, multiselect), a widget bar, and SQL named parameters (`:name`) |

The rules that did not change: Python runs as the app's service principal, for administrators only,
and the app never runs code that it fetched with its own authority.

## The session protocol

Files under `<volume>/<session>/`:

- `cmd/NNNNNN.json`: a command from the app.
- `out/NNNNNN.json`: progress (`final: false`), then the result (`final: true`).
- `hb.json`: a heartbeat counter. The reader judges it with its own clock.
- `ctl/lease.json`, `ctl/interrupt`, `ctl/stop`: the app asks to keep, stop one cell, or end the session.

Limits: 2 sessions for each user, 3 in all. A heartbeat that is 45 s old means the session is gone.
A session that has not started after 300 s is cancelled. A session lives 4 h at most. The app waits
10 s after an interrupt, then cancels the job and says the variables are gone.

## What was measured on `opengenie-dev`

| Measure | Value |
|---|---|
| First result, including compute start | 28 s |
| A warm cell | 1.1 to 1.2 s |
| Stop on a Python loop | 1.2 to 3.7 s |
| Stop on `%sh sleep 120` | 1.5 s, and the variables stay |
| Files API call | 0.3 to 0.6 s |
| Python on serverless | 3.11.10 |

The live check is `tools/kernel_live_check.py`. All checks passed. It covers: session start, a
variable that survives, progress while a cell runs, Stop on a loop, `%sh` (both streams, exit status),
a real `%pip install`, `%md`, widgets, `dbutils.fs` next to the widget shim, a nested Spark table,
`%run`, Stop on `%sh`, Stop of the job, Restart, and "no run is left going".

## A fault that only real compute showed

Stop on a long `%sh` command did not work on serverless. It passed in the local tests.

- The app asks to stop a cell by writing `ctl/interrupt`. The job reads the file and deletes it.
- On a volume a deleted file can be read again a moment later. The job sent the interrupt twice.
- The second interrupt arrived in the clean-up of the first. The clean-up never killed the program.
  The job then waited for `sleep 120` and the app ended the session after 10 s.

Two changes fixed it. The job sends one interrupt for each cell. The clean-up of a program (kill,
wait, join) cannot be skipped by a later interrupt. The local test for a repeated request passes
without the fix as well, because a local file is deleted at once. The live check is the test that
shows this fault.

## What the app's service principal needs

- `scripts/provision-session-volume.sh` creates the volume and grants the rest. It runs as step 6 of
  `make deploy`. The grants are USE_CATALOG on the catalog, USE_SCHEMA on the schema, and
  READ_VOLUME + WRITE_VOLUME on `/Volumes/workspace/agent_scratch/kernel_sessions`
  (`APP_SESSION_VOLUME`).
- `APP_PYTHON_SESSION=auto` (the default). `off` keeps one-shot runs only.
- The other limits: `APP_SESSION_IDLE_SECONDS`, `APP_SESSION_MAX_PER_USER`, `APP_SESSION_MAX_TOTAL`.

The app writes a session's files with the Files API, but it cannot create the volume and cannot
grant itself anything. So the volume is a deploy step, and `verify-deployed.sh` checks the grant: a
missing volume is a session that never starts, which the app reports in words and falls back from.

A 403 "resolving file endpoints" warning from the SDK is harmless: it uses the default endpoints.

## Not done, and not true

- Python does not run as the signed-in user. Scala and R are not supported.
- A widget change does not re-run cells. The widget bar says so.
- `%run` takes no arguments. It stops at 3 levels, 200 cells, or 500 KB, and it refuses a cycle.
- A package installed with `%pip` is not loaded again in a session that already imported it. Restart
  the session.
- Not yet checked after deploy: the HTML output frame under the platform content security policy.
  `make deploy ENV=dev` has not been run.
