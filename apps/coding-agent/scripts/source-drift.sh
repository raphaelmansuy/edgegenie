#!/usr/bin/env bash
# Is the Workspace source the app builds from actually your checkout? Exits non-zero when it drifts.
#
#   scripts/source-drift.sh [workspace-path]
#
# Why this exists. An earlier version of `make doctor` checked that three files EXISTED in the Workspace
# and reported "Ready" — while the fix I had just written was not in it. Existence is not currency.
# This compares CONTENT: every tracked file is fetched and compared byte for byte, so a one-line change
# is caught. That is the difference between "the file is present" and "the code is deployed".
#
# It goes through the REST API directly rather than `databricks workspace export` per file: 377 CLI calls
# took six minutes and needed a token the CLI does not pick up from an OAuth session ("Invalid Token").
# One session of HTTP calls is seconds, and it reports the same facts.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$APP_DIR/../.." && pwd)"
: "${DATABRICKS_HOST:?set DATABRICKS_HOST}"
export DATABRICKS_HOST
DEST="${1:-/Workspace/Users/raphael.mansuy@gmail.com/coding-agent}"

cd "$REPO"
export REPO APP_DIR DEST
export DATABRICKS_TOKEN="${DATABRICKS_TOKEN:-$(databricks auth token --host "$DATABRICKS_HOST" -o json \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')}"

python3 - <<'PY'
import base64, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

host = os.environ["DATABRICKS_HOST"].rstrip("/")
token = os.environ["DATABRICKS_TOKEN"]
dest = os.environ["DEST"]
repo = os.environ["REPO"]

# The same unit `sync` ships, so the two cannot disagree about which files matter.
files = subprocess.run(["git", "ls-files", "apps/coding-agent"], cwd=repo,
                       capture_output=True, text=True).stdout.split()
files = [f for f in files if not any(f.endswith(e) for e in (".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2", ".ttf"))]

def get(path: str) -> tuple[bytes | None, str]:
    """(content, why-not) — the reason matters: a 404 means "not synced", a timeout means "ask again"."""
    url = f"{host}/api/2.0/workspace/export?path={urllib.parse.quote(path)}&format=AUTO"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read())
            content = body.get("content")
            if content is None:
                return None, "no content in the response"
            return base64.b64decode(content), ""
    except urllib.error.HTTPError as e:
        # 429/403 here is the workspace's rate limiter, not a missing file. Retry with a backoff before
        # reporting: a probe that confuses "slow down" with "not deployed" is worse than no probe.
        if e.code in (403, 429, 503):
            for wait in (0.6, 1.5, 3.0):
                time.sleep(wait)
                try:
                    with urllib.request.urlopen(req, timeout=90) as r:
                        content = json.loads(r.read()).get("content")
                        return (base64.b64decode(content), "") if content is not None else (None, "no content")
                except Exception:
                    continue
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:60]}"

from concurrent.futures import ThreadPoolExecutor

def check(f: str):
    rel = f[len("apps/coding-agent/"):]
    remote, why = get(f"{dest}/{rel}")
    if remote is None:
        return ("MISSING", rel, why)
    with open(os.path.join(repo, f), "rb") as fh:
        return ("same" if fh.read() == remote else "DIFFERS", rel, "")

same = differ = missing = 0
drift: list[str] = []
# 16 at a time: one request per file over a wide pipe, but enough concurrency that 377 files take seconds
# rather than the six minutes a sequential loop took.
with ThreadPoolExecutor(max_workers=4) as pool:
    for verdict, rel, why in pool.map(check, files):
        if verdict == "same":
            same += 1
        elif verdict == "MISSING":
            missing += 1
            if len(drift) < 10: drift.append(f"MISSING  {rel}  ({why})")
        else:
            differ += 1
            if len(drift) < 10: drift.append(f"DIFFERS  {rel}")

print(f"  {same} identical, {differ} differ, {missing} not exported")
if differ or missing:
    for d in drift: print(f"  \033[33m{d}\033[0m")
    print("\n  \033[33mThe Workspace is behind this checkout.\033[0m The next deploy would ship the OLD files.")
    print("  Run: make sync\n")
    sys.exit(1)
print("  \033[32mthe Workspace source matches this checkout\033[0m")
PY
