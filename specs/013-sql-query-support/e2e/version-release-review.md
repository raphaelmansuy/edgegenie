# SQL Query support dev release candidate

Version: `1.2.0-rc.1`; planned tag: `v1.2.0-rc.1`.

- Source: `8e9e520fb0a0a244a758f13daab96c08517161f5` on `codex/sql-query-support-dev-20261112`.
- User explicitly requested a version cut and authorized necessary tested dev app fixes for this public branch.
- [Version patch](version-release.patch), SHA-256: `be355297f9e487a56d227e16a19028fa8e83bdaa3b01721fefc1b6006110b37e`.
- Five app files: `VERSION`, `pyproject.toml`, `tests/test_version.py`, `web/package.json`, and root metadata in `web/package-lock.json`. No dependency versions change.
- Includes preceding two-file [wording fix](dev-wording-fix-review.md), commit `dff5e22`.
- This is a prerelease: native create/run/update and restart durability remain unqualified in dev. It must not replace the stable release designation.
- Publish the annotated tag and GitHub prerelease only after live version/API/UI checks and individual screenshot review. Reports: [deployment](deployment.json), [live smoke](deployed-report.json), [local E2E](report.json).

## Recorded outcome

The publication approval and deployment steps above are historical. The user approved publication and necessary tested dev fixes, then requested a version cut. Final [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) (`8e9e520`) is published and running in dev; 10 live checks pass and all four final live images were individually inspected. See [deployment record](deployment.json) and [visual ledger](visual-inspection.md).
