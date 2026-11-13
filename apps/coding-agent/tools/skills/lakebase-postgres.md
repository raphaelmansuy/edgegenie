# Lakebase instances: explicit cost, reviewed creation and readiness

Read dbx_capabilities first. Use dbx_define(kind="instance") with the session instance prefix and an
explicit capacity. Instance creation incurs ongoing cost and always waits for review, including Auto.

Creation returning an instance is not proof that it is ready. Use a durable dbx_run readiness operation
and poll dbx_operation until AVAILABLE, or report the last observed state. Tools return within 30
seconds; never repeat a submission whose outcome is unknown. Do not obtain or print database tokens.

For application code, a separately authorized runtime can obtain a short-lived credential. Use TLS
and parameterized SQL. The agent's own app identity is never a fallback database execution identity.
If the advertised tool catalogue has no database SQL capability, report that limitation explicitly.

Instances created by this session appear in Resources. Review cleanup there. A renamed or changed
instance is refused for automatic cleanup, and archiving alone does not stop its ongoing cost.

For a separately authorized application runtime, configure PGHOST and LAKEBASE_ENDPOINT and use
psycopg with TLS. Operator capacity sizing must account for max − min, not just the maximum.
Standalone full-profile MCP exposes dbx_lakebase_database, dbx_lakebase_role and dbx_lakebase_tables;
these administrative tools are not a fallback permission path when the agent capability is absent.
