"""Jobs and runs, as a page reads them: one call per fact, five facts for a job.

The shape follows 013's `LakebaseBrowser` deliberately — same `DbxHttp`, same error contract, same
per-method call with no aggregation. The one place it aggregates is `job()`, and it exists because a page
needs five independent answers and one slow or denied call must not blank the other four.

**Identity.** Reads use whatever token the router hands in, which for these APIs is the app's service
principal: `jobs` is not a grantable `user_api_scopes` value, so a forwarded user token cannot call the
Jobs API at all (spec 014 [RB-1]). The payload says which identity read it, so a page never implies the
stronger claim (013's precedent in `routers/infra.py`).

**What a run's state is.** `life_cycle_state` and `result_state` are separate fields and only the pair
answers "did it work": a failed run is `TERMINATED` + `FAILED`. `api.domain.jobs.run_word` is the one
place that combination becomes a word, and this module never decides a state word itself.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ...domain import jobs as vocab
from .http import DbxHttp

BASE = "/api/2.2/jobs"

#: A terminal run never changes: its timestamps are frozen when the platform writes them, so it is safe to
#: keep for as long as this process lives. A job's settings DO change, so they get a TTL (spec 014 [07 §2]).
JOB_TTL_SECONDS = 30.0
#: The runs a job page shows. Five, not "all": a page that lists every run of a busy job takes a second to
#: paint and tells the user nothing extra.
RUNS_SHOWN = 5


class _Cache:
    """Per-token, per-key. Keyed by the credential because the token is the permission boundary: one
    identity's result must never answer another's request (013's [E-28]; reused, not re-written).

    A row with no expiry is kept for the life of the process, which is only correct for a fact that can
    never change — a terminal run. Everything else carries a TTL.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[int, str], tuple[float | None, Any]] = {}

    def get(self, token: str | None, key: str):
        hit = self._rows.get((hash(token or ""), key))
        if hit is None:
            return None
        expires, value = hit
        if expires is not None and time.monotonic() > expires:
            return None
        return value

    def put(self, token: str | None, key: str, value: Any, ttl: float | None) -> Any:
        self._rows[(hash(token or ""), key)] = (
            None if ttl is None else time.monotonic() + ttl, value)
        return value

    def invalidate(self, token: str | None, prefix: str = "") -> None:
        mark = hash(token or "")
        for key in [k for k in self._rows if k[0] == mark and k[1].startswith(prefix)]:
            self._rows.pop(key, None)


class JobsBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._cache = _Cache()

    # -- lists -----------------------------------------------------------------------------
    async def jobs(self, token: str | None, limit: int = 25) -> list[dict[str, Any]]:
        """The first page of jobs, without a run state.

        Deliberately no run state: `jobs/list` carries none, and reading it per job would be `n` round
        trips before the rail paints (`[RB-7]`, the systems lens). The schedule IS in the payload, so a
        rail row can say whether a job is paused without another call.
        """
        data = await self._http.get(f"{BASE}/list", token,
                                    {"limit": min(max(limit, 1), 100), "expand_tasks": "false"})
        return [self._job_row(j) for j in data.get("jobs", [])]

    # -- one job ----------------------------------------------------------------------------
    async def job(self, job_ref: object, token: str | None) -> dict[str, Any]:
        """One job, with its independent blocks. Any block may be `{"error": …}` instead of data."""
        identifier = vocab.job_id(job_ref)
        key = f"job:{identifier}"
        if (hit := self._cache.get(token, key)) is not None:
            return hit

        detail = await self._http.get(f"{BASE}/get", token, {"job_id": identifier})
        settings = detail.get("settings") or {}
        tasks = self._tasks(settings.get("tasks"))
        blocks: dict[str, Any] = {
            "job": {
                "job_id": identifier,
                "name": settings.get("name") or "",
                "owner": settings.get("run_as_user_name") or detail.get("creator_user_name") or "",
                "created": detail.get("created_time"),
                "schedule": self._schedule(settings.get("schedule")),
                "tasks": tasks,
                "queueing": bool((settings.get("queue") or {}).get("enabled", True)),
                "timeoutSeconds": settings.get("timeout_seconds") or 0,
                "maxRetries": settings.get("max_retries") or 0,
                "tags": settings.get("tags") or {},
                "performanceTarget": settings.get("performance_target") or "",
            },
            "levels": vocab.task_levels(tasks),
            "graphProblem": vocab.task_graph_problem(tasks),
            "summary": _describe(tasks),
            "identity": "the app's service principal",
        }

        # The run history, in its own gather so a denial is local to its block.
        runs_result = await asyncio.gather(self._runs(identifier, token), return_exceptions=True)
        runs = runs_result[0]
        if isinstance(runs, BaseException):
            blocks["runs"] = {"error": _sentence(runs)}
            blocks["latestRun"] = {"error": _sentence(runs)}
        else:
            blocks["runs"] = runs
            blocks["latestRun"] = (await self._run_detail(runs[0]["run_id"], token)) if runs else None
        return self._cache.put(token, key, blocks, JOB_TTL_SECONDS)

    async def _runs(self, identifier: int, token: str | None, limit: int = RUNS_SHOWN) -> list[dict]:
        data = await self._http.get(f"{BASE}/runs/list", token,
                                    {"job_id": identifier, "limit": min(limit, 25)})
        return [self._run_row(r) for r in data.get("runs", [])]

    async def run(self, run_ref: object, token: str | None) -> dict[str, Any]:
        """A run on its own, for the run page and for the `#/run/<id>` route.

        It carries the job's NAME, resolved through the job cache, because a run id alone is not context:
        a user pastes `#/run/812345679` into a ticket and the reader needs to know which job it belongs to.
        The job read is already cached for 30 s by `job()`, so a run page opened from a job page costs
        nothing extra ([RUN-1]).
        """
        row = await self._run_detail(vocab.job_id(run_ref), token)
        row["jobName"] = await self._job_name(row.get("job_id"), token)
        return row

    async def _job_name(self, job_ref: object, token: str | None) -> str:
        """The job's name, or "" when it cannot be read. Never a failure: the run's own facts still stand."""
        try:
            identifier = vocab.job_id(job_ref)
        except vocab.JobError:
            return ""
        hit = self._cache.get(token, f"job:{identifier}")
        if hit is not None:
            return ((hit or {}).get("job") or {}).get("name") or ""
        try:
            detail = await self._http.get(f"{BASE}/get", token, {"job_id": identifier})
            return ((detail.get("settings") or {}).get("name")) or ""
        except Exception:  # noqa: BLE001 - the name is context, not the answer
            return ""

    async def _run_detail(self, run_id: int, token: str | None) -> dict[str, Any]:
        """A run's tasks and, only when it matters, its output.

        `get-output` is documented as valid for a finished run only, so asking during a run is a `400` on
        every poll of a running job — the page's most-read state (spec 014 [RB-6]). The guard is
        `vocab.is_terminal`, and there is a test asserting no call is made for a running run.
        """
        key = f"run:{run_id}"
        if (hit := self._cache.get(token, key)) is not None:
            return hit
        detail = await self._http.get(f"{BASE}/runs/get", token, {"run_id": run_id})
        state = detail.get("state") or {}
        life = state.get("life_cycle_state") or ""
        row = self._run_row(detail)
        row["tasks"] = [self._task_run(t) for t in detail.get("tasks") or []]
        row["trigger"] = (detail.get("trigger") or "").lower() or "manual"
        failed = next((t for t in row["tasks"]
                       if (t.get("result") or "") in ("FAILED", "TIMEDOUT")), None)
        if vocab.is_terminal(life) and failed is not None:
            try:
                out = await self._http.get(f"{BASE}/runs/get-output", token,
                                           {"run_id": failed.get("taskRunId") or run_id})
                row["output"] = {
                    "taskKey": failed.get("taskKey"),
                    "error": str(out.get("error") or "")[:4000],
                    "traceTail": str(out.get("error_trace") or "")[-2000:],
                }
            except Exception as exc:  # noqa: BLE001 - the run's own facts are still worth showing
                row["output"] = {"taskKey": failed.get("taskKey"), "error": _sentence(exc)}
        # A live run must be re-read on every poll, so it is NOT cached; a terminal one is kept forever.
        return row if not vocab.is_terminal(life) else self._cache.put(token, key, row, None)

    # -- rows -------------------------------------------------------------------------------
    @staticmethod
    def _schedule(schedule: dict | None) -> dict[str, Any] | None:
        if not schedule:
            return None
        return {
            "cron": schedule.get("quartz_cron_expression") or "",
            "timezone": schedule.get("timezone_id") or "",
            "paused": (schedule.get("pause_status") or "").upper() == "PAUSED",
        }

    @staticmethod
    def _tasks(tasks: list[dict] | None) -> list[dict]:
        """A task flattened into the `job_graph` shape.

        The platform nests a task's target inside a task-type field; `job_graph` expects a flat key. This
        is the one place the two shapes meet, and it is why `task_levels` can be shared at all (`[RB-5]`).
        """
        out = []
        for t in tasks or []:
            item: dict = {
                "task_key": t.get("task_key") or "",
                "depends_on": [d.get("task_key") for d in t.get("depends_on") or []
                               if d.get("task_key")],
                "timeout_seconds": t.get("timeout_seconds") or 0,
                "max_retries": t.get("max_retries") or 0,
            }
            for kind, (outer, inner) in (("notebook_path", ("notebook_task", "notebook_path")),
                                         ("python_file", ("spark_python_task", "python_file")),
                                         ("sql_file", ("sql_task", "file")),
                                         ("pipeline_id", ("pipeline_task", "pipeline_id")),
                                         ("job_id", ("run_job_task", "job_id"))):
                node = t.get(outer) or {}
                value = (node.get(inner) or {}).get("path") if inner == "file" else node.get(inner)
                if value:
                    item[kind] = value
                    break
            out.append(item)
        return out

    @staticmethod
    def _job_row(j: dict) -> dict[str, Any]:
        settings = j.get("settings") or {}
        schedule = settings.get("schedule") or {}
        return {
            "job_id": j.get("job_id"),
            "name": settings.get("name") or "",
            "owner": settings.get("run_as_user_name") or j.get("creator_user_name") or "",
            "schedule": JobsBrowser._schedule(schedule or None),
            "paused": (schedule.get("pause_status") or "").upper() == "PAUSED",
        }

    @staticmethod
    def _run_row(r: dict) -> dict[str, Any]:
        state = r.get("state") or {}
        life = state.get("life_cycle_state") or ""
        result = state.get("result_state") or None
        word = vocab.run_word(life, result)
        return {
            "run_id": r.get("run_id"),
            "job_id": r.get("job_id"),
            "lifeCycle": life,
            "result": result,
            "word": word,
            "tone": vocab.tone(word),
            "startTime": r.get("start_time"),
            "endTime": r.get("end_time"),
            "duration": vocab.describe_duration(
                vocab.duration_seconds(r.get("start_time"), r.get("end_time"), _now_ms())),
            "active": vocab.is_active(life),
            "cancel": vocab.can_cancel(life),
            "repair": vocab.can_repair(result, life),
            "message": state.get("state_message") or "",
            "url": r.get("run_page_url") or "",
        }

    @staticmethod
    def _task_run(t: dict) -> dict[str, Any]:
        state = t.get("state") or {}
        life = state.get("life_cycle_state") or ""
        result = state.get("result_state") or None
        # A task with neither state has not begun. `not started` is the honest word: a queued task is not
        # running, and saying it is makes a stalled run look busy (spec 014 [RUN-1]).
        word = vocab.run_word(life, result) if (life or result) else "not started"
        return {
            "taskKey": t.get("task_key") or "",
            "taskRunId": t.get("run_id"),
            "lifeCycle": life,
            "result": result,
            "word": word,
            "tone": vocab.tone(word) if (life or result) else "quiet",
            "startTime": t.get("start_time"),
            "endTime": t.get("end_time"),
            "duration": vocab.describe_duration(
                vocab.duration_seconds(t.get("start_time"), t.get("end_time"), _now_ms())),
            "message": state.get("state_message") or "",
        }

    # -- cache ------------------------------------------------------------------------------
    def invalidate(self, token: str | None, prefix: str = "") -> None:
        self._cache.invalidate(token, prefix)

    def forget_run(self, token: str | None, run_id: int) -> None:
        self._cache.invalidate(token, f"run:{run_id}")


def _describe(tasks: list[dict]) -> str:
    """`3 tasks in 2 levels`, from the graph module so the tool and the page agree on the arithmetic."""
    if not tasks:
        return "no tasks"
    from ...domain import jobs as vocab  # local: keeps the module importable on its own
    levels = vocab.task_levels(tasks)
    if not levels:
        return f"{len(tasks)} tasks, with a cycle"
    noun = "task" if len(tasks) == 1 else "tasks"
    if len(levels) == 1:
        return f"{len(tasks)} {noun}, all independent"
    return f"{len(tasks)} {noun} in {len(levels)} levels"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sentence(exc: BaseException) -> str:
    """An exception as the one sentence a page can show. Never a class name alone: `KeyError` is not
    information about a workspace."""
    if isinstance(exc, PermissionError):
        return str(exc) or "permission denied by the workspace"
    if isinstance(exc, LookupError):
        return str(exc) or "not found"
    return (str(exc) or type(exc).__name__)[:400]
