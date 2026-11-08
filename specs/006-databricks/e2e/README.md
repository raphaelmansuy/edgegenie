# e2e evidence

Generated, never hand-placed. Two directories:

| Directory | What it holds |
|---|---|
| [`before/`](before/) | the deployed app **before** spec 006: `audit.json` plus one screenshot per width, and a `-doc.png` per width showing the state with a document open |
| `after/` | the same measurement **after** the implementation, plus the thirteen named screenshots in [12 §screenshots](../12-e2e-plan.md#screenshots-that-must-exist) |

## How `before/` was produced

```bash
cd apps/coding-agent/web
export DATABRICKS_HOST=https://dbc-1e111e44-3334.cloud.databricks.com
databricks auth token --host "$DATABRICKS_HOST" -o json \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])' > /tmp/bearer.txt
APP_URL=https://coding-agent-7474654624275247.aws.databricksapps.com \
BEARER_FILE=/tmp/bearer.txt \
WIDTHS=1600,1180,1024,760 \
  node scripts/dock-audit.mjs ../../../specs/006-databricks/e2e/before
```

## What `before/audit.json` proves

The one number that matters, at every width, with a real file open:

```text
transcriptVisibleWithDocOpen   false  false  false  false
turnsRenderedWithDocOpen       0      0      0      0
```

and the model control, hidden by CSS below 1100 px:

```text
modelChipVisible   760: false   1024: false   1180: true   1600: true
```

Full reading in [01 §the five numbers](../01-current-state-audit.md#the-five-numbers).

## Two caveats, recorded because the first run of this script was wrong

1. The first version opened a **folder**, not a file, so `chromePx` was `null` and the transcript was
   still on screen. The fix walks the tree to a leaf; the lesson is in the script's comment.
2. A measurement needs a session, so the script sends one trivial prompt first. A slow agent makes the
   audit slow rather than making it fail — which is why every run is checked against a screenshot.

## The bearer token is not committed

`/tmp/bearer.txt` holds a live workspace token. It is written outside the repository, used by the
script, and never copied here. The `audit.json` contains no token and no user email beyond the
`user` field the app itself reports in `/api/me`.
