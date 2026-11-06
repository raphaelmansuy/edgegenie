# Authoring and editing notebooks that run and read well

## Write
- `dbx_write_notebook(path, cells=[{"type":"markdown","source":"..."}, {"type":"code","source":"..."}])`.
  Pass `cells` as a real list. The reply shows `markdown_cells` / `code_cells`: check them.
- Structure for an analyst: title cell (question + data source) -> for each analysis a
  short markdown cell then a code cell -> a final "Findings" markdown cell quoting numbers.
- Charts: `display(df)` renders a table that can be switched to a chart; or matplotlib.
- If the task needs a return value, the LAST cell calls `dbutils.notebook.exit(json.dumps({...}))`
  with values computed in code, never typed in.

## Run and verify
- `dbx_run_notebook(path)` runs it on serverless and returns `exit_value` or the `error`.
  A success with no `exit_value` means `dbutils.notebook.exit` was never reached.
- Fix the cause of any error and run again. Do not report until a run succeeded.

## Edit an existing notebook
- `dbx_read_notebook` (page through `next_offset`), change the smallest thing, write it back
  with the same cell layout and every line the user said to keep. Then run it.
- A notebook can run without error and still be wrong: compare its result with an
  independent SQL query before you say it is fixed.

## Serverless gotchas
- No `spark.sparkContext`, RDDs, `.cache()`, `.persist()`.
- ANSI mode is on: bad strings fail the run. Use `try_cast`, `try_to_timestamp`, `try_divide`.
- `F.sum("col")` on a column that does not exist is an AnalysisException: describe tables first.
- `DataFrame.first()` without `orderBy` returns an arbitrary row.
