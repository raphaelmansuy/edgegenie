# ETL jobs and pipelines at the identity's available tier

Start with dbx_capabilities. Describe every source/output table before SQL. State the grain before
aggregating. Use fully qualified names and defensive casts; do not guess column names.

## Definitions and changes
Create notebook stages inside the folder with dbx_create. Edit existing stages through cell operations
with base revision and cell SHAs. Read a job/pipeline definition before dbx_define and carry its base.
Jobs use native notebook_task, sql_task or pipeline_task definitions and explicit dependencies.

Without Jobs/Pipelines user scopes, define a complete Databricks Asset Bundle inside the folder at
<project>/databricks.yml. Include bundle.name and resources.jobs or resources.pipelines. Report
"defined, not deployed" and provide databricks bundle validate followed by databricks bundle deploy.
A definition file is a file resource; it is not a deployed job or pipeline.

## Runs
Use dbx_run then dbx_operation with its returned operation ID. Tools return in at most 30 seconds;
poll rather than extending a wait. Pending/unknown submissions are never submitted again. Pipeline
validate_only checks source without materialization. Full refresh always requires a person.
Repair only task keys observed as failed, preserving successful tasks. Run as the signed-in user.

## Verify
Make writes idempotent within the writable schema. Establish the correct deduplication/validation
order, and account for rejected rows. Observe the completed native operation and its per-task output.
Read each changed asset back. Compare output counts and aggregates with independent supported SQL.
System-table observations can lag; state their source and refresh time. A permission refusal is final.
Quote real values and exact invocationIds. Do not report a planned or refused run as successful.
