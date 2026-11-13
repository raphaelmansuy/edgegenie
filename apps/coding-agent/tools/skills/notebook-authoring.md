# Author and edit notebooks with revision-bound cell operations

Read dbx_capabilities first. The advertised tools and identity tiers are authoritative.

## Focused edits
1. Read dbx_read(kind="notebook", id=path), following every next_offset needed for the task.
2. Keep its revision and the affected cell SHA. Use dbx_edit with base and ops; supported operations
   are replace_cell, insert_cell, delete_cell and move_cell. Cell indices are zero based.
3. In Review, end the turn while awaiting_review. Nothing is written until the user chooses.
4. A conflict requires a fresh read and a new proposal. Never rewrite unrelated cells or make a copy
   to bypass a stale base. A rejected change is final.
5. After apply, read back the produced revision. If execution was requested, submit dbx_run and
   poll dbx_operation using the returned operation ID. Never repeat an unknown submission.

New notebooks use dbx_create with SOURCE text inside the working folder. Include the Databricks SOURCE
header and command separators. Write a question/title, explain assumptions in markdown, and finish
with findings grounded in observed results. Never claim that defining a notebook executed it.

## Serverless correctness
Describe every referenced table and copy its real columns. Avoid RDDs and sparkContext. Use defensive
casts with ANSI mode. Order rows before selecting a first value. For a returned notebook value, use
actual computed values in dbutils.notebook.exit(json.dumps(...)). Quote results only from a successful
operation observation and cite that observation's invocationId in Evidence.

If Jobs scope is unavailable, notebook execution is unavailable. Read-back can verify source, but
cannot prove execution. No code may run as the app service principal.
