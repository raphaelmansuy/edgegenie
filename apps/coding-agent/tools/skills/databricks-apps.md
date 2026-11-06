# Databricks Apps: app.yaml format, port, database access, deployment

## app.yaml (the manifest) - exact format
`command` is a TOP-LEVEL list. `env` is a top-level LIST of objects with `name` and
`value` (or `valueFrom` to reference a resource or secret). Nothing is nested under
`entry:` or `environment:` - those keys do not exist.

```yaml
command: ["python", "app.py"]
env:
  - name: PGDATABASE
    value: "databricks_postgres"
  - name: PGHOST
    valueFrom: "database"      # a database resource attached to the app
  - name: PGPORT
    value: "5432"
```

## Runtime contract
- Listen on `0.0.0.0` at the port in env `DATABRICKS_APP_PORT` (default 8000 locally).
  Typical FastAPI entry: `uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))`.
- `requirements.txt` lists pip packages (fastapi, uvicorn, psycopg2-binary, databricks-sdk, pydantic).
- Never put tokens or passwords in any file. Read PGPASSWORD from the environment, or
  generate a short-lived Lakebase credential with the SDK (see skill `lakebase-postgres`).

## Files
Use `dbx_write_file` for app.py, app.yaml, requirements.txt (plain workspace files, not notebooks).

## Deployment
Some workspaces refuse to create Apps unless the app is backed by a Git repository.
`dbx_create_app` returns the platform's answer verbatim, including refusals. If it
refuses, quote the exact `platform_error` in your report and say the app was NOT
deployed. Never claim a deployment, URL or "running" status you did not observe.
