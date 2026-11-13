# Dev SQL capability wording correction

Visual inspection of the live transport-fix deployment found that the native workspace called non-durable history “demo history.” Replace it with “Temporary drafts and history.” Replace internal persistence/parser/interoperability wording in capability messages with user-facing availability and temporary-draft disclosures. Capability flags and behavior remain unchanged.

- Publication authorized by the user's approval of `0f63b19` and further necessary tested dev fixes on the same public branch.
- Two app files, 4 lines changed: `api/services/sql_service.py`, `web/src/components/QueryEditor.tsx`.
- [Exact patch](dev-wording-fix.patch), SHA-256: `7b1a1459f48c1e1071feeb478c598f9e075bc4b96dd3b4e1c4d2a264a5b3cf6e`.
- SQL suite: 53 passed. Frontend: 1,231 passed in 83 files. Production build passed. Final local and deployed E2E results are recorded in [deployment evidence](deployment.json).
- No credentials, documents, screenshots or unrelated changes are in the app commit. This review document stays local.

## Recorded outcome

The publication approval and deployment steps above are historical. The user approved publication and necessary tested dev fixes, then requested a version cut. Final [v1.2.0-rc.1](https://github.com/raphaelmansuy/opengenie/releases/tag/v1.2.0-rc.1) (`8e9e520`) is published and running in dev; 10 live checks pass and all four final live images were individually inspected. See [deployment record](deployment.json) and [visual ledger](visual-inspection.md).
