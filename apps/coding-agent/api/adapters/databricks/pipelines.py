"""Lakeflow pipelines, as a page reads them: the pipeline, its updates, its events.

The shape is `JobsBrowser`'s, and for the same reasons. The one thing that is specific here is **which
state answers the user's question**: a pipeline's own `state` is `IDLE` both when it has never run and
when its last update failed, so `pipeline_word` reads the last update (spec 014 [F5], [PIPE-5]). This
module never decides a word itself; it hands the fields to `api.domain.jobs`.

`libraries` may arrive as `{notebook: {path}}`, `{file: {path}}` or `{glob: {include}}`, and the page shows
the path either way — so the flattening lives here, once, exactly as `pipeline_body.describe_libraries`
does it on the write side.
"""
from __future__ import annotations

import time
from typing import Any

from ...domain import jobs as vocab
from .http import DbxHttp

BASE = "/api/2.0/pipelines"

#: A pipeline's libraries and configuration change only when someone edits it, so they can be cached for a
#: minute. The LAST UPDATE is never cached: it is the fact the page exists to report (spec 014 [07 §2]).
SPEC_TTL_SECONDS = 60.0
EVENTS_SHOWN = 20


class _Cache:
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


class PipelinesBrowser:
    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)
        self._cache = _Cache()

    # -- list --------------------------------------------------------------------------------
    async def pipelines(self, token: str | None, limit: int = 25) -> list[dict[str, Any]]:
        """Every pipeline the caller can see, each carrying its LAST UPDATE's state.

        The list payload already contains `latest_updates`, so this needs no fan-out: one call, one page
        (`[RB-7]`). A pipeline that has never been updated reports `lastUpdate: null`, never a synthesised
        state ([TOOL-8]).
        """
        data = await self._http.get(BASE, token, {"max_results": min(max(limit, 1), 100)})
        return [self._row(p) for p in data.get("statuses", data.get("pipelines", []))]

    # -- one pipeline -------------------------------------------------------------------------
    async def pipeline(self, pipeline_ref: object, token: str | None,
                       events: int = EVENTS_SHOWN) -> dict[str, Any]:
        """The pipeline's five blocks. Any block may be `{"error": …}` instead of data."""
        identifier = vocab.pipeline_id(pipeline_ref)
        key = f"spec:{identifier}"
        if (hit := self._cache.get(token, key)) is not None:
            blocks = dict(hit)
        else:
            detail = await self._http.get(f"{BASE}/{identifier}", token)
            spec = detail.get("spec") or {}
            blocks = {
                "pipeline": {
                    "pipeline_id": identifier,
                    "name": spec.get("name") or detail.get("name") or "",
                    "state": detail.get("state") or "",
                    "catalog": spec.get("catalog") or "",
                    "schema": spec.get("schema") or "",
                    "serverless": bool(spec.get("serverless")),
                    "edition": spec.get("edition") or "",
                    "channel": spec.get("channel") or "",
                    "continuous": bool(spec.get("continuous")),
                    "development": bool(spec.get("development")),
                    "libraries": _libraries(spec),
                    "creator": detail.get("creator_user_name") or "",
                    "storage": spec.get("storage") or "",
                },
                "identity": "the app's service principal",
            }
            self._cache.put(token, key, blocks, SPEC_TTL_SECONDS)

        # Updates and events are read on every load: they are the transient half of the page.
        try:
            updates = await self.updates(identifier, token, limit=3)
            blocks["updates"] = updates
            latest = updates[0] if updates else None
            blocks["lastUpdate"] = latest
            blocks["word"] = vocab.pipeline_word(
                (blocks.get("pipeline") or {}).get("state"),
                (latest or {}).get("state"))
            blocks["tone"] = vocab.tone(blocks["word"])
            blocks["activeUpdate"] = next(
                (u for u in updates if vocab.update_is_active(u.get("state"))), None)
        except Exception as exc:  # noqa: BLE001 - the spec is still worth showing
            blocks["updates"] = {"error": _sentence(exc)}
            blocks["lastUpdate"] = {"error": _sentence(exc)}
            blocks["word"] = vocab.pipeline_word(
                (blocks.get("pipeline") or {}).get("state"), None)

        try:
            blocks["events"] = await self.events(identifier, token, limit=events)
        except Exception as exc:  # noqa: BLE001
            blocks["events"] = {"error": _sentence(exc)}
        return blocks

    async def updates(self, identifier: str, token: str | None, limit: int = 3) -> list[dict]:
        data = await self._http.get(f"{BASE}/{identifier}/updates", token,
                                    {"max_results": max(1, min(limit, 25))})
        return [_update_row(u) for u in data.get("updates") or []]

    async def events(self, identifier: str, token: str | None,
                     limit: int = EVENTS_SHOWN) -> list[dict]:
        """The recent events, errors and warnings first.

        A page that lists 200 INFO lines puts the one ERROR below the fold, and a model reading them
        spends its context on nothing — so the filter goes to the platform and the order is applied here
        (spec 014 [PIPE-6]).
        """
        data = await self._http.get(f"{BASE}/{identifier}/events", token,
                                    {"max_results": min(max(limit, 1), 100),
                                     "filter": "level in ('ERROR', 'WARN')"})
        rows = [_event_row(e) for e in data.get("events") or []]
        rank = {"ERROR": 0, "WARN": 1, "INFO": 2}
        rows.sort(key=lambda r: (rank.get(r["level"], 9), -(r["timestamp"] or 0)))
        return rows

    def invalidate(self, token: str | None, identifier: str = "") -> None:
        self._cache.invalidate(token, f"spec:{identifier}" if identifier else "")

    # -- rows ----------------------------------------------------------------------------------
    @staticmethod
    def _row(p: dict) -> dict[str, Any]:
        updates = p.get("latest_updates") or []
        latest = updates[0] if updates else None
        last_state = (latest or {}).get("state")
        word = vocab.pipeline_word(p.get("state"), last_state)
        return {
            "pipeline_id": p.get("pipeline_id"),
            "name": p.get("name") or "",
            "state": p.get("state") or "",
            "word": word,
            "tone": vocab.tone(word),
            "lastUpdate": ({"update_id": latest.get("update_id"), "state": last_state,
                            "creationTime": latest.get("creation_time")} if latest else None),
            "catalog": p.get("catalog") or "",
            "creator": p.get("creator_user_name") or "",
        }


