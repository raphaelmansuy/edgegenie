"""Shared helpers for the Genie-Code-replacement exam suite.

Everything here runs on the *grader's* machine with the PAT in ../.env. The
agent under test never sees the grader: it gets a prompt and tools, and the
grader inspects live workspace state afterwards. That is the point of an
execution-based exam: we do not trust what the agent *says* it did.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

ROOT = Path(__file__).resolve().parent.parent
HOST = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
USER = "raphael.mansuy@gmail.com"
CATALOG = "workspace"


def _token() -> str:
    if os.environ.get("EXAM_DATABRICKS_TOKEN"):
        return os.environ["EXAM_DATABRICKS_TOKEN"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("TOKEN missing in .env")


TOKEN = _token()
_S = requests.Session()
_S.headers["Authorization"] = f"Bearer {TOKEN}"
_AUTH = None


# --------------------------------------------------------------------------
# REST
# --------------------------------------------------------------------------
def api(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    ok_404: bool = False,
) -> Any:
    global _AUTH
    if os.environ.get("EXAM_DATABRICKS_PROFILE"):
        # Explicit opt-in for long local qualifications. SDK unified auth refreshes the same user
        # credential before a request; it never retries an uncertain mutation or bypasses a 403.
        if _AUTH is None:
            from databricks.sdk.core import Config

            _AUTH = Config(profile=os.environ["EXAM_DATABRICKS_PROFILE"], host=HOST)
            if _AUTH.host.rstrip("/") != HOST:
                raise RuntimeError("Grader credential workspace mismatch")
        _S.headers.update(_AUTH.authenticate())
    query = {
        key: str(value).lower() if isinstance(value, bool) else value
        for key, value in (params or {}).items()
    }
    r = _S.request(method, HOST + path, json=body, params=query, timeout=120)
    if r.status_code == 404 and ok_404:
        return None
    if not r.ok:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def verify_identity() -> dict:
    """Read-only qualification before a grader may seed any isolated workspace fixture."""
    identity = api("GET", "/api/2.0/preview/scim/v2/Me")
    if identity.get("userName") != USER:
        raise RuntimeError(
            "Grader identity does not match the configured workspace user. No fixture was seeded."
        )
    return identity


_WH: list[str] = []


def warehouse() -> str:
    if not _WH:
        whs = api("GET", "/api/2.0/sql/warehouses")["warehouses"]
        _WH.append(whs[0]["id"])
    return _WH[0]


def sql(statement: str, timeout: int = 180) -> list[list[Any]]:
    """Run SQL synchronously and return rows (list of lists of strings)."""
    d = api(
        "POST",
        "/api/2.0/sql/statements",
        {
            "warehouse_id": warehouse(),
            "statement": statement,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        },
    )
    t0 = time.time()
    while d["status"]["state"] in ("PENDING", "RUNNING") and time.time() - t0 < timeout:
        time.sleep(2)
        d = api("GET", f"/api/2.0/sql/statements/{d['statement_id']}")
    if d["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"SQL failed: {d['status']} :: {statement[:200]}")
    return (d.get("result") or {}).get("data_array") or []


def sql_val(statement: str) -> Any:
    rows = sql(statement)
    return rows[0][0] if rows else None


def table_exists(full: str) -> bool:
    return api("GET", f"/api/2.1/unity-catalog/tables/{full}", ok_404=True) is not None


# --------------------------------------------------------------------------
# workspace / notebooks / runs
# --------------------------------------------------------------------------
def mkdirs(path: str) -> None:
    api("POST", "/api/2.0/workspace/mkdirs", {"path": path})


def import_nb(path: str, source: str) -> None:
    api(
        "POST",
        "/api/2.0/workspace/import",
        {
            "path": path,
            "format": "SOURCE",
            "language": "PYTHON",
            "overwrite": True,
            "content": base64.b64encode(source.encode()).decode(),
        },
    )


def export_nb(path: str) -> str | None:
    d = api(
        "GET",
        "/api/2.0/workspace/export",
        params={"path": path, "format": "SOURCE"},
        ok_404=True,
    )
    return base64.b64decode(d["content"]).decode() if d else None


def delete_path(path: str) -> None:
    api(
        "POST",
        "/api/2.0/workspace/delete",
        {"path": path, "recursive": True},
        ok_404=True,
    )


def run_notebook(path: str, params: dict | None = None, timeout: int = 600) -> dict:
    """Submit a serverless one-off run of a notebook and wait. Returns
    {ok, state, result (dbutils.notebook.exit value), error}."""
    task: dict[str, Any] = {"task_key": "t", "notebook_task": {"notebook_path": path}}
    if params:
        task["notebook_task"]["base_parameters"] = params
    run_id = api(
        "POST",
        "/api/2.1/jobs/runs/submit",
        {"run_name": "exam-grader", "tasks": [task]},
    )["run_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = api("GET", "/api/2.1/jobs/runs/get", params={"run_id": run_id})
        st = d["state"]
        if st["life_cycle_state"] in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            break
        time.sleep(5)
    task_run = d["tasks"][0]["run_id"]
    out = api("GET", "/api/2.1/jobs/runs/get-output", params={"run_id": task_run})
    return {
        "ok": st.get("result_state") == "SUCCESS",
        "state": st.get("result_state") or st["life_cycle_state"],
        "result": (out.get("notebook_output") or {}).get("result"),
        "error": out.get("error"),
        "run_id": run_id,
    }


def find_jobs(name_prefix: str) -> list[dict]:
    jobs = api("GET", "/api/2.1/jobs/list", params={"limit": 100}).get("jobs", [])
    return [
        j for j in jobs if (j["settings"].get("name") or "").startswith(name_prefix)
    ]


def latest_run(job_id: int) -> dict | None:
    runs = api(
        "GET", "/api/2.1/jobs/runs/list", params={"job_id": job_id, "limit": 5}
    ).get("runs", [])
    return runs[0] if runs else None


# --------------------------------------------------------------------------
# exam model
# --------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    weight: int = 1
    detail: str = ""


@dataclass
class Ctx:
    run_id: str  # e.g. "r1a2b3"
    mission: str
    extra: dict = field(default_factory=dict)

    @property
    def schema(self) -> str:  # full catalog.schema the agent may write to
        return f"{CATALOG}.exam_{self.run_id}"

    @property
    def schema_name(self) -> str:
        return f"exam_{self.run_id}"

    @property
    def home(self) -> str:  # workspace folder the agent may write to
        return f"/Users/{USER}/exams/{self.run_id}"


@dataclass
class Mission:
    id: str
    title: str
    capability: str  # Genie Code capability exercised (C-number)
    difficulty: int  # 1..5
    prompt: Callable[[Ctx], str]
    setup: Callable[[Ctx], None]
    grade: Callable[[Ctx, str], list[Check]]
    # Programmatic reference solution: performs the work the agent should do
    # and returns the answer text. Used to validate the grader (must score
    # 100%) -- a grader that cannot pass its own reference is a bug.
    reference: Callable[[Ctx], str] = lambda ctx: ""
    cleanup: Callable[[Ctx], None] = lambda ctx: None
    max_minutes: int = 12
    uses_schema: bool = True


def score(checks: list[Check]) -> tuple[int, int]:
    return sum(c.weight for c in checks if c.passed), sum(c.weight for c in checks)


def has(text: str, *patterns: str, flags: int = re.I) -> bool:
    return all(re.search(p, text, flags) for p in patterns)
