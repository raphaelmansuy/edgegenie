"""The workspace write mechanics, pinned to what the API actually does.

Both cases here were discovered by running against a real workspace, and both are the kind of thing
that silently regresses:

  1. `overwrite=true` is **rejected** with `format=SOURCE`, so an overwrite is delete-then-import.
  2. After that delete, `language` is **required** — the API answers "The zip archive contains no
     items." without it, because there is no object left to infer from.

Neither is documented in a way we could rely on, so they are asserted here against a fake HTTP layer
that *behaves like the real one* (fails on overwrite+SOURCE, fails on a missing language).
"""

from __future__ import annotations

import base64

import pytest

from api.adapters.databricks.workspace import WorkspaceBrowser


class FakeHttp:
    """A stand-in for the API with the two behaviours that bit us."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.objects: dict[str, str] = {}

    async def get(self, path: str, token, params=None):  # noqa: ARG002
        p = (params or {}).get("path", "")
        if path.endswith("/get-status"):
            if p not in self.objects:
                raise LookupError(p)
            return {"object_id": "oid", "modified_at": 1, "size": len(self.objects[p]),
                    "language": "PYTHON", "object_type": "NOTEBOOK"}
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path: str, token, body=None):  # noqa: ARG002
        body = body or {}
        self.calls.append((path, body))
        if path.endswith("/workspace/delete"):
            if body["path"] not in self.objects:
                raise LookupError(body["path"])
            del self.objects[body["path"]]
            return {}
        if path.endswith("/workspace/import"):
            # The real API's rules, as observed.
            if body.get("overwrite"):
                raise RuntimeError("INVALID_PARAMETER_VALUE: Overwrite cannot be used for SOURCE format")
            if not body.get("language"):
                raise RuntimeError("BAD_REQUEST: The zip archive contains no items.")
            self.objects[body["path"]] = base64.b64decode(body["content"]).decode()
            return {"path": body["path"]}
        raise AssertionError(f"unexpected POST {path}")


@pytest.mark.asyncio
async def test_overwrite_is_delete_then_import():
    http = FakeHttp()
    http.objects["/a/notes"] = "old"
    wb = WorkspaceBrowser("https://example", lambda: None, http)  # type: ignore[arg-type]
    await wb.import_source("/a/notes", "new text\n", None, language="PYTHON")
    paths = [c[0] for c in http.calls]
    assert paths == ["/api/2.0/workspace/delete", "/api/2.0/workspace/import"]
    assert http.objects["/a/notes"] == "new text\n"


@pytest.mark.asyncio
async def test_no_overwrite_flag_is_sent():
    """The one flag combination the API refuses must never leave this adapter."""
    http = FakeHttp()
    wb = WorkspaceBrowser("https://example", lambda: None, http)  # type: ignore[arg-type]
    await wb.import_source("/a/new", "x\n", None, language="PYTHON")
    _, body = http.calls[-1]
    assert "overwrite" not in body


@pytest.mark.asyncio
async def test_creating_a_missing_object_is_not_an_error():
    """A delete of something that does not exist is a create, not a failure."""
    http = FakeHttp()
    wb = WorkspaceBrowser("https://example", lambda: None, http)  # type: ignore[arg-type]
    await wb.import_source("/a/fresh", "x\n", None, language="PYTHON")
    assert http.objects["/a/fresh"] == "x\n"


@pytest.mark.asyncio
async def test_a_missing_language_fails_loudly():
    """Proof the fake models the real API: without a language, an import after delete cannot work.
    The route's job is to always supply one (see `_language_for_path`)."""
    http = FakeHttp()
    wb = WorkspaceBrowser("https://example", lambda: None, http)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="zip archive contains no items"):
        await wb.import_source("/a/nolang", "x\n", None, language="")


def test_language_for_path_covers_the_extensions_we_edit():
    from api.routers.api import _language_for_path
    assert _language_for_path("/x/a.py") == "PYTHON"
    assert _language_for_path("/x/a.sql") == "SQL"
    assert _language_for_path("/x/a.scala") == "SCALA"
    assert _language_for_path("/x/a.r") == "R"
    # A Databricks notebook has no extension; PYTHON is the workspace's own default.
    assert _language_for_path("/x/taxi_hours") == "PYTHON"
