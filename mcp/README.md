# Where the tool server lives now

The Databricks MCP tool server — and the four skills it loads — live in **one** place:

```
apps/coding-agent/tools/databricks_notebook_mcp.py
apps/coding-agent/tools/skills/*.md
```

This folder used to hold a second copy. The two had drifted (987 lines here, 1104 there, with the
app's copy carrying the per-request token read, the 401/403 hook and the run bridge), and the deployed
app resolves `tools/` first — so a fix made here reached nobody. Spec
[013](../specs/013-improve-coding/README.md) found that ([F8]/[F9]) and removed the copy rather than
keeping two files in step by hand.

`tests/test_packaging.py::test_exactly_one_tool_server_exists` now fails if a second copy appears, and
`test_exactly_one_copy_of_each_skill` does the same for the skills.
