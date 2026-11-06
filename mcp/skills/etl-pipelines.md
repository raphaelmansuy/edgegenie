# ETL pipelines as Databricks Jobs (bronze -> silver -> gold)

## Shape
- One notebook per stage under the allowed workspace folder, created with `dbx_write_notebook`.
- Orchestrate with `dbx_create_job(name, tasks=[{"task_key":"silver","notebook_path":...},
  {"task_key":"gold","notebook_path":...,"depends_on":["silver"]}])`, then
  `dbx_run_job(job_id, wait_seconds=300)`. Read the per-task `error` if it fails, fix, run again.

## Rules that decide correctness
- **Idempotent**: write with `CREATE OR REPLACE TABLE ... AS SELECT` (or `INSERT OVERWRITE`).
  A plain `INSERT INTO` doubles the data on a re-run. Run the job twice and compare counts.
- **Order of steps matters**: if the task says "keep the latest row per key, THEN validate",
  deduplicate with `row_number() OVER (PARTITION BY key ORDER BY ingested_at DESC) = 1` first,
  and only then filter invalid rows. Filtering first can resurrect an older bad version.
- **Rejects**: send excluded rows to a rejects table with a reason, using a fixed priority
  when more than one reason applies.
- **Parse defensively**: serverless has ANSI mode on. `CAST('N/A' AS TIMESTAMP)` raises.
  Use `try_to_timestamp(col)`, `try_cast(col AS ...)`, `try_divide(a, b)`.
- Fully qualify every table: `catalog.schema.table`.

## Verify (quote the numbers)
- Row counts of every output table; `silver + rejects = distinct keys of the input`.
- Spot-check one corrected key (the later version won) and one rejected row.
- Compare a gold aggregate to the same aggregate computed directly from silver.
