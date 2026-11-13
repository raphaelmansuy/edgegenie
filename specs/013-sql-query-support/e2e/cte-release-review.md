# CTE execution correction release review

Version: 1.2.0-rc.4. Exact app commit: `717c6216f51b951b21aa9cff34dd434cfd4b245e`. Seven app code/test/version files only. Publication and necessary tested dev app fixes are already authorized in this conversation. No credentials, documents, screenshots or unrelated changes are included.

The parser already recognizes the CTE. The correction distinguishes structural Boolean nodes from functions and uses one reviewed AST/source-spelling registry for Databricks built-ins. Existing mutation/UDF/script gates remain in force. EdgeSQL was assessed from its official source; a parser upgrade is not required for this policy bug.

Exact payload: [patch](cte-release.patch). SHA-256: `66e181d543160cd870ef0875b938d14f46ae45c2ba9c62d7b73f9e95a08866d9`. Added-line credential-pattern scan: no matches.

- `apps/coding-agent/VERSION`
- `apps/coding-agent/api/domain/sqlpolicy.py`
- `apps/coding-agent/pyproject.toml`
- `apps/coding-agent/tests/test_sqlpolicy_databricks.py`
- `apps/coding-agent/tests/test_version.py`
- `apps/coding-agent/web/package-lock.json`
- `apps/coding-agent/web/package.json`

Pre-deployment validation: 2,061 backend tests passed (4 skipped, 7 warnings), including 67 new policy cases; 1,233 frontend tests passed; production build and 16 local SQL browser checks passed. The initial test-server socket mismatch was corrected; an unchanged intermittent notebook stdout-capture test passed in isolation and in the final full suite.

Final validation and actual native/AI CTE results are recorded in [CTE report](cte-report.json) and [deployment](deployment.json).