def _update_row(u: dict) -> dict[str, Any]:
    state = u.get("state") or ""
    return {
        "updateId": u.get("update_id") or "",
        "state": state,
        "word": vocab.update_word(state),
        "tone": vocab.tone(vocab.update_word(state)),
        "creationTime": u.get("creation_time"),
        "fullRefresh": bool(u.get("full_refresh")),
        "cause": (u.get("cause") or "").lower(),
        "active": vocab.update_is_active(state),
    }


def _event_row(e: dict) -> dict[str, Any]:
    return {
        "level": (e.get("level") or "").upper(),
        "message": (e.get("message") or "")[:600],
        "timestamp": e.get("timestamp"),
        "stackTrace": (e.get("details") or {}).get("stack_trace") or e.get("stack_trace") or "",
    }


def _libraries(spec: dict) -> list[dict[str, str]]:
    """Each library as `{kind, path}`, so the page renders one row shape for three platform shapes."""
    out: list[dict[str, str]] = []
    for library in spec.get("libraries") or []:
        for kind, field in (("notebook", "path"), ("file", "path"), ("glob", "include")):
            node = library.get(kind) or {}
            value = node.get(field)
            if value:
                out.append({"kind": kind, "path": value})
                break
    return out


def _sentence(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return str(exc) or "permission denied by the workspace"
    if isinstance(exc, LookupError):
        return str(exc) or "not found"
    return (str(exc) or type(exc).__name__)[:400]
