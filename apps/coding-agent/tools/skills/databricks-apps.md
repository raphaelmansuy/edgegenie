# Databricks Apps: reviewed source, deployment and observed status

Use dbx_capabilities. Create source files with dbx_create(kind="file") and change existing files with
base revision and replace_range operations. Keep all source inside the working folder.

app.yaml has a top-level command array and an env array of name/value objects:

```yaml
command: ["python", "app.py"]
env:
  - name: EXAMPLE_SETTING
    value: "example"
```

Listen on 0.0.0.0 and DATABRICKS_APP_PORT (8000 for local development). Declare runtime packages in
requirements.txt. Never place tokens, passwords or service principal credentials in source.

Use dbx_define(kind="app") with the session's app name prefix. Agent-created apps cannot attach
secrets or database resources. A new app's creation and its deployment are distinct facts.
Deploy through dbx_run with source_code_path inside the folder. Deployment always needs a person,
including Auto mode. Poll its operation ID with dbx_operation; quote its observed status and URL.
A platform refusal is final. Say that the app was not deployed; do not invent a running URL.

Stop through a reviewed run action, and delete only a session-created resource through Resources
cleanup. Existing apps that can read app secrets/databases cannot receive model-written code.
