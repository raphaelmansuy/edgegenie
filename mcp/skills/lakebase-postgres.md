# Lakebase (managed Postgres): create, connect, query

## Flow with the tools
1. `dbx_lakebase_create(name, capacity="CU_1")`: creates the instance and waits for `AVAILABLE`.
   Idempotent. Name must start with the allowed prefix.
2. `dbx_lakebase_sql(instance, sql)`: runs SQL (several statements allowed) with a fresh
   short-lived credential. Use it to create schemas/tables, insert seed rows, and to verify.
3. Verify with a SELECT (row count, a sample) and quote the result in your report.

## Facts
- Default database is `databricks_postgres`. The Postgres user is your Databricks identity
  (your email). The password is a short-lived token, never a stored secret.
- TLS is required: `sslmode=require`. Port 5432.
- Create objects explicitly: `CREATE SCHEMA IF NOT EXISTS app;` then
  `CREATE TABLE IF NOT EXISTS app.tasks (...)`. `SERIAL` / `TIMESTAMPTZ DEFAULT now()` work.

## Credentials from code (for an app or script)
```python
import uuid
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
token = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()), instance_names=["<instance>"]).token
conn = psycopg2.connect(host=host, port=5432, dbname="databricks_postgres",
                        user=w.current_user.me().user_name, password=token, sslmode="require")
```

## Application SQL
Use parameterised queries only: `cur.execute("INSERT ... VALUES (%s)", (value,))`.
Never build SQL with f-strings from request data.
