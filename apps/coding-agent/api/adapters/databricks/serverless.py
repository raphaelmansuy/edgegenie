"""Submit a notebook to serverless compute as the app's own identity, and read the run back.

This is the only code that touches the Jobs and Workspace APIs for Python cells. It authenticates the
way the Databricks SDK does by default: in a deployed app that is the app's service principal (the
platform injects its client id and secret); on a laptop it is whatever the environment holds. It is
never given a user's token, because the platform offers no scope to run compute as a user.

The notebook is written to the identity's own home, run once, and deleted when the run has been read.
Nothing here decides *whether* to run: that is the router's (administrators only) and the domain's.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

#: Even a stuck run must end: serverless compute is billed while it waits.
RUN_TIMEOUT_SECONDS = 900
RUN_DIR = "coding_agent_cell_runs"


@dataclass(frozen=True, slots=True)
class RunInfo:
    life_cycle: str
    result_state: str
    message: str
    task_run_id: int | None


class ServerlessRunner:
    """The SDK, behind four verbs. A fake with the same verbs stands in for it in tests."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._home: str | None = None

    def _w(self) -> Any:
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # imported late: a demo needs no SDK auth

            self._client = WorkspaceClient()
        return self._client

    def _identity_home(self) -> str:
        if self._home is None:
            self._home = f"/Users/{self._w().current_user.me().user_name}"
        return self._home

    async def submit(self, name: str, source: str) -> tuple[int, str]:
        """Upload the notebook and start a run. Returns (run id, notebook path)."""
        return await asyncio.to_thread(self._submit, name, source)

    def _submit(self, name: str, source: str) -> tuple[int, str]:
        import io

        from databricks.sdk.service import jobs, workspace

        w = self._w()
        folder = f"{self._identity_home()}/{RUN_DIR}"
        w.workspace.mkdirs(folder)
        path = f"{folder}/{name}"
        w.workspace.upload(path, io.BytesIO(source.encode("utf-8")),
                           format=workspace.ImportFormat.SOURCE, language=workspace.Language.PYTHON,
                           overwrite=True)
        try:
            waiter = w.jobs.submit(
                run_name=f"coding-agent {name}", timeout_seconds=RUN_TIMEOUT_SECONDS,
                tasks=[jobs.SubmitTask(task_key="cells", notebook_task=jobs.NotebookTask(
                    notebook_path=path, source=jobs.Source.WORKSPACE))])
        except Exception:
            self._discard(path)
            raise
        response = getattr(waiter, "response", waiter)
        return int(response.run_id), path

    async def info(self, run_id: int) -> RunInfo:
        return await asyncio.to_thread(self._info, run_id)

    def _info(self, run_id: int) -> RunInfo:
        run = self._w().jobs.get_run(run_id)
        state = run.state
        life = getattr(getattr(state, "life_cycle_state", None), "value", "") or ""
        result = getattr(getattr(state, "result_state", None), "value", "") or ""
        task = (run.tasks or [None])[0]
        return RunInfo(life, result, getattr(state, "state_message", "") or "",
                       getattr(task, "run_id", None))

    async def output(self, task_run_id: int | None) -> tuple[str | None, str]:
        """(the notebook's exit value, the platform's error text) for a finished task run."""
        if task_run_id is None:
            return None, ""
        return await asyncio.to_thread(self._output, task_run_id)

    def _output(self, task_run_id: int) -> tuple[str | None, str]:
        out = self._w().jobs.get_run_output(task_run_id)
        result = getattr(getattr(out, "notebook_output", None), "result", None)
        error = " ".join(p for p in (getattr(out, "error", "") or "",
                                     (getattr(out, "error_trace", "") or "")[-800:]) if p)
        return result, error

    async def cancel(self, run_id: int) -> None:
        await asyncio.to_thread(lambda: self._w().jobs.cancel_run(run_id))

    async def discard(self, path: str) -> None:
        await asyncio.to_thread(self._discard, path)

    def _discard(self, path: str) -> None:
        try:
            self._w().workspace.delete(path)
        except Exception as exc:  # noqa: BLE001 - a leftover scratch notebook is not worth failing a run
            log.debug("could not remove %s: %s", path, exc)

