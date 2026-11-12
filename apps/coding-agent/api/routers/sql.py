"""SQL HTTP boundary: authentication, bounded inputs, delegation and sanitized typed errors."""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from ..adapters.databricks.http import ScopeMissing
from ..domain.sqlquery import SqlActor, SqlError, native_id

router = APIRouter(prefix="/api/sql")


class SqlBodyLimit:
    """Bound request bytes before JSON decoding, including chunked bodies without a length header."""

    def __init__(self, app, limit=256 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or not scope.get("path", "").startswith("/api/sql/")
            or scope.get("method") not in {"POST", "PATCH"}
        ):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.limit:
                response = JSONResponse(
                    {"detail": "SQL request exceeds the 256 KiB limit"}, status_code=413
                )
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        return await self.app(scope, replay, send)


def actor(request: Request):
    # Production SQL never uses the app credential or an ambient token as fallback.
    cfg = request.app.state.settings
    token = request.headers.get("x-forwarded-access-token")
    if not cfg.production:
        token = token or request.app.state.dev_token
    return SqlActor(request.app.state.sql_workspace, request.state.user_id, token)


@contextmanager
def errors():
    try:
        yield
    except SqlError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}) from exc
    except ScopeMissing as exc:
        raise HTTPException(403, {"code": "SCOPE_MISSING", "message": str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(
            403,
            {
                "code": "ACCESS_DENIED",
                "message": "Access was denied. Check user authorization, query, warehouse and data permissions.",
            },
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            404, {"code": "NOT_FOUND", "message": "This item is unavailable or no longer accessible."}
        ) from exc
    except Exception as exc:
        raise HTTPException(
            503,
            {
                "code": "UPSTREAM_UNAVAILABLE",
                "message": "SQL service is unavailable. Your local draft is preserved; check status before retrying execution.",
            },
        ) from exc


class Draft(BaseModel):
    text: str = Field(max_length=200 * 1024)
    name: str = Field(default="Untitled query", max_length=200)
    version: int | None = None
    originQueryId: str = ""
    warehouseId: str = Field(default="", max_length=128)
    catalog: str = Field(default="", max_length=256)
    schema_: str = Field(default="", max_length=256, alias="schema")


class Parameter(BaseModel):
    name: str = Field(max_length=128)
    type: str = Field(default="STRING", max_length=40)
    value: str | None = Field(default=None, max_length=16384)


class Selection(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class Run(BaseModel):
    draftId: str
    version: int
    warehouseId: str = Field(min_length=1, max_length=128)
    catalog: str = Field(default="", max_length=256)
    schema_: str = Field(default="", max_length=256, alias="schema")
    selection: Selection | None = None
    parameters: list[Parameter] = Field(default_factory=list, max_length=100)


class Create(BaseModel):
    draftId: str
    version: int
    name: str = Field(min_length=1, max_length=200)
    parent: str = Field(min_length=2, max_length=512)


def operation_key(value):
    if not value or len(value) > 160:
        raise SqlError("INVALID_OPERATION", "A unique operation key is required.")
    return value


@router.get("/capabilities")
async def capabilities(request: Request):
    return request.app.state.sql.capabilities()


@router.get("/queries")
async def queries(request: Request, cursor: str = "", pageSize: int = 50):
    with errors():
        if len(cursor) > 4096:
            raise SqlError("INVALID_CURSOR", "The query page cursor is invalid.")
        return await request.app.state.sql.provider.list(actor(request), cursor, max(1, min(pageSize, 50)))


@router.get("/queries/{query_id}")
async def query(request: Request, query_id: str):
    with errors():
        return await request.app.state.sql.source(actor(request), "query", query_id)


@router.post("/queries", status_code=202)
async def create(request: Request, body: Create, idempotency_key: str = Header(default="")):
    with errors():
        return await request.app.state.sql.create(
            actor(request), body.model_dump(by_alias=True), operation_key(idempotency_key)
        )


@router.get("/warehouses")
async def warehouses(request: Request):
    with errors():
        return {"items": await request.app.state.sql.provider.warehouses(actor(request))}


@router.post("/drafts", status_code=201)
async def draft(request: Request, body: Draft):
    with errors():
        return await request.app.state.sql.draft(actor(request), body.model_dump(by_alias=True))


@router.get("/drafts/{draft_id}")
async def get_draft(request: Request, draft_id: str):
    with errors():
        return await request.app.state.sql.source(actor(request), "query-draft", draft_id)


@router.patch("/drafts/{draft_id}")
async def patch_draft(request: Request, draft_id: str, body: Draft):
    with errors():
        return await request.app.state.sql.draft(
            actor(request), body.model_dump(by_alias=True), native_id(draft_id)
        )


@router.post("/runs", status_code=202)
async def run(request: Request, body: Run, idempotency_key: str = Header(default="")):
    with errors():
        return await request.app.state.sql.run(
            actor(request),
            body.model_dump(exclude_none=True, by_alias=True),
            operation_key(idempotency_key),
        )


@router.get("/runs")
async def history(request: Request):
    with errors():
        return {"items": await request.app.state.sql.history(actor(request))}


@router.get("/runs/{run_id}")
async def status(request: Request, run_id: str):
    with errors():
        return await request.app.state.sql.observe(actor(request), run_id)


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel(request: Request, run_id: str):
    with errors():
        return await request.app.state.sql.observe(actor(request), run_id, cancel=True)


@router.post("/runs/{run_id}/acknowledge")
async def acknowledge(request: Request, run_id: str):
    with errors():
        return await request.app.state.sql.acknowledge(actor(request), run_id)
