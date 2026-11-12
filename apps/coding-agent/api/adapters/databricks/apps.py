"""Databricks Apps: their state, their resources, and whether they actually answer.

The last one is the point. A deployment's `SUCCEEDED` means the process started, not that the app
serves your code — this repository learned that the expensive way for its own deployment, where
`make deploy` reported success three times while serving none of the work. So `health()` makes a real
HTTP request and reports what came back (spec 013 [AP-4], [UI-4]).

A cold start is a *state*, not a failure: an app that scales to zero takes seconds to answer its first
request, and calling that "down" is a false alarm that teaches users to distrust the page
(spec 013 [RB-7], [E-14]).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .http import DbxHttp

BASE = "/api/2.0/apps"
#: "I asked and it answered quickly." Below this the app is simply running.
FAST_SECONDS = 3.0
#: "It has not answered yet, but an app that scaled to zero legitimately takes this long."
COLD_SECONDS = 15.0
HEALTH_TTL = 15.0


def state_of(app: dict) -> tuple[str, str]:
    """(state, raw) — the app's own state, preferring the deployment's when it is the more specific.

    A `DEPLOYING` deployment is not a state the user asked about, so it is reported as `deploying`
    and the page shows which. A `RUNNING` app with a failed deployment is `failing`: the app is up and
    serving something wrong, which is the case that wastes the most user time."""
    app_status = (app.get("app_status") or {}).get("state") or ""
    dep = (app.get("active_deployment") or {}).get("status") or {}
    dep_state = dep.get("state") or ""
    if dep_state in ("FAILED", "ERROR"):
        return "failing", dep_state
    if dep_state in ("IN_PROGRESS", "DEPLOYING"):
        return "deploying", dep_state
    if app_status:
        word = {"RUNNING": "running", "STOPPED": "stopped", "CRASHED": "failing",
                "DEPLOYING": "deploying", "UNAVAILABLE": "starting"}.get(app_status, app_status.lower())
        return word, app_status
    if dep_state:
        return dep_state.lower(), dep_state
    return "unknown", ""


def health_word(status: int | None, ms: int, timed_out: bool) -> str:
    """Five states, each with a distinct meaning for a person (spec 013 [AP-4], [E-14])."""
    if timed_out:
        return "starting"
    if status is None:
        return "unreachable"
    if 200 <= status < 400:
        return "running" if ms <= FAST_SECONDS * 1000 else "starting"
    if status >= 500:
        return "failing"
    return "failing"


class AppsBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._host = host
        self._health: dict[str, tuple[float, dict[str, Any]]] = {}

    async def apps(self, token: str | None) -> list[dict[str, Any]]:
        """One call, and `resources` is read from the LIST payload so "which app uses this project"
        is `O(n)` items and not `O(n)` round trips ([06 §6.2])."""
        data = await self._http.get(BASE, token)
        return [self._row(a) for a in data.get("apps", [])]

    async def app(self, name: str, token: str | None) -> dict[str, Any]:
        data = await self._http.get(f"{BASE}/{name}", token)
        row = self._row(data)
        row["servicePrincipal"] = data.get("service_principal_client_id") or ""
        row["computeSize"] = data.get("compute_size") or ""
        row["deploymentState"] = ((data.get("active_deployment") or {}).get("status") or {}).get("state") or ""
        return row

    async def health(self, url: str, token: str | None = None) -> dict[str, Any]:
        """A real GET, with the two bounds that make a cold start distinguishable from a breakage.

        Cached for 15 s: the check is time-sensitive ("is it working NOW") but not per-render.
        """
        key = url or ""
        if (hit := self._health.get(key)) and time.monotonic() - hit[0] < HEALTH_TTL:
            return hit[1]
        full = url if url.startswith("http") else f"https://{url}"
        started = time.monotonic()
        result: dict[str, Any]
        try:
            async with httpx.AsyncClient(timeout=COLD_SECONDS, follow_redirects=True) as client:
                r = await client.get(full)
            ms = int((time.monotonic() - started) * 1000)
            result = {"status": r.status_code, "ms": ms,
                      "state": health_word(r.status_code, ms, False),
                      "url": full, "logs": f"{full}/logz",
                      "checkedAt": time.strftime("%H:%M:%S")}
        except (httpx.TimeoutException, asyncio.TimeoutError):
            result = {"status": None, "ms": int((time.monotonic() - started) * 1000),
                      "state": "starting", "url": full, "logs": f"{full}/logz",
                      "detail": f"no response in {int(COLD_SECONDS)} s: a cold start, or a hung process",
                      "checkedAt": time.strftime("%H:%M:%S")}
        except httpx.HTTPError as exc:
            result = {"status": None, "ms": int((time.monotonic() - started) * 1000),
                      "state": "unreachable", "url": full, "logs": f"{full}/logz",
                      "detail": exc.__class__.__name__, "checkedAt": time.strftime("%H:%M:%S")}
        self._health[key] = (time.monotonic(), result)
        return result

    def forget(self, url: str) -> None:
        self._health.pop(url, None)

    @staticmethod
    def _row(a: dict) -> dict[str, Any]:
        state, raw = state_of(a)
        url = a.get("url") or ""
        resources = a.get("resources") or []
        postgres = next((r for r in resources if r.get("postgres")), None)
        lakebase = ""
        if postgres:
            branch = ((postgres.get("postgres") or {}).get("branch") or "")
            parts = [p for p in branch.split("/") if p]
            if "projects" in parts and len(parts) > 1:
                lakebase = parts[parts.index("projects") + 1]
        return {
            "name": a.get("name") or "",
            "url": url if url.startswith("http") else (f"https://{url}" if url else ""),
            "state": state,
            "stateRaw": raw,
            "lakebase": lakebase,
            "resources": [{
                "name": r.get("name") or "",
                "kind": next((k for k in ("postgres", "sql_warehouse", "serving_endpoint", "secret",
                                          "job", "uc_securable", "database") if r.get(k)), "other"),
                "permission": ((r.get("postgres") or {}).get("permission")
                               or (r.get("database") or {}).get("permission") or ""),
                "branch": (r.get("postgres") or {}).get("branch") or "",
            } for r in resources],
            "creator": a.get("creator") or "",
        }


def apps_using(apps: list[dict[str, Any]], project: str) -> list[dict[str, Any]]:
    """The apps whose postgres resource names this project. Pure: one pass over the list ([06 §6.2])."""
    if not project:
        return []
    return [a for a in apps if a.get("lakebase") == project]
