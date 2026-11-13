"""Legacy tool vocabulary shared by registration and reported counts. Removed with the facade migration."""
CORE_TOOLS = frozenset( {
    "dbx_whoami", "dbx_list_tables", "dbx_describe_table", "dbx_search_tables", "dbx_run_sql",
    "dbx_list_notebooks", "dbx_read_notebook", "dbx_grep_notebook", "dbx_write_notebook",
    "dbx_write_file", "dbx_run_notebook", "dbx_run_notebook_status", "dbx_create_job", "dbx_run_job", "dbx_job_run_status",
    "dbx_lakebase_create", "dbx_lakebase_status", "dbx_lakebase_sql", "dbx_create_app", "dbx_skill",
})
